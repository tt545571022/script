#!/bin/bash

# ==============================================================================
# 默认参数配置 (Default Configuration)，通过输入参数传递时，会覆盖这些默认值
# ==============================================================================
MODEL_PATH=/data2/weights/Qwen3-8B/
SERVER_NAME=Qwen3-8B
PORT=5678
TAG="src"
OUTPUT_PATH="./results/${SERVER_NAME}_${TAG}_$(date +%Y%m%d_%H%M%S)"


random_range_ratio=0
random_range_ratio_percent=0

# ==============================================================================
# 定义测试参数数组 (Test Parameters Array)
# 格式: "request_rate max_concurrency num_prompts input_len output_len"
# ==============================================================================
params=(
    # "inf 8 8 128 128"         # just for test

    "inf 1 5 16384 8192"
    "inf 1 5 32768 512"
    "inf 1 5 131072 4096"

    "inf 4 20 16384 8192"
    "inf 4 20 32768 512"
    "inf 4 20 131072 4096"

    "inf 8 40 16384 8192"
    "inf 8 40 32768 512"
    "inf 8 40 131072 4096"

    "inf 16 80 16384 8192"
    "inf 16 80 32768 512"
    "inf 16 80 131072 4096"

    "inf 32 160 16384 8192"
    "inf 32 160 32768 512"
    "inf 32 160 131072 4096"

    "inf 64 320 16384 8192"
    "inf 64 320 32768 512"
    "inf 64 320 131072 4096"

    "inf 128 640 16384 8192"
    "inf 128 640 32768 512"
    "inf 128 640 131072 4096"

    "inf 256 1280 16384 8192"
    "inf 256 1280 32768 512"
    "inf 256 1280 131072 4096"
)

# ==============================================================================
# 命令行参数解析 (Parse Command Line Arguments)
# ==============================================================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model-path) MODEL_PATH="$2"; shift 2 ;;
        -s|--server-name) SERVER_NAME="$2"; shift 2 ;;
        -p|--port) PORT="$2"; shift 2 ;;
        -o|--output) OUTPUT_PATH="$2"; shift 2 ;;
        -t|--tag) TAG="$2"; shift 2 ;;
        -*) echo "Unknown parameter passed: $1"
            echo "Usage: $0 [-m|--model-path <path>] [-s|--server-name <name>] [-p|--port <port>] [-o|--output <path>] [-t|--tag <tag>]"
            echo "  -m, --model-path    模型权重路径 (默认: $MODEL_PATH)"
            echo "  -s, --server-name   vllm served-model-name (默认: $SERVER_NAME)"
            echo "  -p, --port          服务端口号 (默认: $PORT)"
            echo "  -o, --output        结果保存路径 (默认: $OUTPUT_PATH)"
            echo "  -t, --tag           标签 (默认: $TAG)"
            exit 1 ;;
        *) shift ;;  # 跳过位置参数
    esac
done

# ==============================================================================
# Helper Functions and Core Logic
# ==============================================================================
# 定义一个函数来安全地提取值
extract_value() {
    local result="$1"
    local pattern="$2"
    local value=$(echo "$result" | grep "$pattern" | awk '{print $NF}')
    if [ -z "$value" ]; then
        echo "Error: Value for pattern '$pattern' not found." >&2
        return
    fi
    echo "$value"
}

