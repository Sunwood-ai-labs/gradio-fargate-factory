#!/bin/bash

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
    local width=50
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
    echo -e "${PURPLE}║${WHITE}                    🚀 ECS DESTROYER 3000 🚀                   ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${CYAN}                  Complete ECS Cleanup Tool                  ${PURPLE}║${NC}"
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

# ECS完全削除スクリプト
REGION="ap-northeast-1"
CLUSTER_NAME="gradio-ecs-cluster"

clear
print_header

echo -e "${WHITE}クラスター: ${YELLOW}$CLUSTER_NAME${NC}"
echo -e "${WHITE}リージョン: ${YELLOW}$REGION${NC}"
echo -e "${WHITE}開始時刻: ${YELLOW}$(date)${NC}"
echo ""

# カウントダウン
echo -e "${RED}${BOLD}⚠️  危険な操作です！ 3秒後に開始します... ⚠️${NC}"
for i in 3 2 1; do
    echo -e "${RED}${BOLD}$i...${NC}"
    sleep 1
done
echo -e "${GREEN}${BOLD}🚀 開始！${NC}"
echo ""

total_steps=7
current_step=0

# 1. すべてのECSサービスを確認・削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 1: ECSサービス削除"

print_executing "ECSサービスを検索中..."
SERVICES=$(aws ecs list-services --cluster $CLUSTER_NAME --region $REGION --query 'serviceArns[*]' --output text 2>/dev/null)

if [ -n "$SERVICES" ] && [ "$SERVICES" != "None" ]; then
    service_count=$(echo $SERVICES | wc -w)
    echo -e "${CYAN}📋 発見されたサービス数: ${YELLOW}$service_count${NC}"
    
    service_num=0
    for service_arn in $SERVICES; do
        SERVICE_NAME=$(basename $service_arn)
        service_num=$((service_num + 1))
        echo -e "${WHITE}  [$service_num/$service_count] ${CYAN}$SERVICE_NAME${NC}"
        
        # サービスの詳細取得
        DESIRED_COUNT=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query 'services[0].desiredCount' --output text)
        echo -e "    ${GRAY}現在のdesiredCount: ${YELLOW}$DESIRED_COUNT${NC}"
        
        # サービスを0にスケールダウン
        if [ "$DESIRED_COUNT" != "0" ]; then
            print_executing "    スケールダウン中..."
            aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --desired-count 0 --region $REGION >/dev/null 2>&1
            
            # スケールダウン完了を待機
            print_executing "    安定化を待機中..."
            aws ecs wait services-stable --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION &
            spinner $!
        fi
        
        # サービス削除
        print_executing "    サービス削除中..."
        aws ecs delete-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --region $REGION >/dev/null 2>&1
        print_success "    サービス削除完了: $SERVICE_NAME"
    done
else
    print_info "アクティブなサービスはありません"
fi

echo ""

# 2. すべてのタスク定義を確認・削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 2: タスク定義削除"

print_executing "タスク定義を検索中..."
TASK_DEFINITIONS=$(aws ecs list-task-definitions --region $REGION --status ACTIVE --query 'taskDefinitionArns[*]' --output text 2>/dev/null)

if [ -n "$TASK_DEFINITIONS" ] && [ "$TASK_DEFINITIONS" != "None" ]; then
    td_count=$(echo $TASK_DEFINITIONS | wc -w)
    echo -e "${CYAN}📋 発見されたタスク定義数: ${YELLOW}$td_count${NC}"
    
    td_num=0
    for td_arn in $TASK_DEFINITIONS; do
        TD_NAME=$(echo $td_arn | cut -d'/' -f2)
        td_num=$((td_num + 1))
        echo -e "${WHITE}  [$td_num/$td_count] ${CYAN}$TD_NAME${NC}"
        
        # タスク定義を非アクティブ化
        print_executing "    非アクティブ化中..."
        aws ecs deregister-task-definition --task-definition $td_arn --region $REGION >/dev/null 2>&1
        print_success "    非アクティブ化完了: $TD_NAME"
    done
else
    print_info "アクティブなタスク定義はありません"
fi

echo ""

# 3. 実行中のタスクを強制停止
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 3: 実行中タスク停止"

print_executing "実行中タスクを検索中..."
RUNNING_TASKS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $REGION --query 'taskArns[*]' --output text 2>/dev/null)

if [ -n "$RUNNING_TASKS" ] && [ "$RUNNING_TASKS" != "None" ]; then
    task_count=$(echo $RUNNING_TASKS | wc -w)
    echo -e "${CYAN}📋 実行中のタスク数: ${YELLOW}$task_count${NC}"
    
    task_num=0
    for task_arn in $RUNNING_TASKS; do
        TASK_ID=$(basename $task_arn)
        task_num=$((task_num + 1))
        echo -e "${WHITE}  [$task_num/$task_count] ${CYAN}$TASK_ID${NC}"
        
        # タスク強制停止
        print_executing "    強制停止中..."
        aws ecs stop-task --cluster $CLUSTER_NAME --task $task_arn --reason "🔥 FORCE DELETION BY ECS DESTROYER 3000" --region $REGION >/dev/null 2>&1
        print_success "    停止完了: $TASK_ID"
    done
    
    # すべてのタスクが停止するまで待機
    print_executing "すべてのタスク停止を待機中..."
    sleep 10 &
    spinner $!
