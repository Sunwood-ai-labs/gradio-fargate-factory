#!/bin/bash

# =================================================
# 🔧 ENV GENERATOR 3000 - Terraform to .env Converter
# =================================================

set -e

# カラーコード定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# アニメーション効果
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# プログレスバー
progress_bar() {
    local current=$1
    local total=$2
    local width=40
    local percentage=$((current * 100 / total))
    local filled=$((current * width / total))
    
    printf "\r${CYAN}["
    for ((i=0; i<filled; i++)); do printf "█"; done
    for ((i=filled; i<width; i++)); do printf "░"; done
    printf "] ${percentage}%%${NC}"
}

# ヘッダー表示
print_header() {
    echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${WHITE}                  🔧 ENV GENERATOR 3000 🔧                    ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${CYAN}              Terraform to .env Converter Tool              ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# セクションヘッダー
print_section() {
    echo -e "${BOLD}${BLUE}▶ $1${NC}"
    echo -e "${GRAY}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 成功メッセージ
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# エラーメッセージ
print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 警告メッセージ
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# 情報メッセージ
print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# 実行メッセージ
print_executing() {
    echo -e "${PURPLE}🔄 $1${NC}"
}

# Default paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_TERRAFORM_DIR="$PROJECT_ROOT/terraform/environments/existing-vpc"

# Usage function
usage() {
    print_header
    echo -e "${WHITE}${BOLD}📖 USAGE GUIDE${NC}"
    echo -e "${GRAY}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${CYAN}Usage:${NC} ${WHITE}$0 [OPTIONS]${NC}"
    echo ""
    echo -e "${YELLOW}📝 Description:${NC}"
    echo -e "  Generate ${CYAN}deploy_server/.env${NC} from Terraform outputs"
    echo ""
    echo -e "${YELLOW}⚙️  Options:${NC}"
    echo -e "  ${GREEN}-s, --tfstate PATH${NC}    Path to terraform.tfstate file"
    echo -e "  ${GREEN}-v, --tfvars PATH${NC}     Path to terraform.tfvars file"
    echo -e "  ${GREEN}-o, --output PATH${NC}     Output .env file path ${GRAY}(default: ../deploy_server/.env)${NC}"
    echo -e "  ${GREEN}-h, --help${NC}           Show this help message"
    echo ""
    echo -e "${YELLOW}💡 Examples:${NC}"
    echo -e "  ${CYAN}$0${NC}  ${GRAY}# Use default paths${NC}"
    echo -e "  ${CYAN}$0 -s /path/to/terraform.tfstate -v /path/to/terraform.tfvars${NC}"
    echo -e "  ${CYAN}$0 --tfstate /abs/path/tfstate --tfvars /abs/path/tfvars --output /abs/path/.env${NC}"
    echo ""
    exit 1
}

# Parse command line arguments
TFSTATE_FILE=""
TFVARS_FILE=""
ENV_FILE=""
CUSTOM_PATHS_USED=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--tfstate)
            TFSTATE_FILE="$2"
            CUSTOM_PATHS_USED=true
            shift 2
            ;;
        -v|--tfvars)
            TFVARS_FILE="$2"
            CUSTOM_PATHS_USED=true
            shift 2
            ;;
        -o|--output)
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Set default values if not provided
if [[ -z "$TFSTATE_FILE" ]]; then
    TFSTATE_FILE="$DEFAULT_TERRAFORM_DIR/terraform.tfstate"
fi

if [[ -z "$TFVARS_FILE" ]]; then
    TFVARS_FILE="$DEFAULT_TERRAFORM_DIR/terraform.tfvars"
fi

if [[ -z "$ENV_FILE" ]]; then
    ENV_FILE="$SCRIPT_DIR/../.env"
fi

# Convert to absolute paths
TFSTATE_FILE="$(realpath "$TFSTATE_FILE")"
TFVARS_FILE="$(realpath "$TFVARS_FILE")"
ENV_FILE="$(realpath "$ENV_FILE")"

clear
print_header

echo -e "${WHITE}📂 ${BOLD}Input Files:${NC}"
echo -e "${CYAN}  📄 Terraform State: ${YELLOW}$TFSTATE_FILE${NC}"
echo -e "${CYAN}  📄 Terraform Vars:  ${YELLOW}$TFVARS_FILE${NC}"
echo -e "${WHITE}📝 ${BOLD}Output File:${NC}"
echo -e "${CYAN}  📄 Environment:     ${YELLOW}$ENV_FILE${NC}"
echo -e "${WHITE}🕒 ${BOLD}Start Time:${NC} ${YELLOW}$(date)${NC}"
echo ""

