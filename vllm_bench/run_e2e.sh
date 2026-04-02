set -e
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export VISIBLE_DEVICES=${VISIBLE_DEVICES:-14,15}

USAGE_THRESHOLD=${USAGE_THRESHOLD:-20}

MODEL_PATH=${1:-"/data2/weights/Qwen_Qwen3-VL-8B-Instruct/"}
SERVER_NAME=${2:-"Qwen_Qwen3-VL-8B-Instruct"}
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
    stop_vllm_processes 3
    if ps aux | grep -iE "vllm serve|VLLM" | grep -qvE "grep|defunct"; then
        echo "⚠ 仍有 vllm 进程在运行"
    else
        echo "✓ 服务已停止"
    fi
    echo ""
}

stop_vllm_processes() {
    pkill -f -9 "VLLM|vllm" 2>/dev/null || true
    sleep "${1:-2}"
}

init_device_env() {
    if command -v npu-smi >/dev/null 2>&1 && ! command -v nvidia-smi >/dev/null 2>&1; then
        export ASCEND_RT_VISIBLE_DEVICES="$VISIBLE_DEVICES"
        DEVICE_TYPE=npu
        echo "检测到 NPU 环境，使用设备: ${ASCEND_RT_VISIBLE_DEVICES}"
        return 0
    fi

    if command -v nvidia-smi >/dev/null 2>&1 && ! command -v npu-smi >/dev/null 2>&1; then
        export CUDA_VISIBLE_DEVICES="$VISIBLE_DEVICES"
        DEVICE_TYPE=gpu
        echo "检测到 GPU 环境，使用设备: ${CUDA_VISIBLE_DEVICES}"
        return 0
    fi

    echo "无法自动判断当前设备类型" >&2
    exit 1
}

