set -e
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=4,5
MODEL_PATH=${1:-"/nfs_data/weight/hf_Sehyo-Qwen3.5-122B-A10B-NVFP4"}
SERVER_NAME=${2:-"hf_Sehyo-Qwen3.5-122B-A10B-NVFP4"}
PORT=${3:-5678}
TAG=${4:-"src"}

RESULT_PATH="./results/${SERVER_NAME}_${TAG}_$(date +%Y%m%d_%H%M%S)"
SERVER_LOG="$RESULT_PATH/server_${TAG}.log"
CLIENT_LOG="$RESULT_PATH/client_${TAG}.log"



# ── 工具函数 ────────────────────────────────────────────
# wait_for_health <retries> [interval_sec]
wait_for_health() {
    local retries="${1:-30}"
    local interval="${2:-3}"
    local _i http_code
    for _i in $(seq 1 "$retries"); do
        echo -ne "\r尝试 $_i/${retries} - 检查 服务器健康状态..."
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 \
                    "http://localhost:${PORT}/health" 2>/dev/null) || http_code="000"
        if [ "$http_code" = "200" ]; then
            echo "✓ 服务器健康检查通过, http_code: ${http_code}"
            return 0
        fi
        sleep "$interval"
    done
    echo "✗ 服务器健康检查失败（重试 ${retries} 次仍无响应，最后状态码: ${http_code}）"
    exit 1
}

# wait_for_startup <stage_label> <log_file> [max_wait_sec] [log_offset]
wait_for_startup() {
    local stage_label="$1"
    local log_file="$2"
    local max_wait="${3:-3000}"
    local log_offset="${4:-0}"
    local waited=0
    echo "等待 ${stage_label} 服务器启动..."
    while [ $waited -lt $max_wait ]; do
        if tail -n +"$((log_offset + 1))" "$log_file" 2>/dev/null | grep -q "Application startup complete."; then
            echo "✓ ${stage_label} 服务器启动完成 (用时 ${waited}s)"
            wait_for_health
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
        echo -ne "\r  等待中... (${waited}s)"
    done
    echo "✗ ${stage_label} 服务器启动超时"
    tail -30 "$log_file"
    exit 1
}

stop_server() {
    pkill -f -9 "VLLM|vllm" 2>/dev/null || true
    sleep 3
    if ps aux | grep -iE "vllm serve|VLLM" | grep -qvE "grep|defunct"; then
        echo "⚠ 仍有 vllm 进程在运行"
    else
        echo "✓ 服务已停止"
    fi
    echo ""
}

check_and_clear_gpu() {
    echo "检查 GPU 状态并清理..."
    local mem_threshold=20000
    local gpu_args=()
    [ -n "$CUDA_VISIBLE_DEVICES" ] && gpu_args=("-i" "$CUDA_VISIBLE_DEVICES")

    local start_time=$(date +%s)
    
    while true; do
        pkill -f -9 "VLLM|vllm" 2>/dev/null || true
        sleep 2

        local busy_info=""
        local all_free=true

        # 一次性并行查询所有指定的 GPU 内存状态
        while IFS=',' read -r g_idx g_mem; do
            g_idx=$(echo "$g_idx" | tr -d ' ')
            g_mem=$(echo "$g_mem" | tr -d ' ')
            if [ -n "$g_mem" ] && [ "$g_mem" -lt "$mem_threshold" ]; then
                busy_info="${busy_info} [GPU${g_idx}: ${g_mem} MB]"
                all_free=false
            fi
        done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits "${gpu_args[@]}")
        
        if $all_free; then
            break
        fi
        
        # 在同一行刷新输出，防止刷屏，并显示等待时间
        local elapsed=$(( $(date +%s) - start_time ))
        echo -ne "\r\033[K⚠ 等待 GPU 内存释放 (已等待 ${elapsed}s):${busy_info} ..."
    done
    
    # 打印最终状态：两行显示（一行 Device ID，一行 Free Memory）
    local ids="Device ID   : "
    local mems="Free Memory : "
    while IFS=',' read -r g_idx g_mem; do
        g_idx=$(echo "$g_idx" | tr -d ' ')
        g_mem=$(echo "$g_mem" | tr -d ' ')
        ids="${ids}$(printf '%-12s' "${g_idx}")"
        mems="${mems}$(printf '%-12s' "${g_mem}MB")"
    done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits "${gpu_args[@]}")
    
    echo -e "${ids}\n${mems}"
    echo "✓ 所有指定 GPU 内存已全部就绪"
}

# ── 初始化日志文件 ──────────────────────────────────────
mkdir -p "$RESULT_PATH"
echo server log: "$SERVER_LOG"
echo client log: "$CLIENT_LOG"
echo "" > "$SERVER_LOG"
echo "" > "$CLIENT_LOG"

check_and_clear_gpu

bash start_vllm.sh -m "$MODEL_PATH" -s "$SERVER_NAME" -p "$PORT" > "$SERVER_LOG" 2>&1 &
wait_for_startup "Stage-1" "$SERVER_LOG"

bash run_bench_hci.sh -m "$MODEL_PATH" -s "$SERVER_NAME" -p "$PORT" -o "$RESULT_PATH" > "$CLIENT_LOG" 2>&1

stop_server
