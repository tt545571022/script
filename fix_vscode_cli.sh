#!/bin/bash

# 脚本功能：修复VS Code CLI连接问题
# 适用场景：当使用code命令出现"Unable to connect to VS Code server"错误时

set -e

echo "=== VS Code CLI 连接修复脚本 ==="

# 步骤1: 查找当前活跃的VS Code IPC socket文件
echo "步骤1: 查找当前活跃的VS Code IPC socket文件..."
if ls /tmp/vscode-ipc-*.sock 1> /dev/null 2>&1; then
    echo "找到以下IPC socket文件:"
    ls -la /tmp/vscode-ipc-*.sock
else
    echo "警告: 未找到IPC socket文件，请确认VS Code服务器正在运行"
    exit 1
fi

# 步骤2: 获取最新的IPC socket文件
echo "步骤2: 获取最新的IPC socket文件..."
LATEST_SOCK=$(ls -t /tmp/vscode-ipc-*.sock | head -n 1)
echo "最新IPC socket文件: $LATEST_SOCK"

# 步骤3: 设置环境变量
echo "步骤3: 设置VSCODE_IPC_HOOK_CLI环境变量..."
export VSCODE_IPC_HOOK_CLI="$LATEST_SOCK"
echo "已设置 VSCODE_IPC_HOOK_CLI=$VSCODE_IPC_HOOK_CLI"

# 步骤4: 验证环境变量
echo "步骤4: 验证环境变量..."
if [ -z "$VSCODE_IPC_HOOK_CLI" ]; then
    echo "错误: 环境变量设置失败"
    exit 1
else
    echo "环境变量设置成功"
fi

# 步骤5: 提供使用说明
echo "步骤5: 使用说明..."
echo "现在你可以正常使用code命令了，例如:"
echo "  code /path/to/your/file"
echo ""
echo "要永久解决此问题，可以将以下内容添加到你的~/.bashrc或~/.zshrc文件中:"
echo "  export VSCODE_IPC_HOOK_CLI=\"$LATEST_SOCK\""
echo ""
echo "注意: 如果VS Code服务器重启，可能需要重新运行此脚本"

echo "=== 脚本执行完成 ==="