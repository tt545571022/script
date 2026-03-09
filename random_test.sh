#!/bin/bash

# set -ex

# model_name="DeepSeek-R1-Distill-Qwen-1.5B"
# model_name="DeepSeek-R1-Distill-Qwen-7B"
# model_name="DeepSeek-R1-Distill-Llama-8B"
# model_name="DeepSeek-R1-Distill-Qwen-14B"
# model_name="DeepSeek-R1-Distill-Qwen-32B"
# model_name="DeepSeek-R1-Distill-Llama-70B"
# model_name="DeepSeek-V2-Lite-Chat"
model_name="GLM-4.7-W8A8"

results_folder="/workspace/outputs/$model_name"
mkdir -p $results_folder
model_path="/usr/local/serving/models/"
svc_model_name="glm"

tag="$svc_model_name"-"$(date +%s)"
prefix_len=0
input_len=$4
output_len=$5
random_range_ratio=0
random_range_ratio_percent=0

request_rate=$1
max_concurrency=$2
num_prompts=$3


# 计算 input 范围
input_start=$((prefix_len + input_len - input_len * random_range_ratio_percent / 100))
input_end=$((prefix_len + input_len + input_len * random_range_ratio_percent / 100))

# 计算 output 范围
output_start=$((output_len - output_len * random_range_ratio_percent / 100))
output_end=$((output_len + output_len * random_range_ratio_percent / 100))

# 定义一个函数来安全地提取值
extract_value() {
    local result="$1"
    local pattern="$2"
    local value=$(echo "$result" | grep "$pattern" | awk '{print $NF}')
    if [ -z "$value" ]; then
        echo "Error: Value for pattern '$pattern' not found." >&2
        exit 1
    fi
    echo "$value"
}

benchmark() {
  dataset_name="random"
  # echo "测试参数：req_rate: $request_rate, max_concurrency: $max_concurrency, num_prompts: $num_prompts, input: $input_start-$input_end，output: $output_start-$output_end"
  benchmark_result=$(
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
          --base-url http://127.0.0.1:18000 \
          --endpoint /v1/completions \
          --save-result \
          --result-dir $results_folder \
          --result-filename "$tag"-concurrency-"$max_concurrency".json \
          --max-concurrency "$max_concurrency" \
          --trust-remote-code \
          --seed $(date +%s) \
          --burstiness 100 \
          --ignore-eos \
          --ready-check-timeout-sec 0 \
          --percentile-metrics ttft,tpot,itl,e2el \
          --metric-percentiles "25,50,75,90,95,99"
                  
  )
  echo "$benchmark_result" 
  # 提取所需的值
  duration=$(extract_value "$benchmark_result" "Benchmark duration (s):")
  request_throughput=$(extract_value "$benchmark_result" "Request throughput (req/s):")
  output_token_throughput=$(extract_value "$benchmark_result" "Output token throughput (tok/s):")
  total_token_throughput=$(extract_value "$benchmark_result" "Total token throughput (tok/s):")
  mean_ttft=$(extract_value "$benchmark_result" "Mean TTFT (ms):")
  p90_ttft=$(extract_value "$benchmark_result" "P90 TTFT (ms):")
  p95_ttft=$(extract_value "$benchmark_result" "P95 TTFT (ms):")
  p99_ttft=$(extract_value "$benchmark_result" "P99 TTFT (ms):")
  mean_tpot=$(extract_value "$benchmark_result" "Mean TPOT (ms):")
  p90_tpot=$(extract_value "$benchmark_result" "P90 TPOT (ms):")
  p95_tpot=$(extract_value "$benchmark_result" "P95 TPOT (ms):")
  p99_tpot=$(extract_value "$benchmark_result" "P99 TPOT (ms):")
  mean_itl=$(extract_value "$benchmark_result" "Mean ITL (ms):")
  p90_itl=$(extract_value "$benchmark_result" "P90 ITL (ms):")
  p95_itl=$(extract_value "$benchmark_result" "P95 ITL (ms):")
  p99_itl=$(extract_value "$benchmark_result" "P99 ITL (ms):")

  # echo "测试参数：req_rate: $request_rate, max_concurrency: $max_concurrency, num_prompts: $num_prompts, input: $input_start-$input_end，output: $output_start-$output_end"
  # 组合成所需的字符串，使用空格作为分隔符
  result=$(printf "%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s" "$request_rate" "$max_concurrency" "$num_prompts" "$input_start" "$output_start" "$duration" "$request_throughput" "$output_token_throughput" "$total_token_throughput" "$mean_ttft" "$p90_ttft" "$p95_ttft" "$p99_ttft" "$mean_tpot" "$p90_tpot" "$p95_tpot" "$p99_tpot" "$mean_itl" "$p90_itl" "$p95_itl" "$p99_itl")
  echo "$result"

  sleep 1
}

main() {
  cd "$(dirname "$0")"
  export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')

  benchmark
}

main "$@"