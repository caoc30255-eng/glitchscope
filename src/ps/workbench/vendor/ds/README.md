# GLITCHSCOPE 第三功能 · 独立分析版 v0.2

日期：2026-10-24。输入一次图片传输的CONFIG+64个ITEM原件，在PS侧对14组d/s统一评估，输出独立交互报告。它可以处理历史会话，也可由图片采集完成后的程序调用。没有接入主工作台，没有新硬件执行入口，不用AI。

## 本版已实现

- 校验源图、CONFIG的SHA和逐块CRC、64个请求、实际B配置、接收字节与采样、毛刺数量/身份、CAP及退役凭据的已提交文件。
- 所有ITEM统一使用同一组d/s比较；不逐块挑参数后拼成“整图最优”。14组、全部保留NCO相位均参与计算。
- 原A/B接收的整帧正确数、等长帧位置误码、载荷位置误码单独统计；候选d/s只有局部窗口推演，没有候选整图CRC预测。
- 输出最低最坏误差候选集合、声明门槛内的离散区域、零错候选和未解决窗口。并列保留；默认门槛为局部位错0、停止位错0。
- 明确处理零毛刺无CAP、缺窗口、缺记录、UNKNOWN/未退役、未对齐、模型矛盾、输入损坏和用户中断。缺口不按零错计数；完整性失败或中断时撤回全部推荐。
- 报告可选择统一d/s、ITEM、保留相位、字节和位；查看参考、实测、软件重建三轨迹及三点表决表，放大MARK/字节范围，导出SVG/CSV/JSON。
- 独立Notebook、CLI、输出哈希校验、结果ZIP导出及采集后调用API。报告为单文件HTML，可下载后离线打开，不需启动Web服务，不访问外网。

## 开始使用

将本目录放到 `/home/xilinx/jupyter_notebooks/test_10_14/`。打开 `ds_analysis.ipynb`，使用新内核，按四格执行：选择已保存会话和评分门槛 → 分析64块 → 查看/下载报告 → 导出结果ZIP。

默认会话为session_00000027。普通Python只需有读取原件、写入输出的权限；不用Overlay或原生UART库。若同板有正在执行的独占试验，本地POSIX共享文件锁会拒绝/阻止并行分析，不修改锁文件。

纯软件检查：

```bash
python3 -B software_check.py --output /path/to/new_check
```

读取已有真实原件分析：

```bash
python3 -B workbench.py --session /path/to/session_00000027 --output /path/to/new_report
```

可选 `--policy capture_only` 使用仅CAP冷启动模型，或默认 `reference_prefix`。可选 `--max-bit-errors N --max-framing-errors N` 在分析前固定门槛。CLI退出码：0为分析结束（可能有证据缺口），2为输入完整性阻断，3为软件分析被中断。是否存在全64候选以summary.json为准，不能只看退出码。

验证与打包：

```bash
python3 -B output_tools.py --output /path/to/new_report
python3 -B output_tools.py --output /path/to/new_report --zip /path/to/new_report.zip
```

采集程序已经完成并关闭接收器/独占会话后，可显式调用：

```python
from workbench import run
result = run(completed_session_path, new_analysis_directory,
             policy="reference_prefix", max_bits=0, max_framing=0)
```

此API只读文件。它不会代为初始化、重发、续跑、切换实际B参数或修改旧执行器。会话仍在运行时不要调用。无需每块手动运行，软件分析一次处理64块。

## 手动与随机毛刺

分析使用EXECUTOR保存的实际请求计划，不重新抽取随机数。兼容同一65条协议布局下的连续多点、单点、禁用毛刺；随机计划存在时核对其SHA及逐块配置。任意手动计划只有实际输出相同证据合同才可分析，并非所有未来采集器都已做实板兼容验证。

零毛刺块没有MARK快照时显示NO_MARK_WINDOW。原接收字节仍可统计，但不会补造一段理想实测波形来给候选加分。因此含缺窗/零毛刺的会话可能只能给局部诊断，不能给全64推荐。当前7010每个ITEM的多点仍共用一个位号、宽度和相位。

## 模型和范围

CAP每块4096点，名义10ns/点，约40.96微秒；本轮通常只对其中2个完整字节评分，64块共1024位，约为图片载荷位数的0.78%。完整传输包含278字节帧，本功能不声称重建全部原始波形。

参考轨迹来自发送原件编码；实测轨迹来自CAP CH0数字采样；第三轨迹是软件表决字节的UART形式展示。A接收器也会出错，不被用作干净真值；A字节事件只辅助估计字符间隔与独立对照。

逐周期B模型保持此前1125例RTL对照版本的SHA。默认对齐会生成CAP sample0之前、首毛刺字节之前的理想参考前缀供模型预热，未采集前缀不计分。这是明确的额外假设，不是硬件测得的初态。选择capture_only时不加入前缀，可能因窗口从字节中途开始而无法对齐。

相位拟合使用非目标B字节、标志和相对时间，目标字节仅作一致性检查，不筛选相位。所有保留相位都用于误差界；各窗口极值之和是保守界，不保证它们能同时由某个单一全局相位达到。

默认排名先比较最坏局部停止位错误，再比较最坏局部数据位错误。门槛区域和最低上界候选分开；“最低”不等于零错，也不等于硬件推荐。硬件验证区域始终为空，直到独立实板对照另行验收。

本版仍待：PYNQ Python3.8/ARM实际复算、用户浏览器交互体验、新候选的实板对照。旧长零载故障不被本模块修复。没有修改7010/7020比特流，没有新增试验预算或START。

## 输出

report.html为自包含交互报告；summary.json、profiles.csv和report_notes.md为汇总；items/item_XX保存每块包络、对齐与显示数据；input_manifest.json绑定原件；analysis_code.json绑定分析代码；output_sha256.json校验全部产物。结果ZIP不包含完整原始会话，请继续保留原件。

代码只用标准库，JS在浏览器本地运行。开发检查使用Node验证JS与所有投票点的数据关联，未使用Computer Use或浏览器自动化；不将静态/纯函数检查称为浏览器视觉验收。
