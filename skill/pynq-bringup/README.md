# PYNQ分阶段部署预检

适用于已有bit/hwh和寄存器说明的PYNQ工程；其他板卡可改profile，不依赖GLITCHSCOPE地址。输入和边界见[profile说明](references/profile.md)。

在本目录运行：

```bash
python -B scripts/preflight.py --profile examples/counter/profile.json --output counter_check.json
python -B scripts/preflight.py --profile examples/fir/profile.json --output fir_check.json
python -B scripts/check_notebook.py --reference examples/reference.ipynb --candidate examples/reformatted.ipynb
python -B -m unittest discover -s tests -v
```

输出文件不能已存在。离线阶段也会解析HWH并核对ip_name、接口、基址和跨度；示例HWH为结构化MOCK元数据。两个profile的资产均明确标为MOCK，只验证参数化和离线入口，不是可下载的bit文件。

迁移到实板时，替换真实bit/hwh及SHA，按实物填写`asset_kind=REAL_BOARD_ASSET`、目标机器和寄存器。只读现板用`--stage inspect`；任务确实允许下载时才用`--stage load --allow-overlay-download`。所有load阶段均需`--allow-clock-write`：Overlay本身可能先应用HWH时钟，不能只检查configure_mhz。这些参数是防误操作标记，不会替用户产生授权。

已验证效果：不同基址/身份/跨度的counter与FIR配置通过离线验证；Notebook注释、格式和输出变化可接受，字面值或代码单元格变化拒绝；伪造目标设备测试可检查副作用顺序。测试不接触真实PYNQ。

项目依据：历史部署中曾因root/sudo环境未加载而No Devices Found；Notebook末尾换行导致旧文本比较误拒绝。出处及修复说明见`references/project_evidence/`及[案例](references/cases.md)。这些是历史工程经验，不是本轮重新上板的结果。

失效条件：profile不完整、读地址有副作用、实际硬件接口不匹配、IPython魔法语法无法由Python AST解析、加载中断。工具不处理DMA缓存一致性、运行中Overlay热切换、精确bitstream硬件指纹或全局硬件锁。

## v1.1自动检查与人工边界

自动：拒绝mask=0；XML映射与profile逐项交叉检查；下载前检查时钟影响范围；记录显式时钟写入和Overlay可能的隐式配置；下载中途失败保留前后读回；采集Python/PYNQ版本、机器位数、内核和可用Device Tree描述。

人工/外部：HWH和实际加载位流的一致性、只读地址是否真的无副作用、Linux板卡描述是否对应手中硬件、物理时钟频率、真实功能。配置描述匹配不等于硬件密码学身份。

报告schema=2。旧clock_write_attempted保留为兼容字段：离线/inspect为false，Overlay内部动作未被监测时为null，显式设置Clocks时为true。应读取explicit_clock_write_attempted和overlay_clock_configuration_possible，不能把null当false。


## 跨板实验状态

本项通过AX7010跨板实验验证。结果来源与范围见 [实验记录](../verification/cross_board_experiment.json)。既有自动测试原件保持不变，新增原始实测日志未提供。
