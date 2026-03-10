#!/bin/bash

# ── 参数解析 ──────────────────────────────────────────────────────────────────
kill_target=""
[[ "$1" == "-k" || "$1" == "--kill" ]] && { kill_target="$2"; shift 2; }
if [[ -n "$1" ]]; then
    echo "Usage: $(basename "$0") [-k|--kill <container_name>]"
    echo "  （不带参数）列出占用 NPU/GPU 的进程及对应容器"
    echo "  -k, --kill <container_name>  杀掉指定容器占用 NPU/GPU 的所有进程"
    exit 1
fi

# ── 检测硬件，定义 get_pid() ──────────────────────────────────────────────────
if command -v npu-smi >/dev/null 2>&1; then
    smi_cmd="npu-smi info"
    proc_re='\| *[0-9]{1,2} +[0-9] +\| *[0-9]+ *\| .*\| *[0-9]+ *\|'
    get_pid() { IFS='|' read -ra _f <<< "$1"; echo "${_f[2]// /}"; }
elif command -v nvidia-smi >/dev/null 2>&1; then
    smi_cmd="nvidia-smi"
    proc_re='\|\s+[0-9]+\s+.*[0-9]+\s+[CG]\s+.*\|'
    get_pid() {
        local _t; read -ra _t <<< "$1"
        for _j in "${!_t[@]}"; do
            [[ "${_t[$_j]}" =~ ^(C|G|C\+G)$ ]] && echo "${_t[$((_j-1))]}" && return
        done
    }
else
    echo "未检测到 npu-smi 或 nvidia-smi 命令，请确保已安装驱动及相关工具。"; exit 1
fi

# ── 准备 ──────────────────────────────────────────────────────────────────────
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT

# 后台运行 smi
$smi_cmd > "$tmp" &
smi_bg=$!

# 与 smi 并行：构建 cid → 容器名映射（docker ps 一次调用）
declare -A cid_name=()
while IFS=$'\t' read -r cid name; do
    cid_name["$cid"]="$name"
done < <(docker ps --no-trunc --format $'{{.ID}}\t{{.Names}}' 2>/dev/null)

wait "$smi_bg"
mapfile -t lines < "$tmp"

# 通过 cgroup 查 pid 对应容器名（纯 bash 读文件，缺失时补 docker inspect）
pid_to_container() {
    local pid=$1 cid="" cgline
    while IFS= read -r cgline; do
        [[ "$cgline" =~ ([0-9a-f]{64,}) ]] && cid="${BASH_REMATCH[1]}" && break
    done < "/proc/${pid}/cgroup" 2>/dev/null
    if [[ -n "$cid" && -z "${cid_name[$cid]+x}" ]]; then
        local n; n=$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null)
        cid_name["$cid"]="${n#/}"
    fi
    echo "${cid_name[$cid]}"
}

# ── Kill 模式 ─────────────────────────────────────────────────────────────────
if [[ -n "$kill_target" ]]; then
    declare -a target_pids=()
    for line in "${lines[@]}"; do
        [[ "$line" =~ $proc_re ]] || continue
        pid=$(get_pid "$line"); [[ -z "$pid" ]] && continue
        [[ "$(pid_to_container "$pid")" == "$kill_target" ]] && target_pids+=("$pid")
    done
    if [[ ${#target_pids[@]} -eq 0 ]]; then
        echo "未找到容器 '$kill_target' 占用 NPU/GPU 的进程"; exit 1
    fi
    echo "将杀掉容器 '$kill_target' 的以下进程：${target_pids[*]}"
    for pid in "${target_pids[@]}"; do
        kill -9 "$pid" 2>/dev/null && echo "  已杀掉 PID $pid" || echo "  杀掉 PID $pid 失败（权限不足或已退出）"
    done
    exit 0
fi

# ── 查询模式 ──────────────────────────────────────────────────────────────────
declare -A rt=()
while read -r ppid petime; do rt["$ppid"]="$petime"; done \
    < <(ps -e -o pid=,etime= 2>/dev/null)

for line in "${lines[@]}"; do
    if [[ "$line" =~ $proc_re ]]; then
        pid=$(get_pid "$line")
        echo "$line   ${rt[$pid]:-N/A} | $(pid_to_container "$pid")"
    else
        echo "$line"
    fi
done
