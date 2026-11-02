# 复现操作

## 环境

- Vivado/Vitis：原实现与推荐复现版本2026.1。7020当前工作条件按寄存器与33.333333MHz参考晶振推算约100MHz，STA按100MHz解释；PYNQ名义读回150MHz的原因见 clock_reference.md。
- 板侧：PYNQ Linux armv7l/32bit，Python3.8.2，既有环境 `/usr/local/share/pynq-venv/bin/python3`。
- STM32：Keil uVision、ARM编译器配置见 uvprojx、Keil.STM32F1xx_DFP 2.4.1，ST-LINK/V2。
- 电脑：Python3.8及以上；依赖见 requirements.txt。运行日志应写在仓库外。

## 1. 验证交付

`python -B build/verify_release.py`。归档SHA见交付根目录；软件单元和HTTP检查通过不等于新版本上板通过。

## 2. 只读网页

`python -B board/start_preview.py`，打开 http://127.0.0.1:8780/ 。只在127.0.0.1监听；无实板配置时真实执行拒绝。历史人物图未公开，可以上传自己的图片完成预览。原始会话需自行登记，目录必须保持原名和内部结构；不要把结果JSON冒充原件。

## 3. 从源构建

在独立空 Vivado 会话执行 `source build/rebuild_ax7010.tcl` 或 `source build/rebuild_ax7020.tcl`。脚本只构建、报告，默认不下载硬件；新生成 bitstream 的功能等价和板级性能仍需单独验证。原验收 `.bit/.hwh` 在 board/firmware，哈希由交付清单记录。

STM32使用 `build/rebuild_stm32.py` 在外部新目录重建，安装指定DFP；该入口恢复生成头固定大小写。详见 fresh_reproduction.md。构建前检查RAM、器件和Flash算法。芯片写入和复位必须由操作者主动执行，复现脚本不会自动烧录。第三方启动代码原版权保留。

在 ARM 板运行 `bash build/build_native.sh` 可编译原生库到外部输出目录。编译成功后先比较接口和执行线程调度检查；重新编译的二进制不应直接冒充已经绑定哈希的旧库。

## 4. 板侧实操

优先使用独立证据包内保持完整的验收发行版核对当前装置。公开源码经过英文路径整理与媒体剔除，须先在目标板重新跑软件检查；不能拿旧软件PASS文件给新manifest授权。

既有板卡工程：保留原 board_runs、namespace_allocations.jsonl、trial_registry 和追加账本，不清空、不复制别人授权。配置JSON绑定原bit、hwh、native与本次软件检查凭据。`board/create_live_config.py` 只生成配置，不授权、不映射硬件。

```bash
python -B src/ps/workbench/software_check.py --output /path/outside/repo/target_check
python -B board/create_live_config.py --runs /existing/test_10_14/board_runs --assets board/firmware --receipt /path/outside/repo/target_check/report.json --output /path/outside/repo/live_config.json
python -B src/ps/workbench/prepare_demo_install.py --config /path/outside/repo/live_config.json
python -B src/ps/workbench/server.py --port 8765 --runs /existing/test_10_14/board_runs --data /path/outside/repo/web_data --live-config /path/outside/repo/live_config.json
```

以原PYNQ环境和必要权限运行。通过SSH将电脑18768转发到板侧127.0.0.1:8765后浏览器访问18768。若No Devices Found，先在同一shell加载 `/etc/environment` 和 `/etc/profile.d/*.sh`；读取系统环境期间不要启用nounset。不要降低Host/Origin/令牌校验来修复端口转发。

网页中先由操作者确认本轮范围与预算，再预览单任务并确认实际条数；每个新硬件会话前手动重载原7010，STM32运行，避免调试器暂停DUT。异常立即停止，保留完整会话，不自动重试。全新SD首次部署入口已合入，见`docs/first_installation.md`与`board/fresh_install_bootstrap/`。新安装从0记录和0额度开始；旧安装继续核对原历史，不伪造编号或清空账本。

## 5. 结果复核

扫描用原始反馈、实际READY、严格退役与保存的MMIO读写绑定重建；图片分别评价首轮接收和软件恢复；候选d/s局部软件分数与配对实板结果分别报告。只有输出HTML/CSV，不代表包含完整原始证据。外部证据包包含49–4f等原件，可与对应验收报告逐项核对。


## 运行前核对时钟换算

见 [clock_reference.md](clock_reference.md)。当前镜像PYNQ参考值50MHz与板卡33.333333MHz不符，因此原代码请求150、读回150，对应分频5×2和约100MHz推算值。按本发行版要求保留原配置；不要单独把150改为100，也不要只修改PYNQ参考值后继续请求150。

可运行 `sudo /usr/local/share/pynq-venv/bin/python3 -B board/clock_readonly_probe.py`；先在同一个root shell加载 `/etc/environment` 与 `/etc/profile.d/*.sh`，否则可能出现No Devices Found。该脚本只读SLCR、PYNQ实现和设备树，不设置时钟、不加载Overlay、不发送START。设备树及寄存器计算不是独立物理测频。


## 统一复现入口与最新结果

见 [fresh_reproduction.md](fresh_reproduction.md)：含两板FPGA、STM32和板端软件/原生库的新入口，以及本地通过范围。备用SD后续实测与证据边界见[fresh_sd_acceptance_20261101.md](fresh_sd_acceptance_20261101.md)。
