import datetime
from node_registry import node_registry

@node_registry.register('emailNode')
def generate_email_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Email Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    to_email = node.get('data', {}).get('toEmail', '').replace('"', '\\"')
    subject = node.get('data', {}).get('subject', 'Auto Flow 알림').replace('"', '\\"')
    
    lines.append(f"{indent}import smtplib")
    lines.append(f"{indent}from email.mime.text import MIMEText")
    lines.append(f"{indent}from email.mime.multipart import MIMEMultipart")
    lines.append(f"{indent}import os")
    lines.append(f"{indent}smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')")
    lines.append(f"{indent}smtp_port = int(os.getenv('SMTP_PORT', '587'))")
    lines.append(f"{indent}smtp_user = os.getenv('SMTP_USER', '')")
    lines.append(f"{indent}smtp_password = os.getenv('SMTP_PASSWORD', '')")
    lines.append(f"{indent}msg = MIMEMultipart()")
    lines.append(f"{indent}msg['From'] = smtp_user")
    lines.append(f"{indent}msg['To'] = '{to_email}'")
    lines.append(f"{indent}msg['Subject'] = '{subject}'")
    lines.append(f"{indent}msg.attach(MIMEText(str({prev_res_var if prev_res_var else 'last_result'}), 'plain', 'utf-8'))")
    
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    if not smtp_user or not smtp_password:")
    lines.append(f"{indent}        raise ValueError('SMTP credentials missing in .env')")
    lines.append(f"{indent}    server = smtplib.SMTP(smtp_server, smtp_port)")
    lines.append(f"{indent}    server.starttls()")
    lines.append(f"{indent}    server.login(smtp_user, smtp_password)")
    lines.append(f"{indent}    server.send_message(msg)")
    lines.append(f"{indent}    server.quit()")
    lines.append(f"{indent}    print(f'\\n[Email Successfully Sent to {to_email}]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = f'Email Successfully Sent to {to_email}'")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    print(f'\\n[Email Sending Failed: {{str(e)}}]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = f'Email Sending Failed: {{str(e)}}'")
    lines.append(f"{indent}last_result = res_text_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)


@node_registry.register('kakaoNode')
def generate_kakao_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Kakao Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    access_token = node.get('data', {}).get('accessToken', '').replace('"', '\\"')
    receiver = node.get('data', {}).get('receiver', '').replace('"', '\\"')
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import json")
    lines.append(f"{indent}kakao_token_{node_id} = \"{access_token}\"")
    lines.append(f"{indent}kakao_msg_{node_id} = str({prev_res_var if prev_res_var else 'last_result'})")
    lines.append(f"{indent}kakao_msg_{node_id} = kakao_msg_{node_id}[:190] + '...' if len(kakao_msg_{node_id}) > 190 else kakao_msg_{node_id}")
    lines.append(f"{indent}kakao_receiver_{node_id} = \"{receiver}\"")
    
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
    lines.append(f"{indent}            res_text_{node_id} = 'Kakao Send Success'")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            print(f'\\n[Kakao Send Failed: {{resp_{node_id}.text}}]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = f'Kakao Send Failed: {{resp_{node_id}.text}}'")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Kakao Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = f'Kakao Error: {{str(e)}}'")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Kakao Skipped: No Access Token provided]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = 'Kakao Skipped: No Access Token'")
    
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('discordNode')
def generate_discord_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Discord Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    webhook_url = node.get('data', {}).get('webhookUrl', '').replace('"', '\\"')
    message = node.get('data', {}).get('message', '').replace('"', '\\"').replace('\n', '\\n')
    
    lines.append(f"{indent}import requests")
    lines.append(f"{indent}import json")
    lines.append(f"{indent}discord_webhook_{node_id} = \"{webhook_url}\"")
    lines.append(f"{indent}discord_msg_{node_id} = \"{message}\" if \"{message}\" else str({prev_res_var if prev_res_var else 'last_result'})")
    lines.append(f"{indent}if discord_webhook_{node_id}:")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        payload_{node_id} = {{'content': discord_msg_{node_id}}}")
    lines.append(f"{indent}        resp_{node_id} = requests.post(discord_webhook_{node_id}, json=payload_{node_id}, timeout=10)")
    lines.append(f"{indent}        if resp_{node_id}.status_code in [200, 204]:")
    lines.append(f"{indent}            print(f'\\n[Discord Webhook Success]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = 'Discord Send Success'")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            print(f'\\n[Discord Webhook Failed: {{resp_{node_id}.status_code}}]\\n')")
    lines.append(f"{indent}            res_text_{node_id} = f'Discord Send Failed: {{resp_{node_id}.status_code}}'")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        print(f'\\n[Discord Webhook Error: {{str(e)}}]\\n')")
    lines.append(f"{indent}        res_text_{node_id} = f'Discord Send Error: {{str(e)}}'")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    print(f'\\n[Discord Webhook Skipped: No URL provided]\\n')")
    lines.append(f"{indent}    res_text_{node_id} = 'Discord Webhook Skipped'")
    
    lines.append(f"{indent}last_result = res_text_{node_id}")
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register("slackNode")
def generate_slack_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    channel = node.get('data', {}).get('channel', '#general')
    message = node.get('data', {}).get('message', 'Hello from Visual Task Automation!')
    
    # Use repr to safely escape newlines and quotes in the generated python code
    safe_channel = repr(channel)
    safe_message_base = repr(message)
    
    lines.append(f"{indent}# --- Slack Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}slack_channel_{node_id} = {safe_channel}")
    
    if prev_res_var:
        # Strip the trailing quote, append newlines, then close the quote + append variable
        safe_message = safe_message_base[:-1] + "\\n\\n\" + str(" + prev_res_var + ")"
        lines.append(f"{indent}slack_msg_{node_id} = {safe_message}")
    else:
        lines.append(f"{indent}slack_msg_{node_id} = {safe_message_base}")
        
    lines.append(f"{indent}print(f'Mocking Slack send to {{slack_channel_{node_id}}}: {{slack_msg_{node_id}}}')")
    lines.append(f"{indent}last_result = f'Sent message to Slack channel {{slack_channel_{node_id}}}'")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    if not next_edges:
        lines.append(f"{indent}return last_result")
    else:
        for target_id, handle in next_edges:
            generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"last_result", visited=visited)

@node_registry.register('tossNode')
def generate_toss_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Toss Payments Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    secret_key = node.get('data', {}).get('secretKey', '').replace('"', '\\"')
    search_type = node.get('data', {}).get('searchType', 'paymentKey')
    search_value = node.get('data', {}).get('searchValue', '').replace('"', '\\"')
    
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
