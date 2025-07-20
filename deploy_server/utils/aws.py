from utils.common import (
    AWS_REGION,
    CLUSTER_NAME,
    get_config_value,
    load_terraform_outputs,
)
from fastapi import HTTPException
from loguru import logger
import boto3

def register_task_definition(ecs, app_name, req, ecr_url, gradio_root_path, log_group_name, execution_role_arn, task_role_arn):
    logger.info(f"Registering task definition with CPU: {req.cpu}, Memory: {req.memory}")
    ecs.register_task_definition(
        family=app_name,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu=req.cpu,
        memory=req.memory,
        executionRoleArn=execution_role_arn,
        taskRoleArn=task_role_arn,
        containerDefinitions=[
            {
                "name": app_name,
                "image": f"{ecr_url}:latest",
                "portMappings": [
                    {
                        "containerPort": 7860,
                        "protocol": "tcp"
                    }
                ],
                "essential": True,
                "environment": [
                    {"name": "GRADIO_SERVER_NAME", "value": "0.0.0.0"},
                    {"name": "GRADIO_SERVER_PORT", "value": "7860"},
                    {"name": "GRADIO_ROOT_PATH", "value": gradio_root_path}
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": log_group_name,
                        "awslogs-region": AWS_REGION,
                        "awslogs-stream-prefix": "ecs"
                    }
                }
            }
        ]
    )

def update_ecs_service(ecs, app_name, task_definition_family):
    logger.info(f"Updating existing ECS service: {app_name}")
    try:
        ecs.update_service(
            cluster=CLUSTER_NAME,
            service=app_name,
            taskDefinition=task_definition_family,
            enableExecuteCommand=True, 
            forceNewDeployment=True
        )
        logger.info(f"Successfully updated service: {app_name}")
        return "update"
    except Exception as update_e:
        logger.error(f"Failed to update service: {update_e}")
        raise HTTPException(status_code=500, detail=f"Service update failed: {update_e}")

def delete_ecs_service(ecs, app_name):
    logger.info(f"Force recreate requested - deleting existing service")
    try:
        ecs.delete_service(cluster=CLUSTER_NAME, service=app_name, force=True)
        logger.info(f"Deleted existing service for recreation")
        return True
    except Exception as del_e:
        logger.warning(f"Failed to delete service: {del_e}")
        return False

def create_ecs_service(ecs, app_name, task_definition_family, tg_arn, subnets, security_groups):
    logger.info(f"Creating new ECS service: {app_name}")
    
    # プライベートサブネットを使用しているかチェック
    tf_outputs = load_terraform_outputs()
    private_subnet_ids = tf_outputs.get("private_subnet_ids", [])
    
    # サブネットがプライベートサブネットの場合は assignPublicIp を DISABLED に
    is_using_private_subnets = any(subnet in private_subnet_ids for subnet in subnets)
    assign_public_ip = "DISABLED" if is_using_private_subnets else "ENABLED"
    
    logger.info(f"Using subnets: {subnets}")
    logger.info(f"Private subnets available: {private_subnet_ids}")
    logger.info(f"Using private subnets: {is_using_private_subnets}")
    logger.info(f"Assign public IP: {assign_public_ip}")
    
    try:
        ecs.create_service(
            cluster=CLUSTER_NAME,
            serviceName=app_name,
            taskDefinition=task_definition_family,
            enableExecuteCommand=True,
            loadBalancers=[{
                "targetGroupArn": tg_arn,
                "containerName": app_name,
                "containerPort": 7860
            }],
            desiredCount=1,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": subnets,
                    "securityGroups": security_groups,
                    "assignPublicIp": assign_public_ip
                }
            },
            healthCheckGracePeriodSeconds=300
        )
        logger.info(f"Successfully created service: {app_name}")
        return "create"
    except Exception as create_e:
        logger.error(f"Failed to create service: {create_e}")
        raise HTTPException(status_code=500, detail=f"Service creation failed: {create_e}")