#!/usr/bin/env bash
#
# 07 — uploads/ 의 기존 파일을 소유자 디렉토리(uploads/u<owner_id>/)로 옮긴다.
#
# 왜: 업로드·생성 파일의 물리 위치가 소유자별로 나뉘었다(마이그레이션 0023 + resolver).
# 코드가 배포된 뒤에도 레거시 루트의 파일은 계속 열리지만(폴백), 물리 격리를 완성하려면
# 장부(uploaded_files)에 소유자가 기록된 파일을 실제로 옮겨야 한다.
#
# 원칙(ADR-0010): **장부에 없는 파일은 건드리지 않는다.** 소유자를 모르는 파일을 추측해서
# 옮기면 워크플로우가 참조하던 결과물이 조용히 사라질 수 있다 — 루트에 남긴다.
#
#   scripts/server/07-uploads-per-user-move.sh            # dry-run: 무엇을 옮길지 보여만 준다
#   scripts/server/07-uploads-per-user-move.sh --apply    # 실제로 옮긴다
#
# 멱등하다 — 이미 옮겨진 파일(소유자 디렉토리에 존재)은 건너뛴다. 실행 전 마이그레이션
# 0023 이 적용돼 있어야 한다(deploy.sh 경유 배포면 이미 적용됨).

set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/app}"
BACKEND="$APP_ROOT/backend"
VENV_PY="${VENV_PY:-$BACKEND/venv/bin/python}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

fail() { printf '\033[31m중단: %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[1m%s\033[0m\n' "$*"; }

[ -x "$VENV_PY" ] || fail "python 이 없다: $VENV_PY"
[ -f "$BACKEND/.env" ] || fail ".env 가 없다: $BACKEND/.env"

info "uploads per-user 이동 ($([ "$APPLY" = 1 ] && echo 실행 || echo dry-run))"

cd "$BACKEND"
APPLY="$APPLY" "$VENV_PY" - <<'PY'
import os
from pathlib import Path

from dotenv import load_dotenv

# 이 코드는 stdin heredoc 으로 실행된다 — 인자 없는 load_dotenv() 는 find_dotenv() 가
# 콜스택에서 호출자 파일을 찾다가 <stdin> 프레임에서 AssertionError 로 죽는다.
# cwd 가 $BACKEND 이므로 경로를 명시한다.
load_dotenv(".env")

import database  # noqa: E402  (DATABASE_URL 로 세션을 만든다)
import models  # noqa: E402
from upload_security import owner_dir, upload_dir  # noqa: E402

apply = os.environ.get("APPLY") == "1"
root = upload_dir().resolve()
db = database.SessionLocal()

moved = skipped_done = missing = unknown_owner = stale_removed = 0
try:
    rows = db.query(models.UploadedFile).all()
    name_counts = {}
    for row in rows:
        name_counts[row.stored_name] = name_counts.get(row.stored_name, 0) + 1
    for row in rows:
        owner = int(row.owner_user_id or 0)
        if owner <= 0:
            unknown_owner += 1
            continue
        src = root / row.stored_name
        dst = owner_dir(owner) / row.stored_name
        if dst.is_file():
            # 이미 옮겨졌는데 루트 사본이 남아 있으면(이전 실행 중단 등) 낡은 사본이 읽기를
            # 가린다(섀도잉). 같은 이름의 행이 이 행 하나뿐일 때만 루트 사본을 지운다 —
            # 여럿이면 남의 이관 전 파일일 수 있다.
            if src.is_file() and name_counts.get(row.stored_name, 0) == 1:
                print(f"  [낡은 루트 사본 제거] {row.stored_name}")
                if apply:
                    src.unlink()
                stale_removed += 1
            skipped_done += 1
            continue
        if not src.is_file():
            missing += 1
            print(f"  [없음] {row.stored_name} (owner={owner}) — 디스크에 파일이 없다")
            continue
        print(f"  [이동] {row.stored_name} → u{owner}/ ({row.size_bytes or 0}B)")
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        moved += 1

    # 장부에 없는 루트 파일 개수만 보고한다(옮기지 않는다 — ADR-0010).
    tracked = {r.stored_name for r in rows}
    untracked = [p.name for p in root.iterdir() if p.is_file() and p.name not in tracked]

    label = "옮김" if apply else "옮길 것"
    print()
    print(f"{label}: {moved} · 이미 완료: {skipped_done} · 낡은 루트 사본 제거: {stale_removed} · "
          f"디스크에 없음: {missing} · 소유자 미상 행: {unknown_owner} · "
          f"장부에 없는 루트 파일(그대로 둠): {len(untracked)}")
    if untracked[:5]:
        print("  장부에 없는 파일 예:", ", ".join(untracked[:5]))
finally:
    db.close()
PY

if [ "$APPLY" = 0 ]; then
  echo ""
  info "실제로 옮기려면 --apply 를 붙여라."
  echo ""
  echo "옮긴 뒤 확인:"
  echo "  1) 브라우저에서 프로젝트 하나 열어 업로드 파일이 걸린 워크플로우 실행"
  echo "  2) 실행 결과의 파일 다운로드 링크 클릭"
  echo "  3) curl -s http://127.0.0.1:8000/api/ready"
fi
