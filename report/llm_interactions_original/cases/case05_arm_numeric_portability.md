# ARM黄金查询误报与Python/C一致性验证

本文件为事后整理的案例导读，不是重写后的原始对话。原始消息编号可在独立评审记录包中定位。

## 问题

ARM环境的黄金查询采用全字段严格相等，浮点末位差异导致OSS_GOLDEN_QUERY_CHANGED。

## 操作者的作用

操作者在目标板执行检查并回传失败与修复后的完整报告。

## 模型与工具的迭代

定位约2e-16的浮点差异；只为指定score/entropy字段设置绝对1e-12容差，类别、动作和权限仍严格比较，模型权重不改。

## 结果

原110项契约复用，8项修复检查、45条黄金查询及450条C比较通过。

## 结论边界

推理兼容通过不等于实板选点提效；计时边界与进程启动/IO开销按原报告保留。

## 原始记录定位

### m03962 · user · 2026-10-26T08:16:43.168000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03962`。

> 3d打印需要时间 我们来检查边缘ai
> 
> Last login: Sat Nov 20 21:17:38 UTC 2021 on ttyPS0
> xilinx@pynq:~$ cd /home/xilinx/jupyter_notebooks/test_10_14
> xilinx@pynq:~/jupyter_notebooks/test_10_14$ bash 边缘AI_开源增强_板端软件检查_2026-10-26.sh
> GLITCHSCO…

### m03963 · assistant · 2026-10-26T08:18:29.481000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03963`。

> 故障发生在第3步的参考输出比对，尚未执行后面的C推理检查。我先定位具体差异，确认是跨平台数值误差还是模型输出发生了变化；保留这次目录，不必重跑前两步。

### m03964 · assistant · 2026-10-26T08:23:21.137000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03964`。

> 板端日志确认：110项软件检查全部通过，失败只在后面的参考输出比对。
> 
> 我在本地复现了跨版本差异：Python 3.8式求和让其中一条分数相差约 **0.0000000000000002**，原脚本却要求整个输出完全相等。Python官方也记录了3.12的浮点求和算法变更。[说明](https://docs.python.org/3/library/functions.html#sum)
> 
> 这是检查脚本的兼容性问题。我会保留原包和日志，…

### m03965 · assistant · 2026-10-26T08:32:40.730000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03965`。

> **板端110项检查已全部通过，失败出在参考输出比对。** 我已复现浮点末位差导致的误报，并准备了修复包；模型权重没有改动。
> 
> 上传这两个文件到板端 `test_10_14`：
> 
> - [修复包](C:/workspace/Desktop/claude_code/EdgeAI_OSS_Check_Fix_v1_1_1_2026-10-26.zip)
> - [续检脚本](C:/workspace/Desktop/claude_code…

### m03966 · user · 2026-10-26T08:34:26.432000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03966`。

> 4 Verify prior110 contracts (when bound), then8 repair-specific checks
> 3/4 Native45-query comparison; only score/entropy allow absolute1e-12 drift
> 4/4 Compile/run original emlearn C; no FPGA or hardware service
> {
>   "stat…

### m03967 · assistant · 2026-10-26T08:34:58.306000+00:00

评审包内路径：`raw/dialogue_20261026.md#m03967`。

> 板端续检通过了：45条参考输出和450条C推理对照都正常，唯一差异也与本地复现的浮点末位误差一致。Python推理平均约10.95ms，P95约18.99ms。
> 
> 我先归档完整报告并核对原件。这可以确认板端软件运行通过；真实扫描选点是否提效，仍需后续实板对照。

## 工程验证关联

- `report/verification/edgeai_arm/owner_review.json`
- `skill/edge-model-portability/SKILL.md`
