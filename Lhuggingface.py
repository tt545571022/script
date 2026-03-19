#!/usr/bin/env python3
"""
Hugging Face 模型仓库下载脚本
使用 HF API 获取文件列表，aria2 多线程下载，支持断点续传
用法：
  # 完整 URL（推荐）
  python Lhuggingface.py https://huggingface.co/Tengyunw/GLM-4.7-NVFP4/tree/main
  # 仓库 ID 简写
  python Lhuggingface.py Tengyunw/GLM-4.7-NVFP4
  python Lhuggingface.py Tengyunw/GLM-4.7-NVFP4 -r main -o ./GLM-4.7-NVFP4
  python Lhuggingface.py Tengyunw/GLM-4.7-NVFP4 -f .safetensors
"""

import os
import re
import sys
import subprocess
import argparse
import requests
from pathlib import Path


# ── 镜像站配置 ──────────────────────────────────────────────
DEFAULT_MIRROR = "https://hf-mirror.com"
HF_API_BASE    = "https://huggingface.co"   # API 始终走官网


def parse_repo_input(raw: str):
    """
    解析输入，支持以下格式：
      https://huggingface.co/owner/repo/tree/revision
      https://hf-mirror.com/owner/repo/tree/revision
      owner/repo
    返回 (repo_id, revision) 其中 revision 为 None 表示未指定。
    """
    raw = raw.strip().rstrip("/")
    # 匹配完整 URL：域名/owner/repo/tree/revision
    m = re.match(
        r"https?://(?:huggingface\.co|hf-mirror\.com)/([^/]+/[^/]+)/tree/([^/?#]+)",
        raw,
    )
    if m:
        return m.group(1), m.group(2)
    # 匹配 URL 但没有 /tree/ 部分：域名/owner/repo
    m = re.match(
        r"https?://(?:huggingface\.co|hf-mirror\.com)/([^/]+/[^/]+)",
        raw,
    )
    if m:
        return m.group(1), None
    # 直接是 owner/repo
    if re.match(r"^[^/]+/[^/]+$", raw):
        return raw, None
    raise ValueError(
        f"无法解析输入: {raw!r}\n"
        "请使用以下格式之一：\n"
        "  https://huggingface.co/owner/repo/tree/main\n"
        "  owner/repo"
    )


