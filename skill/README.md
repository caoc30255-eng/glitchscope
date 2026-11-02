# GLITCHSCOPE 可复用技能包 v1.2

本版针对外部评审完成正确性、接口语义、可运行示例和验证边界修订。原六项保持原样，第七项独立加入；各项仍可独立复制；第六项的组合账本例子显式依赖第四项，核心框架无此依赖。

|技能|可直接运行的入口|v1.1重点|
|---|---|---|
|[pynq-bringup](pynq-bringup/README.md)|preflight.py、check_notebook.py|拒绝零掩码、HWH范围交叉验证、Overlay隐式时钟影响与环境信息|
|[axi-lite-contract-check](axi-lite-contract-check/README.md)|contract.py、generate_driver.py、pynq_mmio_example.py|字段级RW/RO/W1C/PULSE/保留位、语义总线模型、显式真实MMIO入口|
|[rtl-reference-cosim](rtl-reference-cosim/README.md)|run_simulation.py、compare_trace.py|六场景384周期实际Vivado闭环、背压注错、全流程分块/逐行校验|
|[hardware-session-evidence](hardware-session-evidence/README.md)|run_protocol_demo.py、verify_lifecycle.py、benchmark_ledger.py|真实项目帧契约、OS合作设备租约、UNKNOWN留证、关闭失败隔离、增量+最终审计|
|[edge-model-portability](edge-model-portability/README.md)|build_and_compare.py、export_predictions.py、inference_bench.py|同工件Python/C双实现、实际加载钩子、逐字段量纲容差、诚实计时边界|
|[bounded-active-benchmark](bounded-active-benchmark/README.md)|campaign.py、ledger_bridge.py|新鲜重复样本、UNKNOWN闭环、campaign级区间、实际消耗与组合适配|
|[pynq-clock-reference-audit](pynq-clock-reference-audit/README.md)|collect_clock.py、audit_clock.py、diagnose_clock_tree.py、inspect_platform.py|跨PYNQ版本采集、参考源核对、通用时钟树与分层诊断|


## 从哪开始

每项README给出输入、使用方法、已验证效果和失效条件；SKILL.md供智能体发现并按需加载references。迁移到别的题目时改配置/模型/参考/设备适配，不复制本项目地址、命名空间或固定预算。

Python工具面向3.8及以上，标准库即可运行离线例子。PYNQ只在明确的目标板阶段导入；C示例需GCC/兼容Clang，RTL示例需Vivado。不会自动安装工具、注册全局技能或运行硬件试验。

本目录内可运行：

```bash
python -B validate_all.py --output /path/to/new_validation
python -B run_examples.py --output /path/to/new_examples
```

两个输出目录必须不存在，父目录可写。工具自动把测试临时目录放到所选输出目录下，避免API服务的系统TEMP权限差异。原生C、Vivado及本机TCP例子按各项README显式执行。

## 已自动检查和仍需外部确认

见[verification_matrix.md](verification_matrix.md)。本轮离线单元、复制目录命令、原生Vivado正向/注错、Python/C、真实协议本机对端和多轮噪声验证分别记账，v1.1原六项基线计数以verification/summary.json为准；v1.2七项最新计数与范围见verification/current_summary.json。

没有新PYNQ板卡运行、物理START或训练。六项已通过AX7010跨板实验验证；另一操作者独立复现、真实硬件多轮噪声实验、温度/时序/电气行为仍待完成。本轮同工件C运行发生在作者PC，不能写成新的ARM运行。

## 历史与本轮证据

每项references/project_evidence保存未修改的历史报告和来源SHA。references/current_validation保存本轮新验证，来源按PC、仿真、合成、本机协议对端分开。历史接收器1125例、旧ARM450对照、72条实板比较不能替代新模板；新模板通过也不扩大旧硬件验收范围。

这仍是工程技能包，不是任意IP、任意模型的一键实板交付器。原始大模型提示词/回答/纠错记录须从平台导出；案例摘要不冒充原始对话。设计报告继续由负责人补齐。

## 赛题对应

按自主选题3.3.5.2提供工作流、工程/接口模板、校验脚本和踩坑案例；六项AX7010跨板实验结果已登记，原始日志未随本次结论提供；通用PYNQ的适用范围仍以各技能说明为准。文件和目录使用英文，README.md、SKILL.md、LICENSE为标准入口名；正文可中文。MIT许可随每项保留。


## 原六项AX7010跨板实验验证（历史记录）

原六项Skill均通过AX7010跨板实验验证，由原Zynq-7020平台迁移使用。实验结论记录见 verification/cross_board_experiment.json；本次据提供的实测结果更新，未附新增原始日志，也未重新执行板卡操作。该结论不扩大为任意板卡兼容、时序签核、模型精度或AI优势证明。


## v1.2 第七项与通用性

七项离线回归共195项。第七项把通用方法、离线时钟树和原始设备适配分开：Zynq7000采集记录覆盖7020/PYNQ2.7与AX7010/PYNQ2.4；通用图支持不同参考源、分数PLL、多域、请求/读回/声明和门控状态，未知设备需按其手册接入适配。不能声称任意设备已实测或无资料自动修复。频率结论采用参考时钟与寄存器配置推算。第七项AX7010设备树的约10ppm差异原样保留为严格审计待复核项，不伪造成完全一致。
