import datetime
from node_registry import node_registry
from node_bindings import bound_expr

@node_registry.register('emailNode')
def generate_email_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 실행 로직은 delivery_runtime.send_smtp 에 있다(ADR-0018, 우선 백로그 20). 예전에는 여기서
    # MIMEMultipart 컨테이너를 만들어 놓고 실제로는 text/plain 본문 하나만 붙였다 — 첨부를 표현할
    # 자리가 아예 없었고, 수신자·제목이 헤더에 그대로 들어가 개행 하나로 헤더를 덧붙일 수 있었다.
    from .delivery_support import attachments_config, upstream_artifacts_expr

    lines.append(f"{indent}# --- Email Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    to_email = node.get('data', {}).get('toEmail', '').replace('\\', '\\\\').replace('"', '\\"')
    subject = node.get('data', {}).get('subject', 'Auto Flow 알림').replace('\\', '\\\\').replace('"', '\\"')
    smtp_credentials = node.get('data', {}).get('smtp_credentials', '').replace("'", "\\'")
    upstream = prev_res_var if prev_res_var else 'last_result'

    # 자격증명 해석은 예전과 같다 — API 센터 reference 면 .env 의 SMTP_USER/PASSWORD 를, 노드에
    # 직접 넣은 `user:password` 면 그 값을 쓴다.
    lines.append(f"{indent}import os")
    lines.append(f"{indent}smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')")
    lines.append(f"{indent}smtp_port = int(os.getenv('SMTP_PORT', '587'))")
    lines.append(f"{indent}smtp_credentials_str = '{smtp_credentials}'")
    lines.append(f"{indent}if smtp_credentials_str.startswith('{{{{API_CENTER:'):")
    lines.append(f"{indent}    smtp_user = os.getenv('SMTP_USER', '')")
    lines.append(f"{indent}    smtp_password = os.getenv('SMTP_PASSWORD', '')")
    lines.append(f"{indent}elif smtp_credentials_str and ':' in smtp_credentials_str:")
    lines.append(f"{indent}    smtp_user, smtp_password = smtp_credentials_str.split(':', 1)")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    smtp_user = os.getenv('SMTP_USER', '')")
    lines.append(f"{indent}    smtp_password = os.getenv('SMTP_PASSWORD', '')")

    lines.append(f"{indent}from delivery_runtime import send_smtp as _send_smtp")
    lines.append(f"{indent}email_body_{node_id} = str({upstream}) if {upstream} is not None else ''")
    lines.append(f"{indent}_email_res_{node_id} = _send_smtp(")
    lines.append(f"{indent}    smtp_server=smtp_server, smtp_port=smtp_port,")
    lines.append(f"{indent}    smtp_user=smtp_user, smtp_password=smtp_password,")
    # 바인딩된 필드는 리터럴이 아니라 런타임 조회다(계획 §4) — bound_expr 가 둘 중 맞는 표현식을
    # 만들어 준다. 바인딩이 없으면 repr 리터럴이라 이스케이프 걱정도 없다.
    lines.append(f"{indent}    to_email={bound_expr(node, node_id, 'toEmail')}, "
                 f"subject={bound_expr(node, node_id, 'subject', 'Auto Flow 알림')}, body=email_body_{node_id},")
    lines.append(f"{indent}    db=db, owner_user_id=__owner_user_id__, project_id=kwargs.get('project_id'),")
    lines.append(f"{indent}    attachments_config={attachments_config(node)!r},")
    lines.append(f"{indent}    upstream_artifact_ids={upstream_artifacts_expr(node_id, incoming_edges)},")
    lines.append(f"{indent}    upstream_text=email_body_{node_id}, node_id='{node_id}')")
    # 성공/실패 모두 실제 본문을 결과로 남긴다 — 상태 문구로 덮어쓰면 평가 기능이 그 문구를 놓고
    # 채점하는 버그가 재발한다(discordNode 에서 먼저 발견됐던 것과 같은 이유).
    lines.append(f"{indent}res_text_{node_id} = str(_email_res_{node_id})")
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_email_res_{node_id})")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('kakaoNode')
def generate_kakao_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Kakao Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    access_token = node.get('data', {}).get('accessToken', '').replace('\\', '\\\\').replace('"', '\\"')
    receiver = node.get('data', {}).get('receiver', '').replace('\\', '\\\\').replace('"', '\\"')
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import json")
    lines.append(f"{indent}kakao_token_{node_id} = \"{access_token}\"")
    lines.append(f"{indent}kakao_msg_{node_id} = str({prev_res_var if prev_res_var else 'last_result'})")
    lines.append(f"{indent}kakao_msg_{node_id} = kakao_msg_{node_id}[:190] + '...' if len(kakao_msg_{node_id}) > 190 else kakao_msg_{node_id}")
    lines.append(f"{indent}kakao_receiver_{node_id} = {bound_expr(node, node_id, 'receiver')}")
    
    lines.append(f"{indent}if kakao_token_{node_id}:")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        headers_{node_id} = {{'Authorization': f'Bearer {{kakao_token_{node_id}}}'}}")
    lines.append(f"{indent}        template_object_{node_id} = {{")
    lines.append(f"{indent}            'object_type': 'text',")
    lines.append(f"{indent}            'text': kakao_msg_{node_id},")
    lines.append(f"{indent}            'link': {{'web_url': 'https://developers.kakao.com', 'mobile_web_url': 'https://developers.kakao.com'}}")
    lines.append(f"{indent}        }}")
    lines.append(f"{indent}        payload_{node_id} = {{'template_object': json.dumps(template_object_{node_id})}}")
    
    lines.append(f"{indent}        if kakao_receiver_{node_id}:")
    lines.append(f"{indent}            payload_{node_id}['receiver_uuids'] = json.dumps([kakao_receiver_{node_id}])")
    lines.append(f"{indent}            url_{node_id} = 'https://kapi.kakao.com/v1/api/talk/friends/message/default/send'")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            url_{node_id} = 'https://kapi.kakao.com/v2/api/talk/memo/default/send'")
    
    lines.append(f"{indent}        resp_{node_id} = requests.post(url_{node_id}, headers=headers_{node_id}, data=payload_{node_id}, timeout=10)")
    lines.append(f"{indent}        if resp_{node_id}.status_code == 200:")
    lines.append(f"{indent}            print(f'\\n[Kakao Send Success]\\n')")
    # 성공 시 실제 발송 내용(kakao_msg)을 그대로 결과로 남긴다 (discordNode/emailNode와 동일한 이유).
    lines.append(f"{indent}            res_text_{node_id} = kakao_msg_{node_id}")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            print(f'\\n[Kakao Send Failed: {{resp_{node_id}.text}}]\\n')")
    # 발송 실패/스킵 시에도 실제 생성된 메시지는 버리지 않는다 (discordNode/emailNode와 동일한 이유).
    lines.append(f"{indent}            res_text_{node_id} = kakao_msg_{node_id} + f'\\n\\n[⚠️ 카카오 발송 실패: {{resp_{node_id}.text}}]'")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Kakao Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = kakao_msg_{node_id} + f'\\n\\n[⚠️ 카카오 발송 오류: {{str(e)}}]'")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Kakao Skipped: No Access Token provided]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = kakao_msg_{node_id} + '\\n\\n[⚠️ 카카오 액세스 토큰이 설정되지 않아 실제 발송은 되지 않았습니다]'")
    
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('discordNode')
def generate_discord_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 실행 로직은 delivery_runtime.send_discord 에 있다(ADR-0018, 우선 백로그 20). 예전에는 여기서
    # requests 호출을 문자열로 조립했고, 첨부는 **앞 노드의 결과 문자열에서 `uploads/...` 를
    # 정규식으로 찾아** 그 경로를 그대로 열었다. 그 방식은 파일 소유자를 확인하지 않았고, 첨부가
    # 생기면 payload_json.content 를 빈 값으로 만들어 사용자가 쓴 본문까지 지웠다.
    #
    # 이제 첨부는 타입으로 이어진다 — 선행 노드가 등록한 artifactId 를 첨부 포트에서 읽고,
    # 소유·프로젝트·만료·형식·크기를 외부 호출 전에 전부 확인한다.
    from .delivery_support import attachments_config, upstream_artifacts_expr

    lines.append(f"{indent}# --- Discord Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    bot_token = node.get('data', {}).get('botToken', '').replace('\\', '\\\\').replace('"', '\\"')
    channel_id = node.get('data', {}).get('channelId', '').replace('\\', '\\\\').replace('"', '\\"')
    upstream = prev_res_var if prev_res_var else 'last_result'

    lines.append(f"{indent}from delivery_runtime import send_discord as _send_discord")
    lines.append(f"{indent}discord_msg_{node_id} = str({upstream}) if {upstream} is not None else ''")
    lines.append(f"{indent}_discord_res_{node_id} = _send_discord(")
    lines.append(f"{indent}    token=\"{bot_token}\", channel_id={bound_expr(node, node_id, 'channelId')},")
    lines.append(f"{indent}    body=discord_msg_{node_id}, db=db, owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}    project_id=kwargs.get('project_id'),")
    lines.append(f"{indent}    attachments_config={attachments_config(node)!r},")
    lines.append(f"{indent}    upstream_artifact_ids={upstream_artifacts_expr(node_id, incoming_edges)},")
    lines.append(f"{indent}    upstream_text=discord_msg_{node_id}, node_id='{node_id}')")
    # 성공해도 상태 문구로 덮어쓰지 않는다 — 예전에 'Discord Send Success' 로 last_result 를
    # 바꿨더니 평가 기능이 그 문구를 놓고 채점했고, 뒤에 노드가 이어지면 실제 내용 대신 상태만
    # 전달됐다. 실패해도 만들려던 본문은 그대로 남긴다(NodeResult.passthrough).
    lines.append(f"{indent}res_text_{node_id} = str(_discord_res_{node_id})")
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=_discord_res_{node_id})")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('telegramNode')
def generate_telegram_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # discordNode(발송)와 동일한 패턴. 텔레그램은 채널ID 대신 chatId를 쓰고, Bot API가
    # 훨씬 단순해서(웹훅/봇API 구분 없이 항상 sendMessage 하나) discordNode보다 코드가 짧다.
    lines.append(f"{indent}# --- Telegram Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    bot_token = node.get('data', {}).get('botToken', '').replace('\\', '\\\\').replace('"', '\\"')
    chat_id = node.get('data', {}).get('chatId', '').replace('\\', '\\\\').replace('"', '\\"')

    lines.append(f"{indent}import requests")
    lines.append(f"{indent}telegram_token_{node_id} = \"{bot_token}\"")
    lines.append(f"{indent}telegram_chat_{node_id} = {bound_expr(node, node_id, 'chatId')}")
    lines.append(f"{indent}telegram_msg_{node_id} = str({prev_res_var if prev_res_var else 'last_result'})")
    lines.append(f"{indent}if telegram_token_{node_id} and telegram_chat_{node_id}:")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        resp_{node_id} = requests.post(")
    lines.append(f"{indent}            f'https://api.telegram.org/bot{{telegram_token_{node_id}}}/sendMessage',")
    lines.append(f"{indent}            json={{'chat_id': telegram_chat_{node_id}, 'text': telegram_msg_{node_id}[:4000]}}, timeout=10,")
    lines.append(f"{indent}        )")
    lines.append(f"{indent}        if resp_{node_id}.status_code == 200:")
    lines.append(f"{indent}            print(f'\\n[Telegram Send Success]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = telegram_msg_{node_id}")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            print(f'\\n[Telegram Send Failed: {{resp_{node_id}.text}}]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = telegram_msg_{node_id} + f'\\n\\n[⚠️ Telegram 발송 실패: {{resp_{node_id}.text}}]'")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Telegram Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = telegram_msg_{node_id} + f'\\n\\n[⚠️ Telegram 발송 오류: {{str(e)}}]'")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Telegram Skipped: No Bot Token/Chat ID provided]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = telegram_msg_{node_id} + '\\n\\n[⚠️ Telegram 봇 토큰 또는 chatId가 설정되지 않아 실제 발송은 되지 않았습니다]'")

    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register("slackNode")
def generate_slack_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    channel = node.get('data', {}).get('channel', '#general')
    message = node.get('data', {}).get('message', 'Hello from Visual Task Automation!')

    # repr()로 안전하게 이스케이프했었으나, repr()이 항상 큰따옴표 문자열을 만든다고
    # 가정한 문자열 자르기+이어붙이기가 있어서(작은따옴표로 나오는 흔한 경우 SyntaxError로 깨짐),
    # 다른 노드들과 같은 방식(직접 이스케이프 후 f-string에 삽입)으로 통일한다.
    safe_channel = channel.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    safe_message = message.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    lines.append(f"{indent}# --- Slack Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}slack_channel_{node_id} = {bound_expr(node, node_id, 'channel', '#general')}")

    if prev_res_var:
        lines.append(f"{indent}slack_msg_{node_id} = {bound_expr(node, node_id, 'message')} + \"\\n\\n\" + str({prev_res_var})")
    else:
        lines.append(f"{indent}slack_msg_{node_id} = {bound_expr(node, node_id, 'message')}")

    lines.append(f"{indent}print(f'Mocking Slack send to {{slack_channel_{node_id}}}: {{slack_msg_{node_id}}}')")
    # 실제 발송한 메시지 내용을 그대로 결과로 남긴다 (discordNode/emailNode/kakaoNode와 동일한 이유 —
    # 상태 문구로 덮어쓰면 평가 기능이 실제 내용을 못 보고 채점한다).
    lines.append(f"{indent}last_result = slack_msg_{node_id}")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"last_result", visited=visited)

@node_registry.register('tossNode')
def generate_toss_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Toss Payments Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    secret_key = node.get('data', {}).get('secretKey', '').replace('\\', '\\\\').replace('"', '\\"')
    search_type = node.get('data', {}).get('searchType', 'paymentKey')
    search_value = node.get('data', {}).get('searchValue', '').replace('\\', '\\\\').replace('"', '\\"')
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import base64")
    lines.append(f"{indent}toss_sk_{node_id} = \"{secret_key}\"")
    lines.append(f"{indent}toss_val_{node_id} = \"{search_value}\" if \"{search_value}\" else str({prev_res_var if prev_res_var else 'last_result'})")
    
    lines.append(f"{indent}if toss_sk_{node_id} and toss_val_{node_id}:")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        auth_str_{node_id} = base64.b64encode((toss_sk_{node_id} + ':').encode('utf-8')).decode('utf-8')")
    lines.append(f"{indent}        headers_{node_id} = {{'Authorization': f'Basic {{auth_str_{node_id}}}'}}")
    lines.append(f"{indent}        if '{search_type}' == 'paymentKey':")
    lines.append(f"{indent}            url_{node_id} = f'https://api.tosspayments.com/v1/payments/{{toss_val_{node_id}}}'")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            url_{node_id} = f'https://api.tosspayments.com/v1/payments/orders/{{toss_val_{node_id}}}'")
    
    lines.append(f"{indent}        resp_{node_id} = requests.get(url_{node_id}, headers=headers_{node_id}, timeout=10)")
    lines.append(f"{indent}        if resp_{node_id}.status_code == 200:")
    lines.append(f"{indent}            print(f'\\n[Toss Query Success]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = resp_{node_id}.text")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            print(f'\\n[Toss Query Failed: {{resp_{node_id}.text}}]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = f'Toss Query Failed: {{resp_{node_id}.text}}'")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Toss Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = f'Toss Error: {{str(e)}}'")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Toss Skipped: Missing API Key or Value]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = 'Toss Skipped: Missing arguments'")
    
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)

@node_registry.register('paymentLinkNode')
def generate_payment_link_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Payment Link Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    
    provider = node.get('data', {}).get('provider', 'toss').replace('\\', '\\\\').replace('"', '\\"')
    order_data = node.get('data', {}).get('orderData', '').strip()
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import json")
    
    # Resolve dynamic input
    lines.append(f"{indent}raw_val_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
    if not order_data or order_data == '{{last_result}}' or ('{{' in order_data and '}}' in order_data):
        lines.append(f"{indent}if isinstance(raw_val_{node_id}, (dict, list)):")
        lines.append(f"{indent}    order_data_val_{node_id} = json.dumps(raw_val_{node_id}, ensure_ascii=False)")
        lines.append(f"{indent}else:")
        lines.append(f"{indent}    import re")
        lines.append(f"{indent}    order_data_val_{node_id} = re.sub(r'^```(json)?|```$', '', str(raw_val_{node_id}).strip(), flags=re.MULTILINE).strip()")
    else:
        safe_order_data = repr(order_data)
        lines.append(f"{indent}order_data_val_{node_id} = {safe_order_data}")

    lines.append(f"{indent}payload_{node_id} = {{")
    lines.append(f"{indent}    'provider': '{provider}',")
    lines.append(f"{indent}    'orderData': order_data_val_{node_id}")
    lines.append(f"{indent}}}")
    
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    resp_{node_id} = requests.post('http://localhost:3002/mock/payment/create-link', json=payload_{node_id}, timeout=10)")
    lines.append(f"{indent}    if resp_{node_id}.status_code == 200:")
    lines.append(f"{indent}        checkout_url_{node_id} = resp_{node_id}.json().get('checkoutUrl')")
    lines.append(f"{indent}        try:")
    lines.append(f"{indent}            order_dict = json.loads(order_data_val_{node_id})")
    lines.append(f"{indent}            items_text = '\\n'.join([f\"- {{item.get('name', '상품')}} ({{item.get('qty', 1)}}개)\" for item in order_dict.get('items', [])])")
    lines.append(f"{indent}            if not items_text: items_text = \"- 상품 정보 없음\"")
    lines.append(f"{indent}            res_text_{node_id} = f\"✅ 주문이 확인되었습니다!\\n\\n[주문 내역]\\n{{items_text}}\\n\\n🔗 결제 링크:\\n{{checkout_url_{node_id}}}\"")
    lines.append(f"{indent}        except:")
    lines.append(f"{indent}            res_text_{node_id} = f\"✅ 주문이 확인되었습니다!\\n🔗 결제 링크:\\n{{checkout_url_{node_id}}}\"")
    lines.append(f"{indent}        print(f'\\n[Payment Link Created: {{checkout_url_{node_id}}}]\\n')")
    lines.append(f"{indent}    else:")
    lines.append(f"{indent}        print(f'\\n[Payment Link Failed: {{resp_{node_id}.text}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = f'Payment Link Failed: {{resp_{node_id}.text}}'")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    print(f'\\n[Payment Link Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = f'Payment Link Error: {{str(e)}}'")

    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")

    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('googleSheetsNode')
def generate_google_sheets_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # 서비스 계정 인증 실패("설정 안 됨")와 시트 접근 실패(공유 안 함, 잘못된 ID 등)를
    # google_sheets_utils가 둘 다 RuntimeError로 던지므로, 여기서는 그 메시지를 그대로
    # 사용자에게 보여주기만 하면 된다(discordNode/kakaoNode의 "설정 안 됨" 안내와 동일한 패턴).
    lines.append(f"{indent}# --- Google Sheets Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    data = node.get('data', {})
    mode = data.get('mode', 'read')
    spreadsheet_id = data.get('spreadsheetId', '').replace('\\', '\\\\').replace('"', '\\"')
    range_str = data.get('range', '').replace('\\', '\\\\').replace('"', '\\"')
    values_literal = data.get('values', '').strip()

    lines.append(f"{indent}import json")
    lines.append(f"{indent}import google_sheets_utils as _gs_{node_id}")
    lines.append(f"{indent}_gs_sheet_id_{node_id} = \"{spreadsheet_id}\"")
    lines.append(f"{indent}_gs_range_{node_id} = \"{range_str}\"")
    if mode != 'read':
        # 인증/권한 오류로 실패해도 "무엇을 기록하려고 했는지"는 버리지 않는다(kakaoNode/discordNode와
        # 동일한 이유) — try 블록 어디서 실패하든 except에서 참조할 수 있게 미리 초기화해둔다.
        lines.append(f"{indent}_gs_attempted_{node_id} = None")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    if not _gs_sheet_id_{node_id}:")
    lines.append(f"{indent}        raise ValueError('spreadsheetId가 비어있습니다')")

    if mode == 'read':
        lines.append(f"{indent}    _gs_rows_{node_id} = _gs_{node_id}.read_range(_gs_sheet_id_{node_id}, _gs_range_{node_id})")
        lines.append(f"{indent}    res_text_{node_id} = json.dumps(_gs_rows_{node_id}, ensure_ascii=False)")
        lines.append(f"{indent}    print(f'\\n[Google Sheets Read Success: {{len(_gs_rows_{node_id})}} rows]\\n')")
    else:
        # append/write 둘 다 "채울 값"이 필요하다 — data.values에 직접 JSON을 써놨으면 그걸 쓰고,
        # 비어있으면 fileModifierNode와 동일한 관례로 직전 노드의 출력(JSON)을 그대로 쓴다.
        if values_literal:
            safe_values = values_literal.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}    _gs_raw_{node_id} = \"{safe_values}\"")
        else:
            lines.append(f"{indent}    _gs_raw_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
        lines.append(f"{indent}    if isinstance(_gs_raw_{node_id}, str):")
        lines.append(f"{indent}        _gs_values_{node_id} = json.loads(_strip_json_fence(_gs_raw_{node_id}))")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        _gs_values_{node_id} = _gs_raw_{node_id}")
        # dict 하나가 오면 append/write 둘 다 "값들의 리스트"가 필요하므로 values()로 풀어준다
        # (예: llmNode의 구조적 출력이 {"name": "홍길동", "amount": 1000} 형태로 오는 경우가 흔하다).
        lines.append(f"{indent}    if isinstance(_gs_values_{node_id}, dict):")
        lines.append(f"{indent}        _gs_values_{node_id} = list(_gs_values_{node_id}.values())")
        lines.append(f"{indent}    _gs_attempted_{node_id} = _gs_values_{node_id}")

        if mode == 'append':
            lines.append(f"{indent}    _gs_{node_id}.append_row(_gs_sheet_id_{node_id}, _gs_range_{node_id}, _gs_values_{node_id})")
            lines.append(f"{indent}    res_text_{node_id} = f'구글 시트에 한 행을 추가했습니다: ' + json.dumps(_gs_values_{node_id}, ensure_ascii=False)")
            lines.append(f"{indent}    print(f'\\n[Google Sheets Append Success]\\n')")
        else:  # write
            # write는 2차원(행렬)이어야 한다 — 평평한 리스트 하나만 왔으면 한 행짜리로 감싼다.
            lines.append(f"{indent}    if _gs_values_{node_id} and not isinstance(_gs_values_{node_id}[0], list):")
            lines.append(f"{indent}        _gs_values_{node_id} = [_gs_values_{node_id}]")
            lines.append(f"{indent}    _gs_{node_id}.write_range(_gs_sheet_id_{node_id}, _gs_range_{node_id}, _gs_values_{node_id})")
            lines.append(f"{indent}    res_text_{node_id} = f'구글 시트에 값을 기록했습니다: ' + json.dumps(_gs_values_{node_id}, ensure_ascii=False)")
            lines.append(f"{indent}    print(f'\\n[Google Sheets Write Success]\\n')")

    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    print(f'\\n[Google Sheets Error: {{str(e)}}]\\n')")
    if mode == 'read':
        lines.append(f"{indent}    res_text_{node_id} = f'[⚠️ 구글 시트 연동 실패: {{str(e)}}]'")
    else:
        lines.append(f"{indent}    _gs_note_{node_id} = f' (기록하려던 내용: {{json.dumps(_gs_attempted_{node_id}, ensure_ascii=False)}})' if _gs_attempted_{node_id} is not None else ''")
        lines.append(f"{indent}    res_text_{node_id} = f'[⚠️ 구글 시트 연동 실패: {{str(e)}}]' + _gs_note_{node_id}")

    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('googleCalendarNode')
def generate_google_calendar_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # googleSheetsNode와 동일한 서비스 계정을 쓴다 — 인증/권한 에러는 google_calendar_utils가
    # RuntimeError로 던지는 메시지를 그대로 사용자에게 보여준다.
    lines.append(f"{indent}# --- Google Calendar Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    data = node.get('data', {})
    mode = data.get('mode', 'create')
    calendar_id = data.get('calendarId', '').replace('\\', '\\\\').replace('"', '\\"')
    event_data_literal = data.get('eventData', '').strip()
    time_min = data.get('timeMin', '').replace('\\', '\\\\').replace('"', '\\"')
    time_max = data.get('timeMax', '').replace('\\', '\\\\').replace('"', '\\"')
    max_results = data.get('maxResults', 10)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 10

    lines.append(f"{indent}import json")
    lines.append(f"{indent}import google_calendar_utils as _gc_{node_id}")
    lines.append(f"{indent}_gc_cal_id_{node_id} = \"{calendar_id}\"")
    if mode != 'list':
        # googleSheetsNode와 동일한 이유 — 인증 실패해도 등록하려던 일정 내용은 버리지 않는다.
        lines.append(f"{indent}_gc_attempted_{node_id} = None")
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    if not _gc_cal_id_{node_id}:")
    lines.append(f"{indent}        raise ValueError('calendarId가 비어있습니다')")

    if mode == 'list':
        lines.append(f"{indent}    _gc_time_min_{node_id} = \"{time_min}\" or None")
        lines.append(f"{indent}    _gc_time_max_{node_id} = \"{time_max}\" or None")
        lines.append(f"{indent}    _gc_events_{node_id} = _gc_{node_id}.list_events(_gc_cal_id_{node_id}, time_min=_gc_time_min_{node_id}, time_max=_gc_time_max_{node_id}, max_results={max_results})")
        lines.append(f"{indent}    res_text_{node_id} = json.dumps(_gc_events_{node_id}, ensure_ascii=False)")
        lines.append(f"{indent}    print(f'\\n[Google Calendar List Success: {{len(_gc_events_{node_id})}} events]\\n')")
    else:  # create
        # googleSheetsNode의 values 필드와 동일한 관례 — eventData에 직접 JSON을 써놨으면 그걸
        # 쓰고, 비어있으면 직전 노드의 출력(JSON: summary/start/end/description/location)을
        # 그대로 쓴다. eventData 안에 {{key}} 자리표시자가 있으면(notionNode의 properties와 같은
        # 이유로 LLM이 실제로 이렇게 쓰는 경우가 있다) 직전 노드가 만든 값으로 먼저 채운다.
        lines.append(f"{indent}    _gc_upstream_raw_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
        lines.append(f"{indent}    if isinstance(_gc_upstream_raw_{node_id}, str):")
        lines.append(f"{indent}        try:")
        lines.append(f"{indent}            _gc_upstream_dict_{node_id} = json.loads(_strip_json_fence(_gc_upstream_raw_{node_id}))")
        lines.append(f"{indent}        except Exception:")
        lines.append(f"{indent}            _gc_upstream_dict_{node_id} = {{}}")
        lines.append(f"{indent}    elif isinstance(_gc_upstream_raw_{node_id}, dict):")
        lines.append(f"{indent}        _gc_upstream_dict_{node_id} = _gc_upstream_raw_{node_id}")
        lines.append(f"{indent}    else:")
        lines.append(f"{indent}        _gc_upstream_dict_{node_id} = {{}}")
        if event_data_literal:
            safe_event = event_data_literal.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}    _gc_template_{node_id} = \"{safe_event}\"")
            lines.append(f"{indent}    _gc_filled_{node_id} = _fill_template_placeholders(_gc_template_{node_id}, _gc_upstream_dict_{node_id})")
            lines.append(f"{indent}    _gc_event_{node_id} = json.loads(_gc_filled_{node_id})")
        else:
            lines.append(f"{indent}    _gc_event_{node_id} = _gc_upstream_dict_{node_id}")
        lines.append(f"{indent}    _gc_attempted_{node_id} = _gc_event_{node_id}")
        lines.append(f"{indent}    _gc_created_{node_id} = _gc_{node_id}.create_event(_gc_cal_id_{node_id}, _gc_event_{node_id})")
        lines.append(f"{indent}    res_text_{node_id} = f\"일정을 등록했습니다: \" + _gc_created_{node_id}.get('summary','') + f\" ({{_gc_created_{node_id}.get('start','')}}) \" + _gc_created_{node_id}.get('htmlLink','')")
        lines.append(f"{indent}    print(f'\\n[Google Calendar Create Success]\\n')")

    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    print(f'\\n[Google Calendar Error: {{str(e)}}]\\n')")
    if mode == 'list':
        lines.append(f"{indent}    res_text_{node_id} = f'[⚠️ 구글 캘린더 연동 실패: {{str(e)}}]'")
    else:
        lines.append(f"{indent}    _gc_note_{node_id} = f' (등록하려던 일정: {{json.dumps(_gc_attempted_{node_id}, ensure_ascii=False)}})' if _gc_attempted_{node_id} is not None else ''")
        lines.append(f"{indent}    res_text_{node_id} = f'[⚠️ 구글 캘린더 연동 실패: {{str(e)}}]' + _gc_note_{node_id}")

    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('notionNode')
def generate_notion_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    # discordNode/kakaoNode와 동일한 패턴 — data.token은 "{{API_CENTER:notion}}"이면 graph.py의
    # run_workflow가 codegen 전에 이미 실제 토큰 문자열로 치환해둔다(discordTriggerNode처럼 별도
    # resolve 함수가 필요 없다 — 발송/액션 노드는 항상 이 공용 치환 경로를 그냥 탄다).
    lines.append(f"{indent}# --- Notion Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    data = node.get('data', {})
    mode = data.get('mode', 'create')
    token = data.get('token', '').replace('\\', '\\\\').replace('"', '\\"')
    database_id = data.get('databaseId', '').replace('\\', '\\\\').replace('"', '\\"')
    properties_literal = data.get('properties', '').strip()

    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import json")
    lines.append(f"{indent}_notion_token_{node_id} = \"{token}\"")
    lines.append(f"{indent}_notion_db_{node_id} = \"{database_id}\"")
    if mode != 'query':
        # googleSheetsNode/googleCalendarNode와 동일한 이유 — 인증 실패해도 만들려던 페이지 내용은 버리지 않는다.
        lines.append(f"{indent}_notion_attempted_{node_id} = None")
    lines.append(f"{indent}if _notion_token_{node_id} and _notion_db_{node_id}:")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        _notion_headers_{node_id} = {{'Authorization': f'Bearer {{_notion_token_{node_id}}}', 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'}}")

    if mode == 'query':
        lines.append(f"{indent}        _notion_resp_{node_id} = requests.post(f'https://api.notion.com/v1/databases/{{_notion_db_{node_id}}}/query', headers=_notion_headers_{node_id}, json={{}}, timeout=10)")
        lines.append(f"{indent}        if _notion_resp_{node_id}.status_code == 200:")
        lines.append(f"{indent}            _notion_pages_{node_id} = _notion_resp_{node_id}.json().get('results', [])")
        lines.append(f"{indent}            res_text_{node_id} = json.dumps(_notion_pages_{node_id}, ensure_ascii=False)")
        lines.append(f"{indent}            print(f'\\n[Notion Query Success: {{len(_notion_pages_{node_id})}} pages]\\n')")
        lines.append(f"{indent}        else:")
        lines.append(f"{indent}            print(f'\\n[Notion Query Failed: {{_notion_resp_{node_id}.text}}]\\n')")
        lines.append(f"{indent}            res_text_{node_id} = f'[⚠️ Notion 조회 실패: {{_notion_resp_{node_id}.text}}]'")
    else:  # create
        # 직전 노드의 출력을 먼저 dict로 뽑아둔다 — properties에 값을 직접 넣었든(치환용) 비워뒀든
        # (그대로 사용) 둘 다 이 dict가 필요하다.
        lines.append(f"{indent}        _notion_upstream_raw_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
        lines.append(f"{indent}        if isinstance(_notion_upstream_raw_{node_id}, str):")
        lines.append(f"{indent}            try:")
        lines.append(f"{indent}                _notion_upstream_dict_{node_id} = json.loads(_strip_json_fence(_notion_upstream_raw_{node_id}))")
        lines.append(f"{indent}            except Exception:")
        lines.append(f"{indent}                _notion_upstream_dict_{node_id} = {{}}")
        lines.append(f"{indent}        elif isinstance(_notion_upstream_raw_{node_id}, dict):")
        lines.append(f"{indent}            _notion_upstream_dict_{node_id} = _notion_upstream_raw_{node_id}")
        lines.append(f"{indent}        else:")
        lines.append(f"{indent}            _notion_upstream_dict_{node_id} = {{}}")

        if properties_literal:
            # properties를 직접 써놨으면 그 안의 {{key}}를 직전 노드가 만든 값으로 채운 뒤
            # 파싱한다(fileModifierNode의 {{key}} 자리표시자 관례와 동일 — LLM이 자연스럽게
            # 이 문법을 그대로 재사용해서 properties를 짜는 경우가 실제로 있었다).
            safe_props = properties_literal.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            lines.append(f"{indent}        _notion_props_template_{node_id} = \"{safe_props}\"")
            lines.append(f"{indent}        _notion_props_filled_{node_id} = _fill_template_placeholders(_notion_props_template_{node_id}, _notion_upstream_dict_{node_id})")
            lines.append(f"{indent}        _notion_props_{node_id} = json.loads(_notion_props_filled_{node_id})")
        else:
            lines.append(f"{indent}        _notion_props_{node_id} = _notion_upstream_dict_{node_id}")
        lines.append(f"{indent}        _notion_attempted_{node_id} = _notion_props_{node_id}")
        lines.append(f"{indent}        _notion_body_{node_id} = {{'parent': {{'database_id': _notion_db_{node_id}}}, 'properties': _notion_props_{node_id}}}")
        lines.append(f"{indent}        _notion_resp_{node_id} = requests.post('https://api.notion.com/v1/pages', headers=_notion_headers_{node_id}, json=_notion_body_{node_id}, timeout=10)")
        lines.append(f"{indent}        if _notion_resp_{node_id}.status_code == 200:")
        lines.append(f"{indent}            _notion_created_{node_id} = _notion_resp_{node_id}.json()")
        lines.append(f"{indent}            res_text_{node_id} = 'Notion 페이지를 생성했습니다: ' + _notion_created_{node_id}.get('url', '')")
        lines.append(f"{indent}            print(f'\\n[Notion Create Success]\\n')")
        lines.append(f"{indent}        else:")
        lines.append(f"{indent}            print(f'\\n[Notion Create Failed: {{_notion_resp_{node_id}.text}}]\\n')")
        lines.append(f"{indent}            _notion_note_{node_id} = f' (만들려던 페이지 내용: {{json.dumps(_notion_attempted_{node_id}, ensure_ascii=False)}})' if _notion_attempted_{node_id} is not None else ''")
        lines.append(f"{indent}            res_text_{node_id} = f'[⚠️ Notion 페이지 생성 실패: {{_notion_resp_{node_id}.text}}]' + _notion_note_{node_id}")

    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Notion Error: {{str(e)}}]\\n')")
    if mode == 'query':
        lines.append(f"{indent}        res_text_{node_id} = f'[⚠️ Notion 연동 오류: {{str(e)}}]'")
    else:
        lines.append(f"{indent}        _notion_note_{node_id} = f' (만들려던 페이지 내용: {{json.dumps(_notion_attempted_{node_id}, ensure_ascii=False)}})' if _notion_attempted_{node_id} is not None else ''")
        lines.append(f"{indent}        res_text_{node_id} = f'[⚠️ Notion 연동 오류: {{str(e)}}]' + _notion_note_{node_id}")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Notion Skipped: No token/databaseId provided]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = '[⚠️ Notion 토큰 또는 데이터베이스 ID가 설정되지 않아 실제 연동은 되지 않았습니다]'")

    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
