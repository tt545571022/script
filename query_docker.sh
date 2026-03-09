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

# 自动识别硬件类型并进行查询
if command -v npu-smi >/dev/null 2>&1; then
    # Ascend NPU
    npu-smi info | while IFS= read -r line; do
        if echo "$line" | grep -Eq '\|\ *[0-9]{1,2}\ +[0-9]\ +\|\ *[0-9]+\ *\|\ *.*\|\ *[0-9]+\ *\|'; then
            pid=$(echo "$line" | awk -F '|' '{print $3}' | xargs)
            runtime=$(get_process_runtime "$pid")
            container_name=$(get_container_name "$pid")
            echo "${line}   ${runtime} | ${container_name}"
        else
            echo "${line}"
        fi
    done
elif command -v nvidia-smi >/dev/null 2>&1; then
    # NVIDIA GPU
    nvidia-smi | while IFS= read -r line; do
        # 匹配 NVIDIA 进程行，形态如: |    0   N/A  N/A      1234      C   python      100MiB |
        if echo "$line" | grep -Eq '\|\s+[0-9]+\s+.*[0-9]+\s+[CG]\s+.*\|'; then
            # 提取 PID: 查找 Type (C/G/C+G) 前面的那个字段
            pid=$(echo "$line" | awk '{for(i=1;i<=NF;i++) if($i ~ /^(C|G|C\+G)$/) print $(i-1)}')
            runtime=$(get_process_runtime "$pid")
            container_name=$(get_container_name "$pid")
            echo "${line}   ${runtime} | ${container_name}"
        else
            echo "${line}"
        fi
    done
else
    echo "未检测到 npu-smi 或 nvidia-smi 命令，请确保已安装驱动及相关工具。"
    exit 1
fi
