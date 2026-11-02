# RTL与软件参考逐周期对照

适用于可导出确定数字周期轨迹的RTL模块。流式比较器可用于其他状态机和流处理核；示例是通用8位ready/valid累加器，没有本项目UART寄存器或位流依赖。

先生成独立参考：

```bash
python -B scripts/make_demo_reference.py --output demo_reference
python -B -m unittest discover -s tests -v
```

使用本机Vivado，在本目录运行：

```bash
vivado -mode batch -source examples/run_vivado.tcl -tclargs /absolute/path/new_simulation
```

可在NEW_OUTPUT_DIR后再提供目标part；默认part只是演示值，迁移时用自己的器件。

实际轨迹位于新工程的`skill_demo.sim/sim_1/behav/xsim/actual.csv`。收集模拟器完整日志，再比较：

```bash
python -B scripts/compare_trace.py --reference demo_reference/reference.csv --actual /path/to/actual.csv --spec demo_reference/spec.json --output comparison.json
```

可加`--log /path/to/log --pass-marker "SKILL_RTL_PASS cases=6 cycles=384"`。输出不覆盖旧文件。

已验证效果：比较器检测invalid周期保持值错误、短尾、缺/重周期、X/Z和位宽溢出；项目历史1125例、11389950周期的完成日志原件见`references/project_evidence/1_82b507b0_scoreboard.log`。该历史结果针对B接收器有限输入，不等于这个新累加器模板在所有环境已跑通。

v1.1新增示例已实际完成Vivado2026.1编译、展开、仿真及384周期CSV比较；另一次INJECT_STALL_BUG变体被测试台和比较器拒绝。当前新验证回执见verification（包总索引）；历史1125例与新示例分开，不互相替代。

Windows启动器若在API环境静默返回1，应检查PROCESSOR_ARCHITECTURE是否缺失。本次确认64位Windows后仅在子进程补齐AMD64即可进入工具。脚本run_simulation.py可重现：

```bash
python -B scripts/run_simulation.py --vivado /path/to/vivado --output new_sim
python -B scripts/run_simulation.py --vivado /path/to/vivado --output new_bug_sim --inject-stall-bug
```

Windows可使用vivado.bat；--isolate-python-env仅清理子进程的Python/Tcl/Conda冲突，不改系统。必须检查精确标记与CSV，不能只看进程退出码。输出目录新建；父路径建议使用英文路径。

CSV比较及SHA计算现均分块/逐行处理；只保留20条差异和整型case计数，不再整文件read_bytes或累积case集合。

自动：六场景（复位中断、溢出、连续有效、短/长背压及背压中复位）、周期/位宽/完整性与注错失败验证。人工/外部：真实DUT对应的参考模型正确性、CDC、综合与实现时序、板级物理行为。

失效条件：模拟/电气行为、未知逻辑值的自定义等价关系、多时钟CDC、形式证明、时序收敛和真实物理采样均须另做。工具不把软件参考前缀当成实测波形。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
