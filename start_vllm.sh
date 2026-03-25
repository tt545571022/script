export CUDA_VISIBLE_DEVICES=6,7

MODEL_PATH=/home/tjl/pard/hf_Sehyo-Qwen3.5-122B-A10B-NVFP4
SERVER_NAME=hf_Sehyo-Qwen3.5-122B-A10B-NVFP4

# MODEL_PATH="/nfs_data/weight/Qwen3-8B"
# SERVER_NAME="Qwen3-8B"
# SPEC_MODEL_PATH="/nfs_data/weight/amd_PARD-Qwen3-0.6B"
PORT=5678

# ==============================================================================
# 命令行参数解析 (Parse Command Line Arguments)
# ==============================================================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model_path)   MODEL_PATH="$2"; shift 2 ;;
        -s|--server-name)  SERVER_NAME="$2"; shift 2 ;;
        -p|--port)         PORT="$2"; shift 2 ;;
        -*) echo "Unknown parameter passed: $1"
            echo "Usage: $0 [-m|--model_path <path>] [-s|--server-name <name>] [-p|--port <port>]"
            echo "  -m, --model_path    模型权重路径 (默认: $MODEL_PATH)"
            echo "  -s, --server-name   vllm served-model-name (默认: $SERVER_NAME)"
            echo "  -p, --port          服务端口号 (默认: $PORT)"
            exit 1 ;;
        *) shift ;;
    esac
done

# export FLASHPREFILL_ENABLED=1 \
# export FLASHPREFILL_ALPHA=0.08 \


vllm serve $MODEL_PATH \
    --served-model-name $SERVER_NAME \
    --host 0.0.0.0 \
    --port $PORT \
    --seed 42 \
    -tp 2 \
    --gpu_memory_utilization 0.9 \
    --speculative_config '{"method":"mtp", "num_speculative_tokens":1}'
    --kv-cache-dtype "fp8" \


    # --kv_offloading_backend native --kv_offloading_size 20 \
    # --max_model_len 262144 \
    # --max-num-batched-tokens 32768 \
    # --speculative_config "{\"model\": \"$SPEC_MODEL_PATH\", \"num_speculative_tokens\": 12, \"method\": \"draft_model\", \"parallel_drafting\": true}"