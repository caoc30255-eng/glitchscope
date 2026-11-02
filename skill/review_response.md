# 外部评审逐项落实 v1.1

|评审项|本版处理|当前验收|
|---|---|---|
|零掩码使身份检查恒真|配置阶段拒绝mask=0|回归通过|
|Overlay隐式时钟副作用|所有load需时钟影响范围；explicit与overlay_possible分开，未插桩为null，异常也保存读回|假设备异常路径通过；真实PYNQ仍待迁移|
|人工地址未与HWH核对|解析MEMRANGE按IP/interface匹配基址/跨度；采集DT及软件版本|两个MOCK IP＋实际项目HWH解析通过，无板卡访问|
|混合寄存器RW/RO/W1C等|字段覆盖和写常量；write_fields、受限RMW、SemanticBus及显式真实MMIO例子|离线与假MMIO通过，AXI时序不在语义模型范围|
|新RTL示例未真正仿真|六场景ready/valid例子，真实Vivado正向＋背压注错|编译/展开/仿真/CSV比对及注错均通过|
|流式比较末尾整文件SHA|分块SHA与整型case计数，删除全量read_bytes/set累积|有禁止read_bytes的回归|
|账本实际协议和独占接口不足|H5E1 READ32、peer生命周期核对、OS合作租约、关闭失败隔离、collector组合|本机模拟对端和跨进程租约通过；不是新实板|
|每次追加全量重读慢|保守路径保留，显式owned增量＋最终全审计|50条核验2550→100；仅主机IO，不宣称硬件提效|
|模型缺完整C例子|同文件Python/C99、编译器/工件记录、更改参数后对照|三组参数1410查询通过，未在ARM重跑|
|文件SHA只是声明|实际load_model钩子、加载前后hash和参数变更行为测试|本例确实读入；不声称任意runner内存认证|
|inference_only口径过强|改predict_call_elapsed，明确内部IO可能计入|接口/测试及报告已更新|
|统一绝对容差与全局上限|逐字段abs/rel/unit/rationale；精确语义字段禁用容差，补阈值翻转例子|回归及实际C输出通过|
|固定表重复读取不独立|旧入口禁止重复；新campaign按种子/点/重复索引新抽样|30轮/策略模拟通过|
|缺多轮区间与UNKNOWN真实接口|campaign级配对bootstrap、Wilson、完整组与未知占用；真实collector三钩子和原始字节/账本组合|代码及本机例子通过；真实多轮仍待独立实板|
|自动检查与人工约定混淆|verification_matrix及各README逐项区分|文档完成|

这是一套经离线与原生工具验证的工程技能包。物理板卡、第三方适配器事实、噪声代表性和新操作者迁移仍需外部验证，不能由多写一个布尔字段替代。


## 后续跨板实验更新

六项Skill均通过AX7010跨板实验验证。该结果更新此前跨板待验状态，详见 verification/cross_board_experiment.json。原155项测试及既有日志保持原样；未提供新增原始实测日志。新操作者独立复现与各项其他验证边界不因此自动通过。
