---
name: edge-model-portability
description: Validate portable model outputs across PC, ARM and C runtimes with field-scoped float tolerance and inference-only benchmarks. Use for deployment equivalence, not training or hardware-speedup claims.
---

先固定模型工件、查询顺序、输入域和输出schema，实际输出由待测运行时独立生成。

- 对照模型/输入/权限/状态/类别时严格比较类型、键和顺序；仅对事先声明的浮点分数路径使用绝对容差，拒绝NaN/Inf。
- 不通过更换权重或重生成golden来修复跨版本浮点误差。先定位具体字段与数量级，再确定容差，保留差异报告。
- 分类边界和阈值变化会改变行为，即使分数误差小，也要单独比较动作/选点结果。拒答不能转换成通过。
- 用`golden_check.py`作输出比对，用`inference_bench.py`区分预热、加载、计时和独立内存探测。不能把进程启动/IO时间或推理时间当成硬件扫描加速。
- 读取[部署说明](references/porting.md)处理Python/C阈值、特征类型、未知域和版本绑定。报告实际运行机器，不能从armv7l推断具体板卡身份。

使用实际load_model钩子和共同工件的Python/C双实现，变更参数验证模型确实被读入。新容差逐字段声明量纲和理由。通用计时只称predict_call_elapsed，不假定内部没有IO。
