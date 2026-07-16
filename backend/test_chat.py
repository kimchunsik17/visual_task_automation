import requests

res = requests.post("http://localhost:8000/api/chat", json={
    "project_id": "1",
    "message": "매일 날씨 정보를 슬랙으로 알려줘",
    "graph_data": {"nodes": [], "edges": []}
})

print(res.status_code)
print(res.text)