check_and_clear_gpu() {
    echo "检查 GPU 状态并清理..."
    local gpu_args=()
    [ -n "$CUDA_VISIBLE_DEVICES" ] && gpu_args=("-i" "$CUDA_VISIBLE_DEVICES")
    local start_time=$(date +%s)

    while true; do
        stop_vllm_processes

        local busy_info="" all_free=true
        while IFS=',' read -r g_idx g_total g_used; do
            g_idx=${g_idx// /}; g_total=${g_total// /}; g_used=${g_used// /}
            local used_mb=${g_used:-0}
            local usage_pct=$(( g_total > 0 ? used_mb * 100 / g_total : 0 ))
            if [ -n "$g_used" ] && [ "$usage_pct" -gt "$USAGE_THRESHOLD" ]; then
                busy_info+=" [GPU ${g_idx}: ${used_mb}/${g_total}MB]"
                all_free=false
            fi
        done < <(nvidia-smi --query-gpu=index,memory.total,memory.used --format=csv,noheader,nounits "${gpu_args[@]}")

        if $all_free; then break; fi

        local elapsed=$(( $(date +%s) - start_time ))
        echo -ne "\r\033[K⚠ 等待 GPU 内存释放 (已等待 ${elapsed}s):${busy_info} ..."
    done

    echo ""
    nvidia-smi --query-gpu=index,memory.total,memory.used --format=csv,noheader,nounits "${gpu_args[@]}" | \
        awk -F',' '{used=$3; pct=($2>0?used*100/$2:0); printf "  GPU %-3s: %5d / %5d MB used (%2d%%)\n", $1, used, $2, pct}'
    echo "✓ 所有指定 GPU 内存已全部就绪"
}

get_npu_hbm_usage() {
    npu-smi info 2>/dev/null | awk -v visible="${ASCEND_RT_VISIBLE_DEVICES:-}" '
        function t(x){gsub(/^[[:space:]]+|[[:space:]]+$/, "", x); return x}
        BEGIN{
            all=t(visible)==""
            if(!all){split(visible,a,/,/); for(i in a){a[i]=t(a[i]); if(a[i]!="") want[a[i]]=1}}
        }
        /Phy-ID/{phy=1}
        /^\|/ {
            n=split($0,r,/\|/); m=0; delete f
            for(i=1;i<=n;i++){x=t(r[i]); if(x!="") f[++m]=x}
            if(m<2 || f[1] ~ /^(NPU[[:space:]]+Name|Chip([[:space:]]+Phy-ID)?|NPU[[:space:]]+Chip)$/) next
            if(f[2] !~ /^[[:xdigit:]][[:xdigit:]][[:xdigit:]][[:xdigit:]]:[[:xdigit:]][[:xdigit:]]:[[:xdigit:]][[:xdigit:]]\.[[:xdigit:]]$/){split(f[1],a,/ +/); cur=a[1]; next}
            id=cur; if(phy){split(f[1],a,/ +/); id=a[2]}
            if(id=="" || (!all && !(id in want)) || !match(f[m], /[0-9]+[[:space:]]*\/[[:space:]]*[0-9]+[[:space:]]*$/)) next
            split(substr(f[m], RSTART, RLENGTH), a, "/")
            u=t(a[1]); z=t(a[2]); gsub(/[^0-9]/, "", u); gsub(/[^0-9]/, "", z)
            printf "%s\t%s\t%s\t%.0f\n", id, u, z, (z > 0 ? u * 100 / z : 0)
        }
    '
}

check_and_clear_npu() {
    echo "检查 NPU 状态并清理..."

    if ! command -v npu-smi >/dev/null 2>&1; then
        echo "✗ 未找到 npu-smi，无法检查 NPU 状态"
        exit 1
    fi

    local start_time=$(date +%s)

    while true; do
        stop_vllm_processes

        local parsed_usage
        parsed_usage=$(get_npu_hbm_usage)

        if [ -z "$parsed_usage" ]; then
            echo "✗ 无法从 npu-smi info 中解析出目标 NPU 的 HBM 使用信息"
            exit 1
        fi

        local busy_info="" all_free=true
        while IFS=$'\t' read -r device_id used_mb total_mb usage_pct; do
            [ -z "$device_id" ] && continue
            if [ "$usage_pct" -gt "$USAGE_THRESHOLD" ]; then
                busy_info+=" [NPU ${device_id}: ${used_mb}/${total_mb}MB]"
                all_free=false
            fi
        done <<< "$parsed_usage"

        if $all_free; then
            echo ""
            while IFS=$'\t' read -r device_id used_mb total_mb usage_pct; do
                [ -z "$device_id" ] && continue
                printf "  NPU %-3s: %5s / %5s MB used (%2s%%)\n" "$device_id" "$used_mb" "$total_mb" "$usage_pct"
            done <<< "$parsed_usage"
            echo "✓ 所有指定 NPU HBM 已全部就绪"
            return 0
        fi

        local elapsed=$(( $(date +%s) - start_time ))
        echo -ne "\r\033[K⚠ 等待 NPU HBM 释放 (已等待 ${elapsed}s):${busy_info} ..."
    done
}

check_and_clear_device() {
    case "$DEVICE_TYPE" in
        gpu) check_and_clear_gpu ;;
        npu) check_and_clear_npu ;;
    esac
}

# ── 初始化日志文件 ──────────────────────────────────────
init_device_env

mkdir -p "$RESULT_PATH"
echo server log: "$SERVER_LOG"
echo client log: "$CLIENT_LOG"
echo "" > "$SERVER_LOG"
echo "" > "$CLIENT_LOG"
check_and_clear_device

bash start_vllm.sh -m "$MODEL_PATH" -s "$SERVER_NAME" -p "$PORT" > "$SERVER_LOG" 2>&1 &
wait_for_startup "Stage-1" "$SERVER_LOG"

bash run_bench_hci.sh -m "$MODEL_PATH" -s "$SERVER_NAME" -p "$PORT" -o "$RESULT_PATH" -t "$TAG" > "$CLIENT_LOG" 2>&1

stop_server
