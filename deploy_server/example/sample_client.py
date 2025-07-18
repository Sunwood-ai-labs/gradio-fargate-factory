import requests
import json

API_URL = "http://localhost:8001/deploy"

payload = {
    "app_name": "myapp",
    "alb_path": "/myapp/*",
    "git_repo_url": "http://192.168.0.131:3000/Sunwood-ai-labs/gradio-ff-demo-001.git",
    # リソースを大幅に増強
    "cpu": "4096",  # メモリに合わせてCPUも少し増やすと良い
    "memory": "8192" # 4096 -> 8192 に増やす
}

print("🚀 Deploying application with enhanced resources...")
print(f"Request payload: {json.dumps(payload, indent=2)}")
print("-" * 60)

response = requests.post(API_URL, json=payload)

print(f"Status code: {response.status_code}")
print("-" * 60)

try:
    response_data = response.json()
    print("Response:")
    print(json.dumps(response_data, indent=2))
    
    # 成功時はURLを強調表示
    if response.status_code == 200 and response_data.get("status") == "success":
        print("\n" + "=" * 70)
        print("🎉 DEPLOYMENT SUCCESS!")
        print("=" * 70)
        print(f"🚀 Application URL: {response_data.get('deployed_url')}")
        print(f"📱 App Name: {response_data.get('app_name')}")
        print(f"🌐 ALB DNS: {response_data.get('alb_dns_name')}")
        print(f"📍 Path Pattern: {response_data.get('alb_path')}")
        print(f"🔒 Protocol: {response_data.get('protocol')}")
        print(f"💾 CPU: {response_data.get('cpu')}, Memory: {response_data.get('memory')}")
        print(f"⏱️  Estimated ready time: {response_data.get('estimated_ready_time')}")
        print("=" * 70)
        print("\n⚠️  IMPORTANT NOTES:")
        print("• Allow 5-10 minutes for the service to become healthy")
        print("• The app needs time to download dependencies and start")
        print("• Monitor CloudWatch logs for startup progress")
        print("• First request may take longer due to model loading")
        print("\n✨ Your application deployment is in progress!")
    else:
        print("\n❌ Deployment failed or returned non-success status")
        
except json.JSONDecodeError:
    print("Response (raw text):")
    print(response.text)
except Exception as e:
    print(f"Error parsing response: {e}")
    print("Response (raw text):")
    print(response.text)