else
    print_info "実行中のタスクはありません"
fi

echo ""

# 4. 容量プロバイダーの確認・削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 4: 容量プロバイダー削除"

print_executing "容量プロバイダーを検索中..."
CAPACITY_PROVIDERS=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --region $REGION --query 'clusters[0].capacityProviders[*]' --output text 2>/dev/null)

if [ -n "$CAPACITY_PROVIDERS" ] && [ "$CAPACITY_PROVIDERS" != "None" ]; then
    echo -e "${CYAN}📋 発見された容量プロバイダー: ${YELLOW}$CAPACITY_PROVIDERS${NC}"
    print_executing "容量プロバイダー削除中..."
    aws ecs put-cluster-capacity-providers --cluster $CLUSTER_NAME --capacity-providers --region $REGION >/dev/null 2>&1
    print_success "容量プロバイダー削除完了"
else
    print_info "容量プロバイダーはありません"
fi

echo ""

# 5. ECSクラスター削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 5: ECSクラスター削除"

print_executing "クラスターステータス確認中..."
CLUSTER_STATUS=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --region $REGION --query 'clusters[0].status' --output text 2>/dev/null)

if [ "$CLUSTER_STATUS" == "ACTIVE" ]; then
    echo -e "${CYAN}📋 クラスターステータス: ${YELLOW}$CLUSTER_STATUS${NC}"
    print_executing "💥 ECSクラスター削除中..."
    
    # クラスター削除
    aws ecs delete-cluster --cluster $CLUSTER_NAME --region $REGION >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "ECSクラスター削除完了: $CLUSTER_NAME"
    else
        print_error "ECSクラスター削除に失敗しました"
        print_warning "手動で削除が必要な場合があります"
    fi
else
    print_info "クラスターは既に削除されているか存在しません"
fi

echo ""

# 6. 関連するCloudWatchロググループ削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 6: CloudWatchロググループ削除"

print_executing "ロググループを検索中..."
LOG_GROUPS=$(aws logs describe-log-groups --region $REGION --log-group-name-prefix "/ecs/" --query 'logGroups[*].logGroupName' --output text 2>/dev/null)

if [ -n "$LOG_GROUPS" ] && [ "$LOG_GROUPS" != "None" ]; then
    lg_count=$(echo $LOG_GROUPS | wc -w)
    echo -e "${CYAN}📋 発見されたロググループ数: ${YELLOW}$lg_count${NC}"
    
    lg_num=0
    for log_group in $LOG_GROUPS; do
        lg_num=$((lg_num + 1))
        echo -e "${WHITE}  [$lg_num/$lg_count] ${CYAN}$log_group${NC}"
        print_executing "    ロググループ削除中..."
        aws logs delete-log-group --log-group-name $log_group --region $REGION >/dev/null 2>&1
        print_success "    削除完了: $log_group"
    done
else
    print_info "関連するロググループはありません"
fi

echo ""

# 7. Terraformの状態からECS関連リソースを削除
current_step=$((current_step + 1))
progress_bar $current_step $total_steps
echo ""
print_section "Step 7: Terraform状態クリーンアップ"

if command -v terraform &> /dev/null; then
    print_executing "Terraform状態からECS関連削除中..."
    terraform state rm aws_ecs_cluster.main 2>/dev/null && print_success "aws_ecs_cluster.main 削除完了" || print_info "aws_ecs_cluster.main は状態にありません"
    terraform state rm aws_ecs_service.main 2>/dev/null && print_success "aws_ecs_service.main 削除完了" || print_info "aws_ecs_service.main は状態にありません"
    terraform state rm aws_ecs_task_definition.main 2>/dev/null && print_success "aws_ecs_task_definition.main 削除完了" || print_info "aws_ecs_task_definition.main は状態にありません"
else
    print_warning "Terraformが見つかりません"
fi

echo ""

# 完了メッセージ
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${WHITE}                    🎉 削除完了！ 🎉                          ${GREEN}║${NC}"
echo -e "${GREEN}║${CYAN}              ECS DESTROYER 3000 Mission Complete!           ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${WHITE}📊 ${BOLD}確認コマンド:${NC}"
echo -e "${CYAN}   aws ecs list-clusters --region $REGION${NC}"
echo -e "${CYAN}   aws ecs list-services --cluster $CLUSTER_NAME --region $REGION${NC}"
echo ""

echo -e "${WHITE}💡 ${BOLD}次のステップ:${NC}"
echo -e "${YELLOW}   1. terraform destroy でインフラを削除${NC}"
echo -e "${YELLOW}   2. または個別にリソースを削除${NC}"
echo ""

echo -e "${WHITE}完了時刻: ${YELLOW}$(date)${NC}"
echo -e "${GREEN}${BOLD}🚀 ECS環境が正常に更地になりました！ 🚀${NC}"