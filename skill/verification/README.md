# v1.1验证口径与入口

本轮unit_report.json：155项离线回归，作者PC Python运行，Python3.8为语法检查。relocated_commands.json为16条核心复制目录命令；integration_commands.json为9条集成命令，总25条。

vivado_invocation.json/console已更新为本轮实际正向结果；RTL叶项references/current_validation另含正向与注错报告、日志、实际CSV和独立参考。新示例6场景384周期通过，故意背压错误被拒绝。它不是综合、时序或实板验证。

模型叶项current_validation含三组参数，每组47种查询形状重复10次，共1410条Python/C比较。编译器为作者PC已有GCC，C实际执行不是新的ARM运行。每组原报告保留，current_comparison为当前逐字段策略的独立复核。

协议叶项含实际H5E1帧契约在本机TCP模拟对端上的成功/UNKNOWN及压力测试；组合账本/collector和噪声campaign在第六项current_validation。60轮模拟不是真实硬件多轮；源、配置与原件分类均保留。

历史项目证据仍在各项project_evidence，SHA不变。v1.0旧发行ZIP保留，不把旧启动失败/旧86项计数当作本版本当前验收结论。

仍待外部验收：另一块PYNQ/另一操作者真实迁移、真实MMIO/receiver/thread环境、真实多轮噪声、原始大模型交互导出。没有本轮板卡操作、物理START或模型训练。


## 后续跨板实验更新

六项Skill均通过AX7010跨板实验验证。该结果更新此前跨板待验状态，详见 cross_board_experiment.json。原155项测试及既有日志保持原样；未提供新增原始实测日志。新操作者独立复现与各项其他验证边界不因此自动通过。


v1.2新增第七项及七项聚合测试；最新入口为current_summary.json、current_unit_report.json。上文v1.1及原件保持不变，第七项实际采集、通用合成图和PYNQ版本修复分别在其目录记录。
