#!/bin/bash

# 处理 smi 输出并按原顺序打印，附加运行时长和容器名
# $1: smi 输出临时文件路径
# $2: bash [[ =~ ]] 正则，用于匹配进程行
# $3: 字段分隔符（非空时按 FS 分割取 $4 字段提取 PID；为空时扫描 C/G/C+G 前一 token）
# $4: 字段编号（1-indexed，仅 $3 非空时使用）
# $5: 预构建的 runtime_map（关联数组名，通过 nameref）
# $6: 预构建的 cid_to_name（关联数组名，通过 nameref）
process_smi_output() {
    local smi_file="$1"
    local proc_pattern="$2"
    local field_sep="$3"
    local field_num="$4"
    local -n _runtime_map="$5"
    local -n _cid_to_name="$6"

    mapfile -t lines < "$smi_file"

    # 纯 bash 提取 PID，零 fork
    declare -A idx_to_pid=()
    local -a all_pids=()
    local pid tokens j
    for i in "${!lines[@]}"; do
        if [[ "${lines[$i]}" =~ $proc_pattern ]]; then
            pid=""
            if [[ -n "$field_sep" ]]; then
                IFS="$field_sep" read -ra _fields <<< "${lines[$i]}"
                pid="${_fields[$((field_num - 1))]}"
                pid="${pid// /}"
            else
                read -ra tokens <<< "${lines[$i]}"
                for j in "${!tokens[@]}"; do
                    if [[ "${tokens[$j]}" == "C" || "${tokens[$j]}" == "G" || "${tokens[$j]}" == "C+G" ]]; then
                        pid="${tokens[$((j - 1))]}"
                        break
                    fi
                done
            fi
            if [[ -n "$pid" ]]; then
                idx_to_pid["$i"]="$pid"
                all_pids+=("$pid")
            fi
        fi
    done

    if [ ${#all_pids[@]} -eq 0 ]; then
        printf '%s\n' "${lines[@]}"
        return
    fi

    # 纯 bash 读取 cgroup（零 fork），利用预构建 cid_to_name 查表
    declare -A pid_to_cid=()
    declare -A seen_cid=()
    local -a missing_cids=()
    local cid cgline
    for pid in "${all_pids[@]}"; do
        cid=""
        while IFS= read -r cgline; do
            if [[ "$cgline" =~ ([0-9a-f]{64,}) ]]; then
                cid="${BASH_REMATCH[1]}"
                break
            fi
        done < "/proc/${pid}/cgroup" 2>/dev/null
        pid_to_cid["$pid"]="$cid"
        # 若 docker ps 未覆盖（容器已停止但进程存活），收集备查
        if [[ -n "$cid" && -z "${_cid_to_name[$cid]+x}" && -z "${seen_cid[$cid]+x}" ]]; then
            missing_cids+=("$cid")
            seen_cid["$cid"]=1
        fi
    done

    # 补充 inspect 缺失的容器（通常为空，极少调用）
    if [ ${#missing_cids[@]} -gt 0 ]; then
        while IFS=$'\t' read -r cid name; do
            _cid_to_name["$cid"]="${name#/}"
        done < <(docker inspect --format $'{{.Id}}\t{{.Name}}' "${missing_cids[@]}" 2>/dev/null)
    fi

    # 按原顺序输出
    local runtime container_name
    for i in "${!lines[@]}"; do
        if [[ -n "${idx_to_pid[$i]+x}" ]]; then
            pid="${idx_to_pid[$i]}"
            runtime="${_runtime_map[$pid]:-N/A}"
            cid="${pid_to_cid[$pid]}"
            container_name="${_cid_to_name[$cid]}"
            echo "${lines[$i]}   ${runtime} | ${container_name}"
        else
            echo "${lines[$i]}"
        fi
    done
}

# ── 主流程 ────────────────────────────────────────────────────────────────────

if command -v npu-smi >/dev/null 2>&1; then
    smi_cmd="npu-smi info"
    proc_pattern='\| *[0-9]{1,2} +[0-9] +\| *[0-9]+ *\| .*\| *[0-9]+ *\|'
    field_sep='|'; field_num='3'
elif command -v nvidia-smi >/dev/null 2>&1; then
    smi_cmd="nvidia-smi"
    proc_pattern='\|\s+[0-9]+\s+.*[0-9]+\s+[CG]\s+.*\|'
    field_sep=''; field_num=''
else
    echo "未检测到 npu-smi 或 nvidia-smi 命令，请确保已安装驱动及相关工具。"
    exit 1
fi

tmp_smi=$(mktemp)
trap 'rm -f "$tmp_smi"' EXIT

# 1. 在后台启动 smi 命令
$smi_cmd > "$tmp_smi" &
smi_bg=$!

# 2. 与 smi 并行：批量获取所有进程运行时长（一次 ps -e 调用）
declare -A runtime_map=()
while read -r ppid petime; do
    runtime_map["$ppid"]="${petime:-N/A}"
done < <(ps -e -o pid=,etime= 2>/dev/null)

# 3. 与 smi 并行：获取所有运行中容器 ID → 名称（一次 docker ps 调用）
declare -A cid_to_name=()
while IFS=$'\t' read -r cid name; do
    cid_to_name["$cid"]="$name"
done < <(docker ps --no-trunc --format $'{{.ID}}\t{{.Names}}' 2>/dev/null)

# 4. 等待 smi 完成，处理输出
wait "$smi_bg"
process_smi_output "$tmp_smi" "$proc_pattern" "$field_sep" "$field_num" runtime_map cid_to_name
