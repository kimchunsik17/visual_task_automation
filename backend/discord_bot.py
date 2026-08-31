import discord
from usage_tracking import EVENT_WORKFLOW_EXECUTION, outcome_from_result, record_usage
import asyncio
import io
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from graph import run_workflow
from credential_crypto import decrypt_secret

def _reply_attachments(logs, project_id):
    """자동 답장에 붙일 파일. 실행 로그의 artifactId 를 공통 resolver 로 확인한다(ADR-0018).

    예전에는 결과 문자열에서 `uploads/...` 를 정규식으로 찾아 그 경로를 그대로 열었다 —
    소유자·프로젝트·만료를 확인하지 않는 경로였고, 발송 노드와 규칙이 따로 놀았다. 이제
    discordNode 와 **같은** 정책·검증을 쓴다.
    """
    artifact_ids = []
    for entry in logs or []:
        for ref in (entry or {}).get('artifacts') or []:
            aid = ref.get('artifactId') if isinstance(ref, dict) else ref
            if aid and aid not in artifact_ids:
                artifact_ids.append(aid)
    if not artifact_ids:
        return []

    import delivery_attachments
    if not delivery_attachments.connector_enabled('discord'):
        return []

    db = SessionLocal()
    try:
        project = db.query(models.Project).filter(models.Project.id == project_id).first()
        owner_user_id = project.user_id if project else 0
        resolved = delivery_attachments.validate_attachments(
            db, artifact_ids, owner_user_id=owner_user_id, project_id=project_id,
            policy=delivery_attachments.policy_for('discord'),
            node_type='discordTriggerNode',
        )
        # 답장은 별도 프로세스(discord.py 의 이벤트 루프)에서 보내므로 handle 을 넘기지 않고
        # 바이트를 읽어 둔다 — descriptor 를 이벤트 루프 너머로 들고 다니지 않기 위해서다.
        return [(item.filename, item.read_bytes()) for item in resolved]
    except Exception as exc:
        print(f"[discord-bot] 첨부 준비 실패: {exc}")
        return []
    finally:
        db.close()

# Store active bots by project_id
_active_bots = {}


def find_discord_trigger_node(graph_data: dict):
    """그래프에서 discordTriggerNode를 찾는다. (node_id, botToken 원본값) 튜플, 없으면 (None, None).

    예전엔 디스코드 봇이 "배포" 모달에서 토큰을 입력받아 graph_data.discord_bot_token에 저장하는
    별도 경로였는데, 다른 트리거(webhookNode/scheduleNode)처럼 그래프 안의 노드 하나로 통일했다 —
    에디터의 "라이브 시작" 토글 하나로 스케줄/웹훅/디스코드봇이 전부 같은 방식으로 켜지고 꺼진다.
    """
    nodes = (graph_data or {}).get('nodes', [])
    for n in nodes:
        if n.get('type') == 'discordTriggerNode':
            return n.get('id'), (n.get('data', {}) or {}).get('botToken', '')
    return None, None


def resolve_discord_token(graph_data: dict, owner_user_id: int, db) -> str:
    """discordTriggerNode.data.botToken을 실제 봇 토큰 문자열로 바꾼다.
    "{{API_CENTER:discord}}" 플레이스홀더면 UserApiKey(provider='discord')에서 찾아온다
    (discordNode 발송 노드와 동일한 API 센터 자격증명을 그대로 재사용 — 어차피 같은 봇 토큰이다)."""
    _, raw_token = find_discord_trigger_node(graph_data)
    if not raw_token:
        return ""
    if raw_token.strip() == "{{API_CENTER:discord}}":
        key_row = (
            db.query(models.UserApiKey)
            .filter(models.UserApiKey.user_id == owner_user_id, models.UserApiKey.provider == "discord")
            .first()
        )
        return decrypt_secret(key_row.api_key) if key_row else ""
    return raw_token

