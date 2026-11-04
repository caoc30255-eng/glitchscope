# 赛题提交对应与缺项

依据用户提供的AMD指南3.3.5（PDF物理页24–25），按自主选题整理；组别待参赛者填报。源指南文件未重新分发，SHA与页码见 `guide_reference.json`。

|要求|位置|状态|
|---|---|---|
|完整RTL、PS、STM32源码|src/|已整理|
|仿真/验证脚本与结果|sim/、report/verification/|已有记录，保留各自验证范围|
|综合与实现资源/时序报告|build/reports/ax7010、ax7020|已整理原报告；当前配置按约100MHz推算口径解释|
|上板固件、运行脚本、实测比对|board/、report/verification、独立证据包|已整理，既有三板装置已验收|
|可复现构建脚本|build/、docs/fresh_reproduction.md|已补构建修复与统一入口；两板/STM32/PS本地分阶段复现有原件，汇总入口未重复整轮构建|
|技能包及README|skill/|v1.2.1七项；195项离线回归通过。原六项跨板记录保留，第七项两板只读采集通过；频率结论按配置推算，未知芯片仍需适配|
|设计报告|report/design_report/design_report.pdf|40页正式PDF已合入；内容逻辑、原始数据及逐页版面检查通过|
|大模型原始提示词/回答/自我纠错记录|report/llm_interactions_original/、独立评审记录包|22案例Markdown阅读版及来源索引已整理；26页PDF保留为历史版本；主线可恢复4750条可见消息，协作来源分列|
|官方模板单页英文PPT/英文海报|工程目录外单独准备|按用户要求不纳入工程包，不列为工程缺项|
|最终完整演示视频|工程目录外单独准备|按用户要求不纳入工程包，不列为工程缺项|
|队伍、学校、成员、组别|工程目录外单独准备|按用户要求不纳入工程包，不列为工程缺项|
|7020当前工作频率与时序口径|docs/clock_reference.md、report/verification/clock_reference/|参考晶振及寄存器推算约100MHz，与100MHz STA相符；PYNQ名义读回150MHz，未仪器测频|
|7020真正150MHz签核|build/reports/fclk150_signoff/|原路由和新候选均未通过；此频率不是当前配置推算值，不作为现版性能主张，目录继续留空|
|全新目录本地构建与目标板复现|build/fresh_reproduction_results/|本地分阶段重建及板端软件/原生库复现通过；备用SD新安装session7图片/软件分析原件核验通过，fresh分支及从零安装入口已合入，范围见docs/first_installation.md|
|全新板卡/干净SD注册初始化|board/fresh_install_bootstrap/|正式主线支持0历史初始化；新卡session7原件已归档|
|本次最终UI原始验收会话导出|独立评审证据包；board/final_ui_acceptance_originals/不放私有原件|新卡session7完整原件已归档于submission_evidence；仅保留不含源图片的公开摘要|
|演示素材公开授权|data/media_rights_clearance/|未提供，人物图和关联截图不放公共仓库|
|打印外壳装配检查|hardware/measured_enclosure_fit/|8张实拍与实际装配反馈已归档；无修改、无顶碰松动、接口正常插拔|
|GitHub/Gitee公开仓库地址|根目录README|准备了MIT源码；尚未创建或推送远程仓库|

## 使用说明

- 其他约定缺项目录保持为空，目录清单见required_empty_directories.json。Git不记录空目录，克隆后运行`python build/create_empty_directories.py`恢复；源码ZIP包含显式目录。
- 完整评审证据保存在独立submission_evidence资料包，公开源码保留摘要及来源，不默认发布私有图片与原始截图。
- 队伍信息、官方单页英文PPT／海报、最终完整演示视频在工程目录外单独准备；本工程不为三项材料创建占位目录，也不在这里判定其完成状态。
- 规则与AI均作为减少选点方法报告，完整网格为参照，同时呈现记录消耗、覆盖和边界结果，见docs/selection_methods.md。
- 软件候选、现配置接收结果与推荐配置硬件复核分别解释；新SD版本及归档范围见docs/fresh_sd_acceptance_20261101.md。
