import torch
import torch_npu

def profiler(func, *args, profiler_level=1, save_path='./out_prof', **kwargs):

    experimental_config = torch_npu.profiler._ExperimentalConfig(
        export_type=[
            torch_npu.profiler.ExportType.Text
            ],
        # profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
        profiler_level="Level"+str(profiler_level),
        msprof_tx=False,
        aic_metrics=torch_npu.profiler.AiCMetrics.AiCoreNone,
        l2_cache=False,
        op_attr=False,
        data_simplification=True,
        record_op_args=False,
        gc_detect_threshold=None
    )

    with torch_npu.profiler.profile(
        activities=[
            torch_npu.profiler.ProfilerActivity.CPU,
            torch_npu.profiler.ProfilerActivity.NPU
            ],
        schedule=torch_npu.profiler.schedule(wait=0, warmup=1, active=1, repeat=1, skip_first=1),
        on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(save_path),
        record_shapes=True if profiler_level > 0 else False,
        profile_memory=False,
        with_stack=True if profiler_level > 0 else False,
        with_modules=True if profiler_level > 0 else False,
        with_flops=False,
        experimental_config=experimental_config
    ) as prof:
        prof.start()
        for iter in range(4):
            print(f"iter: {iter}")
            res = func(*args, **kwargs)
            prof.step()
        prof.stop()
        return res

if __name__ == "__main__":
    device="npu"
    x = torch.randn(10, 10, dtype = torch.float16, device=device)
    y = torch.randn(10, 10, dtype = torch.float16, device=device)
    def test_func(x1, x2):
        return x1 * x2
    profiler(test_func, x, y, profiler_level=1)