def start_discord_bot(project_id: int, token: str):
    """
    Start a discord bot for a given project.
    If a bot is already running for this project, stop it and restart it.

    옛 클라이언트의 close()와 새 클라이언트의 start()를 각각 별도 태스크로 fire-and-forget하면
    둘 다 이벤트 루프에서 동시에 돌아서, 옛 봇이 아직 완전히 끊기기 전 새 봇이 먼저 연결되는
    구간이 생긴다 — 그 구간 동안 같은 메시지를 두 클라이언트가 동시에 받아 각자 답장해서
    메시지가 두 개씩 나오는 버그가 있었다. run_client() 안에서 close()를 먼저 await한 뒤에
    start()를 부르도록 순서를 강제해서 고친다.
    """
    old_client = _active_bots.pop(project_id, None)

    intents = discord.Intents.default()
    intents.message_content = True  # Need message content to read user inputs
    
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"Discord Bot for project {project_id} logged in as {client.user}")
        
    @client.event
    async def on_message(message):
        # Ignore messages from the bot itself
        if message.author == client.user:
            return
            
        print(f"[DEBUG] Received message from {message.author}: {message.content}")
        print(f"[DEBUG] Is DM: {isinstance(message.channel, discord.DMChannel)}, Mentions bot: {client.user in message.mentions}")
        
        # Respond to DMs or Mentions
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mention = client.user in message.mentions
        
        if not (is_dm or is_mention):
            print(f"[DEBUG] Ignoring message: Not a DM and bot not mentioned.")
            return
            
        # Get message text (remove bot mention if any)
        content = message.content
        if is_mention:
            content = content.replace(f"<@{client.user.id}>", "").strip()
            
        # Send processing message
        try:
            processing_msg = await message.channel.send("⏳ 처리 중...")
        except Exception:
            return # Cannot send message to this channel
        
        # Run workflow in a separate thread
        def _run():
            db = SessionLocal()
            try:
                project = db.query(models.Project).filter(models.Project.id == project_id).first()
                if not project:
                    return "Error: Project not found.", {}, [], False

                # 토큰 체크 및 봇 정지
                user = db.query(models.User).filter(models.User.id == project.user_id).first()
                if user and user.token_balance <= 0:
                    stop_discord_bot(project_id)
                    project.deploy_mode = 'chatbot'
                    db.commit()
                    return "토큰을 모두 소진하여 디스코드 봇이 정지되었습니다. 토큰 충전 후 봇을 다시 배포해주세요.", {}, [], False

                nodes = project.graph_data.get('nodes', [])
                edges = project.graph_data.get('edges', [])
                # 워크플로우가 discordNode(더 이상 나가는 엣지가 없는 리프)로 끝나면, 그 노드가
                # 이미 실제 내용을 채널에 직접 보낸 상태다 — 문자열 매칭이 아니라 그래프 구조로
                # 판단해야, discordNode의 결과값이 이제 실제 발송 내용을 담고 있어도(평가 기능이
                # 제대로 채점할 수 있도록 바꿨다) 여기서 중복 표시하지 않을 수 있다.
                sources_with_outgoing = {e.get('source') for e in edges}
                ends_in_discord_send = any(
                    n.get('type') == 'discordNode' and n.get('id') not in sources_with_outgoing
                    for n in nodes
                )
                result_text, tokens, logs = run_workflow(nodes, edges, db=db, session_id=str(message.author), project_id=project_id, default_input=content)
                return result_text, tokens, logs, ends_in_discord_send
            except Exception as e:
                import traceback
                traceback.print_exc()
                return f"Error executing workflow: {str(e)}", {}, [], False
            finally:
                db.close()

        result_text, tokens, logs, ends_in_discord_send = await asyncio.to_thread(_run)

        # Handle empty or too long results
        if not result_text or result_text.strip() == "":
            result_text = "No output generated."
        elif len(result_text) > 1950:
            result_text = result_text[:1950] + "\n... (truncated)"

        # discordNode(발송)가 실패하면 실제로 반환하는 문자열은 (콘솔 print의 영어 문구가 아니라)
        # "⚠️ Discord 발송 실패/오류/...설정되지 않아" 같은 한국어 경고문이다(integration_nodes.py
        # generate_discord_node 참고). 예전엔 여기서 print 전용 영어 문구를 찾고 있어서 이 체크가
        # 항상 False가 되어, 발송이 실패해도 무조건 "처리 중..." placeholder를 지워버리는 바람에
        # 사용자에게는 답장이 통째로 사라지는 것처럼 보이는 버그가 있었다.
        # 이제 discordNode 는 실패를 구조화 오류(NodeError v1)로 실행 로그에 남기므로 그것을 먼저 본다.
        # 문자열 검색은 legacy fallback(ADR-0016).
        from node_errors import runtime as _node_error_runtime
        is_discord_failure = (
            _node_error_runtime.has_node_error(logs, "discordNode")
            or "⚠️ Discord 발송" in result_text or "⚠️ Discord 봇 토큰" in result_text
        )
        if ends_in_discord_send and not is_discord_failure:
            # 실제 내용은 discordNode가 이미 채널에 직접 보냈으므로, "처리 중..." placeholder를
            # 다시 그 내용으로 덮어쓰면 중복으로 남으니 그냥 지운다. 발송이 실패/스킵된 경우는
            # 사용자가 알아야 하니 그대로 보여준다.
            try:
                await processing_msg.delete()
            except Exception:
                pass
        else:
            _files = await asyncio.to_thread(_reply_attachments, logs, project_id)
            if _files:
                # 메시지 편집으로는 첨부파일을 깔끔하게 붙일 수 없어서, placeholder는 지우고
                # 파일이 첨부된 새 메시지를 보낸다(discordNode의 파일 첨부 처리와 동일한 이유).
                try:
                    await processing_msg.delete()
                except Exception:
                    pass
                try:
                    # 본문은 첨부가 있어도 함께 보낸다 — 예전 경로는 파일만 보내고 결과 텍스트를
                    # 통째로 버렸다(§4.10 "메일 본문과 Discord 캡션은 첨부 유무와 관계없이 유지").
                    await message.channel.send(
                        content=result_text,
                        files=[discord.File(io.BytesIO(data), filename=name) for name, data in _files],
                    )
                except Exception as e:
                    await message.channel.send(f"⚠️ 파일 전송 실패: {e}")
            else:
                await processing_msg.edit(content=result_text)
        
        def _save_log():
            import json
            db = SessionLocal()
            try:
                project = db.query(models.Project).filter(models.Project.id == project_id).first()
                owner_id = project.user_id if project else None

                log = models.BotLog(
                    project_id=project_id,
                    username=str(message.author),
                    message=content,
                    response=result_text
                )
                db.add(log)

                record_usage(
                    db,
                    billable_user_id=owner_id,
                    actor_user_id=None,
                    project_id=project_id,
                    token_usage=tokens if isinstance(tokens, dict) else None,
                    payload=json.dumps({"discord_user": str(message.author), "content": content}, ensure_ascii=False),
                    result=result_text,
                    event_type=EVENT_WORKFLOW_EXECUTION,
                    outcome=outcome_from_result(result_text),
                    trigger_type="discord",
                )

                db.commit()
            except Exception as e:
                print(f"Failed to save bot log: {e}")
            finally:
                db.close()
                
        await asyncio.to_thread(_save_log)
        
    _active_bots[project_id] = client

    async def run_client():
        if old_client is not None:
            try:
                await old_client.close()
            except Exception as e:
                print(f"Error closing previous bot for project {project_id}: {e}")
        try:
            await client.start(token)
        except Exception as e:
            print(f"Discord Bot Error for project {project_id}: {e}")

    asyncio.create_task(run_client())