def check_aria2_installed():
    """检查 aria2 是否已安装"""
    try:
        subprocess.run(["aria2c", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_aria2():
    """尝试自动安装 aria2"""
    print("正在尝试安装 aria2...")
    for cmd in [
        ["pip", "install", "aria2"],
        ["conda", "install", "-c", "bioconda", "aria2", "-y"],
    ]:
        try:
            subprocess.run(cmd, check=True)
            print(f"✓ 安装成功: {' '.join(cmd)}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    try:
        if os.path.exists("/etc/debian_version"):
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "aria2", "-y"], check=True)
        elif os.path.exists("/etc/redhat-release"):
            subprocess.run(["sudo", "yum", "install", "aria2", "-y"], check=True)
        print("✓ 使用系统包管理器安装成功")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    print("✗ 无法自动安装 aria2，请手动安装后重试")
    return False


def get_repo_files(repo_id, revision="main", token=None, file_pattern=None):
    """
    调用 HF API 递归获取仓库所有文件路径。
    返回文件路径列表（相对仓库根目录）。
    """
    print(f"正在获取 {repo_id}@{revision} 的文件列表...")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    files = []
    url = f"{HF_API_BASE}/api/models/{repo_id}/tree/{revision}"
    params = {"recursive": "true"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"✗ 获取文件列表失败: {e}")
        sys.exit(1)

    for item in resp.json():
        if item.get("type") == "file":
            path = item["path"]
            if file_pattern is None or file_pattern in path:
                files.append(path)

    print(f"共找到 {len(files)} 个文件")
    return files


def generate_download_entries(repo_id, files, revision="main", mirror=DEFAULT_MIRROR):
    """生成带 out= 指令的 aria2 输入格式（保留子目录结构）"""
    entries = []
    for f in files:
        url = f"{mirror}/{repo_id}/resolve/{revision}/{f}"
        entries.append(f"{url}\n  out={f}")
    return entries


def download_with_aria2(entries, output_dir, threads=16):
    """使用 aria2c 下载，支持子目录结构"""
    if not entries:
        print("没有需要下载的文件")
        return False

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    links_file = Path("/tmp/hf_download_links.txt")
    links_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

    aria2_cmd = [
        "aria2c",
        "-i", str(links_file),
        "-d", str(output_dir),
        "-x", str(threads),          # 单文件最大连接数
        "-s", str(threads),          # 单文件分片数
        "-j", str(min(threads, 5)),  # 最大并行任务数
        "--continue=true",
        "--max-tries=10",
        "--retry-wait=15",
        "--timeout=600",
        "--connect-timeout=15",
        "--check-certificate=false",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--file-allocation=none",    # 不预分配磁盘，加快启动
        "--console-log-level=notice",
    ]

    print(f"\n开始下载 {len(entries)} 个文件 → {output_dir}")
    print(f"命令: {' '.join(aria2_cmd[:6])} ...")

    env = os.environ.copy()
    env["HF_ENDPOINT"] = DEFAULT_MIRROR

    try:
        subprocess.run(aria2_cmd, env=env, check=True)
        links_file.unlink(missing_ok=True)
        print("\n✓ 下载完成！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ 下载失败 (exit code {e.returncode})")
        print(f"  链接文件保留在: {links_file}，可手动重试")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="下载 Hugging Face 仓库的所有文件（使用 aria2 多线程）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s https://huggingface.co/Tengyunw/GLM-4.7-NVFP4/tree/main
  %(prog)s Tengyunw/GLM-4.7-NVFP4
  %(prog)s Tengyunw/GLM-4.7-NVFP4 -o /data/models/GLM-4.7-NVFP4
  %(prog)s Tengyunw/GLM-4.7-NVFP4 -f .safetensors -t 32
  %(prog)s Tengyunw/GLM-4.7-NVFP4 --no-mirror --token hf_xxxx
        """,
    )
    parser.add_argument(
        "repo_id",
        metavar="REPO",
        help="仓库 ID 或完整 URL，如:\n"
             "  Tengyunw/GLM-4.7-NVFP4\n"
             "  https://huggingface.co/Tengyunw/GLM-4.7-NVFP4/tree/main",
    )
    parser.add_argument("-r", "--revision", default=None, help="分支/tag/commit (默认: main，URL 中已包含则自动提取)")
    parser.add_argument("-o", "--output",   default=None,   help="本地保存目录 (默认: ./<模型名>)")
    parser.add_argument("-t", "--threads",  type=int, default=16, help="下载线程数 (默认: 16)")
    parser.add_argument("-f", "--filter",   default=None,   help="文件路径过滤关键词，如 .safetensors")
    parser.add_argument("--token",          default=None,   help="HuggingFace Access Token（私有模型需要）")
    parser.add_argument("--no-mirror",      action="store_true", help="不使用镜像站，直接访问 huggingface.co")
    parser.add_argument("--dry-run",        action="store_true", help="仅列出文件，不执行下载")

    args = parser.parse_args()

    # ── 解析仓库输入（支持完整 URL） ───────────────────────────
    try:
        repo_id, url_revision = parse_repo_input(args.repo_id)
    except ValueError as e:
        print(e)
        sys.exit(1)

    # revision 优先级：命令行 -r > URL 中提取 > 默认 main
    revision = args.revision or url_revision or "main"
    print(f"仓库: {repo_id}  分支/版本: {revision}")

    # ── 镜像站设置 ────────────────────────────────────────────
    mirror = HF_API_BASE if args.no_mirror else DEFAULT_MIRROR
    if not args.no_mirror:
        os.environ["HF_ENDPOINT"] = mirror
        print(f"使用镜像站: {mirror}")

    # ── 输出目录 ──────────────────────────────────────────────
    output_dir = args.output or f"./{repo_id.split('/')[-1]}"

    # ── 检查 aria2 ────────────────────────────────────────────
    if not args.dry_run:
        if not check_aria2_installed():
            print("aria2 未安装，尝试自动安装...")
            if not install_aria2():
                sys.exit(1)

    # ── 获取文件列表 ──────────────────────────────────────────
    files = get_repo_files(
        repo_id,
        revision=revision,
        token=args.token,
        file_pattern=args.filter,
    )

    if not files:
        print("没有找到匹配的文件，退出")
        sys.exit(0)

    # ── 打印文件列表 ──────────────────────────────────────────
    print("\n文件列表:")
    for f in files:
        print(f"  {f}")

    if args.dry_run:
        print(f"\n[dry-run] 共 {len(files)} 个文件，不执行下载")
        return

    # ── 生成下载条目并执行下载 ────────────────────────────────
    entries = generate_download_entries(repo_id, files, revision, mirror)
    success = download_with_aria2(entries, output_dir, args.threads)

    if success:
        print(f"文件保存在: {Path(output_dir).resolve()}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)

