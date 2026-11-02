# 有界实验与原始证据流水账

适用于UART、传感器、电机和其他存在非幂等物理动作的实验编排。该实现只写本地文件，不映射MMIO、不打开串口、不发送START。

最短例子：

```bash
python -B scripts/run_demo.py --output new_synthetic_session
python -B scripts/session_ledger.py audit --root new_synthetic_session
python -B -m unittest discover -s tests -v
```

演示只构造合成证据：setup完成、reference尝试后超时、最后一条取消。预期occupied=2、recorded_completions=1、unknown=1、cleanup报告后cancelled=1。它不伪造硬件START次数。

真实集成按顺序调用create→begin→实际执行器→协议回执验证→complete；异常调用unknown。接口及数据范围见[集成说明](references/integration.md)。合成例子和任何自填`adapter_reported`字段均不是硬件测量证明。

已验证效果：先占用后完成、未知不退款、未关闭资源保留预留、重复/超序/超预算拒绝、证据文件改动/路径越界/日志截断拒绝、已有锁不删除。历史扫描后端的退役、UNKNOWN、STOP与资源报告见`references/project_evidence/`。

失败来源：控制超时可能已产生动作；初始化成功不等于试验完成；执行完成后上层解析字段出错不能倒推动作未发生；旧内核可能继续持锁。因此“尝试”“记录完成”“物理确认”“关闭”分开表达。

失效条件：此账本不是安全签名、防篡改硬件、分布式全局额度服务或全局设备锁。攻击者若能改全部内容并重算哈希，哈希链不能认证来源。一个有效JSON也不能证明真实DUT回执。断电残留writer.lock时先查进程和现场，工具不自动删锁或恢复运行。

## v1.1协议、设备租约与压力测试

新增peer_read_adapter.py采用本项目实际H5E1 READ32帧契约（A55A、版本/类型/长度、CRC16、epoch/txn/地址回显、状态/数量/填充）。只读入口run_readonly接收已授权的transport.exchange；不构造命名空间、不写寄存器、不发送START。忙会话异步通知不在此空闲只读示例范围，必须使用原完整dispatcher。

```bash
python -B scripts/run_protocol_demo.py --output new_protocol
python -B scripts/run_protocol_demo.py --output new_protocol_unknown --corrupt-reply
python -B scripts/benchmark_ledger.py --output new_pressure --records 50
```

前两条是本机TCP模拟对端，真实协议字节，不是板卡实测。正常完成3条，坏CRC只占用1条后UNKNOWN停止；原TX/RX及UNKNOWN原件SHA均保留。verify_lifecycle.py另可只读核对真实peer START_ACK/START_ACCEPT/MARK/DONE/RETIRED通知：它仍不代替本地TX_DONE、档案与READY的严格验收。

DeviceLease使用持久文件上的OS锁，所有合作进程必须对同一设备使用同一路径；不是操作系统禁止其他应用直接MMIO的万能锁。文件不删除，避免创建两套锁域。若接收器关闭未确认，写隔离标记，后续合作调用拒绝；人工确认实际资源关闭并保留现场后才可处理标记。

SessionWriter默认仍每事件完整核验；显式incremental=True在独占写入假设下只核新证据和自己的日志状态，退出时强制全量审计。它不宣称运行中逐次重哈希全部原件。50条主机压力例子核验次数严格模式2550、增量100；这是临时文件开销，不能当硬件提速。

自动：实际帧身份/参数/CRC、UNKNOWN不退款、OS合作租约、关闭失败隔离、增量结束全审计。人工/外部：真实硬件独占纪律、namespace来源、native线程退出、动作权限与物理回执真实性。全量与增量模式的威胁假设不同，不能只保留快速模式而删除独立审计。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
