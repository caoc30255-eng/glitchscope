# Functional Delivery v0.1 验收与复现

结论：实质软件功能和完整样本修复已复现，整体需修复5组问题后再验收。
原交付ZIP SHA256：07996a8e0d3d141934d9a6587a1308219c79acd3e43805b2d3b90a5fb596002a。
本包不含或改写原交付代码、原始采集文件，未执行硬件或真实训练；仅含验收报告、反例、回归及浏览器证据。

先读 review_feedback.md 和 acceptance_notes.md。

复现v0.1现有缺陷（返回成功仅表示现有反例得到重现，不是产品通过）：
python -B reviewer_adversarial.py --package /实际/Functional_Delivery_v0_1_2026-10-19 --output /独立目录/反例.json

期望行为回归（原v0.1为4失败+1错误；修复后这些断言应通过）：
python -B test_expected_regressions.py --package /实际/Functional_Delivery_v0_1_2026-10-19 -v

两个脚本只读产品与交付数据；反例JSON需写到独立文件。刷新参数问题按报告步骤在浏览器复现，截图与AX状态保留。
完整原始接收重建/模型数值检查报告为 reviewer_repair_and_model.json；其中NumPy仅用于本方PC独立线性求解对照，不是新板端依赖。
硬件入口禁用、真实数据训练及ARM/加速实测待完成的范围说明应保留；修复本轮软件缺陷无需重采session24。
