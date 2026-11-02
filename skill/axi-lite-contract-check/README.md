# AXI-Lite契约与主机适配

适用于自定义32位AXI-Lite IP、PYNQ MMIO或提供逻辑整数字读写的传输对象。提供真实可用的`RegisterBank`，不是只有说明文档。

```bash
python -B scripts/contract.py --contract examples/counter.json --words examples/counter_words.json --output counter_check.json
python -B scripts/contract.py --contract examples/fir.json --words examples/fir_words.json --output fir_check.json
python -B scripts/generate_driver.py --contract examples/fir.json --output generated_fir
python -B generated_fir/test_generated.py
python -B -m unittest discover -s tests -v
```

输出文件/生成目录必须不存在。counter使用偏移地址，FIR使用另一基址下的绝对地址。两个输入均为合成寄存器模型。

真实调用方式：用`RegisterBank(your_bus, contract)`，再调用read/write/update_bits/identities；构造函数不访问总线，CLI只调用FakeBus，不导入PYNQ。

验证效果：不同寻址、read/read32绑定、保留位、RO写入、W1C的RMW拒绝、读清零显式意图、身份不匹配和生成骨架的独立执行均有测试。历史扫描后端核验原件在`references/project_evidence/`。

失败来源：项目曾发生底层MMIO对象接口绑定不一致，以及上层读取实际回执不存在的`status`字段；因此从调用签名、契约和实际schema开始适配。缺字段是程序接口错误，不能直接认作被测通信失败。

失效条件：64位/非对齐访问、突发/DMA、字节串线协议、跨主设备原子操作及特殊副作用未在本实现覆盖。FakeBus不模拟完整AXI握手、总线响应错误或W1C硬件逻辑。

## v1.1字段语义与真实MMIO入口

MIXED寄存器可声明完整32位字段：RW、RO、W1C、PULSE和RESERVED；RO/RESERVED必须显式给写入常量，不能靠统一掩码猜测。见examples/mixed.json。RegisterBank.write_fields支持同次更新多个字段，update_bits仅允许RW字段。SemanticBus模拟W1C、读清零及命令脉冲，不模拟AXI周期或其他主设备并发。

真实PYNQ接入脚本为scripts/pynq_mmio_example.py：需--contract、--hwh、--ip-name、--output、--target-confirmed。契约必须由操作者设target_kind=REAL_BOARD_CONTRACT。默认只读身份；只有明确标为全宽普通RW scratch的寄存器才接受--scratch、--value、--allow-scratch-write，可选--restore。工具不加载Overlay、不设时钟、不复位。不要直接用示例地址在实板运行。

自动：字段覆盖/重叠、写入常量、RMW副作用、HWH范围及示例写入门禁。人工：真实字段手册、scratch确实无功能副作用、当前位流与HWH一致、其他AXI主设备并发策略。真实脚本本轮以假PYNQ后端验证，未作为新实板验收。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
