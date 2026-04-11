#!/bin/bash

# export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-5,6}"  # 若环境变量已存在则保留原值，否则使用默认值

# ==============================================================================
# 默认参数配置 (Default Configuration)，通过输入参数传递时，会覆盖这些默认值
# ==============================================================================

MODEL_PATH=/data2/weights/Qwen3-8B/
SERVER_NAME=Qwen3-8B
PORT=5678
SERVER_ARGS=""

usage() {
    echo "Usage: $0 [options]"
    echo "  -m, --model-path <path>    模型权重路径 (默认: $MODEL_PATH)"
    echo "  -s, --server-name <name>   vllm served-model-name (默认: $SERVER_NAME)"
    echo "  -p, --port <port>          服务端口号 (默认: $PORT)"
    echo "      --server-args <args>   追加到 vllm serve 末尾的额外参数"
}

parse_extra_args() {
    EXTRA_ARGS=()
    if [[ -n "$1" ]]; then
        eval "EXTRA_ARGS=($1)"
    fi
}

# ==============================================================================
# 命令行参数解析 (Parse Command Line Arguments)
# ==============================================================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model-path|--model_path) MODEL_PATH="$2"; shift 2 ;;
        -s|--server-name) SERVER_NAME="$2"; shift 2 ;;
        -p|--port) PORT="$2"; shift 2 ;;
        --server-args) SERVER_ARGS="$2"; shift 2 ;;
        -h|--help)
            usage
            exit 0 ;;
        -*)
            echo "Unknown parameter passed: $1"
            usage
            exit 1 ;;
        *) shift ;;
    esac
done


# export FLASHPREFILL_ENABLED=1 \
# export FLASHPREFILL_ALPHA=0.08 \

parse_extra_args "$SERVER_ARGS"

# 其他可选参数示例：
# --additional-config='{"ascend_compilation_config":{"fuse_qknorm_rope":false}}'
# --quantization "ascend"
# --speculative_config '{"method":"mtp", "num_speculative_tokens":1}'
# --kv-cache-dtype "fp8"
# --limit-mm-per-prompt '{"image":3, "video":1}'
# --kv_offloading_backend native --kv_offloading_size 20
# --max-num-batched-tokens 32768
# --speculative_config "{\"model\": \"$SPEC_MODEL_PATH\", \"num_speculative_tokens\": 12, \"method\": \"draft_model\", \"parallel_drafting\": true}"

cmd=(
    vllm serve "$MODEL_PATH"
    --served-model-name "$SERVER_NAME"
    --host 0.0.0.0
    --port "$PORT"
    --seed 42
    -tp 8
    --gpu_memory_utilization 0.95
    --max-cudagraph-capture-size 8
    --max_model_len 20000
    --load-format dummy
    --hf-overrides '{"index_topk_freq": 4}'
)

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    cmd+=("${EXTRA_ARGS[@]}")
fi

"${cmd[@]}"