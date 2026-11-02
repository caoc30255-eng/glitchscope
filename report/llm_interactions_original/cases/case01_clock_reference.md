# 从名义150MHz到参考时钟与寄存器核对

本文件为事后整理的案例导读，不是重写后的原始对话。原始消息编号可在独立评审记录包中定位。

## 问题

既有系统软件显示150MHz，但150MHz时序签核失败，不能直接据此认定板卡超频。

## 操作者的作用

操作者提出实际可能仍为100MHz，并回传只读寄存器、设备树和两板环境结果。

## 模型与工具的迭代

模型由继续推进150MHz实现，转为核对PYNQ参考频率、PLL及分频；随后修复采集器对PYNQ2.4类方法接口的兼容性。

## 结果

按板载参考和寄存器推导当前FCLK0约100MHz，保留原配置，文档区分软件读回与配置推导；提炼为时钟审计Skill。

## 结论边界

此案例是参考与配置一致性核对，不把仅有ID或软件读回当成完整硬件身份和频率证明。

## 原始记录定位

### m04343 · user · 2026-10-29T02:15:32.684000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04343`。

> <send_user_message_question_reply>
> [{"questionItemId":"[\"request_user_input_async\",\"call_dafe40c4779243b78fc7dda0404b0ca2\",0]","question":"原7020固件和新的纯布局优化候选都未通过150MHz时序。后续按哪条路线推进？此前演示一直使用原固件；修改RTL将产生新固件，需要重新仿真和上板验收。本…

### m04362 · user · 2026-10-29T05:53:52.109000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04362`。

> 
> >     fi
> > done
> >
> > /usr/local/share/pynq-venv/bin/python3 -B \
> >   /home/xilinx/jupyter_notebooks/test_10_14/clock_readonly_probe.py
> > SH
> {
>   "schema": "ZYNQ_CLOCK_READONLY_REFERENCE_AUDIT_V1",
>   "pynq_version": "2.7.0…

### m04363 · assistant · 2026-10-29T05:53:57.050000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04363`。

> **结果支持你的判断：按板卡33.333333MHz参考晶振计算，当前FCLK0约为100MHz；PYNQ显示150MHz是参考频率配置错误造成的。**
> 
> 证据很清楚：
> 
> | 项目 | 读到的值 |
> |---|---:|
> | PYNQ采用的参考频率 | **50MHz，与你的板卡不符** |
> | 设备树声明的参考频率 | **33.333333MHz** |
> | IO PLL倍频 | 30 |
> | FCLK0两级分频 | 5、2 |
> 
> …

### m04400 · user · 2026-10-29T09:15:33.934000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04400`。

> 
> 本次部署目录：/home/xilinx/jupyter_notebooks/test_10_14/glitchscope_reproduce_zgYNAbam/deployment_fCRscIvo
> Configuration created; no hardware setup, no consent, no START: /home/xilinx/jupyter_notebooks/test_10_14/glitchscope_r…

### m04422 · assistant · 2026-10-29T09:38:32.974000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04422`。

> 原因已找到：旧脚本按PYNQ 2.7的时钟接口识别，PYNQ 2.4采用不同结构。[官方2.4源码](https://pynq.readthedocs.io/en/v2.4/_modules/pynq/ps.html)
> 
> **兼容版已修复，25项离线检查通过。** 不需要升级PYNQ。
> 
> ① 将[新版collect_clock.py](C:/workspace/Desktop/claude_code/PYNQ_Clock_Refer…

### m04423 · user · 2026-10-29T09:40:03.558000+00:00

评审包内路径：`raw/dialogue_20261029.md#m04423`。

> root@pynq:/home/xilinx#
> root@pynq:/home/xilinx# /usr/bin/python3 -B \
> >   "$base/collect_clock.py" --allow-register-read \
> >   > "$result_file" && cat "$result_file"
> {
>   "pynq_version": "2.4",
>   "ps_module": "/usr/local/…

## 工程验证关联

- `docs/clock_reference.md`
- `report/verification/clock_reference/board_readonly_excerpt.json`
- `skill/pynq-clock-reference-audit/SKILL.md`
