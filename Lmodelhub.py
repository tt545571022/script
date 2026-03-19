#!/usr/bin/env python3
"""统一模型仓库下载脚本。

支持平台：
- Hugging Face
- ModelScope
- Modelers

能力：
- 输入链接后自动识别平台
- 支持指定 revision/ref/PR 引用，也支持平台默认分支
- 支持递归处理带文件夹的仓库
- 生成 manifest、aria2 输入文件、目录结构文件、可选 SHA256 文件
- 可选直接调用 aria2 下载
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


PLATFORM_HUGGINGFACE = "huggingface"
PLATFORM_MODELSCOPE = "modelscope"
PLATFORM_MODELERS = "modelers"

DEFAULT_REVISIONS = {
    PLATFORM_HUGGINGFACE: "main",
    PLATFORM_MODELSCOPE: "master",
    PLATFORM_MODELERS: "main",
}

HF_API_BASE = "https://huggingface.co"
HF_MIRROR_BASE = "https://hf-mirror.com"
MODELSCOPE_BASE = "https://www.modelscope.cn"
MODELERS_BASE = "https://modelers.cn"


@dataclass
class RepoSpec:
    platform: str
    owner: str
    name: str
    revision: str
    source: str

    @property
    def repo_id(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class RepoFile:
    path: str
    download_url: str
    size: int | None = None
    sha256: str | None = None
    extra: dict[str, Any] | None = None


class DownloaderError(RuntimeError):
    """脚本业务错误。"""


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', name).strip()[:200]


def looks_like_sha256(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[0-9a-fA-F]{64}", value))


def detect_platform(raw: str) -> str:
    value = raw.strip()
    lowered = value.lower()

    if "huggingface.co" in lowered or "hf-mirror.com" in lowered:
        return PLATFORM_HUGGINGFACE
    if "modelscope.cn" in lowered:
        return PLATFORM_MODELSCOPE
    if "modelers.cn" in lowered:
        return PLATFORM_MODELERS
    if re.fullmatch(r"[^/]+/[^/]+", value):
        return PLATFORM_HUGGINGFACE

    raise DownloaderError(f"无法识别平台: {raw}")


def parse_repo_input(raw: str, revision_override: str | None = None) -> RepoSpec:
    platform = detect_platform(raw)
    raw = raw.strip().rstrip("/")

    parser_map = {
        PLATFORM_HUGGINGFACE: _parse_huggingface,
        PLATFORM_MODELSCOPE: _parse_modelscope,
        PLATFORM_MODELERS: _parse_modelers,
    }
    parser = parser_map.get(platform)
    if parser is None:
        raise DownloaderError(f"暂不支持的平台: {platform}")

    owner, name, parsed_revision = parser(raw)
    revision = revision_override or parsed_revision or DEFAULT_REVISIONS[platform]
    return RepoSpec(platform=platform, owner=owner, name=name, revision=revision, source=raw)


def _parse_huggingface(raw: str) -> tuple[str, str, str | None]:
    if re.fullmatch(r"[^/]+/[^/]+", raw):
        owner, name = raw.split("/", 1)
        return owner, name, None

    match = re.match(
        r"https?://(?:www\.)?(?:huggingface\.co|hf-mirror\.com)/([^/]+)/([^/?#]+)(?:/tree/([^?#]+))?",
        raw,
        re.IGNORECASE,
    )
    if not match:
        raise DownloaderError(f"无法解析 Hugging Face 链接: {raw}")

    owner, name, revision = match.groups()
    return owner, name, revision


def _parse_modelscope(raw: str) -> tuple[str, str, str | None]:
    parsed, owner, name = _parse_model_repo_url(raw, PLATFORM_MODELSCOPE)
    revision = _extract_query_value(parsed.query, ["Revision", "revision", "ref"])
    return owner, name, revision


def _parse_modelers(raw: str) -> tuple[str, str, str | None]:
    parsed, owner, name = _parse_model_repo_url(raw, PLATFORM_MODELERS)
    revision = _extract_query_value(parsed.query, ["ref", "revision", "Revision"])
    return owner, name, revision


def _parse_model_repo_url(raw: str, platform: str) -> tuple[Any, str, str]:
    parsed = urlparse(raw)
    match = re.match(r"models/([^/]+)/([^/?#]+)", parsed.path.strip("/"))
    if not match:
        raise DownloaderError(f"无法解析 {platform} 链接: {raw}")
    owner, name = match.groups()
    return parsed, owner, name


def _extract_query_value(query: str, keys: list[str]) -> str | None:
    if not query:
        return None
    for chunk in query.split("&"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key in keys and value:
            return value
    return None


def create_session(token: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Lmodelhub/1.0",
        }
    )
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def collect_files(session: requests.Session, spec: RepoSpec, *, hf_use_mirror: bool) -> list[RepoFile]:
    collector_map = {
        PLATFORM_HUGGINGFACE: lambda: collect_huggingface_files(session, spec, hf_use_mirror=hf_use_mirror),
        PLATFORM_MODELSCOPE: lambda: collect_modelscope_files(session, spec),
        PLATFORM_MODELERS: lambda: collect_modelers_files(session, spec),
    }
    collector = collector_map.get(spec.platform)
    if collector is not None:
        return collector()
    raise DownloaderError(f"不支持的平台: {spec.platform}")


def collect_huggingface_files(
    session: requests.Session,
    spec: RepoSpec,
    *,
    hf_use_mirror: bool,
) -> list[RepoFile]:
    api_url = f"{HF_API_BASE}/api/models/{spec.repo_id}/tree/{spec.revision}"
    response = session.get(api_url, params={"recursive": "true"}, timeout=30)
    response.raise_for_status()

    download_base = HF_MIRROR_BASE if hf_use_mirror else HF_API_BASE
    files: list[RepoFile] = []
    for item in response.json():
        if item.get("type") != "file":
            continue
        path = item["path"]
        sha256 = None
        lfs = item.get("lfs") or {}
        oid = lfs.get("oid")
        if looks_like_sha256(oid):
            sha256 = oid
        files.append(
            RepoFile(
                path=path,
                download_url=f"{download_base}/{spec.repo_id}/resolve/{spec.revision}/{path}",
                size=item.get("size"),
                sha256=sha256,
                extra={"source": item},
            )
        )
    return files


def collect_modelscope_files(session: requests.Session, spec: RepoSpec) -> list[RepoFile]:
    api_url = f"{MODELSCOPE_BASE}/api/v1/models/{spec.owner}/{spec.name}/repo/files"
    files: list[RepoFile] = []

    def fetch(root_path: str) -> list[dict[str, Any]]:
        response = session.get(
            api_url,
            params={"Revision": spec.revision, "Root": root_path},
            timeout=30,
            verify=False,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("Success", True):
            raise DownloaderError(payload.get("Message") or "ModelScope API 返回失败")

        return payload.get("Data", {}).get("Files", [])

    def add_file(item: dict[str, Any]) -> None:
        path = item["Path"]
        sha256 = item.get("Sha256") if looks_like_sha256(item.get("Sha256")) else None
        files.append(
            RepoFile(
                path=path,
                download_url=(
                    f"{MODELSCOPE_BASE}/api/v1/models/{spec.owner}/{spec.name}/repo"
                    f"?Revision={spec.revision}&FilePath={quote(path)}"
                ),
                size=item.get("Size"),
                sha256=sha256,
                extra={"source": item},
            )
        )

    _walk_recursive_tree(
        root_path="",
        fetch_entries=fetch,
        is_dir=lambda item: item.get("Type") == "tree",
        is_file=lambda item: item.get("Type") == "blob",
        get_path=lambda item: item["Path"],
        on_file=add_file,
    )
    return files


def collect_modelers_files(session: requests.Session, spec: RepoSpec) -> list[RepoFile]:
    api_url = f"{MODELERS_BASE}/api/v1/file/{spec.owner}/{spec.name}"
    files: list[RepoFile] = []

    def fetch(path: str) -> list[dict[str, Any]]:
        response = session.get(api_url, params={"ref": spec.revision, "path": path}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", {}).get("tree", [])

    def add_file(item: dict[str, Any]) -> None:
        path = item["path"]
        relative_url = item.get("url") or (
            f"/web/v1/file/{spec.owner}/{spec.name}/{quote(spec.revision)}/media/{quote(path)}"
        )
        sha_candidate = item.get("sha256") or item.get("lfs", {}).get("oid") or item.get("etag")
        files.append(
            RepoFile(
                path=path,
                download_url=urljoin(MODELERS_BASE, relative_url),
                size=item.get("size"),
                sha256=sha_candidate if looks_like_sha256(sha_candidate) else None,
                extra={"source": item},
            )
        )

    _walk_recursive_tree(
        root_path="",
        fetch_entries=fetch,
        is_dir=lambda item: item.get("type") in {"dir", "tree"} and bool(item.get("path")),
        is_file=lambda item: item.get("type") in {"file", "blob"} and bool(item.get("path")),
        get_path=lambda item: item["path"],
        on_file=add_file,
    )
    return files


def _walk_recursive_tree(
    *,
    root_path: str,
    fetch_entries: Any,
    is_dir: Any,
    is_file: Any,
    get_path: Any,
    on_file: Any,
) -> None:
    for item in fetch_entries(root_path):
        if is_dir(item):
            _walk_recursive_tree(
                root_path=get_path(item),
                fetch_entries=fetch_entries,
                is_dir=is_dir,
                is_file=is_file,
                get_path=get_path,
                on_file=on_file,
            )
            continue
        if is_file(item):
            on_file(item)


def ensure_output_dir(base_output: str | Path, spec: RepoSpec) -> Path:
    base_path = Path(base_output).expanduser().resolve()
    repo_dir = base_path / f"{spec.platform}_{safe_filename(spec.owner)}_{safe_filename(spec.name)}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


def apply_filters(files: list[RepoFile], keyword: str | None, max_files: int | None) -> list[RepoFile]:
    result = files
    if keyword:
        result = [item for item in result if keyword in item.path]
    if max_files is not None:
        result = result[:max_files]
    return result


def write_artifacts(repo_dir: Path, spec: RepoSpec, files: list[RepoFile]) -> dict[str, Path]:
    manifest_file = repo_dir / f"{spec.name}_manifest.json"
    aria2_file = repo_dir / f"{spec.name}_aria2_input.txt"
    sha_file = repo_dir / f"{spec.name}_sha256.txt"
    tree_file = repo_dir / f"{spec.name}_directory_structure.txt"

    manifest = {
        "repo": asdict(spec),
        "file_count": len(files),
        "files": [asdict(item) for item in files],
    }
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    with aria2_file.open("w", encoding="utf-8") as handle:
        for item in files:
            handle.write(f"{item.download_url}\n")
            handle.write(f"  out={item.path}\n\n")

    sha_lines = [f"{item.sha256}\t{item.path}" for item in files if item.sha256]
    sha_file.write_text("\n".join(sha_lines) + ("\n" if sha_lines else ""), encoding="utf-8")
    tree_file.write_text(render_tree(spec, files), encoding="utf-8")

    return {
        "manifest": manifest_file,
        "aria2": aria2_file,
        "sha256": sha_file,
        "tree": tree_file,
    }


def render_tree(spec: RepoSpec, files: list[RepoFile]) -> str:
    nested: dict[str, Any] = {}
    for file in sorted(files, key=lambda item: item.path):
        cursor = nested
        parts = [part for part in Path(file.path).parts if part]
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = None

    lines = [f"仓库目录结构: {spec.platform}/{spec.repo_id}@{spec.revision}", "=" * 60]

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        names = sorted(node.keys())
        for index, name in enumerate(names):
            last = index == len(names) - 1
            marker = "└── " if last else "├── "
            lines.append(f"{prefix}{marker}{name}")
            child = node[name]
            if isinstance(child, dict):
                extension = "    " if last else "│   "
                walk(child, prefix + extension)

    if nested:
        walk(nested)
    else:
        lines.append("(empty)")
    return "\n".join(lines) + "\n"


def aria2_exists() -> bool:
    return shutil.which("aria2c") is not None


def run_aria2(aria2_file: Path, repo_dir: Path, threads: int) -> None:
    if not aria2_exists():
        raise DownloaderError("未找到 aria2c，请先安装 aria2 或使用 --dry-run")

    cmd = [
        "aria2c",
        "-i",
        str(aria2_file),
        "-d",
        str(repo_dir),
        "-x",
        str(threads),
        "-s",
        str(threads),
        "-j",
        str(min(threads, 8)),
        "--continue=true",
        "--max-tries=10",
        "--retry-wait=5",
        "--timeout=600",
        "--connect-timeout=15",
        "--check-certificate=false",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--file-allocation=none",
        "--console-log-level=notice",
    ]
    subprocess.run(cmd, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一下载 Hugging Face / ModelScope / Modelers 模型仓库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s https://huggingface.co/Tengyunw/GLM-4.7-NVFP4/tree/main\n"
            "  %(prog)s https://www.modelscope.cn/models/ZhipuAI/GLM-5 -r master\n"
            "  %(prog)s https://modelers.cn/models/Eco-Tech/GLM-5-w4a8\n"
            "  %(prog)s https://huggingface.co/owner/repo --pr refs/pr/12 --dry-run"
        ),
    )
    parser.add_argument("repo", help="仓库链接；Hugging Face 也支持 owner/repo 简写")
    parser.add_argument("-o", "--output", default="./downloads", help="输出根目录")
    parser.add_argument("-r", "--revision", default=None, help="指定 revision/ref/branch/tag")
    parser.add_argument("--pr", default=None, help="PR/ref 别名，优先级高于 --revision")
    parser.add_argument("-f", "--filter", default=None, help="按文件路径关键字过滤")
    parser.add_argument("-t", "--threads", type=int, default=16, help="aria2 线程数")
    parser.add_argument("--token", default=None, help="访问令牌，主要用于私有 Hugging Face 仓库")
    parser.add_argument("--dry-run", action="store_true", help="仅拉取清单并生成文件，不执行下载")
    parser.add_argument("--no-hf-mirror", action="store_true", help="Hugging Face 不使用 hf-mirror")
    parser.add_argument("--max-files", type=int, default=None, help="仅处理前 N 个文件，便于测试")
    return parser


def prepare_repository(args: argparse.Namespace) -> tuple[RepoSpec, Path, list[RepoFile], dict[str, Path]]:
    revision_override = args.pr or args.revision
    spec = parse_repo_input(args.repo, revision_override=revision_override)
    session = create_session(args.token)
    files = collect_files(session, spec, hf_use_mirror=not args.no_hf_mirror)
    files = apply_filters(files, args.filter, args.max_files)
    if not files:
        raise DownloaderError("没有找到匹配文件")

    repo_dir = ensure_output_dir(args.output, spec)
    artifacts = write_artifacts(repo_dir, spec, files)
    return spec, repo_dir, files, artifacts


def print_summary(spec: RepoSpec, repo_dir: Path, files: list[RepoFile], artifacts: dict[str, Path], dry_run: bool) -> None:
    print(f"平台: {spec.platform}")
    print(f"仓库: {spec.repo_id}")
    print(f"Revision: {spec.revision}")
    print(f"文件数: {len(files)}")
    print(f"输出目录: {repo_dir}")
    print(f"Manifest: {artifacts['manifest']}")
    print(f"Aria2 输入文件: {artifacts['aria2']}")
    print(f"目录结构文件: {artifacts['tree']}")
    if artifacts["sha256"].stat().st_size > 0:
        print(f"SHA256 文件: {artifacts['sha256']}")
    print("模式: 仅生成清单（dry-run）" if dry_run else "模式: 下载")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        spec, repo_dir, files, artifacts = prepare_repository(args)
        print_summary(spec, repo_dir, files, artifacts, args.dry_run)

        if not args.dry_run:
            run_aria2(artifacts["aria2"], repo_dir, args.threads)
            print("下载完成")
        return 0
    except requests.RequestException as exc:
        print(f"网络请求失败: {exc}", file=sys.stderr)
        return 1
    except DownloaderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"aria2 执行失败，退出码: {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
