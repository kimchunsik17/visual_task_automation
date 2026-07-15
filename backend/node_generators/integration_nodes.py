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
    receiver = node.get('data', {}).get('receiver', '').replace('"', '\\"')
    lines.append(f"{indent}print(f'\\n[Kakao Msg to {receiver}]\\n{{last_result}}\\n')")
    
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=prev_res_var, visited=visited)


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
