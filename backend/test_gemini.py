import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graph import run_workflow
from dotenv import load_dotenv
load_dotenv()

nodes = [
    {"id": "start", "type": "startNode", "data": {}},
    {"id": "llm1", "type": "llmNode", "data": {"model": "gemini-1.5-flash", "systemPrompt": "You are a helpful assistant."}},
    {"id": "prompt1", "type": "promptNode", "data": {"userPrompt": "Say 'hello world'"}}
]
edges = [
    {"source": "start", "target": "prompt1"},
    {"source": "llm1", "target": "prompt1"}
]

res, tokens, logs = run_workflow(nodes, edges)
print("RESULT:", res)
