---
name: bounded-active-benchmark
description: Design and audit fixed-budget adaptive sampling comparisons using prefix-only feedback, explicit reference maps and honest cost accounting. Use to evaluate a selector, not to claim AI superiority from simulation.
---

先声明候选域、条件、准备开销、重复组、主指标、预算和停止条件，再比较策略。沿用用户已允许的范围，不从模型建议推导硬件授权。

- 准备/参照计入成本，区分相同上限与相同实际消耗；规则和模型使用同一任务上下文。
- 策略只接收本次已完成反馈前缀，下一选择和输入哈希先记录，再取得该组结果。参考全图不传入选点API。
- UNKNOWN不是失败标签。模型拒答应如实记录，按事先声明的回退策略处理，不自动造概率。
- 分开报告候选覆盖、边界触达、混合点发现、误判通过、测量次数和墙钟时间。少测4点不能称为完整实测图。
- 本目录`benchmark.py`仅运行明确标记的合成示例，用于验收控制/重放契约。真实硬件对照必须接入真实执行及原件审核链。
- 根据[评价说明](references/evaluation.md)解释持平/失败结果；不能把整个策略的表现归因于某一模型，也不在看到参考答案后改门槛。

重复观测用campaign新鲜样本，不重复静态组。真实collector要接持久化意图、原件验证和完成/UNKNOWN钩子。多轮区间以campaign为单位，真实对照独立于模拟，不因有CI就声称AI硬件提效。
