---
name: axi-lite-contract-check
description: Build or audit uint32 AXI-Lite host adapters from register contracts and generate offline test skeletons. Use for address-binding, bus-method and register-side-effect mismatches.
---

从实际寄存器文档和总线对象签名建立契约，先确认偏移还是绝对地址；不要根据函数名猜地址语义。

- 用`scripts/contract.py`核对宽度、对齐、跨度、访问属性、读副作用、保留位和身份寄存器。
- 同时存在read/read32等方法时显式选择；端序转换由实际传输层负责，本层消费逻辑uint32，不重复字节交换。
- 先以FakeBus和另一个IP的契约验证地址绑定、非法写入和副作用门禁，再连接用户给定的真实总线。
- 需要工程骨架时运行`generate_driver.py`，保留用户已有驱动，生成到新目录。
- W1C/WO/read-clear不能套普通read-modify-write；`update_bits`只串行化同一驱动实例，不保证其他AXI主设备的原子性。
- 回执缺字段时先核对实际schema，报告明确的不兼容；不要添加一个恒真的status字段掩盖问题。
- 按[迁移说明](references/contract.md)报告契约/离线身份测试通过范围，不把其写成AXI时序或全系统硬件通过。

混合寄存器用完整字段契约：RW/RO/W1C/PULSE/RESERVED及明确写入常量。write_fields可处理有读副作用时的完整显式RW值；update_bits不得触及W1C或脉冲。真实MMIO例子默认只读，只有明确安全的scratch才允许写入。
