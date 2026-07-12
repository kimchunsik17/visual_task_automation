import discord
import asyncio
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from graph import run_workflow

# Store active bots by project_id
_active_bots = {}

def start_discord_bot(project_id: int, token: str):
    """
    Start a discord bot for a given project.
    If a bot is already running for this project, stop it and restart it.
    """
    if project_id in _active_bots:
        old_client = _active_bots[project_id]
        asyncio.create_task(old_client.close())
    
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
                    return "Error: Project not found."
                
                nodes = project.graph_data.get('nodes', [])
                edges = project.graph_data.get('edges', [])
                return run_workflow(nodes, edges, default_input=content)
            except Exception as e:
                return f"Error executing workflow: {str(e)}"
            finally:
                db.close()
                
        result = await asyncio.to_thread(_run)
        
        # Handle empty or too long results
        if not result or result.strip() == "":
            result = "No output generated."
        elif len(result) > 1950:
            result = result[:1950] + "\n... (truncated)"
            
        await processing_msg.edit(content=result)
        
    _active_bots[project_id] = client
    
    async def run_client():
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
    Start all discord bots on server startup.
    """
    projects = db.query(models.Project).filter(models.Project.deploy_mode == "discord").all()
    for p in projects:
        token = p.graph_data.get("discord_bot_token")
        if token:
            print(f"Booting up Discord Bot for project {p.id}")
            start_discord_bot(p.id, token)
