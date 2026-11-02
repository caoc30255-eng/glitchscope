# 领航者7020：显示150MHz与约100MHz推算值

## 观察及错误方向

现有PYNQ程序请求并读回150MHz，原已验收PL实现报告却按100MHz约束生成。若把API读回当成真实频率，会得出“必须把已验收RTL优化到150MHz”的过早结论。

原路由在100MHz下WNS +0.048ns、WHS +0.057ns；将该检查点按6.666ns复查得到WNS -3.286ns、28303个建立违例端点。一次以150MHz为目标的新布局候选也未通过。这些结果真实保留，其含义是“实现不满足该150MHz约束”；实际工作条件另按参考时钟和寄存器解释。

## 找到原因

用户提出板上可能仍是100MHz。查询官方PYNQ源码后发现Zynq默认参考值50MHz；本地领航者原理图与工程PS配置为33.333333MHz。经处理sudo环境导致的No Devices Found，运行原只读脚本，用户回传完整JSON。

回传指出：PYNQ2.7实例参考值50MHz，设备树33333333Hz，IO_PLL_CTRL=0x1e000，FPGA0_CLK_CTRL=0x200500，PLL_STATUS=0x3f，两次寄存器读取一致。倍频30、分频5与2，对应 `33.333333×30÷5÷2≈100MHz`；按50MHz计算则恰为150MHz。

## 采用的处理

保持既有设置、PYNQ安装和位流不变，在README、复现说明、设置处注释和验收说明中澄清名义值与约100MHz推算值。频率结论按参考时钟与寄存器配置推算；未把更高频率STA失败改成通过；未追溯修改旧证据。后续移植不得照搬150设置。

## 证据真实性与范围

`examples/navigator_snapshot.json`是正式工程中保存的板侧回传字段摘录，原文件随包复制，SHA见provenance.json；其数据来源为本次实板只读采集回传。`references/historical/clock_readonly_probe.py`保留当时原探针，不用于推广处理所有PLL旁路状态。新采集器/解码器的通用边界由离线测试补充；初版整理时未再次运行板卡；后续新增采集器实板补验见下节。此前六项Skill的跨板通过结论不挪给本项。


## 新采集器实板补验（2026-10-29）

操作者在同一7020上运行collect_clock.py --allow-register-read，输出文件为 `/home/xilinx/jupyter_notebooks/test_10_14/clock_audit_v01_yB4PVWF3.json`。两次原始寄存器完全一致，新增BOOT_MODE=0x5，PLL_STATUS=0x3f、IO_PLL_CTRL=0x1e000、FCLK0_CTRL=0x200500。QUAL/FORCE均为0、PLL锁定，分频5×2，离线解码仍为99.999999MHz并识别PYNQ参考值不匹配。

本包新文件是回传JSON中相关字段的重新序列化摘录，省略两段已安装PYNQ函数源码；没有声称其SHA等于板侧完整原件。保留原板侧JSON。未写寄存器、未加载Overlay、未调用时钟setter、START=0；本节记录7020配置读取，跨板结果见后节。


## AX7010/PYNQ2.4跨板采集

AX7010首次因Python安装路径不同未执行，改为/usr/bin/python3后暴露旧版API识别不兼容。依据官方2.4源码修复类继承解析后，操作者回传成功输出：PYNQ2.4、legacy_classmethod_api、参考33.333333、FCLK读回99.999999、两次寄存器一致。BOOT_MODE=0x5，IO PLL30，分频5×2。

设备树33333000Hz与PYNQ参考33.333333MHz相差约10ppm，参考精度按声明来源记录，严格审计返回REFERENCE_EVIDENCE_CONFLICT供人工复核。未把该声明差异直接判为硬件故障，保留频率推算依据。该结果证明跨板/跨版本采集运行，保留失败与修复轨迹。
