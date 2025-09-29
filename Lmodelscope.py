import requests
import json
import argparse
import re
import os
import sys
import urllib.parse
import traceback
import platform
import time
import hashlib
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用SSL警告
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def safe_filename(name):
    """创建安全的文件名，移除无效字符"""
    if platform.system() == "Windows":
        illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
        name = re.sub(illegal_chars, '_', name)
    return name[:200].strip()

def print_readme():
    """打印使用说明"""
    readme_content = """
==============================================================================================================
README
--------------------------------------------------------------------------------------------------------------
1. 该工具使用方法：Lmodelscope.py [模型链接]
2. 可以添加-p参数来指定本地路径，生成的文件将会保存至该路径中。
3. 如要下载模型，可使用aria2下载，命令如下：
   aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -d <模型目录> -i *url.txt
   注意：必须使用-d参数指定下载目录，才能保持文件夹结构！
4. 若要校验全部文件，在模型文件夹下使用如下命令：sha256sum -c *sha256.txt
5. 若要校验指定文件，file_name=[file_name]; sha256sum ${file_name}; grep  ${file_name} *sha256.txt
6. 使用aria2c下载时，需要对应的第三方库，可以使用`pip install aria2`安装

【重要更新】现在生成的URL文件包含完整的目录结构信息，下载时使用-d参数指定根目录即可保持原有文件夹结构
==============================================================================================================
"""
    print(readme_content)

def parse_arguments():
    """解析命令行参数"""
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(
        description='获取ModelScope模型文件列表',
        formatter_class=argparse.RawTextHelpFormatter,  # 保留格式
        add_help=False  # 禁用默认的help选项
    )

    # 添加自定义帮助选项
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                       help='显示帮助信息并退出')

    # 添加其他参数
    parser.add_argument('model_url', type=str, nargs='?', help='ModelScope模型链接')
    parser.add_argument('-p', '--save_path', type=str, default='./',
                        help='输出文件保存路径，默认为当前目录')
    parser.add_argument('-d', '--direct-download', action='store_true',
                        help='直接下载模式（自动下载所有文件）')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='并发下载工作线程数（默认：4）')

    # 检查参数数量
    if len(sys.argv) == 1:
        print_readme()
        parser.print_help()
        sys.exit(0)

    # 解析命令行参数
    args = parser.parse_args()

    # 如果请求帮助信息
    if any(help_arg in sys.argv for help_arg in ['-h', '--help']):
        print_readme()
        parser.print_help()
        sys.exit(0)

    return args

def parse_model_url(model_url):
    """解析ModelScope URL，提取namespace和model_name"""
    try:
        parsed = urllib.parse.urlparse(model_url)
        path_segments = parsed.path.strip('/').split('/')

        namespace, model_name = None, None

        if len(path_segments) >= 3 and path_segments[0] == "models":
            namespace = path_segments[1]
            model_name = path_segments[2]

        # 支持短链接格式
        if not namespace or not model_name:
            match = re.search(r"models/([^/]+)/([^/?]+)", model_url)
            if match:
                namespace = match.group(1)
                model_name = match.group(2)

        # 使用assert验证解析结果
        assert namespace and model_name, f"❌ 无法解析模型URL: {model_url}\n请使用类似格式: https://www.modelscope.cn/models/namespace/model_name"

        namespace = safe_filename(namespace)
        model_name = safe_filename(model_name)

        print(f"📦 命名空间: {namespace}")
        print(f"🖥️ 模型名称: {model_name}")

        return namespace, model_name

    except Exception as e:
        print(f"URL解析错误: {str(e)}")
        traceback.print_exc()
        raise  # 重新抛出异常

