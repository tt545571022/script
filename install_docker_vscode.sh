#!/bin/bash
# 将宿主机上已有的 VS Code Server 及插件复制到指定容器，无需重新下载
# 用法: ./install_vscode_server.sh <容器名>
#       ./install_vscode_server.sh <容器名> <commit_id>  # 指定特定版本

set -e

CONTAINER=${1:-""}
COMMIT=${2:-""}
HOST_SERVER_BASE="/root/.vscode-server/cli/servers"

# ── 参数检查 ──────────────────────────────────────────────────────────────────
if [[ -z "$CONTAINER" ]]; then
    echo "用法: $0 <容器名> [commit_id]"
    echo ""
    echo "宿主机上已有的 VS Code Server 版本:"
    ls "${HOST_SERVER_BASE}" 2>/dev/null | sed 's/^Stable-/  /' || echo "  (未找到)"
    exit 1
fi

# ── 确认容器在运行 ──────────────────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "[ERROR] 容器 '${CONTAINER}' 不存在或未运行"
    echo "当前运行的容器:"
    docker ps --format '  {{.Names}}'
    exit 1
fi

# ── 确定 commit ──────────────────────────────────────────────────────────────
if [[ -z "$COMMIT" ]]; then
    # 自动选最新的一个
    STABLE_DIR=$(ls -1 "${HOST_SERVER_BASE}" 2>/dev/null | grep "^Stable-" | tail -1)
    if [[ -z "$STABLE_DIR" ]]; then
        echo "[ERROR] 宿主机 ${HOST_SERVER_BASE} 下未找到任何已安装的 VS Code Server"
        exit 1
    fi
    COMMIT=${STABLE_DIR#Stable-}
fi

HOST_SERVER_DIR="${HOST_SERVER_BASE}/Stable-${COMMIT}/server"

if [[ ! -d "$HOST_SERVER_DIR" ]]; then
    echo "[ERROR] 宿主机路径不存在: ${HOST_SERVER_DIR}"
    echo "可用版本:"
    ls "${HOST_SERVER_BASE}" 2>/dev/null | sed 's/^/  /' || echo "  (空)"
    exit 1
fi

CONTAINER_BIN_DIR="/root/.vscode-server/bin/${COMMIT}"

# ── 检查容器内是否已安装 ────────────────────────────────────────────────────
if docker exec "${CONTAINER}" test -f "${CONTAINER_BIN_DIR}/node" 2>/dev/null; then
    echo "[INFO] 容器 '${CONTAINER}' 中已存在 VS Code Server (commit: ${COMMIT:0:12}...)"
    echo "[INFO] 跳过安装，若需重装请先手动删除: ${CONTAINER_BIN_DIR}"
    exit 0
fi

echo "[INFO] 容器:   ${CONTAINER}"
echo "[INFO] Commit: ${COMMIT}"
echo "[INFO] 来源:   ${HOST_SERVER_DIR}"
echo "[INFO] 目标:   ${CONTAINER}:${CONTAINER_BIN_DIR}"
echo ""

# ── 创建目标目录 ────────────────────────────────────────────────────────────
echo "[1/3] 创建容器内目标目录..."
docker exec "${CONTAINER}" mkdir -p "${CONTAINER_BIN_DIR}"

# ── 复制文件 ────────────────────────────────────────────────────────────────
echo "[2/3] 复制 VS Code Server 文件（约 234M，请稍候）..."
# docker cp 不支持直接复制目录内容，需先 tar 打包再解包
tar -C "${HOST_SERVER_DIR}" -cf - . | \
    docker exec -i "${CONTAINER}" tar -C "${CONTAINER_BIN_DIR}" -xf -

# ── 创建标记文件 ────────────────────────────────────────────────────────────
echo "[3/3] 创建标记文件..."
docker exec "${CONTAINER}" bash -c "
    mkdir -p /root/.vscode-server/data/Machine
    touch /root/.vscode-server/data/Machine/.writeMachineMCPConfigMarker
"

# ── 验证 ────────────────────────────────────────────────────────────────────
echo ""
echo "[验证] 检查安装结果..."
docker exec "${CONTAINER}" ls "${CONTAINER_BIN_DIR}/" | tr '\n' '  '
echo ""
echo ""
echo "[OK] VS Code Server 已成功安装到容器 '${CONTAINER}'"
echo ""

# ── 复制宿主机插件 ──────────────────────────────────────────────────────────
HOST_EXT_DIR="/root/.vscode-server/extensions"
CONTAINER_EXT_DIR="/root/.vscode-server/extensions"

# 获取宿主机上所有插件目录（排除 extensions.json 本身）
EXTENSIONS=$(ls -1 "${HOST_EXT_DIR}" 2>/dev/null | grep -v '^extensions\.json$')

if [[ -z "$EXTENSIONS" ]]; then
    echo "[INFO] 宿主机上没有已安装的插件，跳过插件同步"
else
    echo "[插件同步] 宿主机插件列表:"
    echo "$EXTENSIONS" | sed 's/^/  - /'
    echo ""
    echo "[4/4] 同步插件到容器..."
    docker exec "${CONTAINER}" mkdir -p "${CONTAINER_EXT_DIR}"

    # 构造 tar 参数：插件目录 + extensions.json
    TAR_ARGS=$(echo "$EXTENSIONS" | tr '\n' ' ')
    [[ -f "${HOST_EXT_DIR}/extensions.json" ]] && TAR_ARGS="extensions.json ${TAR_ARGS}"

    # 逐个检查并复制未安装的插件
    COPIED=0
    SKIPPED=0
    for EXT in $EXTENSIONS; do
        if docker exec "${CONTAINER}" test -d "${CONTAINER_EXT_DIR}/${EXT}" 2>/dev/null; then
            echo "  [跳过] ${EXT} (已存在)"
            ((SKIPPED++)) || true
        else
            echo "  [复制] ${EXT}"
            tar -C "${HOST_EXT_DIR}" -cf - "${EXT}" | \
                docker exec -i "${CONTAINER}" tar -C "${CONTAINER_EXT_DIR}" -xf -
            ((COPIED++)) || true
        fi
    done

    # 同步 extensions.json
    if [[ -f "${HOST_EXT_DIR}/extensions.json" ]]; then
        docker cp "${HOST_EXT_DIR}/extensions.json" "${CONTAINER}:${CONTAINER_EXT_DIR}/extensions.json"
    fi

    echo ""
    echo "[OK] 插件同步完成：复制 ${COPIED} 个，跳过 ${SKIPPED} 个"
fi
echo ""
echo "     现在可以用 Dev Container 插件连接该容器，无需再下载。"