def stop_discord_bot(project_id: int):
    """
    Stop a running discord bot.
    """
    if project_id in _active_bots:
        client = _active_bots[project_id]
        
        async def _disconnect():
            try:
                # 명시적으로 오프라인 상태로 변경하여 디스코드 클라이언트(UI)에 즉각 반영되도록 함
                await client.change_presence(status=discord.Status.offline)
            except Exception as e:
                print(f"Error changing presence before close: {e}")
            finally:
                await client.close()
                
        asyncio.create_task(_disconnect())
        del _active_bots[project_id]

def boot_existing_discord_bots(db: Session):
    """
    서버 시작 시 "라이브"로 켜져 있던 봇들을 전부 다시 띄운다. scheduler.sync_all_schedules와
    동일한 방식으로(deploy_mode가 아니라) 모든 프로젝트를 스캔해서 discordTriggerNode가 있고
    graph_data.is_live가 True인 것만 골라 토큰을 해석해서 시작한다.
    """
    projects = db.query(models.Project).all()
    for p in projects:
        if not p.graph_data or not p.graph_data.get("is_live"):
            continue
        node_id, _ = find_discord_trigger_node(p.graph_data)
        if not node_id:
            continue
        token = resolve_discord_token(p.graph_data, p.user_id, db)
        if token:
            print(f"Booting up Discord Bot for project {p.id}")
            start_discord_bot(p.id, token)