total_steps=5
current_step=0

# Step 1: File validation
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 1: File Validation"

print_executing "Validating Terraform state file..."
if [[ ! -f "$TFSTATE_FILE" ]]; then
    print_error "terraform.tfstate not found at $TFSTATE_FILE"
    exit 1
fi
print_success "Terraform state file found"

print_executing "Validating Terraform variables file..."
if [[ ! -f "$TFVARS_FILE" ]]; then
    print_error "terraform.tfvars not found at $TFVARS_FILE"
    exit 1
fi
print_success "Terraform variables file found"

print_executing "Checking jq dependency..."
if ! command -v jq &> /dev/null; then
    print_error "jq is required but not installed. Please install jq."
    exit 1
fi
print_success "jq is available"

echo ""

# Step 2: Extract configuration values
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 2: Configuration Extraction"

print_executing "Extracting values from terraform.tfvars..."
PROJECT_NAME=$(grep '^project_name' "$TFVARS_FILE" | cut -d'"' -f2)
ENVIRONMENT=$(grep '^environment' "$TFVARS_FILE" | cut -d'"' -f2)
AWS_REGION=$(grep '^aws_region' "$TFVARS_FILE" | cut -d'"' -f2)

echo -e "  ${GREEN}📦 Project:     ${YELLOW}$PROJECT_NAME${NC}"
echo -e "  ${GREEN}🌍 Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo -e "  ${GREEN}🌏 Region:      ${YELLOW}$AWS_REGION${NC}"
print_success "Configuration values extracted"

echo ""

# Step 3: Extract Terraform outputs
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 3: Terraform Outputs Extraction"

print_executing "Extracting ECS outputs..."
ECS_CLUSTER_NAME=$(jq -r '.outputs.ecs_cluster_name.value' "$TFSTATE_FILE")
ECS_TASK_EXECUTION_ROLE_ARN=$(jq -r '.outputs.ecs_task_execution_role_arn.value' "$TFSTATE_FILE")
ECS_TASK_ROLE_ARN=$(jq -r '.outputs.ecs_task_role_arn.value' "$TFSTATE_FILE")
echo -e "  ${GREEN}🖥️  ECS Cluster:     ${YELLOW}$ECS_CLUSTER_NAME${NC}"
echo -e "  ${GREEN}🔐 Execution Role:  ${GRAY}$(basename $ECS_TASK_EXECUTION_ROLE_ARN)${NC}"

print_executing "Extracting network outputs..."
VPC_ID=$(jq -r '.outputs.vpc_id.value' "$TFSTATE_FILE")
PRIVATE_SUBNET_IDS=$(jq -r '.outputs.private_subnet_ids.value | join(",")' "$TFSTATE_FILE")
ECS_SECURITY_GROUP_ID=$(jq -r '.outputs.ecs_security_group_id.value' "$TFSTATE_FILE")
echo -e "  ${GREEN}🌐 VPC:             ${YELLOW}$VPC_ID${NC}"
echo -e "  ${GREEN}🔒 Security Group:  ${YELLOW}$ECS_SECURITY_GROUP_ID${NC}"

print_executing "Extracting ALB outputs..."
ALB_ARN=$(jq -r '.outputs.alb_arn.value' "$TFSTATE_FILE")
ALB_DNS_NAME=$(jq -r '.outputs.alb_dns_name.value' "$TFSTATE_FILE")
ALB_LISTENER_ARN=$(jq -r '.outputs.alb_listener_arn.value' "$TFSTATE_FILE")
ALB_SECURITY_GROUP_ID=$(jq -r '.outputs.alb_security_group_id.value' "$TFSTATE_FILE")
echo -e "  ${GREEN}⚖️  ALB DNS:         ${YELLOW}$ALB_DNS_NAME${NC}"
echo -e "  ${GREEN}🔒 ALB Security:    ${YELLOW}$ALB_SECURITY_GROUP_ID${NC}"

print_success "All Terraform outputs extracted successfully"

echo ""

# Step 4: Generate .env file
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 4: Environment File Generation"

print_executing "Creating backup of existing .env file..."
if [[ -f "$ENV_FILE" ]]; then
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    print_success "Backup created: $ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
else
    print_info "No existing .env file found"
fi

