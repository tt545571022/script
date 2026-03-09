
#!/bin/bash
# 支持参数传入目录的核心指标提取脚本

# 检查参数
if [ $# -eq 0 ]; then
    echo "使用方法: $0 <处理目录>"
    echo "例如: $0 /path/to/data"
    exit 1
fi

INPUT_DIR="$1"

# 检查目录是否存在
if [ ! -d "$INPUT_DIR" ]; then
    echo "错误: 目录 '$INPUT_DIR' 不存在"
    exit 1
fi

echo "=== 核心指标提取脚本 ==="
echo "处理目录: $INPUT_DIR"

# 输出文件路径（放在输入目录中）
OUTPUT_CSV="$INPUT_DIR/core_metrics.csv"

# 按照要求的格式写入表头
echo -e "total input Tokens\ttotal output Tokens\tduration (s)\t\toutput throughput (tok/s)\t\tMean TTFT (ms)\t\tMean TPOT (ms)\t\tMean ITL (ms)" > "$OUTPUT_CSV"

# 处理所有JSON文件
count=0
success_count=0

# 按照特定顺序处理文件
for dir in  $(ls -rt "$INPUT_DIR"); do
    full_dir="$INPUT_DIR/$dir"
    if [ -d "$full_dir" ]; then
        for json_file in "$full_dir"/*.json; do
            if [ -f "$json_file" ]; then
                echo "处理: $json_file"
                count=$((count + 1))
                
                # 使用sed提取JSON值
                extract_json_value() {
                    local file="$1"
                    local key="$2"
                    sed -n 's/.*"'"$key"'"[[:space:]]*:[[:space:]]*\([0-9.]*\).*/\1/p' "$file" | head -1
                }
                
                total_input_tokens=$(extract_json_value "$json_file" "total_input_tokens" || echo "0")
                total_output_tokens=$(extract_json_value "$json_file" "total_output_tokens" || echo "0")
                duration=$(extract_json_value "$json_file" "duration" || echo "0")
                output_throughput=$(extract_json_value "$json_file" "output_throughput" || echo "0")
                mean_ttft_ms=$(extract_json_value "$json_file" "mean_ttft_ms" || echo "0")
                mean_tpot_ms=$(extract_json_value "$json_file" "mean_tpot_ms" || echo "0")
                mean_itl_ms=$(extract_json_value "$json_file" "mean_itl_ms" || echo "0")
                
                # 数据清理
                clean_number() {
                    echo "$1" | sed 's/[^0-9.]//g' | grep -E '^[0-9]+\.?[0-9]*$' || echo "0"
                }
                
                total_input_tokens=$(clean_number "$total_input_tokens")
                total_output_tokens=$(clean_number "$total_output_tokens")
                duration=$(clean_number "$duration")
                output_throughput=$(clean_number "$output_throughput")
                mean_ttft_ms=$(clean_number "$mean_ttft_ms")
                mean_tpot_ms=$(clean_number "$mean_tpot_ms")
                mean_itl_ms=$(clean_number "$mean_itl_ms")
                
                # 设置默认值
                total_input_tokens=${total_input_tokens:-0}
                total_output_tokens=${total_output_tokens:-0}
                duration=${duration:-0}
                output_throughput=${output_throughput:-0}
                mean_ttft_ms=${mean_ttft_ms:-0}
                mean_tpot_ms=${mean_tpot_ms:-0}
                mean_itl_ms=${mean_itl_ms:-0}
                
                # 按照要求的格式写入数据行
                echo -e "$total_input_tokens\t$total_output_tokens\t$duration\t\t$output_throughput\t\t$mean_ttft_ms\t\t$mean_tpot_ms\t\t$mean_itl_ms" >> "$OUTPUT_CSV"
                success_count=$((success_count + 1))
                echo "  提取结果: $total_input_tokens\t$total_output_tokens\t$duration\t$output_throughput\t$mean_ttft_ms\t$mean_tpot_ms\t$mean_itl_ms"
            fi
        done
    fi
done

echo ""
echo "处理完成!"
echo "总共找到文件: $count 个"
echo "成功处理: $success_count 个"
echo "结果保存到: $OUTPUT_CSV"

# 显示完整结果
echo ""
echo "完整结果:"
cat "$OUTPUT_CSV"