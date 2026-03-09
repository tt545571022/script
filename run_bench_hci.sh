#!/bin/bash

# ==============================================================================
# 默认参数配置 (Default Configuration)
# ==============================================================================
model_path="/date/GLM/GLM-5-w4a8"
svc_model_name="glm-5"
port=8077

random_range_ratio=0
random_range_ratio_percent=0

# ==============================================================================
# 定义测试参数数组 (Test Parameters Array)
# 格式: "request_rate max_concurrency num_prompts input_len output_len"
# ==============================================================================
params=(
    "8 8 8 128 128"         # just for test
    "16 8 8 128 128"         # just for test
    # "32 32 64 128 128"
    # "64 64 128 128 128"
    # "128 128 256 128 128"
    # "256 256 512 128 128"
    # "512 512 1024 128 128"
    # "8 32 64 128 1024"
    # "16 64 128 128 1024"
    # "32 128 256 128 1024"
    # "64 256 512 128 1024"
    # "4 32 64 128 2048"
    # "8 64 128 128 2048"
    # "16 128 256 128 2048"
    # "32 256 512 128 2048"
    # "32 32 64 256 256"
    # "64 64 128 256 256"
    # "128 128 256 256 256"
    # "256 256 512 256 256"
    # "512 512 1024 256 256"
    # "16 32 64 512 512"
    # "128 64 128 512 512"
    # "256 128 256 512 512"
    # "512 256 512 512 512"
    # "256 512 1024 512 512"
    # "32 32 64 1024 128"
    # "64 64 128 1024 128"
    # "128 128 256 1024 128"
    # "256 256 512 1024 128"
    # "512 512 1024 1024 128"
    # "1 8 16 2048 2048"
    # "2 16 32 2048 2048"
    # "4 32 64 2048 2048"
    # "8 64 128 2048 2048"
    # "16 128 256 2048 2048"
    # "32 256 512 2048 2048"
    # "2 8 16 4096 1024"
    # "4 16 32 4096 1024"
    # "8 32 64 4096 1024"
    # "16 64 128 4096 1024"
    # "32 128 256 4096 1024"
    # "64 256 512 4096 1024"
    # "1 8 16 4096 2048"
    # "2 16 32 4096 2048"
    # "4 32 64 4096 2048"
    # "8 64 128 4096 2048"
    # "16 128 256 4096 2048"
    # "1 8 16 4096 4096"
    # "2 16 32 4096 4096"
    # "4 32 64 4096 4096"
    # "8 64 128 4096 4096"
    # "1 8 16 8192 2048"
    # "2 16 32 8192 2048"
    # "4 32 64 8192 2048"
    # "8 64 128 8192 2048"
    # "1 8 16 8192 8192"
    # "2 16 32 8192 8192"
    # "4 32 64 8192 8192"
    # "8 64 128 8192 8192"
    # "1 8 16 16384 6144"
    # "2 16 32 16384 6144"
)

# ==============================================================================
# 命令行参数解析 (Parse Command Line Arguments)
# ==============================================================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -m|--model_path) model_path="$2"; shift ;;
        -s|--server-name) svc_model_name="$2"; shift ;;
        -p|--port) port="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
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
    # echo "测试参数：req_rate: $request_rate, max_concurrency: $max_concurrency, num_prompts: $num_prompts, input: $input_start-$input_end，output: $output_start-$output_end"
    
    local benchmark_result=$(
            vllm bench serve \
            --backend vllm \
            --model $svc_model_name \
            --tokenizer $model_path \
            --dataset-name $dataset_name \
            --random-input-len $input_len \
            --random-output-len $output_len \
            --random-prefix-len $prefix_len \
            --random-range-ratio $random_range_ratio \
            --request-rate $request_rate \
            --num-prompts $num_prompts \
            --base-url http://127.0.0.1:${port} \
            --endpoint /v1/completions \
            --save-result \
            --result-dir "$results_folder" \
            --result-filename "$tag-concurrency-$max_concurrency.json" \
            --max-concurrency "$max_concurrency" \
            --trust-remote-code \
            --seed $(date +%s) \
            --burstiness 100 \
            --ignore-eos \
            --ready-check-timeout-sec 0 \
            --percentile-metrics ttft,tpot,itl,e2el \
            --metric-percentiles "25,50,75,90,95,99"
    )
    
    echo "$benchmark_result"  | tee "$results_folder/$tag-concurrency-$max_concurrency.log"
    
    # 提取所需的值
    local duration=$(extract_value "$benchmark_result" "Benchmark duration (s):")
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
    local result=$(printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s" "$request_rate" "$max_concurrency" "$num_prompts" "$input_start" "$output_start" "$duration" "$request_throughput" "$output_token_throughput" "$total_token_throughput" "$mean_ttft" "$p90_ttft" "$p95_ttft" "$p99_ttft" "$mean_tpot" "$p90_tpot" "$p95_tpot" "$p99_tpot" "$mean_itl" "$p90_itl" "$p95_itl" "$p99_itl")
    echo "$result" >> $results_folder/$tag-summary.csv

    sleep 1
}

main() {
    cd "$(dirname "$0")"
    export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')
    
    # 设置全局输出相关变量
    results_folder="./results/$svc_model_name"
    mkdir -p "$results_folder"
    tag="$svc_model_name"-"$(date +%Y%m%d-%H%M%S)"
    echo "request_rate","max_concurrency","num_prompts","input_start","output_start","duration","request_throughput","output_token_throughput","total_token_throughput","mean_ttft","p90_ttft","p95_ttft","p99_ttft","mean_tpot","p90_tpot","p95_tpot","p99_tpot","mean_itl","p90_itl","p95_itl","p99_itl" > $results_folder/$tag-summary.csv

    # 循环读取 params 数组并进行测试
    for param_str in "${params[@]}"; do
        # 将字符串按空格拆分为对应参数
        read -r req_rate max_conc num_p in_len out_len <<< "$param_str"
        
        # echo "执行参数: request_rate=$req_rate max_concurrency=$max_conc num_prompts=$num_p input_len=$in_len output_len=$out_len"
        run_benchmark "$req_rate" "$max_conc" "$num_p" "$in_len" "$out_len"
    done
}

main "$@"
