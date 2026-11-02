# B接收器RTL对照：Vivado手动仿真入口

2026-10-22。第三功能的软件回放对照；热力图上板工作暂停。本包无综合、实现、bitstream、硬件管理器、板卡或串口操作。

## 直接运行

使用一个没有打开工程的 Vivado 窗口，在 Tcl Console 执行：

```tcl
source {/path/to/glitchscope_source/B_RX_RTL_Vivado_v0_2_2026-10-22/run_b_rx_cosim.tcl}
```

如果搬动本包，把路径改成解压后实际位置，保留花括号。需要保留 rtl、vectors、cases.txt 等完整目录，不要只复制 Tcl。若当前已有工程，脚本会拒绝；手动关闭工程或另开 Vivado 窗口再执行，不自动关闭或修改你正在用的工程。

脚本新建独立行为仿真工程，先把输入复制到仿真目录，再启动 XSim 并自动 run all。不必手动指定 ns。总仿真时间预计113922000 ns（约113.922 ms仿真时间），电脑实际耗时待你运行测得，不作时间承诺。每25个用例显示一次进度。

严格完成标记必须是：

```text
B_RX_RTL_COSIM_PASS cases=1125 cycles=11389950
B_RX_RTL_COSIM_LOG_READY_FOR_REVIEW cases=1125 cycles=11389950
```

1125个用例=350个合成输入用例（14组ds×25个NCO初相）+775个历史数字波形输入用例（31段×25个NCO初相，使用该段实际ds）。逐个100MHz周期比较rx_byte保持值、rx_valid、framing_error，以及NCO accumulator和clock-enable。约1139万个周期。NCO初相是仿真假设，不是已测得硬件初相。

脚本按最终标记和精确计数检查；打开仿真、编译成功或运行命令返回都不等于对照通过。出现B_RX_RTL_FAIL时保留现场，不修改预期向量来绕过。全程无综合或下载。

## 回传

把控制台打印的 B_RX_SIM_OUTPUT 目录下 scoreboard.log、simulate.log/xsim.log（如存在）、xvlog.log、xelab.log，以及 Tcl Console 最后的报错或完成文本发回。若launch阶段失败且没有scoreboard.log，回传整个对应build/run_*目录的日志。不要删掉失败目录或覆盖重跑；脚本再次运行会另建目录。

## 当前真实状态与边界

本包最新测试台已用本机Vivado2026.1的xvlog编译、xelab展开通过；Tcl仅做语法完整性检查，尚未在Vivado GUI实际执行。先前命令行XSim的仿真内核在DLL初始化阶段报0xC0000142，未执行测试台。本包的运行结果仍为PENDING_USER_VIVADO_RUN，不能预先判为PASS。

两个生产RTL文件与冻结参考逐字节一致。测试台仅增加文本scoreboard日志，未修改RTL或Python预期模型。vectors为此前固定Python模型生成，并逐份与vector_manifest.json SHA核对；generator保留模型、生成器及必要历史子集，方便复现。

即使本次逐周期对照通过，也只是有限输入的RTL/软件一致性，不等于所有输入形式证明、硬件验证或实测推荐区域。此前31段局部分析仍是21段当前B匹配、10段相位不确定；本次仿真不自动消除真实初相歧义。4096点快照只是局部窗口，不宣称整ITEM/整图恢复；不采用AI。
