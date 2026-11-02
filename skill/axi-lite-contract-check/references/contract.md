# 契约与副作用

契约：schema=1，word_bits=32，base/span，addressing=offset或absolute，read_method/write_method可显式指定。registers包含name/offset/access/read_effect，可选expected/write_mask。

RO身份寄存器必须明确无读副作用。RW保留位默认允许全部32位，真实工程应按手册收紧；W1C只能写需要清除的位，不先读再回写；read-clear只有调用者显式传allow_clear=True才能读取。

驱动接收逻辑uint32；字节序应在串行/网络传输适配层确定。错误地把绝对地址传给PYNQ MMIO偏移参数可能访问错误范围，不能依赖“读出了非零值”作为验证。

生成器输出driver.py、contract.py、registers.json、test_generated.py。生成测试只验证所给契约和FakeBus，不覆盖实际位流和真实MMIO。连接实际总线前应另有只读预检和对应试验范围。

## 字段级契约

access=MIXED时，fields每项有name、lsb、width、access，字段必须无重叠地覆盖全部32位；未使用位也需RESERVED字段。RO/RESERVED的write_value由手册确定，不默认清零。W1C/PULSE的中性写入为0，其他RW字段保留其读回值。含读副作用时禁止RMW；write_fields必须显式给出所有RW值才能避免读取。

write_fields({irq:mask})保留RW但仅清指定W1C位；write_fields({trigger:1})记录命令脉冲，不把命令位的读值带回。普通access=RW加write_mask的旧契约仍保持保守拒绝，不自动将未知高位清零；混合寄存器应迁移到显式fields。
