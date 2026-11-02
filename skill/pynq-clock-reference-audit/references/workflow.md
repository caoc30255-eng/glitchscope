# 参考频率排查与适用边界

## 证据层级

|材料|能说明什么|不能说明什么|
|---|---|---|
|原理图/板卡手册|该版本PS_CLK器件的额定频率|实物没有换料、实际频偏|
|设备树/HWH/BD|软件/设计声明及分频配置意图|实物参考源与声明精度仍需核对|
|已安装PYNQ代码和实例|计算读回值采用的参考值与公式|真实晶振本身|
|SLCR两次快照|读到的源选择、倍频、分频及状态|读取前后任意时间点、输出门控状态及模拟质量|
|STA及实现检查点|指定约束下的静态路径检查结果|实际运行时钟或板上功能|
|外部参考数据|交叉对比所采用的参考条件|超出该数据来源的其他节点/工况|

## Zynq-7000解码

SLCR基址0xF8000000。PLL控制偏移ARM/DDR/IO分别为0x100/0x104/0x108；PLL_STATUS为0x10C；FPGA0_CLK_CTRL为0x170；BOOT_MODE为0x25C。只读，不写UNLOCK。

FCLK0源选择为bits[5:4]，0/1选IO PLL，2选ARM PLL，3选DDR PLL；DIVISOR0为bits[13:8]，DIVISOR1为bits[25:20]。PLL_FDIV为bits[18:12]，锁定位ARM/DDR/IO分别为PLL_STATUS[0]/[1]/[2]，不是STABLE字段[3:5]。

PLL_BYPASS_FORCE为控制寄存器bit4；PLL_BYPASS_QUAL为bit3。FORCE=1时旁路；FORCE=0且QUAL=1时需要读取BOOT_MODE[4]，不能用“未锁定”直接推断旁路。旧个案探针对该非个案状态的简化不可推广，新解码器显式处理/拒答。原始个案QUAL=0、FORCE=0且PLL锁定，因此该补充不改变约100MHz结论。

正常PLL模式：`f = PS_CLK × PLL_FDIV / DIVISOR0 / DIVISOR1`。旁路模式中分子使用PS_CLK。采集复位/关断、未锁定且无明确旁路、零分频、快照变化时不输出可靠的速率结论。

所有“频率”结果均是条件于参考源正确的寄存器推算。FCLK门控、外部MMCM及波形质量需另行核对。本技能不以成功算出一个数就签核硬件。

## No Devices Found

本项目发现sudo后的shell未加载XRT相关环境。先在同一root shell读取`/etc/environment`和`/etc/profile.d/*.sh`，然后调用正确PYNQ虚拟环境的Python；加载这些系统脚本时不要提前启用nounset。该经验不是所有No Devices Found问题的唯一解释。

采集器遇到设备发现异常直接失败，不自动下载Overlay、解锁SLCR、复位FPGA、重烧固件或重试硬件事务。默认电脑端只运行离线审计；新增采集须符合当前用户授权。

## 官方依据（2026-10-29核对）

- PYNQ2.7实现：https://pynq.readthedocs.io/en/v2.7.0/_modules/pynq/ps.html
- PLL_STATUS字段：https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Register-PLL_STATUS-Details
- IO PLL控制字段：https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Register-IO_PLL_CTRL-Details
- BOOT_MODE字段：https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Register-BOOT_MODE-Details

字段含义应以所用芯片TRM为准，不将该映射套到UltraScale+或RFSoC。


### PYNQ2.4与2.7接口差异

2.4官方源码 `https://pynq.readthedocs.io/en/v2.4/_modules/pynq/ps.html` 中，Clocks继承_ClocksZynq并由_ClocksMeta提供属性；不能把type(Clocks).__name__直接当作硬件架构。2.7则委托给_ClocksZynq实例。采集器分别核对issubclass/isinstance与实际ps模块中的类对象，再提取各自的运行参考值；不调用setter、不升级系统。
