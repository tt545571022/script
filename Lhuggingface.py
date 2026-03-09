    #!/usr/bin/env python3
    """
    Hugging Face模型PR权重下载脚本
    使用aria2进行多线程下载，支持断点续传
    """

    import os
    import sys
    import subprocess
    import argparse
    from pathlib import Path

    def check_aria2_installed():
        """检查aria2是否已安装"""
        try:
            subprocess.run(["aria2c", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def install_aria2():
        """尝试安装aria2"""
        print("正在尝试安装aria2...")
        try:
            # 尝试使用pip安装
            subprocess.run(["pip", "install", "aria2"], check=True)
            print("✓ 使用pip安装aria2成功")
            return True
        except subprocess.CalledProcessError:
            try:
                # 尝试使用conda安装
                subprocess.run(["conda", "install", "-c", "bioconda", "aria2", "-y"], check=True)
                print("✓ 使用conda安装aria2成功")
                return True
            except subprocess.CalledProcessError:
                try:
                    # 尝试使用系统包管理器安装
                    if os.path.exists("/etc/debian_version"):
                        subprocess.run(["sudo", "apt", "update"], check=True)
                        subprocess.run(["sudo", "apt", "install", "aria2", "-y"], check=True)
                    elif os.path.exists("/etc/redhat-release"):
                        subprocess.run(["sudo", "yum", "install", "aria2", "-y"], check=True)
                    print("✓ 使用系统包管理器安装aria2成功")
                    return True
                except subprocess.CalledProcessError:
                    print("✗ 无法自动安装aria2，请手动安装")
                    return False

    def get_pr_files(repo_id, pr_number, file_pattern=None):
        """
        获取PR对应的文件列表
        注意：这里需要先获取PR对应的提交哈希，实际使用时可能需要调用Hugging Face API
        """
        # 这里需要先获取PR对应的提交哈希
        # 实际实现中可能需要使用huggingface_hub库或Git命令来获取PR的具体文件信息
        print(f"获取仓库 {repo_id} PR #{pr_number} 的文件信息...")
        
        # 示例返回结构，实际需要根据PR内容动态获取
        # 这里假设我们已经知道PR对应的提交哈希
        commit_hash = f"pr-{pr_number}"  # 这需要替换为实际的提交哈希
        
        return {
            "repo_id": repo_id,
            "pr_number": pr_number,
            "commit_hash": commit_hash,
            "files": ["pytorch_model.bin", "config.json", "vocab.json", "tokenizer.json"]  # 示例文件
        }

    def generate_download_links(pr_info, file_pattern=None):
        """生成文件的下载链接"""
        base_url = "https://hf-mirror.com"  # 使用国内镜像
        repo_id = pr_info["repo_id"]
        commit_hash = pr_info["commit_hash"]
        
        download_links = []
        
        for filename in pr_info["files"]:
            if file_pattern and file_pattern not in filename:
                continue
                
            # 构造文件下载URL
            file_url = f"{base_url}/{repo_id}/resolve/{commit_hash}/{filename}"
            download_links.append(file_url)
        
        return download_links

    def download_with_aria2(download_links, output_dir, threads=10):
        """使用aria2下载文件"""
        if not download_links:
            print("没有找到要下载的文件")
            return False
        
        # 创建输出目录
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 创建临时文件保存下载链接
        links_file = Path("/tmp/hf_download_links.txt")
        with open(links_file, "w") as f:
            for link in download_links:
                f.write(f"{link}\n")
        
        # 构建aria2命令
        aria2_cmd = [
            "aria2c",
            "-i", str(links_file),           # 输入文件
            "-d", output_dir,                # 下载目录
            "-x", str(threads),             # 每个文件的最大连接数
            "-s", str(threads),             # 每个文件拆分成多个连接
            "-j", str(min(threads, 5)),     # 最大并行下载数
            "--continue=true",              # 启用断点续传
            "--max-tries=5",                # 最大重试次数
            "--retry-wait=10",              # 重试等待时间
            "--timeout=300",                # 超时时间
            "--connect-timeout=10",         # 连接超时
            "--check-certificate=false",    # 不检查证书（加速）
            "--auto-file-renaming=false",   # 禁用自动重命名
            "--allow-overwrite=true"        # 允许覆盖
        ]
        
        print(f"开始下载 {len(download_links)} 个文件到 {output_dir}")
        print(f"使用命令: {' '.join(aria2_cmd)}")
        
        try:
            # 设置环境变量使用镜像站
            env = os.environ.copy()
            env["HF_ENDPOINT"] = "https://hf-mirror.com"
            
            # 执行下载命令
            result = subprocess.run(aria2_cmd, env=env, check=True)
            
            # 清理临时文件
            links_file.unlink(missing_ok=True)
            
            print("✓ 下载完成！")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ 下载失败: {e}")
            return False

    def main():
        parser = argparse.ArgumentParser(description="下载Hugging Face模型PR权重")
        parser.add_argument("repo_id", help="模型仓库ID，如: tencent/HunyuanVideo")
        parser.add_argument("pr_number", type=int, help="PR编号，如: 18")
        parser.add_argument("-o", "--output", default="./download", help="输出目录")
        parser.add_argument("-t", "--threads", type=int, default=10, help="下载线程数")
        parser.add_argument("-f", "--file-pattern", help="文件模式过滤")
        parser.add_argument("--no-mirror", action="store_true", help="不使用镜像站")
        
        args = parser.parse_args()
        
        # 检查aria2是否安装
        if not check_aria2_installed():
            print("aria2未安装，尝试自动安装...")
            if not install_aria2():
                print("请手动安装aria2后重试")
                sys.exit(1)
        
        # 设置镜像站（除非用户明确指定不使用）
        if not args.no_mirror:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            print("使用镜像站: https://hf-mirror.com")
        
        try:
            # 获取PR文件信息
            pr_info = get_pr_files(args.repo_id, args.pr_number, args.file_pattern)
            
            # 生成下载链接
            download_links = generate_download_links(pr_info, args.file_pattern)
            
            if not download_links:
                print("没有找到匹配的文件")
                return
            
            print(f"找到 {len(download_links)} 个文件:")
            for link in download_links:
                print(f"  - {link.split('/')[-1]}")
            
            # 执行下载
            success = download_with_aria2(download_links, args.output, args.threads)
            
            if success:
                print(f"\n文件已下载到: {args.output}")
            else:
                print("下载失败")
                sys.exit(1)
                
        except KeyboardInterrupt:
            print("\n用户中断下载")
            sys.exit(1)
        except Exception as e:
            print(f"发生错误: {e}")
            sys.exit(1)

    if __name__ == "__main__":
        main()

