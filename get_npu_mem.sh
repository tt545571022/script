#!/bin/bash

# 循环获取 NPU 12-15 的内存使用情况
while true; do
    # 获取当前时间
    current_time=$(date '+%Y-%m-%d %H:%M:%S')
    
    # 使用 npu-smi info 获取信息
    npu_info=$(npu-smi info 2>/dev/null)
    
    # 提取各 NPU 卡的内存使用情况 (HBM-Usage 已使用部分)
    # 根据行号精确提取数据
    npu12_mem=$(echo "$npu_info" | sed -n '/|\s*12\s\+.*910B2C/{n;p;}' | awk '{print $10}' | cut -d'/' -f1)
    npu13_mem=$(echo "$npu_info" | sed -n '/|\s*13\s\+.*910B2C/{n;p;}' | awk '{print $10}' | cut -d'/' -f1)
    npu14_mem=$(echo "$npu_info" | sed -n '/|\s*14\s\+.*910B2C/{n;p;}' | awk '{print $10}' | cut -d'/' -f1)
    npu15_mem=$(echo "$npu_info" | sed -n '/|\s*15\s\+.*910B2C/{n;p;}' | awk '{print $10}' | cut -d'/' -f1)
    
    # 如果提取结果为空，则设为0
    [ -z "$npu12_mem" ] && npu12_mem=0
    [ -z "$npu13_mem" ] && npu13_mem=0
    [ -z "$npu14_mem" ] && npu14_mem=0
    [ -z "$npu15_mem" ] && npu15_mem=0
    
    # 输出结果: 当前时间 npu12_memory npu13_memory npu14_memory npu15_memory
    echo "$current_time $npu12_mem $npu13_mem $npu14_mem $npu15_mem"
    
    # 等待1秒钟再进行下一次查询
    # sleep 1
done