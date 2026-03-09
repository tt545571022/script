#!/bin/bash

# 获取进程对应的容器名称
get_container_name() {
    local pid=$1
    local container_id
    container_id=$(cat /proc/${pid}/cgroup 2>/dev/null | grep -o -E "[0-9a-f]{64,}" | head -n 1)
    if [ -z "$container_id" ]; then
        return
    fi
    docker inspect --format '{{.Name}}' "${container_id}" 2>/dev/null | sed 's/^\///'
}

# 获取进程已运行时长（格式：[[DD-]HH:]MM:SS）
get_process_runtime() {
    local pid=$1
    local etime
    etime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
    if [ -z "$etime" ]; then
        echo "N/A"
    else
        echo "$etime"
    fi
}

# 并行查询进程信息并按原顺序输出
# $1: 正则表达式用于匹配进程行
# $2: awk 字段分隔符（为空则不传 -F）
# $3: awk 程序，用于从匹配行中提取 PID
# stdin: smi 命令输出
run_parallel() {
    local proc_pattern="$1"
    local awk_fs="$2"
    local awk_prog="$3"
    local tmpdir
    tmpdir=$(mktemp -d)
    local bg_pids=()

    mapfile -t lines

    for i in "${!lines[@]}"; do
        line="${lines[$i]}"
        if echo "$line" | grep -Eq "$proc_pattern"; then
            if [ -n "$awk_fs" ]; then
                pid=$(echo "$line" | awk -F "$awk_fs" "$awk_prog" | xargs)
            else
                pid=$(echo "$line" | awk "$awk_prog" | xargs)
            fi
            (
                runtime=$(get_process_runtime "$pid")
                container_name=$(get_container_name "$pid")
                printf '%s' "${runtime} | ${container_name}" > "${tmpdir}/${i}"
            ) &
            bg_pids+=($!)
        fi
    done

    for p in "${bg_pids[@]}"; do wait "$p"; done

    for i in "${!lines[@]}"; do
        if [ -f "${tmpdir}/${i}" ]; then
            echo "${lines[$i]}   $(cat "${tmpdir}/${i}")"
        else
            echo "${lines[$i]}"
        fi
    done

    rm -rf "$tmpdir"
}

# 自动识别硬件类型并进行查询
if command -v npu-smi >/dev/null 2>&1; then
    # Ascend NPU
    npu-smi info | run_parallel \
        '\|\ *[0-9]{1,2}\ +[0-9]\ +\|\ *[0-9]+\ *\|\ *.*\|\ *[0-9]+\ *\|' \
        '|' \
        '{print $3}'
elif command -v nvidia-smi >/dev/null 2>&1; then
    # NVIDIA GPU，提取 Type(C/G/C+G) 前面的字段作为 PID
    nvidia-smi | run_parallel \
        '\|\s+[0-9]+\s+.*[0-9]+\s+[CG]\s+.*\|' \
        '' \
        '{for(i=1;i<=NF;i++) if($i ~ /^(C|G|C\+G)$/) print $(i-1)}'
else
    echo "未检测到 npu-smi 或 nvidia-smi 命令，请确保已安装驱动及相关工具。"
    exit 1
fi
