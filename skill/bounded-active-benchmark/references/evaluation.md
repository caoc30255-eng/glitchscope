# 有界策略评价 v1.1

旧benchmark.py是固定参考表契约检查，每点只能取一组，明确禁止重复读取同组假装独立样本。新campaign.py对每个seed/point/repeat_index生成新的可复现随机观测；配对策略共享相同条件的随机数，跨campaign使用不同种子。此为模拟独立抽样，不证明真实噪声IID或平稳。

## 执行接口

run_policy(plan,choose,collector,run_id,origin,on_attempt,evidence_verifier,on_result)。plan只含context、候选坐标、预算、准备成本、重复组和次数上限。choose只收已完成组前缀，不传truth或种子；这是一种API信息分离，不是进程沙箱。

ADAPTER_REPORTED必须提供三个钩子：on_attempt持久化占用及意图；evidence_verifier验证实际原件/回执；on_result写COMPLETE/UNKNOWN。适配器若只填一个verified=true字段却不解析原件，不能声称实板通过。collector接收完整请求身份和context_sha256，回执必须匹配record_id/request_sha256；命令超时、CRC/身份不符或结果日志失败立即停止，不自动重试。

准备也按记录调用collector并计费。每个测量组在预算足够时才开始；未知尝试仍占用，部分有效组不继续学习、不作为完整组。不把UNKNOWN记为False。run包含输入/决策先承诺及逐记录哈希，可audit_run重放检查预算/顺序/计数。

## 多轮与区间

例子预声明30个种子、9点概率场、2条准备、每组3次、14条上限、每点最多2组、UNKNOWN率2%。truth分类阈值、邻接和95%区间在配置中固定；报告绑定配置及代码SHA。

每轮记录实际消耗、覆盖、边界触达、混合点与UNKNOWN。以campaign为统计单位，配对bootstrap对同一seed两策略差值重采样；Wilson用于多轮混合触达率。不能把同一会话里多个ITEM当成独立实验来抬高样本量。未完成轮次不偷偷删掉，成本和覆盖保留；声明相同预算上限不保证实际支出相同。

两种示例策略仍是规则，没有伪造新AI模型。真实冻结模型可实现choose接口，但须在新条件/实板上独立评价。模拟CI排除0也不自动证明硬件收益，硬件墙钟比较仍需测量和预定评价口径。

## 通用失效条件

context混入未来答案、策略自己读取参考文件、适配器伪造回执、真实试次不独立、噪声场与目标硬件不符时，本工具不能替代实验设计和审核。原始数据和权限仍由真实系统管理。
