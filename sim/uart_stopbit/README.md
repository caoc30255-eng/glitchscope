# H3长零载荷发送时序离线检查

仅仿真，禁止综合/生成bit/硬件操作。复制的两个RTL与已审阅综合源码快照逐字节一致，但这不证明板上当前bit精确身份。

5个278字节向量：session3c和3d真实未扰动请求；全00、全ff、00..ff循环对照。真实frame sender配真实byte sender与1拍同步RAM，无毛刺、无中止。每个字节逐周期检查500个周期：起始50、8数据位各50、停止50；两路RAW/masked必须一致且无MARK，字节间不得重叠；最后完成字节数278、无fault。

Vivado GUI Tcl Console:
source {/path/to/glitchscope_source/H3_UART_Stopbit_Offline_v0_1_2026-10-23/run_vivado.tcl}

脚本建独立新工程并run all，无需打开旧工程。理想总仿真约14ms，20ms看门狗。期望最终标记：H3_UART_STOPBIT_RTL_PASS cases=5 bytes=1390 checked_cycles=695000。尚未在主机运行通过：当前Vivado命令行启动失败，因此不宣称仿真PASS。回传完整控制台与scoreboard.log，若Fatal保留日志原件。

范围不含完整控制器/CDC/MMCM、物理IO/线缆、电气噪声、STM执行或真实频率；即使PASS也不能排除实板问题。H3无扰动失败未ARM CAP，现有证据没有实际RAW W19波形，不能凭A/B解码倒推出停止位唯一故障。
