---
name: rtl-reference-cosim
description: Create finite RTL versus software-reference regressions and inspect cycle-level mismatches. Use for stream/state-machine verification and simulator result review, not timing-signoff claims.
---

先写清时钟边沿、复位、输入驱动、输出采样及invalid周期保持值语义，再分别准备参考和RTL实际输出。

- 从[示例](README.md)建立独立仿真目录；不修改已打开的Vivado工程，不下载硬件。
- 黄金参考不读取待测RTL的输出。实际CSV必须来自待测实现，不能复制参考CSV冒充仿真。
- 用`compare_trace.py`流式比较全部周期，包括valid=0时的数据保持值、error和内部状态（按spec选择）。对X/Z、丢周期、重复周期和尾部截断明确失败。
- 分开记录编译、展开、仿真执行、逐周期比较和综合/时序结果。精确PASS标记与计数是必要检查，但仍要保留原日志和向量哈希。
- 接收器/采样器有未知初相时覆盖多个允许初态；仿真覆盖不消除真实硬件初态不确定性。
- 出错保留输入、第一处分歧和前后状态；按[排查说明](references/workflow.md)定位，不通过改黄金答案使失败消失。

优先运行run_simulation.py完成当前六场景384周期真实仿真和独立参考对照，再运行--inject-stall-bug确认错误确实被拒。分块SHA与逐行对比共同保持内存有界；工具退出码或历史日志都不替代当前CSV。
