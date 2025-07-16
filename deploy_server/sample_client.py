import requests

API_URL = "http://localhost:8000/deploy"

payload = {
    "app_name": "myapp",
    "alb_path": "/myapp/*",
    "git_repo_url": "https://github.com/Sunwood-ai-labs/gr-coo-demo-001.git"
    # 必要に応じて "docker_context" や "dockerfile" も追加可能
}

response = requests.post(API_URL, json=payload)

print("Status code:", response.status_code)
try:
    print("Response:", response.json())
except Exception:
    print("Response (raw):", response.text)