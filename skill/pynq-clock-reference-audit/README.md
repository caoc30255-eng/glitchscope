# PYNQ通用时钟一致性排查 v0.2

用于PYNQ频率请求、读回、板卡参考源、时钟树或声明信息不一致时的定位。通用诊断方法与设备原始寄存器适配分离，不因在两块板运行成功就宣称支持任意芯片或能自动修复任何物理问题。

## 从哪里开始

- 未知平台：`python -B scripts/inspect_platform.py --output platform.json`。只读软件/设备树及PYNQ源文件字面声明，不导入PYNQ、不映射MMIO。源文件默认值不是运行时参考值。
- 任意已规范化设备时钟树：`python -B scripts/diagnose_clock_tree.py --snapshot examples/generic_clock_tree.json --output generic_result.json`。示例为合成24MHz参考和125/3倍分数PLL的算例，用于验证时钟树计算。
- 已审查的Zynq-7000原始路径：经允许后，在目标PYNQ解释器运行 `python3 -B scripts/collect_clock.py --allow-register-read > board_snapshot.json`，再用实际板卡参考值和来源运行离线审计。不要覆盖已有原件。

```bash
python -B scripts/audit_clock.py --snapshot examples/navigator_snapshot.json --reference-mhz 33.333333 --reference-source "Navigator schematic PS_CLK and device-tree declaration" --output navigator_result.json
```

输出必须是新文件。预期PYNQ_REFERENCE_MISMATCH，推算约100MHz，结果附带参考来源和寄存器配置。不同板卡不能照搬本案例参考值。新设备接入、规范化格式、时钟类型和处理建议见 [generalization.md](references/generalization.md)。

## 能定位哪些差异

参考源错误、getter版本/模型不符、PLL/分频/旁路解释、请求与读回不同、Overlay重配/分频量化/单位问题的排查线索、HWH/设备树声明不同、已确认的门控停钟、缺失参考证据。支持有理数倍分频链、分数PLL、多域与已解析源选择。工具不给未知芯片猜地址，也不会自动改时钟、PYNQ或RTL。

## 实际来源和验证效果

此技能来自GLITCHSCOPE排查“PYNQ显示150MHz而PL实现报告100MHz”。先按显示值进行150MHz检查并发现违例，随后经源码、晶振、设备树、PLL和分频交叉核对，解释出参考50/33.333333引起的1.5倍换算差异。过程见 [case_study.md](references/case_study.md)。

- 领航者7020/PYNQ2.7：参考假设50MHz、设备树33333333Hz、PLL30和分频5×2，两次原始读取一致；按板卡33.333333MHz参考推算约100MHz。原、新采集器实板只读输出已保存为相关字段摘录。
- AX7010/PYNQ2.4：修复旧classmethod接口识别后采集成功；运行参考33.333333MHz，读回99.999999MHz，两次原始快照一致。设备树33333000Hz相差约10ppm，严格审计保留REFERENCE_EVIDENCE_CONFLICT，供人工核对声明精度；本次频率结论按配置参考值推算。
- 40项离线检查通过：19项原始解码/保守拒答、6项2.4/2.7接口兼容、15项通用时钟树。各平台实测范围与合成测试严格区分，见verification/report.json。

跨板实测证明此采集路径能在两种PYNQ环境运行，不证明所有设备/时钟正确。UltraScale+/RFSoC可通过审查后的规范化时钟树分析，原始寄存器采集适配尚未提供。频率结果采用参考值和寄存器配置推算；配置修改及具体设备验收按各自范围执行。

## 使用边界

输入参考值及图结构由使用者/设备适配器提供，工具不能认证原理图或物理芯片。原件SHA用于追溯而非真实性认证。新设备需先明确型号、PS/PL参考源及厂商时钟树，不能把本项目的地址或默认值复制过去。

只改API设置值或只改PYNQ参考常量都可能改变实际分频。GLITCHSCOPE选择保留已验收设置并补充说明，是个案决策。需要改配置时须另行授权并核对所有setter调用；本包仅诊断。频率结论附带参考来源和寄存器推算依据，STA按声明的实现与时钟条件解释。

离线测试：`python -B -m unittest discover -s tests -v`。Python3.8以上为离线工具目标；现有采集器已在AX7010的Python3.6/PYNQ2.4和7020的Python3.8/PYNQ2.7运行。硬件原始适配与环境故障说明见 [workflow.md](references/workflow.md)。
