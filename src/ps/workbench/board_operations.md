# 板侧部署与实操

将本目录完整复制到原工程旁。保留原board_runs、namespace_allocations.jsonl、trial_registry及原始资源，不复制空注册表替换原件。

运行 software_check.py --output <包外新目录>。只有armv7l/32位上通过本版本检查，才会产生PASS_TARGET_DEMO_SOFTWARE。整个检查只用合成PREVIEW账本、假设备和本机HTTP，不访问FPGA，不授予真实演示额度。

在包外live_config.json填写原runs、bit、hwh、native路径和本次report.json的software_receipt路径。以已加载/etc/environment及/etc/profile.d环境的root运行prepare_demo_install.py --config <配置>，再运行server.py --port8765 --runs <原board_runs> --data <包外网页数据> --live-config <配置>。登记安装不是授权；不会自动创建演示轮次、加载Overlay或发送START。

浏览器经SSH转发18768访问。首次先确认右侧本轮范围/额度，再自选任务参数。初始化前每次由操作者手动重载原7010，保持STM32运行。每次任务启动都要预览、确认名称与条数，不能自动续跑旧任务。

服务意外关闭：不要重跑旧worker或删除账本。活着的原worker可继续被查看；未结清/状态需核对时不恢复额度。正常停止并安全清理后，可以结束本轮；UNKNOWN保留并需明确确认异常记录。无法确认资源关闭时需维护核对，不能靠追加额度解除。

旧版逐计划APPROVED文件不作为本版日常演示入口。新版父授权来自操作者在界面的明确确认。过去的44条提案不因安装或打开网页而获批。


## 当前镜像时钟解释

PYNQ按50MHz参考值计算而板卡PS参考为33.333333MHz，当前名义设置/读回150MHz对应PLL30、分频5×2和约100MHz推算值。保留原设置，不以150MHz宣称PL性能；未做物理测频。换镜像先只读核对参考频率与分频，详见工程 docs/clock_reference.md。不要孤立改150为100或仅修正PYNQ常量。


首次项目安装使用bootstrap_fresh_install.py创建全新数据身份和零注册、零额度；不导入旧历史。目标为领航者7020/PYNQ2.7，其他时钟环境在Overlay设置前拒绝，见工程docs/first_installation.md。旧安装继续原历史校验，不能用fresh标记重置旧账本。
