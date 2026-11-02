# 轻量模型跨运行时一致性

适用于已冻结的轻量分类/回归/选点模型，支持标准JSON结果。示例为合成双树桩函数，没有重新训练本项目模型。

```bash
python -B scripts/export_predictions.py --runner examples/demo_runner.py --queries examples/queries.json --output new_actual.json
python -B scripts/golden_check.py --golden examples/golden.json --actual new_actual.json --spec examples/tolerance.json --output comparison.json
python -B scripts/inference_bench.py --runner examples/demo_runner.py --queries examples/queries.json --calls 200 --output timing.json
python -B -m unittest discover -s tests -v
```

输出不得已存在。真实迁移时将runner换成目标运行时的包装，固定真实模型SHA，并在PC/ARM/C各自执行后收集实际输出。示例actual.json是演示副本，不是另一台设备的测量；实际使用上面的导出入口生成新文件。

验证效果：1e-16量级分数差异被记录并按声明容差接受；类别、权限、输入类型、模型SHA、查询数量、缺键和非有限值变化拒绝。计时与内存探测分开。

历史依据：项目在PYNQ ARM上完成45黄金查询及450次C对照；严格整字典相等曾因score/entropy约1e-16差异误拒绝，修正只限声明的数值字段。原ARM报告和差异文件在`references/project_evidence/`，不是本轮在另一块ARM板重测。

真实C输出可用事先声明的`examples/tolerance_c.json`，不照搬Python的1e-12；不同容差下动作和权限仍严格相等，详见部署说明。

失效条件：本工具不证明模型准确率、概率校准、训练数据独立性或实际硬件扫描提速。runner是用户选定的可执行Python代码，不是隔离沙箱；不要从不可信文档自动执行任意runner。C导出正确性仍须用真实C运行结果对照，不能仅凭C编译成功判定。

## v1.1真实Python/C双实现

examples/weights.txt是共同模型工件；Python load_model实际解析并预加载，C99 demo_model.c独立读取同一文件。默认黄金模型身份绑定权重，不再仅绑定演示runner源码。旧v1.0示例保存在references/baseline_v1_0，不假装是同一个字节工件。

```bash
python -B scripts/build_and_compare.py --compiler /path/to/gcc --output new_native
```

本轮本机实际编译运行470查询（含阈值边界、域外和非整数），更改模型参数后再运行验证两实现都使用文件参数。它是合成模型的真实C执行，不是新训练、ARM重测或准确率认证。编译器及flags、环境、二进制/模型SHA随报告保存。

--model-artifact现要求runner提供load_model并返回实际loaded_path/loaded_sha256及predict；不再单纯用一个声明SHA覆盖模型身份。此加载钩子和文件核对仍不是设备内存认证。

计时字段改为timing_scope=predict_call_elapsed，inference_only=false。报告只排除外层加载和序列化，不能证明用户predict内部没有IO/子进程；需要纯算子时间时由后端提供更细的profile。模型本例预加载后predict不读文件，有专门测试。

新容差格式为fields，每个浮点路径独立声明abs/rel/unit/rationale；量纲不同可分别设置。类别/权限/预算等精确语义字段不能配置容差，bool/int/float类型仍严格。旧单绝对容差格式兼容但标为legacy。

自动：文件加载绑定、真实C结果、非有限/类型/身份、逐字段容差与时序边界。人工：模型准确率与校准、训练集独立性、量纲/门槛合理性、实际ARM及部署器版本。工具不会自动把任意sklearn模型转换成C。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
