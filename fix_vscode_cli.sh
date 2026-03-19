#!/bin/bash

# 脚本功能：修复VS Code CLI连接问题
# 适用场景：当使用code命令出现"Unable to connect to VS Code server"错误时

set -e

echo "=== VS Code CLI 连接修复脚本 ==="
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "提示: 当前是通过 'bash fix_vscode_cli.sh' 执行，环境变量不会保留到父shell。"
    echo "如需让后续命令直接生效，请使用: source fix_vscode_cli.sh"
fi

# 步骤1: 组装候选目录（优先当前用户运行时目录）
echo "步骤1: 组装IPC socket候选目录..."
declare -a SEARCH_DIRS=()
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    SEARCH_DIRS+=("$XDG_RUNTIME_DIR")
fi
SEARCH_DIRS+=("/run/user/$(id -u)" "/tmp")

# 去重，避免重复扫描
declare -a UNIQUE_DIRS=()
for dir in "${SEARCH_DIRS[@]}"; do
    skip=false
    for added in "${UNIQUE_DIRS[@]}"; do
        if [ "$dir" = "$added" ]; then
            skip=true
            break
        fi
    done
    if [ "$skip" = false ]; then
        UNIQUE_DIRS+=("$dir")
    fi
done

echo "将按以下目录顺序查找:"
for dir in "${UNIQUE_DIRS[@]}"; do
    echo "  - $dir"
done

# 步骤2: 查找并按时间排序 socket 文件
echo "步骤2: 查找可用的VS Code IPC socket文件..."
declare -a CANDIDATES=()
for dir in "${UNIQUE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        while IFS= read -r sock; do
            CANDIDATES+=("$sock")
        done < <(find "$dir" -maxdepth 1 -type s -name 'vscode-ipc-*.sock' 2>/dev/null)
    fi
done

if [ ${#CANDIDATES[@]} -eq 0 ]; then
    echo "错误: 未找到任何 vscode-ipc-*.sock 文件。"
    echo "请确认 VS Code Server 正在运行，并且当前 shell 与 VS Code 属于同一用户会话。"
    exit 1
fi

SORTED_SOCKS=$(printf '%s\n' "${CANDIDATES[@]}" | xargs -r ls -1t 2>/dev/null || true)
if [ -z "$SORTED_SOCKS" ]; then
    echo "错误: 找到了候选socket，但无法读取其状态。"
    exit 1
fi

echo "找到候选socket(按最近修改时间排序):"
echo "$SORTED_SOCKS"

# 步骤3: 选择第一个可访问 socket 并设置环境变量
echo "步骤3: 选择可用socket并设置VSCODE_IPC_HOOK_CLI..."
LATEST_SOCK=""
while IFS= read -r sock; do
    [ -z "$sock" ] && continue
    if [ -S "$sock" ]; then
        LATEST_SOCK="$sock"
        break
    fi
done <<< "$SORTED_SOCKS"

if [ -z "$LATEST_SOCK" ]; then
    echo "错误: 候选socket均不可用。"
    exit 1
fi

export VSCODE_IPC_HOOK_CLI="$LATEST_SOCK"
echo "已设置 VSCODE_IPC_HOOK_CLI=$VSCODE_IPC_HOOK_CLI"

# 步骤4: 快速验证 code CLI
echo "步骤4: 验证 code CLI 连接..."
if code --version >/dev/null 2>&1; then
    echo "验证成功: code CLI 已可连接到 VS Code server。"
else
    echo "警告: 仍无法通过当前socket连接。"
    echo "建议重新打开一个 VS Code 终端后再执行本脚本，或重启 VS Code Server。"
    exit 1
fi

# 步骤5: 提供使用说明
echo "步骤5: 使用说明..."
echo "现在你可以正常使用code命令了，例如:"
echo "  code /path/to/your/file"
echo ""
echo "若要在当前shell持续生效，请使用:"
echo "  source fix_vscode_cli.sh"
echo ""
echo "注意: socket会随VS Code会话变化，通常不建议把某个固定socket永久写入~/.bashrc。"

echo "=== 脚本执行完成 ==="