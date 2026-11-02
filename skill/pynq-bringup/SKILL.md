---
name: pynq-bringup
description: Diagnose PYNQ deployment and perform staged Overlay asset, environment and side-effect-free identity checks. Use for board bring-up or Notebook preflight failures, not general Python debugging.
---

先确定用户需要离线检查、现板只读检查还是重新加载Overlay；保留已给出的授权范围，不把重新加载当作默认排错动作。

- 读[README](README.md)选择入口，用profile显式描述bit/hwh、目标机器、时钟及无读副作用的RO寄存器，并按ip_name与HWH地址交叉核对。
- 离线先验资产哈希、地址对齐、范围及Notebook代码AST。例子是假资产，不能用于下载。
- `inspect`只读当前配置，不加载Overlay。不要读取read-clear/FIFO等有副作用的地址。
- `load`会改变PL及可能的时钟。只有任务已经允许时才使用对应显式参数；程序先检查全部写入前置条件，再执行第一次写入。
- No Devices Found先检查同一进程的PYNQ/XRT环境和权限；独占锁冲突先找到占用者；Notebook不一致先分清格式和代码变化。见[案例与定位](references/cases.md)。
- 保留失败报告及已发生的副作用。下载失败不能直接推断“硬件完全没动”；涉及非幂等操作时先确认状态再决定下一步。
- 输出分阶段结论。ID匹配只证明所读身份寄存器匹配；FCLK属性是配置读回，不是物理频率测量。

零掩码不能作为身份校验。Overlay加载可能在失败之前已经应用时钟；优先看独立的显式写入、隐式配置possible及前后读回字段。

所有load都包含HWH时钟的潜在副作用范围，两个写入范围参数均需检查。拒绝mask=0，寄存器按ip_name/interface与HWH绑定。内部写入未插桩时以possible/null记录，不把下载失败当成未改时钟。