print_executing "Generating new .env file..."
sleep 1 &
spinner $!

# Generate .env file
cat > "$ENV_FILE" << EOF
# =================================================
# Gradio Fargate Factory - Deploy Server Configuration
# =================================================
# Generated automatically from Terraform outputs
# Project: $PROJECT_NAME ($ENVIRONMENT)
# Generated at: $(date)

# AWS Configuration
AWS_REGION=$AWS_REGION

# Terraform State File Path
EOF

# Conditionally add TERRAFORM_STATE_PATH based on whether custom paths were used
if [[ "$CUSTOM_PATHS_USED" == "true" ]]; then
    cat >> "$ENV_FILE" << EOF
# TERRAFORM_STATE_PATH=$TFSTATE_FILE  # Commented out because custom paths were specified
EOF
else
    cat >> "$ENV_FILE" << EOF
TERRAFORM_STATE_PATH=$TFSTATE_FILE
EOF
fi

cat >> "$ENV_FILE" << EOF

# Optional: Git Clone Configuration
CLONE_BASE_DIR=$PROJECT_ROOT/tmp

# =================================================
# ECS Configuration (from terraform outputs)
# =================================================
ECS_CLUSTER_NAME=$ECS_CLUSTER_NAME
ECS_TASK_EXECUTION_ROLE_ARN=$ECS_TASK_EXECUTION_ROLE_ARN
ECS_TASK_ROLE_ARN=$ECS_TASK_ROLE_ARN

# =================================================
# Network Configuration (from terraform outputs)
# =================================================
VPC_ID=$VPC_ID
SUBNETS=$PRIVATE_SUBNET_IDS
SECURITY_GROUPS=$ECS_SECURITY_GROUP_ID

# =================================================
# ALB Configuration (from terraform outputs)
# =================================================
ALB_ARN=$ALB_ARN
ALB_DNS_NAME=$ALB_DNS_NAME
ALB_LISTENER_ARN=$ALB_LISTENER_ARN

# =================================================
# Security Groups (from terraform outputs)
# =================================================
ALB_SECURITY_GROUP_ID=$ALB_SECURITY_GROUP_ID
ECS_SECURITY_GROUP_ID=$ECS_SECURITY_GROUP_ID
EOF

print_success ".env file generated successfully"

echo ""

# Step 5: Validation and summary
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 5: Validation & Summary"

print_executing "Validating generated .env file..."
if [[ -f "$ENV_FILE" && -s "$ENV_FILE" ]]; then
    print_success ".env file validation passed"
    ENV_SIZE=$(wc -l < "$ENV_FILE")
    echo -e "  ${GREEN}📊 File size: ${YELLOW}$ENV_SIZE lines${NC}"
else
    print_error ".env file validation failed"
    exit 1
fi

echo ""

# 完了メッセージ
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${WHITE}                  🎉 Generation Complete! 🎉                 ${GREEN}║${NC}"
echo -e "${GREEN}║${CYAN}              ENV GENERATOR 3000 Mission Complete!           ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${WHITE}📋 ${BOLD}Configuration Summary:${NC}"
echo -e "${CYAN}  📦 Project:     ${YELLOW}$PROJECT_NAME ${GRAY}($ENVIRONMENT)${NC}"
echo -e "${CYAN}  🌏 Region:      ${YELLOW}$AWS_REGION${NC}"
echo -e "${CYAN}  🖥️  ECS Cluster: ${YELLOW}$ECS_CLUSTER_NAME${NC}"
echo -e "${CYAN}  ⚖️  ALB DNS:     ${YELLOW}$ALB_DNS_NAME${NC}"
echo ""

echo -e "${WHITE}📁 ${BOLD}Generated Files:${NC}"
echo -e "${GREEN}  ✅ ${CYAN}$ENV_FILE${NC}"
echo ""

echo -e "${WHITE}🚀 ${BOLD}Next Steps:${NC}"
echo -e "${YELLOW}  1. ${CYAN}cd deploy_server && python main.py${NC}"
echo -e "${YELLOW}  2. ${CYAN}Check the configuration with: cat .env${NC}"
echo -e "${YELLOW}  3. ${CYAN}Deploy your Gradio applications!${NC}"
echo ""

echo -e "${WHITE}🕒 ${BOLD}Completed at:${NC} ${YELLOW}$(date)${NC}"
echo -e "${GREEN}${BOLD}🎯 Ready to deploy! Environment configured successfully! 🎯${NC}"