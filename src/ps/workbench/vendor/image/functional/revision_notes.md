# v0.1.1 修订与复验说明 · 2026-10-19

收到的负责人新回复实际为 Functional_Delivery_v0_1_Review_Feedback_2026-10-19.zip。已校验反馈清单，并在未改动 v0.1 的情况下复现其五项期望行为回归：4项失败、1项KeyError，与负责人一致。原功能成果获得独立复现，但“整体暂不通过”的结论保留；本版是请求复验的修订候选，不自行替代负责人签收。

## 按项修订

| 问题 | 修改和入口 | 实际复验结果 |
|---|---|---|
| F1 缺失B被误计为已知零像素 | images.repair；仅实际选中的合法替代接收块可填补输出缺失。候选为空保留缺失，来源标 MISSING_NO_ACCEPTED_SOURCE；新增 original_B_missing 与 estimated 掩码 | B缺失+A坏CRC、全路缺失、合法替代块、空候选、估计候选均验证。估计生成时保留原缺失，单列来源与估计掩码；未将占位像素计作已接收 |
| F2 一次观察冒充三次完成 | scans.aggregate；每格输出 required_repeats、occupied_ITEMs、missing/excess_repeats、身份绑定、execution_coverage_complete 与 valid_measurements_sufficient，CSV增加对应列 | 不足/刚好/超额/相同UID重复/不同UID同身份/含UNKNOWN分别检查；真实d4一条记录仍为1次，按3次计划判未完成 |
| F3 刷新参数错位及异步竞态 | web/app.js；恢复全部计划字段，摘要列实际固定条件；草稿/预览中禁止启动；过期响应丢弃；启动中锁住预览及参数 | 实际浏览器d4+重复2+预算30+STM判据刷新后全部保持；草稿启动禁用。实际JS异步测试验证旧响应、快速点击与失败预览 |
| F4 身份查重与诊断UNKNOWN异常 | scans.propose；严格只收64字符小写hex身份；状态仅VALID/UNKNOWN；摘要校验hex；UNKNOWN必须末条 | 整数/混合表示/重复身份拒绝；诊断型UNKNOWN允许结果字段缺省或null，返回结构化STOP、null结果摘要、诊断摘要和诊断引用，不抛KeyError |
| F5 当前B能力域缺少限制 | make_plan/validate/HTTP预览共用校验：d∈1..4且-2≤s≤3-d | 全部合法边界通过，越界、布尔d等拒绝；未将通用字节范围作为当前硬件能力 |

real_hardware_complete 现在仅表示“声明网格ITEM重复数的已审核实测充足”：每格身份绑定、占用数恰好等于声明次数、目标标签全部有效、没有UNKNOWN或超额、全部来自已审核实测。它不证明新计划已获得硬件授权、CONFIG/参照执行或严格退役，completion_scope明确限定。execution_coverage_complete允许UNKNOWN占用该次执行，而valid_measurements_sufficient及real_hardware_complete不允许UNKNOWN补足有效测量。缺失身份不能得到完成结论。

F1的missing表示输出仍缺乏可接受接收数据的区域；original_B_missing永久记录原始B缺失。若实际CRC通过的A/STM替代块被选中，输出missing可解除，原始B缺失仍保留。若只生成估计，原始缺失及输出缺失均保留，estimated=255。uncertain与estimated不替代缺失掩码。新增掩码随图片ZIP导出；已有完整session24样本原四类字节输出未改变。

## 复验证据

- verification/review_regressions_before_fix.log：旧版按负责人未修改脚本复现4失败+1异常。
- verification/review_regressions_after_fix.log：相同脚本对修订源码5/5通过；review_input/保留负责人原始脚本和报告。
- verification/v011_tests_final.log：原24项加10项边界回归共34/34通过，未删除原严格断言。
- verification/ui_state_check.json：实际app.js在可控异步传输下8组检查通过。此为JS单元测试，Node仅PC开发检查使用，不是板端新增依赖。
- verification/ui_refresh_fixed.txt、ui_refresh_form_fixed.png、ui_refresh_fixed.png：实际浏览器刷新、自定义参数恢复和对应计划摘要。使用独立127.0.0.1:8767工作区，无目标板动作。
- verification/v011_existing_results_preserved.json 与 independent_repair.json：192真包再解码、反序组装、纯修复禁止文件访问、旧四种结果逐字节对照。
- verification/http_v011.json：模拟幂等、STOP、UNKNOWN、导出及真实入口保持拒绝；非法配置另见http_profile_v011.json。

同一批session24结果仍为：未修复B/CRC择优3174错误、MAE6.648987；仅B修复497错误、MAE2.067505；多路修复0错误、MAE0且匹配接收CONFIG SHA；视觉中值3102错误、MAE3.224182。多路输出SHA仍为6192177385d8d6a5513d80d5a53a45c891fb34f8f8603fcda53fb91172215330。仅对该样本和连续同位突发模型有效，不扩大无损范围。

## 未完成项与责任排期

本端统一负责本次五项软件修改及复验，已完成并打包。主线仍需新版有界执行器/真实网格/预算、训练及评估授权、ARM连接、实时接收路径。未进行新物理START、真实训练、ARM计时或新比特流；原44/88次仅建议，未执行。

负责人复验通过后，沿用原依赖到齐T0排期：接口材料到齐后1个工作日内适配及契约联调；真实网格数据到齐后1个工作日内审核聚合；获训练授权及独立数据后2个工作日内对照；目标板可连接后1个工作日内ARM推理和接收联调。此为本端估计，不是已约定日期。M1完整真实网格、M2真实加速及ARM实测、M4硬件/实时入口仍待完成。

## 本轮开发失败记录

第一轮重建候选结果尝试写入源码内results，被既有只读输出保护拒绝；随后预览启动因工作区尚未生成而按预期拒绝。改为独立工作区生成，再由打包步骤拷入候选包，没有放宽产品来源或目录保护。浏览器select的标签定位不匹配时，按页面实际target标识完成操作。原首次失败日志与v0.1所有有效成果保留，不覆盖旧包或原件。