def get_all_files_recursive(session, namespace, model_name, root_path=""):
    """
    递归获取模型仓库中的所有文件（包括子文件夹）
    
    Args:
        session: requests会话对象
        namespace: 命名空间
        model_name: 模型名称
        root_path: 当前递归的根路径
    
    Returns:
        list: 包含所有文件信息的列表
    """
    api_url = f"https://www.modelscope.cn/api/v1/models/{namespace}/{model_name}/repo/files"
    params = {"Revision": "master", "Root": root_path}
    
    try:
        response = session.get(api_url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("Success", True):
            error_msg = data.get("Message", "未知错误")
            raise ValueError(f'API返回错误: {error_msg}')
        
        all_files = []
        
        for item in data['Data']['Files']:
            if item.get("Type") == "tree":  # 如果是目录，递归获取
                print(f"📁 发现子目录: {item['Path']}")
                try:
                    subdir_files = get_all_files_recursive(session, namespace, model_name, item['Path'])
                    all_files.extend(subdir_files)
                except Exception as subdir_error:
                    print(f"⚠️ 跳过子目录 {item['Path']}: {str(subdir_error)}")
                    continue
            elif item.get("Type") == "blob":  # 如果是文件，添加到列表
                all_files.append(item)
        
        return all_files
        
    except requests.exceptions.Timeout:
        print(f"❌ 获取路径 {root_path} 的文件列表超时")
        raise
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络错误获取路径 {root_path}: {str(e)}")
        raise
    except Exception as e:
        print(f"❌ 获取路径 {root_path} 的文件列表失败: {str(e)}")
        raise

def create_local_directories(file_paths, base_dir):
    """
    在下载前创建所有必要的本地目录结构
    
    Args:
        file_paths: 所有文件的路径列表
        base_dir: 基础目录路径
    """
    try:
        # 收集所有需要创建的目录
        dirs_to_create = set()
        for file_path in file_paths:
            dir_path = os.path.dirname(file_path)
            if dir_path:  # 跳过根目录
                full_dir_path = os.path.join(base_dir, dir_path)
                dirs_to_create.add(full_dir_path)
        
        # 创建目录
        for dir_path in sorted(dirs_to_create):
            os.makedirs(dir_path, exist_ok=True)
            # 设置目录权限（755）
            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        
        print(f"✅ 已创建 {len(dirs_to_create)} 个本地目录")
        
    except Exception as e:
        print(f"❌ 创建本地目录失败: {str(e)}")
        raise

def verify_file_integrity(file_path, expected_sha256):
    """
    验证文件完整性
    
    Args:
        file_path: 文件路径
        expected_sha256: 预期的SHA256值
    
    Returns:
        bool: 验证是否通过
    """
    try:
        if not os.path.exists(file_path):
            return False
        
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        actual_sha256 = sha256_hash.hexdigest()
        return actual_sha256 == expected_sha256
        
    except Exception as e:
        print(f"❌ 文件完整性验证失败 {file_path}: {str(e)}")
        return False

def download_file_with_retry(session, download_url, local_path, expected_sha256, max_retries=3):
    """
    带重试机制的文件下载函数
    
    Args:
        session: requests会话
        download_url: 下载URL
        local_path: 本地保存路径
        expected_sha256: 预期的SHA256值
        max_retries: 最大重试次数
    
    Returns:
        bool: 下载是否成功
    """
    for attempt in range(max_retries + 1):
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 下载文件
            response = session.get(download_url, stream=True, timeout=300)
            response.raise_for_status()
            
            # 计算下载大小
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 显示下载进度
                        if total_size > 0:
                            percent = (downloaded_size / total_size) * 100
                            print(f"📥 下载进度: {os.path.basename(local_path)} - {percent:.1f}%", end='\r')
            
            # 验证文件完整性
            if verify_file_integrity(local_path, expected_sha256):
                # 设置文件权限（644）
                os.chmod(local_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                print(f"✅ 下载完成: {local_path}")
                return True
            else:
                print(f"❌ 文件校验失败: {local_path}")
                # 删除损坏的文件
                if os.path.exists(local_path):
                    os.remove(local_path)
                
        except Exception as e:
            print(f"❌ 下载失败 (尝试 {attempt + 1}/{max_retries + 1}): {local_path} - {str(e)}")
            
            # 删除可能损坏的文件
            if os.path.exists(local_path):
                os.remove(local_path)
            
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 指数退避
                print(f"⏳ 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"❌ 达到最大重试次数，放弃下载: {local_path}")
    
    return False

def get_model_files(namespace, model_name, save_path='./'):
    """获取模型文件列表（支持文件夹结构）并生成三种输出文件"""
    # 创建会话
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    })

    try:
        print("🔍 开始递归获取模型仓库文件结构...")
        
        # 递归获取所有文件
        all_files = get_all_files_recursive(session, namespace, model_name)
        
        if not all_files:
            raise ValueError("未找到任何文件，请检查模型仓库是否为空或权限设置")
        
        print(f"✅ 成功获取文件结构，共发现 {len(all_files)} 个文件")
        
        # 确定模型目录
        save_path = os.path.abspath(save_path)
        if os.path.basename(save_path) == model_name:
            model_dir = save_path
        else:
            model_dir = os.path.join(save_path, f"{namespace}_{model_name}")

        # 创建基础目录
        os.makedirs(model_dir, exist_ok=True)
        
        # 创建所有必要的子目录结构
        file_paths = [file_info['Path'] for file_info in all_files if file_info.get("Type") == "blob"]
        create_local_directories(file_paths, model_dir)

        # 定义输出文件
        json_file = os.path.join(model_dir, f"{model_name}_files.json")
        url_file = os.path.join(model_dir, f"{model_name}_url.txt")
        sha_file = os.path.join(model_dir, f"{model_name}_sha256.txt")
        dir_structure_file = os.path.join(model_dir, f"{model_name}_directory_structure.txt")

        # 1. 保存完整的文件列表JSON
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({"Data": {"Files": all_files}}, f, indent=2, ensure_ascii=False)

        # 生成下载基础URL
        base_url = f"https://www.modelscope.cn/api/v1/models/{namespace}/{model_name}/repo?Revision=master"

        # 2. 生成URL文件、SHA256文件和目录结构文件
        with open(url_file, "w", encoding="utf-8") as f_url, \
             open(sha_file, "w", encoding="utf-8") as f_sha, \
             open(dir_structure_file, "w", encoding="utf-8") as f_dir:

            # 写入目录结构头信息
            f_dir.write(f"模型仓库目录结构: {namespace}/{model_name}\n")
            f_dir.write("=" * 50 + "\n")
            
            # 按目录分组文件，用于生成目录结构
            dir_structure = {}
            for file_info in all_files:
                file_path = file_info['Path']
                dir_path = os.path.dirname(file_path)
                filename = os.path.basename(file_path)
                
                if dir_path not in dir_structure:
                    dir_structure[dir_path] = []
                dir_structure[dir_path].append(filename)
                
                # 只处理文件（blob类型）
                if file_info.get("Type") == "blob":
                    sha256 = file_info.get("Sha256", "").strip()
                    if sha256:
                        # 生成下载链接
                        quoted_path = urllib.parse.quote(file_path)
                        download_url = f"{base_url}&FilePath={quoted_path}"

                        # 写入URL文件（包含out参数指定保存路径）
                        f_url.write(f"{download_url}\n")
                        f_url.write(f"  out={file_path}\n")
                        f_url.write(f"  dir={model_dir}\n\n")

                        # 写入SHA256文件（包含完整路径）
                        f_sha.write(f"{sha256}\t{file_path}\n")

            # 生成目录结构树
            f_dir.write("\n目录结构:\n")
            for dir_path in sorted(dir_structure.keys()):
                # 根目录显示为 "."
                display_path = dir_path if dir_path else "."
                f_dir.write(f"\n{display_path}/\n")
                for filename in sorted(dir_structure[dir_path]):
                    f_dir.write(f"    ├── {filename}\n")

        # 3. 生成专门的Aria2输入文件（兼容旧格式）
        aria2_input_file = os.path.join(model_dir, f"{model_name}_aria2_input.txt")
        with open(aria2_input_file, "w", encoding="utf-8") as f_aria2:
            for file_info in all_files:
                if file_info.get("Type") == "blob":
                    file_path = file_info['Path']
                    sha256 = file_info.get("Sha256", "").strip()
                    if sha256:
                        quoted_path = urllib.parse.quote(file_path)
                        download_url = f"{base_url}&FilePath={quoted_path}"
                        
                        # Aria2输入文件格式：每行包含URL和参数
                        f_aria2.write(f"{download_url}\n")
                        f_aria2.write(f"  out={file_path}\n")
                        f_aria2.write(f"  checksum=sha-256={sha256}\n\n")

        # 4. 生成批量下载脚本
        download_script_file = os.path.join(model_dir, f"{model_name}_download.py")
        with open(download_script_file, "w", encoding="utf-8") as f_script:
            f_script.write(f'''#!/usr/bin/env python3
# {model_name} 批量下载脚本
# 自动生成于: {time.strftime("%Y-%m-%d %H:%M:%S")}

import os
import sys
import requests
import hashlib
import stat
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def verify_file_integrity(file_path, expected_sha256):
    """验证文件完整性"""
    try:
        if not os.path.exists(file_path):
            return False
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest() == expected_sha256
    except:
        return False

def download_file(args):
    """下载单个文件"""
    session, download_url, local_path, expected_sha256, max_retries = args
    for attempt in range(max_retries + 1):
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            response = session.get(download_url, stream=True, timeout=300)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
            
            if verify_file_integrity(local_path, expected_sha256):
                os.chmod(local_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                return True, local_path
            else:
                if os.path.exists(local_path):
                    os.remove(local_path)
        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return False, local_path

# 下载任务列表
download_tasks = [
''')
            
            # 写入下载任务
            for file_info in all_files:
                if file_info.get("Type") == "blob":
                    file_path = file_info['Path']
                    sha256 = file_info.get("Sha256", "").strip()
                    if sha256:
                        quoted_path = urllib.parse.quote(file_path)
                        download_url = f"{base_url}&FilePath={quoted_path}"
                        f_script.write(f"    ('{download_url}', '{file_path}', '{sha256}'),\n")
            
            f_script.write(''']

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    session = requests.Session()
    session.verify = False
    
    # 准备下载参数
    download_args = []
    for url, file_path, sha256 in download_tasks:
        local_path = os.path.join(base_dir, file_path)
        download_args.append((session, url, local_path, sha256, 3))
    
    print(f"开始下载 {len(download_args)} 个文件...")
    
    # 使用线程池并行下载
    successful_downloads = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_args = {executor.submit(download_file, args): args for args in download_args}
        
        for future in as_completed(future_to_args):
            args = future_to_args[future]
            success, file_path = future.result()
            if success:
                successful_downloads += 1
                print(f"✅ 下载成功: {file_path}")
            else:
                print(f"❌ 下载失败: {file_path}")
    
    print(f"\\n下载完成: {successful_downloads}/{len(download_tasks)} 个文件成功")
    
    # 生成校验脚本
    verify_script = os.path.join(base_dir, "verify_downloads.sh")
    with open(verify_script, "w") as f:
        f.write("#!/bin/bash\\n")
        f.write(f"# {model_name} 文件校验脚本\\n")
        f.write("echo '开始校验文件完整性...'\\n")
        for file_info in all_files:
            if file_info.get("Type") == "blob":
                file_path = file_info['Path']
                sha256 = file_info.get("Sha256", "").strip()
                if sha256:
                    f.write(f"echo '校验: {file_path}'\\n")
                    f.write(f"echo '{sha256}  {file_path}' | sha256sum -c -\\n")
        f.write("echo '校验完成!'\\n")
    
    os.chmod(verify_script, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    print(f"校验脚本已生成: {verify_script}")

if __name__ == "__main__":
    main()
''')
        
        # 设置下载脚本权限
        os.chmod(download_script_file, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)

        print(f"✅ 请求成功! 文件总数: {len(all_files)}")
        print(f"📁 模型目录: {model_dir}")
        print(f"💾 完整文件列表已保存至: {json_file}")
        print(f"🔗 下载链接已保存至: {url_file}")
        print(f"🔐 SHA256校验文件已保存至: {sha_file}")
        print(f"📂 目录结构图已保存至: {dir_structure_file}")
        print(f"🚀 Aria2专用输入文件已保存至: {aria2_input_file}")
        print(f"🐍 Python批量下载脚本已保存至: {download_script_file}")
        
        # 显示目录结构统计
        file_count = len([f for f in all_files if f.get("Type") == "blob"])
        dir_count = len([f for f in all_files if f.get("Type") == "tree"])
        print(f"📊 统计: {file_count} 个文件, {dir_count} 个文件夹")
        
        # 重要的使用说明
        print("\n" + "="*80)
        print("📋 多种下载方式说明:")
        print("="*80)
        print("方法1（推荐）- Aria2c批量下载（保持目录结构）:")
        print(f'  aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -d "{model_dir}" -i {model_name}_aria2_input.txt')
        print("\n方法2 - Python脚本批量下载（自动重试和校验）:")
        print(f'  cd "{model_dir}" && python3 {model_name}_download.py')
        print("\n方法3 - 传统Aria2方式:")
        print(f'  cd "{model_dir}" && aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -i {model_name}_url.txt')
        print("\n方法4 - 手动校验下载文件:")
        print(f'  cd "{model_dir}" && bash verify_downloads.sh')
        print("\n💡 提示:")
        print("   • 方法1和2可以完美保持原始目录结构！")
        print("   • Python脚本提供自动重试和完整性校验")
        print("   • 所有本地目录结构已预先创建完成")
        
        return model_dir

    except Exception as e:
        error_msg = f"❌ 操作失败: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            error_msg += f"\n响应内容: {e.response.text[:200]}..."
        assert False, error_msg

def download_model_directly(namespace, model_name, save_path='./', max_workers=4):
    """
    直接下载模型文件（可选功能）
    
    Args:
        namespace: 命名空间
        model_name: 模型名称
        save_path: 保存路径
        max_workers: 最大并发下载数
    
    Returns:
        bool: 下载是否成功
    """
    try:
        print("🚀 开始直接下载模型文件...")
        
        # 获取文件列表
        session = requests.Session()
        session.verify = False
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        all_files = get_all_files_recursive(session, namespace, model_name)
        file_count = len([f for f in all_files if f.get("Type") == "blob"])
        
        if file_count == 0:
            print("❌ 未找到可下载的文件")
            return False
        
        # 确定模型目录
        save_path = os.path.abspath(save_path)
        model_dir = os.path.join(save_path, f"{namespace}_{model_name}")
        os.makedirs(model_dir, exist_ok=True)
        
        # 创建目录结构
        file_paths = [file_info['Path'] for file_info in all_files if file_info.get("Type") == "blob"]
        create_local_directories(file_paths, model_dir)
        
        # 准备下载任务
        download_tasks = []
        base_url = f"https://www.modelscope.cn/api/v1/models/{namespace}/{model_name}/repo?Revision=master"
        
        for file_info in all_files:
            if file_info.get("Type") == "blob":
                file_path = file_info['Path']
                sha256 = file_info.get("Sha256", "").strip()
                if sha256:
                    quoted_path = urllib.parse.quote(file_path)
                    download_url = f"{base_url}&FilePath={quoted_path}"
                    local_path = os.path.join(model_dir, file_path)
                    download_tasks.append((session, download_url, local_path, sha256, 3))
        
        print(f"📥 准备下载 {len(download_tasks)} 个文件...")
        
        # 并行下载
        successful_downloads = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {executor.submit(download_file_with_retry, *task): task for task in download_tasks}
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                success = future.result()
                if success:
                    successful_downloads += 1
                print(f"进度: {successful_downloads}/{len(download_tasks)}")
        
        success_rate = (successful_downloads / len(download_tasks)) * 100
        print(f"✅ 下载完成: {successful_downloads}/{len(download_tasks)} 文件 ({success_rate:.1f}%)")
        
        return successful_downloads == len(download_tasks)
        
    except Exception as e:
        print(f"❌ 直接下载失败: {str(e)}")
        return False

def main():
    try:
        # 解析命令行参数
        args = parse_arguments()
        
        if not args.model_url:
            print("❌ 请提供模型URL")
            sys.exit(1)

        print(f"🔍 正在处理模型链接: {args.model_url}")
        print(f"📂 保存路径: {args.save_path}")

        # 解析模型URL
        namespace, model_name = parse_model_url(args.model_url)

        # 检查是否启用直接下载模式
        if args.direct_download:
            # 直接下载模式
            success = download_model_directly(namespace, model_name, args.save_path, args.workers)
            if success:
                print("🎉 模型下载完成！")
            else:
                print("⚠️ 部分文件下载失败，请检查网络连接后重试")
        else:
            # 传统模式：生成下载文件
            model_dir = get_model_files(namespace, model_name, args.save_path)
            print("🎉 下载文件已生成完成！")

    except AssertionError as e:
        print(e.args[0] if e.args else str(e))
        sys.exit(1)
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print_readme()

if __name__ == "__main__":
    main()