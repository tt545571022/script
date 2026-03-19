# Scripts

工具脚本集合，主要用于 Ascend NPU 环境下的模型下载、容器管理、性能测试与调试。

---

## 目录

| 脚本 | 类型 | 简介 |
|------|------|------|
| [Lmodelhub.py](#lmodelhubpy) | Python | 统一模型下载器（HuggingFace / ModelScope / Modelers） |
| [docker.sh](#dockersh) | Shell | 启动 vllm-ascend Docker 容器 |
| [fix_vscode_cli.sh](#fix_vscode_clish) | Shell | 修复 VS Code CLI 连接问题 |
| [get_npu_mem.sh](#get_npu_memsh) | Shell | 实时监控 NPU 显存占用 |
| [install_docker_vscode.sh](#install_docker_vscodesh) | Shell | 将宿主机 VS Code Server 复制到容器 |
| [my_utils.py](#my_utilspy) | Python | PyTorch / Ascend NPU 调试工具库 |
| [profiler.py](#profilerpy) | Python | torch_npu Profiler 封装函数 |
| [query_docker.sh](#query_dockersh) | Shell | 查询/终止占用 NPU 的 Docker 进程 |
| [random_test.sh](#random_testsh) | Shell | 单次 vllm 随机数据集性能测试 |
| [result.sh](#resultsh) | Shell | 从测试结果 JSON 提取核心指标到 CSV |
| [run.sh](#runsh) | Shell | 批量运行多组性能测试参数 |
| [run_bench_hci.sh](#run_bench_hcish) | Shell | HCI 环境批量性能测试（GLM-5） |
| [run_test.sh](#run_testsh) | Shell | 指定模型与端口的标准性能测试入口 |

---

## Lmodelhub.py

统一模型仓库下载工具，支持三大平台，通过 URL 或 `owner/repo` 简写自动识别平台。

**支持平台：** HuggingFace、ModelScope、Modelers（modelers.cn）

**功能特性：**
- 自动识别平台，无需手动指定
- 支持指定 `--revision` 或 `--pr`（PR 号优先级更高）
- 递归遍历含子目录的仓库
- 生成 manifest JSON、aria2 输入文件、SHA256 文件、目录树
- 默认调用 aria2c 执行多线程下载，`--dry-run` 可跳过实际下载
- 支持华为镜像站 `hf-mirror.com`（默认开启，`--no-hf-mirror` 关闭）

**用法：**

```bash
# 下载 HuggingFace 模型（自动走镜像站）
python3 Lmodelhub.py Qwen/Qwen2.5-7B-Instruct

# 下载 ModelScope 模型，指定输出目录
python3 Lmodelhub.py https://www.modelscope.cn/Qwen/Qwen2.5-7B-Instruct -o /data/models

# 下载 Modelers 模型，指定 revision
python3 Lmodelhub.py https://modelers.cn/MooreThreads/MTel-8B -r main

# 仅列出文件，不下载
python3 Lmodelhub.py Qwen/Qwen2.5-7B-Instruct --dry-run

# 过滤文件名，仅下载 safetensors
python3 Lmodelhub.py Qwen/Qwen2.5-7B-Instruct -f safetensors
```

**完整参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `repo` | 仓库 URL 或 `owner/repo` | 必填 |
| `-o, --output` | 下载根目录 | `./downloads` |
| `-r, --revision` | 指定分支/tag/commit | 平台默认分支 |
| `--pr` | 指定 PR 号（覆盖 `--revision`） | - |
| `-f, --filter` | 过滤文件名（子字符串匹配） | - |
| `-t, --threads` | aria2c 并发线程数 | 16 |
| `--token` | API Token（私有仓库） | - |
| `--dry-run` | 仅列出文件，不下载 | False |
| `--no-hf-mirror` | 关闭 HF 镜像站加速 | False |
| `--max-files` | 限制最大处理文件数 | - |

---

## docker.sh

启动 vllm-ascend 容器，挂载 Ascend NPU 设备（davinci0–15）及相关驱动目录。

**主要配置：**
- 容器名：`tjl-lmcahce1501`
- 镜像：`quay.io/ascend/vllm-ascend:v0.15.0rc1`（可在文件顶部切换）
- 共享内存：500 GB
- 挂载：`/home/tjl`、`/data`、`/data2/weights`、Ascend 驱动目录

**用法：**

```bash
bash docker.sh
```

修改文件顶部的 `name` 和 `image` 变量可切换容器名称和镜像版本。

---

## fix_vscode_cli.sh

修复 VS Code CLI 连接问题（`Unable to connect to VS Code server`）。

脚本自动扫描 `/run/user/<uid>`、`/tmp` 等目录，找到最新的 `vscode-ipc-*.sock` 文件并设置 `VSCODE_IPC_HOOK_CLI` 环境变量。

**用法：**

```bash
# 当前 shell 生效（推荐）
source fix_vscode_cli.sh

# 仅本次运行（环境变量不保留到父 shell）
bash fix_vscode_cli.sh
```

---

## get_npu_mem.sh

实时循环打印 NPU 12–15（Ascend 910B2C）的 HBM 内存使用量（MB）。

**输出格式：**

```
2025-01-01 12:00:00  1024  2048  0  512
```

每列依次为：时间戳、NPU12 显存、NPU13、NPU14、NPU15（单位 MB）。

**用法：**

```bash
bash get_npu_mem.sh
# 或重定向记录到文件
bash get_npu_mem.sh | tee npu_mem.log
```

---

## install_docker_vscode.sh

将宿主机上已安装的 VS Code Server 复制到指定 Docker 容器，无需在容器内重新下载。适用于容器无法访问外网的场景。

**用法：**

```bash
# 自动选最新版本
bash install_docker_vscode.sh <容器名>

# 指定 commit_id
bash install_docker_vscode.sh <容器名> <commit_id>

# 示例
bash install_docker_vscode.sh tjl-lmcache1501
```

---

## my_utils.py

PyTorch / Ascend NPU 调试工具库，作为模块 import 使用。

**提供的工具函数：**

| 函数 | 功能 |
|------|------|
| `activation_hook` | 捕获并打印各层激活值的内存大小 |
| `register_activation_hooks(model)` | 为模型所有层批量注册 hook |
| `print_memory_stats()` | 打印当前 NPU 已分配/保留内存（含调用位置） |
| `print_tensor_size(tensor, shift)` | 打印 Tensor 的 dtype、shape 及内存占用（支持 B/KB/MB/GB） |
| `print_debug(info, with_stack)` | 带 PID 和代码位置的调试输出，可附带调用栈 |

**示例：**

```python
from my_utils import print_tensor_size, print_debug
import torch

x = torch.randn(1024, 4096, dtype=torch.float16)
print_tensor_size(x, shift='MB')  # Tensor dtype: torch.float16, shape: ..., size: 8.00 MB
print_debug("checkpoint reached", with_stack=False)
```

---

## profiler.py

`torch_npu.profiler` 的封装函数，一行代码为任意函数开启 Ascend NPU profiling。

策略：`skip_first=1, warmup=1, active=1`（共运行 4 次迭代，取第 3 次采集数据）。

**用法：**

```python
from profiler import profiler

def my_forward(x, y):
    return x @ y

result = profiler(my_forward, x, y, profiler_level=1, save_path='./prof_out')
```

profiling 结果保存为 TensorBoard 可读的 trace 格式，可用 `tensorboard --logdir ./prof_out` 查看。

---

## query_docker.sh

列出当前占用 NPU/GPU 资源的进程及其所属 Docker 容器，支持 Ascend（`npu-smi`）和 NVIDIA（`nvidia-smi`）双平台。

**特性：**
- 自动检测 `npu-smi` / `nvidia-smi`
- 通过 `/proc/<pid>/cgroup` 零 fork 解析容器归属
- 后台并行执行 `smi`、`docker ps`、`ps -e`，减少等待时间
- 支持 `-k/--kill` 终止指定容器的所有 NPU 占用进程

**用法：**

```bash
# 列出所有占用 NPU 的进程
bash query_docker.sh

# 终止指定容器的所有 NPU 进程
bash query_docker.sh -k tjl-lmcache1501
```

---

## random_test.sh

调用 `vllm bench serve` 对在线服务进行单次随机数据集性能测试，输出 TTFT、TPOT、吞吐量等指标并保存 JSON 结果。

**用法：**

```bash
bash random_test.sh <request_rate> <max_concurrency> <num_prompts> <input_len> <output_len>

# 示例：并发32，300条请求，输入1024 tokens，输出512 tokens
bash random_test.sh 32 32 300 1024 512
```

---

## result.sh

遍历指定目录下的所有 JSON 测试结果文件，提取核心性能指标并汇总为 `core_metrics.csv`。

**提取指标：** 总输入 tokens、总输出 tokens、测试时长、输出吞吐量、Mean TTFT、Mean TPOT、Mean ITL

**用法：**

```bash
bash result.sh <结果目录>

# 示例
bash result.sh /workspace/outputs/GLM-4.7-W8A8
# 输出: /workspace/outputs/GLM-4.7-W8A8/core_metrics.csv
```

---

## run.sh

使用预定义的多组参数组合批量调用 `random_test.sh`，覆盖从短序列（128/128）到长序列（8192/8192）的各种场景。

**参数格式：** `request_rate max_concurrency num_prompts input_len output_len`

**用法：**

```bash
bash run.sh
```

---

## run_bench_hci.sh

HCI（超融合）环境专用批量测试脚本，默认针对 GLM-5 模型（`/date/GLM/GLM-5-w4a8`，端口 8077）。

与 `run.sh` 类似，但在文件头部集中配置了模型路径、服务名称和端口，更适合在固定测试环境中复用。

**用法：**

```bash
bash run_bench_hci.sh
```

修改文件顶部的 `model_path`、`svc_model_name`、`port` 变量可适配不同模型。

---

## run_test.sh

通用性能测试入口脚本，通过命令行参数指定模型名称和端口，温度固定为 0.65，自动运行多套参数组合。

**用法：**

```bash
bash run_test.sh --model <模型名> --port <端口号>

# 示例
bash run_test.sh --model Qwen3-32B --port 4567
bash run_test.sh --model GLM-4.7-W8A8 --port 8077
```

---

## 环境依赖

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | Lmodelhub.py、my_utils.py、profiler.py |
| `requests` | Lmodelhub.py API 请求 |
| `aria2c` | Lmodelhub.py 文件下载 |
| `torch` + `torch_npu` | my_utils.py、profiler.py |
| `npu-smi` | get_npu_mem.sh、query_docker.sh（Ascend） |
| `docker` | docker.sh、install_docker_vscode.sh、query_docker.sh |
| `vllm` | random_test.sh、run.sh、run_bench_hci.sh、run_test.sh |
