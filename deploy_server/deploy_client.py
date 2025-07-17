#!/usr/bin/env python3
"""
deploy_client.py – 汎用デプロイリクエスト送り込みスクリプト
例:
uv run python deploy_client.py --app app2 --path "/app2*" \
      --git http://192.168.0.131:3000/Sunwood-ai-labs/gradio-ff-demo-001.git --cpu 512 --mem 1024
"""

import argparse, json, requests, sys

API_URL = "http://localhost:8001/deploy"

def main():
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--app",    required=True,  help="アプリ名 (ECS Service 名と同じ)")
    p.add_argument("--path",   required=True,  help='ALB パスパターン 例 "/myapp/*" or "/*"')
    p.add_argument("--git",    default=None,   help="Git リポジトリ URL (省略可)")
    p.add_argument("--cpu",    default="512",  help="タスク CPU (1024=1vCPU)")
    p.add_argument("--mem",    default="1024", help="タスク Memory (MiB)")
    p.add_argument("--force",  action="store_true", help="既存サービスを強制再作成")
    args = p.parse_args()

    payload = {
        "app_name":  args.app,
        "alb_path":  args.path,
        "git_repo_url": args.git,
        "cpu": args.cpu,
        "memory": args.mem,
        "force_recreate": args.force
    }

    print("🚀 Deploying …")
    print(json.dumps(payload, indent=2))
    print("-"*60)

    resp = requests.post(API_URL, json=payload)
    print(f"Status: {resp.status_code}")
    print("-"*60)

    try:
        data = resp.json()
    except json.JSONDecodeError:
        sys.exit(resp.text)

    print(json.dumps(data, indent=2))

    if resp.ok and data.get("status") == "success":
        print("\n✅ SUCCESS")
        print(f"URL: {data.get('deployed_url')}")
    else:
        print("\n❌ FAILED")

if __name__ == "__main__":
    main()
