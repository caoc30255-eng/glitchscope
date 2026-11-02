# 通用性：处理方法与设备适配分离

## 覆盖的“任何设备”是什么意思

通用的是诊断方法和离线时钟树引擎，不是向任何芯片盲读同一组寄存器。未知芯片需按其手册补充只读适配或导出规范化快照。没有原理图、寄存器定义或独立时基时，不能承诺自动识别并修复真实频率；模拟器或SHA也不能补造物理事实。

|层|实现|验证范围|
|---|---|---|
|未知平台发现|inspect_platform.py读取OS/设备树及PYNQ源文件的字面声明，不导入PYNQ、不映射MMIO|软件及声明信息发现|
|通用时钟树|diagnose_clock_tree.py，无硬编码晶振或MMIO地址|离线：任意有理倍分频链、分数PLL、多时钟域、已解析的源选择及门控状态|
|Zynq-7000原始解码|audit_clock.py、collect_clock.py|两台操作者指明的板卡：领航者7020/PYNQ2.7与AX7010/PYNQ2.4只读采集|
|其他SoC/外部时钟芯片|经审查的适配器或规范化时钟树输入|没有预置任意设备的实板保证；UltraScale+/RFSoC原始寄存器采集器尚未提供|

## 不一致的分类和处理建议

1. 软件参考值与板卡参考不同：修正频率解释；如需修改运行环境，先保证预期分频/频率和所有setter调用一致，不孤立改常量。
2. 请求与读回不同：核对可实现分频、四舍五入、HWH重配顺序、实际调用对象及缓存；不能直接归咎晶振。
3. 读回与按安装版本getter模型计算不符：核对版本、单位、源选择、旁路、分数模式及快照时点。
4. 设备树/HWH声明与时钟树不同：核对声明和启动配置；Linux时钟缓存按软件配置来源解释。
5. 时钟门控关闭：先核对域与使能状态，不能靠修改参考值解决停钟。
6. 缺少参考时钟或映射：输出具体补证据步骤，不填入本项目33.333333/50MHz默认值。
7. 只有约10ppm等小声明差异：保留精度与容差依据，不为了得到PASS静默放宽阈值。AX7010本次就是此类例子；采集兼容运行通过不等于所有声明完全相等。

通用引擎只给建议，不自动配置硬件。涉及温度漂移、外部振荡器、信号完整性或波形的结论，需要相应的外部参考数据。

## 规范化输入

`examples/generic_clock_tree.json`是合成24MHz参考、125/3倍PLL、1/10分频的例子，不属于任何板卡实测。

```bash
python -B scripts/diagnose_clock_tree.py --snapshot examples/generic_clock_tree.json --output generic_result.json
```

根参考由`references`描述频率Hz及来源；`nodes`用parent和正有理数numerator/denominator描述已解析的时钟树；`clocks`声明目标节点、使能、软件采用的参考Hz、读回/请求/元数据声明及显式ppm容差与理由。不能把未验证的图配置当成已验证芯片适配器。若硬件getter用另一条路径，可提供同参考根的software_node。

输入不允许表达式执行或任意内存地址；重复节点、循环、缺父节点、零/负/布尔分频、非有限值和不稳定快照拒绝。参考缺失时返回补证据步骤，频率保持未知。

## 新芯片接入

先用inspect_platform.py形成软件发现包，再根据精确型号TRM核对源选择、PLL整数/小数、旁路、跨域分频和门控。适配器只读已审查地址，保存双快照，将选中的实际路径导出为上述图。用厂商算例、反例和实板结果分别验证。不同SoC不能仅凭aarch64/armv7l或类名相近就套地址。

例如UltraScale+有PRE_SRC/POST_SRC、DIV2和小数PLL，PL参考还可能经过跨域分频；不能复制Zynq-7000的SLCR布局。依据：[UG1087 IOPLL_CTRL](https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/IOPLL_CTRL-CRL_APB-Register)、[PL1_REF_CTRL](https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/PL1_REF_CTRL-CRL_APB-Register)。这些资料用于指导新适配，不代表本包已经完成该平台实板验证。
