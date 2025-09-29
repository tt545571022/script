import requests
import json
import argparse
import re
import os
import sys
import urllib.parse
import traceback
import platform

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
        response = session.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("Success", True):
            error_msg = data.get("Message", "未知错误")
            raise ValueError(f'API返回错误: {error_msg}')
        
        all_files = []
        
        for item in data['Data']['Files']:
            if item.get("Type") == "tree":  # 如果是目录，递归获取
                print(f"📁 发现子目录: {item['Path']}")
                subdir_files = get_all_files_recursive(session, namespace, model_name, item['Path'])
                all_files.extend(subdir_files)
            elif item.get("Type") == "blob":  # 如果是文件，添加到列表
                all_files.append(item)
        
        return all_files
        
    except Exception as e:
        print(f"❌ 获取路径 {root_path} 的文件列表失败: {str(e)}")
        raise

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

        os.makedirs(model_dir, exist_ok=True)

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
            for file_info in all_files:
                file_path = file_info["Path"]
                file_url = f"{base_url}&FilePath={urllib.parse.quote(file_path)}"
                f_url.write(f"{file_url}\n")
                f_sha.write(f"{file_info.get('Sha256', '')}  {file_path}\n")
                f_dir.write(f"{file_path}\n")

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
                        # 关键修改：添加out参数，保持原始目录结构[1,7](@ref)
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
                        
                        # Aria2输入文件格式：每行包含URL和参数[7](@ref)
                        f_aria2.write(f"{download_url}\n")
                        f_aria2.write(f"  out={file_path}\n")

        print(f"✅ 请求成功! 文件总数: {len(all_files)}")
        print(f"📁 模型目录: {model_dir}")
        print(f"💾 完整文件列表已保存至: {json_file}")
        print(f"🔗 下载链接已保存至: {url_file}")
        print(f"🔐 SHA256校验文件已保存至: {sha_file}")
        print(f"📂 目录结构图已保存至: {dir_structure_file}")
        print(f"🚀 Aria2专用输入文件已保存至: {aria2_input_file}")
        
        # 显示目录结构统计
        file_count = len([f for f in all_files if f.get("Type") == "blob"])
        dir_count = len([f for f in all_files if f.get("Type") == "tree"])
        print(f"📊 统计: {file_count} 个文件, {dir_count} 个文件夹")
        
        # 重要的使用说明
        print("\n" + "="*60)
        print("📋 重要下载说明:")
        print("="*60)
        print("方法1（推荐）- 使用-d参数指定下载目录:")
        print(f'  aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -d "{model_dir}" -i {model_name}_aria2_input.txt')
        print("\n方法2 - 使用专门的输入文件:")
        print(f'  aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -i {model_name}_aria2_input.txt')
        print("\n方法3 - 传统方式（需进入模型目录）:")
        print(f'  cd "{model_dir}" && aria2c -j 4 -x 4 -s 4 -c --check-certificate=false -i {model_name}_url.txt')
        print("\n💡 提示: 使用方法1可以完美保持原始目录结构！")
        
        return model_dir

    except Exception as e:
        error_msg = f"❌ 操作失败: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            error_msg += f"\n响应内容: {e.response.text[:200]}..."
        assert False, error_msg

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

        # 获取模型文件（支持文件夹结构）
        model_dir = get_model_files(namespace, model_name, args.save_path)

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