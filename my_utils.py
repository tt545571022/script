import torch, torch_npu
import sys
import os
from datetime import datetime

B2C = 65452113920
B4 = 31662800896

KB = 1024
MB = KB * 1024
GB = MB * 1024


def activation_hook(module, input, output):
    """
    Hook function to capture and print the memory size of activations.
    """
    print(f"Layer: {module.__class__.__name__}")
    if isinstance(output, tuple):  # Check if output is a tuple
        for idx, tensor in enumerate(output):
            print(f"Output {idx + 1}:")
            print_tensor_size(tensor, shift='MB')
    elif isinstance(output, dict):  # Check if output is a dictionary
        for key, value in output.items():
            print(f"Key: {key}")
            print_tensor_size(value, shift='MB')
    else:
        print_tensor_size(output, shift='MB')


def register_activation_hooks(model):
    """
    Register activation hooks for all modules in the model.
    """
    for name, module in model.named_modules():
        module.register_forward_hook(activation_hook)


def print_memory_stats():
    return 
    torch.npu.synchronize()
    allocated = torch_npu.npu.memory_allocated()
    reserved = torch_npu.npu.memory_reserved()
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    caller_info = "unknown"
    try:
        frame = sys._getframe(1)
        caller_info = f"{frame.f_code.co_filename}:{frame.f_lineno} {frame.f_code.co_name}"
    except ValueError:
        pass
    finally:
        if 'frame' in locals():
            del frame
    print(
        f"[MEM {timestamp}] caller: {caller_info}, allocated: {allocated:,}, reserved: {reserved:,}",
        flush=True,
    )


def print_tensor_size(tensor: torch.Tensor, shift: str = 'B'):
    shift = shift.upper()
    if shift == 'B':
        shift_value = 1
    elif shift == 'KB':
        shift_value = KB
    elif shift == 'MB':
        shift_value = MB
    elif shift == 'GB':
        shift_value = GB
    else:
        raise ValueError(f"Invalid shift: {shift}")
    tensor_size = tensor.element_size() * tensor.nelement() / shift_value
    print(f"Tensor dtype: {tensor.dtype}, shape: {tensor.shape}, size: {tensor_size:.2f} {shift}")

def print_debug(info: str, with_stack: bool = False):
    # return
    pid = os.getpid()
    caller = sys._getframe(1)
    print(f"[TJL_DEBUG {pid} {caller.f_code.co_filename}:{caller.f_lineno}]: {info}", flush=True)
    if with_stack:
        frame = sys._getframe(1)
        while frame:
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            function = frame.f_code.co_name
            print(f'[{pid}] {filename}:{lineno} , in {function}')
            frame = frame.f_back

def _debug_arg(name: str, value) -> None:
    # return
    """Print debug information for tensors or plain values."""
    prefix = f"[TJL-DEBUG][{__file__}:{sys._getframe(1).f_lineno}]"
    if value is None:
        print(f"{prefix} {name}: None", flush=True)
        return
    if isinstance(value, torch.Tensor):
        try:
            shape = tuple(value.shape)
            strides = tuple(value.stride())
            print(
                f"{prefix} {name}: shape={shape}, dtype={value.dtype}, "
                f"device={value.device}, contiguous={value.is_contiguous()}, layout={value.layout}, strides={strides}",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - debug only
            print(f"{prefix} Failed to log {name}: {exc}", flush=True)
    else:
        print(f"{prefix} {name}: {value}", flush=True)