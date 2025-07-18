from pydantic import BaseModel

class DeployRequest(BaseModel):
    app_name: str
    docker_context: str = "./"
    dockerfile: str = "Dockerfile"
    alb_path: str  # 例: "/image-filter/*"
    git_repo_url: str | None = None
    cpu: str = "2048"
    memory: str = "4096"
    force_recreate: bool = False