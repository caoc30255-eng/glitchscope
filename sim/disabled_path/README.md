# H3 无扰动配置链路离线复核

两次真实日志TYPE3A禁用请求/ACK7A精确匹配，CRC有效，实际UART RX捕获绑定通过，控制字段禁用且保留字段零。这不是物理mask状态测量。

新仿真沿用已审阅owner+guard+range+frame/byte UART原件，采用1拍同步RAM，输入为两次实际H3 ITEM字节。TYPE3A上下文使用既有组件测试的合法上下文，并非重放完整板级原控制帧/ARM/START流程。验证配置禁用后RAW/masked各278字节正确、停止位中心高、零翻转/零MARK、物理完成和点数正确。

约5.6ms仿真，30ms看门狗。预期 H3_DISABLED_OWNER_GUARD_UART_PASS cases=2 bytes=556 zero_inversions_zero_marks。组件级检查，不覆盖MMCM、CDC、AXI、reset_handoff、真实IO、电气链路或固件。

GUI Tcl Console:
source {/path/to/glitchscope_source/H3_Disabled_Path_Offline_v0_1_2026-10-23/run_vivado.tcl}

主机CLI启动失败，尚未运行新用例；待GUI实跑日志复核。不生成bit，不操作板卡，不新增START。保留3c/3d UNKNOWN。
