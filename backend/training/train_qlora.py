from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    base_model = os.getenv("QLORA_BASE_MODEL", config.get("base_model", "")).strip()
    if not base_model:
        raise ValueError("QLORA_BASE_MODEL 또는 config.base_model을 설정해야 합니다.")
    return {**config, "base_model": base_model}


def train(config: dict) -> None:
    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "QLoRA 학습 의존성이 없습니다. training/requirements-qlora.txt를 설치하세요."
        ) from exc

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(config["base_model"], use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        config["base_model"],
        quantization_config=quantization,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    dataset = load_dataset("json", data_files={
        "train": config["train_file"],
        "validation": config["validation_file"],
    })

    lora = LoraConfig(
        r=int(config.get("lora_rank", 16)),
        lora_alpha=int(config.get("lora_alpha", 32)),
        lora_dropout=float(config.get("lora_dropout", 0.05)),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=config.get("target_modules"),
    )
    args = SFTConfig(
        output_dir=config["output_dir"],
        num_train_epochs=float(config.get("epochs", 2)),
        per_device_train_batch_size=int(config.get("batch_size", 1)),
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 16)),
        learning_rate=float(config.get("learning_rate", 2e-4)),
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=int(config.get("eval_steps", 50)),
        save_steps=int(config.get("save_steps", 50)),
        bf16=True,
        optim="paged_adamw_8bit",
        report_to="none",
        seed=int(config.get("seed", 42)),
        max_length=int(config.get("max_seq_length", 4096)),
        gradient_checkpointing=True,
        use_cache=False,
    )
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        peft_config=lora,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(config["output_dir"])


def main() -> int:
    parser = argparse.ArgumentParser(description="16GB VRAM용 4-bit NF4 QLoRA SFT")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="설정만 검증하고 학습하지 않음")
    args = parser.parse_args()
    config = load_config(args.config)
    if not args.check:
        train(config)
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
