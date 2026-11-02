# 执行、协议与资源集成 v1.1

## 账本与动作

计划声明本次record_ids和max_records，不固定44条。原子顺序仍是：持久化ATTEMPT→真实动作→原始捕获落盘→对应协议验证→COMPLETE/UNKNOWN。UNKNOWN保留捕获文件及SHA，但不被当成被测FAIL，也不退款。

默认free functions和SessionWriter(incremental=False)每事件核验全部历史；增量模式只在明确选择且文件由该writer独占、原件保持不变时使用。它不抵御运行中能篡改文件并恢复元数据的攻击者；退出强制独立全审计。每个快照标明final_full_audit_required，不冒充已经实时重哈希全部旧文件。

## 真实项目协议示例

peer_read_adapter.py按实际项目ch1_control_session.py的帧格式实现只读READ32：A55A、version=1、type3B/7B、payload<=32、CRC16-CCITT初值ffff；payload为epoch/txn/op/count/address/value/填充，明确核对全部回显、状态、数量和保留填充。此入口无写寄存器/START/复位方法。

run_readonly的transport由调用者注入，需exchange(request,0x7b)和close()。epoch/txn由真实系统合法分配，不复制演示的0x10000001去访问已用命名空间。只用于空闲RO窗口，收到异步消息混合流就停止，不能丢弃通知继续。忙会话仍用原完整dispatcher。

verify_lifecycle.py另对原项目0x80 START命令ACK以及0x31 START_ACCEPT、0x33 MARK、0x32 DONE、0x38 RETIRED执行CRC/完整身份/记录号/次序核对。输入应为保存的生命周期专用捕获；混有其他帧不能当成完整协议都验证了。缺事件返回INCOMPLETE_UNKNOWN。即使peer序列通过，strict_local_retirement_verified仍为false：本地TX_DONE、档案和READY必须由原执行器/owner核对。

这些工具提供实际协议适配与原件检查例子，不复制或绕过现有ticket、门禁、全局命名空间和严格退役逻辑。READ32示例、本机TCP对端和合成生命周期帧不冒充新的实板验收。

## 设备租约与关闭

DeviceLease在同一持久文件上使用flock或Windows字节锁。所有合作进程须约定同一设备同一路径；不删除该文件，避免新旧inode同时被锁。它不是内核阻止任意Jupyter/第三方程序直接访问FPGA的设备独占。

close返回True仍只是adapter报告，不是OS线程存活证明。若无法确认关闭，保存quarantine标记；后续合作任务拒绝获取该设备。人工先确认原进程/线程和实际设备状态、保留现场，再处理标记，不能把删文件当硬件已释放。

## 第六项组合接口

第六项ledger_bridge示例使用本项SessionWriter/DeviceLease和同一H5E1格式：on_attempt先落盘、collector捕获字节、evidence_verifier核对序号/参数、on_result完成或UNKNOWN，再关闭并全审计。真实执行器可复用这层接口，但真实动作和安全前置条件仍由设备owner负责。
