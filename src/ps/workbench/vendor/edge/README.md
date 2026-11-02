# GLITCHSCOPE 边缘AI开源增强软件候选 v1.1

日期：2026-10-26。新增实际使用scikit-learn 1.7.2、scikit-activeml 1.0.1和emlearn 0.23.2的候选链路。旧v1.0模型和执行入口保留作对照，未悄悄切换默认版本。没有修改比特流或新增硬件试验。

## 已完成的开源接入

- PC使用sklearn随机森林回归器估计三个二值目标的未校准分数，训练只用84条已审查训练数据；40条验证和30条历史不参与拟合。STM模型不使用B的d/s特征。
- PC直接调用scikit-activeml的UncertaintySampling，做标准熵选点基线。板端使用标准库实现等价归一化熵并加入已声明的覆盖、完整重复组和次数上限；真实反馈只影响当前选点，不自动重训全局模型。
- emlearn实际导出三个C99模型。针对sklearn的“<=”和导出器“<”差异，在整数特征域使用floor(t)+0.5转换。37440组输入比较sklearn、轻量Python和C；C最大分数差约8.04e-8，熵计算与上游归一化结果一致。未在ARM运行过此版。
- 四策略同预算回放：原规则、旧AI、上游标准熵、新混合策略。原始会话只读重建；未选择格点的标签不交给选择器。旧公开数据已用于开发，所以只是回顾性诊断。

## 自选配置覆盖

计划/选点/反馈采样入口接受现有底层的全部合法范围：14组d/s；byte20…275、bit0…7；phase5…44、width1…40且和<=45；TYPE3A单点、TYPE3C连续多点（首字节+数量<=276）、DISABLED；任意256字节载荷，route0。

每个扫描会话仍固定一组B参数；不同d/s需分独立计划/会话。有限域最多256候选、当前每计划最多44条（含CONFIG和参照）。这些是当前软件边界，不等于RTL永久限制。独立任意位置多点和额外route尚未由底层支持，本版没有凭空增加。

**配置能选，不等于模型已经学过。** 当前84条训练仍仅覆盖递增载荷、byte20/bit0单点、d3/d4、s=-1。新模型严格按完整上下文和坐标包络检查支持；其余配置显示未学习并安排规则探索，关闭回退时停止。不会对新载荷、多点或新d/s伪造预测。后续真实采样可走全上下文队列，审核和用户批准后生成新训练快照，再重新训练/导出。

## 新版入口

- `edgeai_oss.ipynb`：查询与计划预览，全部为软件操作。
- `oss_cli.py predict/plan/suggest`：新版接口；`plan --request ... --output ...`自动绑定OSS策略和模型SHA。
- `oss_cli.py collect --session ... --output ...`：关闭真实会话后的原始证据重建，包含所有合法上下文，UNKNOWN不作为失败训练。
- `oss_cli.py prepare-dataset --queue ... --approval ... --output ...`：需要队列文件SHA匹配、负责人审核与用户训练批准；不自动训练。
- `oss/train_oss.py --data ... --output ...`：PC训练与emlearn导出；后续新数据必须是审核快照，输出目录不可覆盖原件。
- `oss_arm_check.py --output <包外目录>`：标准库Python推理、契约检查，以及存在cc/gcc时编译导出C作一致性检查。不访问FPGA，不创建会话，不发送START。
- `oss/report.html`：新版指标及四策略回放摘要；`reports/model_report`和旧Notebook属于v1.0对照。

模型实际运行文件在backend/oss_runtime/models；OSS策略及运行代码包含在执行器代码绑定/审批清单中。`oss/portable.py`只是PC导入shim。PC训练依赖见requirements-pc.txt，本次使用Python3.13；板端不需要安装sklearn/scikit-activeml/emlearn，继续Python3.8。

## 当前效果与验收边界

B目标按格点留组可估计覆盖71.4%，在这部分以0.5作诊断阈值的准确率85%。验证40条的诊断准确率B77.5%、STM载荷85%、STM业务100%，同时B有2条、STM载荷有6条假通过；这些分数不构成自动通过判定。小样本结果不能当成泛化保证。

在14条预算的旧3a/3b回放中，B目标覆盖/混合发现尚未超越原规则。STM部分目标有更多边界触达或混合发现，但不同策略/会话不总相同，详见完整表。不能宣称实板已提速，也不能凭此改写实测热力图。

软件接口和C导出链路已完成本地验证；本版ARM检查、新参数数据覆盖、前瞻同预算实板提效验收及主网页接入仍待完成。所有新硬件试验另需用户批准。旧第三功能的635条累计记录不变，本轮新增START0。

## 开源来源与许可证

- https://github.com/scikit-activeml/scikit-activeml （发行包包含BSD/Apache相关许可）
- https://github.com/emlearn/emlearn （MIT，导出代码及许可随包保存）
- https://github.com/scikit-learn/scikit-learn （BSD-3-Clause）

具体许可原文在oss/third_party，版本已固定。Optuna和AEPsych本轮未引入，避免把找最优点误当边界覆盖，也避免额外重依赖。
