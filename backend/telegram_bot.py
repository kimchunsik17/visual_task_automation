"""
telegram_bot.py — telegramTriggerNode/telegramNode용 텔레그램 봇 연동.

discord_bot.py와 같은 목적(그래프 안의 트리거 노드 하나로 "라이브 시작"만 켜면 배포 끝)이지만,
구현 방식은 훨씬 단순하다 — 디스코드는 게이트웨이에 계속 붙어있는 WebSocket 클라이언트를
프로세스 메모리에 띄워둬야 하지만(discord_bot.py의 _active_bots), 텔레그램 Bot API는 웹훅
방식을 지원해서 그냥 우리 서버의 평범한 HTTP 엔드포인트 하나(POST /telegram-webhook/{project_id})로
메시지를 받을 수 있다. 그래서 서버 프로세스가 재시작돼도 별도로 "재연결"할 게 없다 — 텔레그램이
알아서 그 URL로 계속 보내준다(라이브를 끌 때 deleteWebhook만 호출해서 더 안 오게 하면 된다).
"""
import os
import requests
from usage_tracking import EVENT_WORKFLOW_EXECUTION, outcome_from_result, record_usage
from database import SessionLocal
import models
from graph import run_workflow
from credential_crypto import decrypt_secret

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://wa-pnu.duckdns.org").rstrip("/")


def find_telegram_trigger_node(graph_data: dict):
    """그래프에서 telegramTriggerNode를 찾는다. (node_id, botToken 원본값) 튜플, 없으면 (None, None)."""
    nodes = (graph_data or {}).get('nodes', [])
    for n in nodes:
        if n.get('type') == 'telegramTriggerNode':
            return n.get('id'), (n.get('data', {}) or {}).get('botToken', '')
    return None, None


def resolve_telegram_token(graph_data: dict, owner_user_id: int, db) -> str:
    """telegramTriggerNode.data.botToken을 실제 봇 토큰 문자열로 바꾼다. "{{API_CENTER:telegram}}"
    플레이스홀더면 UserApiKey(provider='telegram')에서 찾아온다(discordNode 발송 노드가
    "{{API_CENTER:discord}}"를 쓰는 것과 동일한 패턴 — telegramNode 발송 노드도 같은 값을 공유한다).
    텔레그램 봇 토큰은 @BotFather에서 한 번 발급받으면 만료되지 않으므로, 카카오처럼 access_token
    자동 갱신 로직이 필요 없다 — 저장된 값을 그대로 쓰면 된다."""
    _, raw_token = find_telegram_trigger_node(graph_data)
    if not raw_token:
        return ""
    if raw_token.strip() == "{{API_CENTER:telegram}}":
        key_row = (
            db.query(models.UserApiKey)
            .filter(models.UserApiKey.user_id == owner_user_id, models.UserApiKey.provider == "telegram")
            .first()
        )
        return decrypt_secret(key_row.api_key) if key_row else ""
    return raw_token


def set_telegram_webhook(token: str, project_id: int) -> bool:
    """이 프로젝트로 들어오는 메시지를 우리 서버의 웹훅 엔드포인트로 보내도록 텔레그램에 등록한다."""
    if not token:
        return False
    webhook_url = f"{PUBLIC_BASE_URL}/telegram-webhook/{project_id}"
    try:
        resp = requests.post(
            TELEGRAM_API_BASE.format(token=token, method="setWebhook"),
            json={"url": webhook_url},
            timeout=10,
        )
        ok = resp.ok and resp.json().get("ok", False)
        if not ok:
            print(f"[telegram_bot] setWebhook 실패(project {project_id}): {resp.text}")
        return ok
    except Exception as e:
        print(f"[telegram_bot] setWebhook 오류(project {project_id}): {e}")
        return False


def delete_telegram_webhook(token: str) -> bool:
    if not token:
        return False
    try:
        resp = requests.post(TELEGRAM_API_BASE.format(token=token, method="deleteWebhook"), timeout=10)
        return resp.ok
    except Exception as e:
        print(f"[telegram_bot] deleteWebhook 오류: {e}")
        return False


