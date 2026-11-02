---
name: hardware-session-evidence
description: Organize bounded physical-experiment attempts, unresolved outcomes and append-only evidence records. Use when duplicate actions or timeout accounting matter; the included ledger never operates hardware.
---

根据用户实际任务定义计划和重试策略。对可能已经产生物理效果的超时，不把“没有收到回复”当作“没有执行”。

- 计划先绑定目标、记录身份和预算，使用新目录保留旧现场。工具的origin明确区分合成与适配器报告，不接受直接自称独立实板认证。
- 在真实动作之前写入ATTEMPT；收到结果后，由对应协议适配器先验证原始回执，再登记证据。UNKNOWN仍占用已尝试记录。
- 未知结果阻断本会话新动作。是否开新会话或采取恢复操作按用户范围决定，不自动清故障、复位或重发。
- 哈希链和文件SHA只验证保存内容一致；完整物理真实性仍依赖协议、测量链和独立审核。
- 资源关闭须由真实适配器报告；账本不等于OS线程退出证明。未报告关闭前保留未执行预留量。
- 读[集成说明](references/integration.md)，把本地元数据记账与硬件命令发送分开，先运行合成例子。

可用实际H5E1只读/生命周期适配例子连接原始回执；未知坏帧也绑定SHA。SessionWriter增量是显式选项，最终全审计不可省。设备合作租约不删除，接收器关闭未确认时隔离后续任务，不仅填一个lock_closed布尔值。
