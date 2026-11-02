## 公开版数据说明

本子模块的历史说明保留原阶段语境。当前公开副本移除了完整图像与原始接收帧，仅保留算法、指标和合成测试。历史复建需私有原件；正式工作台使用用户自备图像及新采集会话，入口为工程根目录README。

# 三板实验工作台：功能候选 v0.1.1

本版针对负责人 v0.1 验收中的 F1～F5 修订；详见《revision_notes.md》。原 v0.1 交付与负责人反馈保留。历史《functional_delivery.md》说明原阶段成果，本轮结果以修订说明为准。

本版交付可运行的软件、开发模拟和已审核真实证据的离线回放。没有进行新物理 START、真实数据训练或目标板运行。硬件执行按钮明确返回依赖未满足，不能按完整 M4 硬件验收通过。

## 启动

先解压到独立目录。在该目录执行，Python 3.8 或更高版本，只用标准库，无需安装依赖：

```text
python -B verify_delivery.py
python -B main.py init-demo --workspace ../functional_demo_run
python -B main.py serve --workspace ../functional_demo_run --port 8765
```

浏览器打开 http://127.0.0.1:8765 。运行目录必须是新目录，不能放在交付包或旧证据目录中。服务仅监听本机；在 PYNQ 运行时使用既有授权的 SSH 端口转发访问。停止服务用 Ctrl+C。服务重启会阻断未结束运行，不自动恢复执行。无需 NumPy，不升级现有 PYNQ 2.7、Python 3.8、NumPy 1.20.3。

界面操作顺序：预览计划 → 选择明确标识的开发模拟 → 启动或停止 → 点击格点查看来源 → 导出 CSV/SVG。真实回放按钮切回已审核记录，不启动采集。图片页选择四种实际算法结果，并导出数据、掩码和指标。AI 页展示五种合成种子的真实计算结果。

## 实际程序入口

| 功能 | 入口 | 结果 |
|---|---|---|
| 有限扫描计划、下一条提案 | scans.make_plan / scans.propose | 预声明候选及 STOP，不生成硬件身份或授予预算 |
| B/STM 聚合 | scans.aggregate、render.py、浏览器扫描页 | 同条件分图、缺测/非法/UNKNOWN/预测分开；逐点追溯及 CSV/SVG |
| 实际拟合/选点 | learner.Estimator、main.py algorithm-demo | RBF 后验、均值/不确定度、选点、可保存和加载模型 |
| 推理计时 | main.py infer | 当前机器实测耗时、Python 内存峰值、actual_ARM_run |
| 真帧解码、重组、修复 | images.py、evidence.prepare | CH0/CH1 实际包、身份校验、乱序重组、掩码、四种算法及指标 |
| 服务与界面 | main.py serve、server.py、web/ | 实际调用计划、模拟、回放、停止和导出接口 |
| 主线适配建议 | executor_contract.py | 可测试的 transport 适配契约；当前不是已部署协议 |

重跑合成评估与推理（输出目录位于交付包外）：

```text
python -B main.py algorithm-demo --workspace ../algorithm_run
python -B main.py infer --model ../algorithm_run/algorithm/b_frame_correct_model.json --plan ../algorithm_run/algorithm/evaluation_plan.json --output ../algorithm_run/inference.json
python -B -m unittest discover -s tests -v
```

目标 ARM 使用相同 infer 命令才会产生该目标的实测记录。本包 host_inference.json 来自 Windows AMD64，不能作为 ARM 耗时。tracemalloc 是 Python 分配峰值，不能当作进程 RSS。

从旧原件重建（不需要重新索要或打包旧资源）：

```text
python -B main.py prepare --baseline ../return_shared_integration_v0_6_2026-10-18 --baseline-zip ../return_shared_integration_v0_6_2026-10-18.zip --workspace ../real_rebuild --temp-root ../source_review_temp
python -B main.py algorithm-demo --workspace ../real_rebuild
```

prepare 核对固定 v0.6 ZIP SHA、ZIP 内清单和所有旧文件，经公开 SourceRegistry.register/review 审核，重新解码实际包、修复并独立评估。路径中的旧目录名按实际位置调整，workspace 必须尚不存在。verification/complete_artifacts.py 可对结果目录再解码192包、反序重组、禁止文件访问重跑修复，最后独立评估，并导出静态图。verification/http_check.py 仅用于独立本机模拟工作区的接口检查，会建立测试运行。

## 输出与边界

results/ 保存审核报告、77条公开审核记录、归一化回放（另保留历史 UNKNOWN）、真实稀疏热力图、192个实际接收原包、逐块来源、受损与修复图/字节/掩码、合成模型及比较。源图展示文件只服务独立评估，不是修复输入。原始采集样本和完整来源仍引用旧 v0.6；本包只附必要的接收帧子集，没有重打包旧资料包。

sha256_manifest.json 覆盖交付静态文件。新增状态、锁和运行输出只在独立工作区产生。自带清单用于传输完整性；它不替代负责人提供的可信 ZIP 摘要。详见《functional_delivery.md》《training_integration_notes.md》《failure_repair_notes.md》。
