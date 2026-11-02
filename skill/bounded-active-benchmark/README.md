# 有界主动选点的公平验收

适用于主动采样、边界探索、实验设计和参数搜索。工具将通用候选坐标、策略API、前缀承诺、预算和评价分开；不固定本项目14格或44条。

```bash
python -B scripts/benchmark.py --experiment examples/experiment.json --output new_demo
python -B -m unittest discover -s tests -v
```

例子为九点一维合成域，准备2条、每点3条、各策略预算14；输出两个策略的选择日志和比较报告。coverage和boundary_rule都是演示规则，**这里没有假装训练出AI模型**。

策略函数接收domain、observed、groups_per_point、remaining_records、repeats和max_groups_per_point；reference仅留在测试执行器侧。记录每次选择的输入前缀和哈希，再附本组反馈，可独立replay。

验证效果：越域、超预算、重复上限、伪造前缀、反馈类型变化和篡改决策拒绝；早停策略明确标记实际支出不等，不把同上限称为同消耗。合成报告不计算硬件墙钟收益。

历史依据：本项目前瞻规则14/AI14/完整参照44的72条对照，规则与AI各覆盖4格、触及6个边界格中的2个；主要指标持平，未证明硬件提速。未修改的结果在`references/project_evidence/`。这也是技能价值：能识别“没有提效”，不只展示成功案例。

失效条件：旧静态示例参考每点只有一个有限重复组，v1.1禁止在该入口重复选同一点；独立重复由新campaign入口提供。API信息分离不是进程/文件系统沙箱。参考三次重复并非真实概率；真实选择器、板卡墙钟和新条件泛化需要另做前瞻验证。

## v1.1多轮噪声、UNKNOWN及真实collector接口

旧benchmark.py只允许固定表每点一组；重复确认改用campaign.py，不再重复同一组三条反馈冒充新测量。

```bash
python -B scripts/campaign.py --config examples/noisy_campaign.json --output new_campaign
python -B examples/ledger_bridge.py --ledger-scripts ../hardware-session-evidence/scripts --output new_bridge
python -B examples/ledger_bridge.py --ledger-scripts ../hardware-session-evidence/scripts --output new_bridge_unknown --unknown-at 4
```

campaign例子预先声明30个独立模拟种子、概率分类门槛、邻接关系和95%区间；每次点/重复索引用新的可复现抽样，对策略采用配对随机数。输出campaign级配对bootstrap、混合发现率Wilson区间、边界触达、实际消耗与UNKNOWN。不把ITEM当作独立实验重复来抬高样本量。

run_policy提供真实collector回调接口。ADAPTER_REPORTED必须传durable on_attempt、原件evidence_verifier和on_result，先占用并记意图再调用设备。UNKNOWN（含CRC/身份/记录异常）立即阻断，部分重复组不继续学习、不当False；budget计入准备与未知尝试。CLI仍只模拟，不接受自填HARDWARE后宣称验收。

ledger_bridge将真实H5E1字节校验、OS合作设备租约、账本和collector接起来；本例对端是本机内存模拟器，正常8条，注错第4条立即停止并保持占用。完整六项包中可运行该组合例子；单独复制本技能时只有该组合例子需要显式提供ledger脚本路径，核心框架独立。

自动：选择前承诺、上下文/反馈顺序、完整组与UNKNOWN、真实适配器钩子、预算/计数、多轮独立模拟及campaign级区间。人工/外部：真实设备数据、噪声模型代表性、候选域与指标设计、新硬件多轮对照及另一操作者迁移。区间排除0也只代表给定模拟条件，不自动证明AI或硬件优越。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
