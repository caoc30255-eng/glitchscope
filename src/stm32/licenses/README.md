# 第三方来源

`keil/rte/device/stm32f103c8` 的启动、系统时钟和配置文件来自原交接工程/Keil.STM32F1xx_DFP 2.4.1，原版权头保留。启动文件只调整栈 0x800 和堆 0。
CMSIS / STM32 寄存器头由安装的软件包提供，不复制进本源码包；使用与交接环境相同的软件包并遵循其中许可证。
新增 src/image_stream、src/main 和事件测试为本任务实现；src/image_protocol 从阶段 0–2 代码继承，增加完整候选头解析入口以支持安全 M=0 回报。
