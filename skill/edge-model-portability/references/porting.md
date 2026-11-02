# 文件加载、逐字段容差与计时边界 v1.1

## 输出和模型身份

golden/actual仍为schema=1、model_sha256、queries；查询id、顺序、输入、键及类型严格一致。新例子的model_sha256绑定examples/weights.txt。旧v1.0源码绑定例子保留在references/baseline_v1_0；升级是显式工件版本变更，没有用重写黄金数值掩盖跨运行时差异。

export_predictions的--model-artifact要求load_model(path)返回loaded_path、loaded_sha256和predict。工具在加载前后核对文件及对象记录；没有加载钩子的旧predict模块不能靠声明文件哈希冒充模型加载。任意用户钩子仍可能自报错误，所以这不是内存认证；本例Python解析器和独立C加载器可通过变更参数后的实际预测检验。

## 容差

新格式fields按JSON Pointer指定abs、rel、unit、rationale；允许误差为max(abs,rel*max(|expected|,|actual|))。不再给不同量纲统一套1e-4上限。量纲和理由须在运行前声明、人工评审；不接受拼错或未知策略键。

bool/int/float类型严格，action、execution_allowed、status、state、class、budget、remaining、model_sha256不得声明容差。重复JSON键、NaN/Inf、缺键、少查询和模型身份变更拒绝。旧absolute_tolerance/float_result_paths格式作为legacy兼容，仍有原1e-4上限，新任务优先用fields。

Python例子对score用1e-12、entropy用1e-12；C例子分别声明2e-6。它们只是此双树桩例子的预定门槛，不保证适合任意回归模型。阈值附近的动作仍严格相等，不因分数差小就忽略类别翻转。

整数特征树的<=与<导出转换仅在整数域才可用floor(t)+0.5等处理；连续特征不能照搬。迁移训练模型时先固定特征顺序、类型、量化和支持域，再做真实目标运行结果对照。

## 计时

通用工具只承诺predict_call_elapsed：外部加载和外部JSON序列化不计入，但predict内部IO/子进程可能计入。inference_only=false，不靠函数名字证明纯算子。需要纯算子时间时使用后端细分profile，记录实际边界。

本例Model先读文件、保存不可变参数，predict不再读取权重；有专门禁止read_bytes的测试。内存追踪另跑，不污染计时；tracemalloc不是RSS。C进程耗时包括启动/输入输出，不能与Python函数调用耗时直接相除称加速。

## 已自动检查与外部要求

自动检查模型加载钩子、文件身份、Python/C结果、输出契约和预定数值门槛。人负责门槛/量纲合理性、模型准确率、校准、训练数据独立性和目标部署环境。真实ARM迁移仍需目标机运行，不能把本轮Windows C执行标成ARM执行。

真实分类或选点runner应输出最终类别/建议，不能只提交分数。校验器对这些结果严格比较；专门的阈值两侧夹具验证即便分数差在容差内，类别翻转也失败。此双树桩示例只提供未校准分数，不擅自把0.5阈值升级为硬件通过概率。