def get_telegram_bot_name(token: str) -> str:
    """봇 관리 화면에 표시할 봇 이름을 가져온다. 실패해도 조용히 빈 문자열을 돌려준다(표시만
    안 될 뿐 기능에는 영향 없음)."""
    if not token:
        return ""
    try:
        resp = requests.get(TELEGRAM_API_BASE.format(token=token, method="getMe"), timeout=5)
        if resp.ok and resp.json().get("ok"):
            info = resp.json().get("result", {})
            username = info.get("username")
            return f"@{username}" if username else info.get("first_name", "")
    except Exception:
        pass
    return ""


def send_telegram_message(token: str, chat_id, text: str) -> None:
    if not token or not chat_id:
        return
    text = text if text and text.strip() else "No output generated."
    if len(text) > 4000:
        text = text[:4000] + "\n... (truncated)"
    try:
        requests.post(
            TELEGRAM_API_BASE.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[telegram_bot] sendMessage 오류: {e}")


def process_update(project_id: int, update: dict) -> None:
    """텔레그램 웹훅이 보낸 Update 하나를 처리한다 — 실제 워크플로우 실행은 동기(블로킹)라서
    반드시 별도 스레드(asyncio.to_thread)에서 호출해야 한다(main.py의 웹훅 라우터 참고).
    discord_bot.py의 on_message와 동일한 흐름: 메시지 텍스트를 default_input으로 넘겨
    워크플로우를 실행하고, 그 결과를 그대로 답장으로 보낸다."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    if not chat_id or not text:
        return

    db = SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        if not project:
            return
        # 라이브를 끈 직후에도 텔레그램 쪽 webhook 삭제가 완전히 반영되기 전 짧은 틈에 메시지가
        # 하나 더 들어올 수 있다 — is_live가 아니면 여기서 조용히 무시한다(수신자에게 답장 없음).
        if not (project.graph_data or {}).get("is_live"):
            return

        user = db.query(models.User).filter(models.User.id == project.user_id).first()
        if user and user.token_balance <= 0:
            token = resolve_telegram_token(project.graph_data, project.user_id, db)
            send_telegram_message(token, chat_id, "토큰을 모두 소진하여 봇이 응답할 수 없습니다. 토큰 충전 후 다시 시도해주세요.")
            return

        token = resolve_telegram_token(project.graph_data, project.user_id, db)
        if not token:
            return

        nodes = project.graph_data.get('nodes', [])
        edges = project.graph_data.get('edges', [])
        result_text, tokens, logs = run_workflow(
            nodes, edges, db=db, session_id=f"telegram_{chat_id}", project_id=project_id, default_input=text
        )

        send_telegram_message(token, chat_id, result_text)

        import json
        log = models.BotLog(
            project_id=project_id,
            username=str(chat_id),
            message=text,
            response=result_text,
        )
        db.add(log)

        record_usage(
            db,
            billable_user_id=project.user_id,
            actor_user_id=None,
            project_id=project_id,
            token_usage=tokens if isinstance(tokens, dict) else None,
            payload=json.dumps({"telegram_chat_id": chat_id, "content": text}, ensure_ascii=False),
            result=result_text,
            event_type=EVENT_WORKFLOW_EXECUTION,
            outcome=outcome_from_result(result_text),
            trigger_type="telegram",
        )

        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def sync_all_telegram_webhooks(db) -> None:
    """서버 시작 시, 라이브 상태인 텔레그램 프로젝트들의 웹훅을 다시 등록한다(idempotent —
    텔레그램은 재등록해도 안전하다). 디스코드처럼 프로세스 메모리에 연결을 들고 있는 게 아니라
    텔레그램 서버 쪽에 등록해두는 방식이라 사실 서버 재시작으로 끊기지는 않지만, 그 사이
    프로젝트 URL이 바뀌었거나 최초로 한 번도 등록되지 않았을 가능성에 대비해 확인 차 재등록한다."""
    projects = db.query(models.Project).all()
    for p in projects:
        if not p.graph_data or not p.graph_data.get("is_live"):
            continue
        node_id, _ = find_telegram_trigger_node(p.graph_data)
        if not node_id:
            continue
        token = resolve_telegram_token(p.graph_data, p.user_id, db)
        if token:
            print(f"Registering Telegram webhook for project {p.id}")
            set_telegram_webhook(token, p.id)
