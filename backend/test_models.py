import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("OPENAI_API_KEY not found in environment.")
else:
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get("https://api.openai.com/v1/models", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        models = sorted([m['id'] for m in data['data'] if 'gpt' in m['id'] or 'o1' in m['id'] or 'o3' in m['id'] or 'babbage' in m['id'] or 'dall-e' in m['id']])
        for m in models:
            print(m)
    else:
        print(f"Error: {resp.status_code} - {resp.text}")
