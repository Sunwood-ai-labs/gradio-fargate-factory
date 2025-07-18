terraform {
  backend "s3" {
    # 事前にS3バケットを作成してください
    bucket = "sunwood-ai-labs-gff-state"
    key    = "gradio-ecs/base-infrastructure/terraform.tfstate"
    region = "ap-northeast-1"
  }
}