run_benchmark() {
    local request_rate=$1
    local max_concurrency=$2
    local num_prompts=$3
    local input_len=$4
    local output_len=$5

    local prefix_len=0

    # 计算 input 范围
    local input_start=$((prefix_len + input_len - input_len * random_range_ratio_percent / 100))
    local input_end=$((prefix_len + input_len + input_len * random_range_ratio_percent / 100))

    # 计算 output 范围
    local output_start=$((output_len - output_len * random_range_ratio_percent / 100))
    local output_end=$((output_len + output_len * random_range_ratio_percent / 100))

    local dataset_name="random"
    echo "测试参数：req_rate: $request_rate, max_concurrency: $max_concurrency, num_prompts: $num_prompts, input: $input_start-$input_end，output: $output_start-$output_end"

    result_json="prompts-$num_prompts-in-$input_len-out-$output_len-concur-$max_concurrency-$(date +%Y%m%d_%H%M%S).json"
    result_log="$OUTPUT_PATH/prompts-$num_prompts-in-$input_len-out-$output_len-concur-$max_concurrency-$(date +%Y%m%d_%H%M%S).log"  

    local benchmark_result=$(
            vllm bench serve \
            --backend vllm \
            --model $SERVER_NAME \
            --tokenizer $MODEL_PATH \
            --dataset-name $dataset_name \
            --random-input-len $input_len \
            --random-output-len $output_len \
            --random-prefix-len $prefix_len \
            --random-range-ratio $random_range_ratio \
            --request-rate $request_rate \
            --num-prompts $num_prompts \
            --base-url http://127.0.0.1:${PORT} \
            --endpoint /v1/completions \
            --save-result \
            --result-dir "$OUTPUT_PATH" \
            --result-filename ${result_json} \
            --max-concurrency "$max_concurrency" \
            --trust-remote-code \
            --seed $(date +%s) \
            --burstiness 100 \
            --ignore-eos \
            --ready-check-timeout-sec 0 \
            --percentile-metrics ttft,tpot,itl,e2el \
            --metric-percentiles "25,50,75,90,95,99" \
    )
    
    echo "$benchmark_result"  | tee ${result_log}
    
    # 提取所需的值
    local duration=$(extract_value "$benchmark_result" "Benchmark duration (s):")
    local failed_requests=$(extract_value "$benchmark_result" "Failed requests:")
    local request_throughput=$(extract_value "$benchmark_result" "Request throughput (req/s):")
    local output_token_throughput=$(extract_value "$benchmark_result" "Output token throughput (tok/s):")
    local total_token_throughput=$(extract_value "$benchmark_result" "Total token throughput (tok/s):")
    local mean_ttft=$(extract_value "$benchmark_result" "Mean TTFT (ms):")
    local p90_ttft=$(extract_value "$benchmark_result" "P90 TTFT (ms):")
    local p95_ttft=$(extract_value "$benchmark_result" "P95 TTFT (ms):")
    local p99_ttft=$(extract_value "$benchmark_result" "P99 TTFT (ms):")
    local mean_tpot=$(extract_value "$benchmark_result" "Mean TPOT (ms):")
    local p90_tpot=$(extract_value "$benchmark_result" "P90 TPOT (ms):")
    local p95_tpot=$(extract_value "$benchmark_result" "P95 TPOT (ms):")
    local p99_tpot=$(extract_value "$benchmark_result" "P99 TPOT (ms):")
    local mean_itl=$(extract_value "$benchmark_result" "Mean ITL (ms):")
    local p90_itl=$(extract_value "$benchmark_result" "P90 ITL (ms):")
    local p95_itl=$(extract_value "$benchmark_result" "P95 ITL (ms):")
    local p99_itl=$(extract_value "$benchmark_result" "P99 ITL (ms):")

    # 组合成所需的字符串，使用空格作为分隔符
    local result=$(printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s" "$request_rate" "$max_concurrency" "$num_prompts" "$input_start" "$output_start" "$duration" "$failed_requests" "$request_throughput" "$output_token_throughput" "$total_token_throughput" "$mean_ttft" "$p90_ttft" "$p95_ttft" "$p99_ttft" "$mean_tpot" "$p90_tpot" "$p95_tpot" "$p99_tpot" "$mean_itl" "$p90_itl" "$p95_itl" "$p99_itl")
    echo "$result" >> $OUTPUT_PATH/$tag-summary.csv

    sleep 1
}

main() {
    cd "$(dirname "$0")"
    export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')
    
    # 设置全局输出相关变量
    mkdir -p "$OUTPUT_PATH"
    tag="$SERVER_NAME"-"$(date +%Y%m%d-%H%M%S)"
    echo "request_rate","max_concurrency","num_prompts","input_start","output_start","duration","failed_requests","request_throughput","output_token_throughput","total_token_throughput","mean_ttft","p90_ttft","p95_ttft","p99_ttft","mean_tpot","p90_tpot","p95_tpot","p99_tpot","mean_itl","p90_itl","p95_itl","p99_itl" > $OUTPUT_PATH/$tag-summary.csv

    # 循环读取 params 数组并进行测试
    for param_str in "${params[@]}"; do
        # 将字符串按空格拆分为对应参数
        read -r req_rate max_conc num_p in_len out_len <<< "$param_str"
        
        run_benchmark "$req_rate" "$max_conc" "$num_p" "$in_len" "$out_len"
    done
}

main "$@"
