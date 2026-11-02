# 本地源码复现与板端下一步

## 已完成和未完成

本次从发布ZIP提取新目录后实际运行Vivado、Keil及独立Python环境。7010恢复历史高密度实现流程后完成；7020修复模块引用发现并使用短输出目录后完成100MHz实现；STM32在新的外部副本中恢复CMSIS生成头的规定大小写后，重新编译的HEX与已验收HEX完全一致。PS的5组软件测试在独立PC虚拟环境通过。

证据见 `build/fresh_reproduction_results/`。7010 WNS +0.220ns、WHS +0.008ns、17条原样保留的DRC警告；4个异步输出没有外部延迟契约，不能称为全板外部接口时序已闭环。7020在100MHz下WNS +0.048ns、WHS +0.057ns，建立/保持/脉宽无违例。修复过程包含分阶段运行；新汇总入口未再重复执行整个长时构建，不能冒充一键从头验收通过。

板端软件/原生库复现通过，原生库重编SHA与验收库一致；原2026-10-29报告作为历史版本证据保留。2026-11-01已返回备用SD新安装session7完整原件，图片65条、64/64块ARM d/s分析核验通过，对应fresh执行分支现已合入正式主线。新安装不再要求旧79条历史；旧安装仍保留原历史门禁。首次部署见first_installation.md，实际验证范围见fresh_sd_acceptance_20261101.md。

## 电脑端Vivado入口

使用Vivado2026.1。输出必须是不存在的、仓库外的短英文目录；Windows路径过长会导致IP生成失败。不要在图形界面打开其他项目时复用同一Vivado会话。构建入口不会下载硬件或生成新bitstream。

```powershell
python -B build/reproduce_fpga.py --board ax7010 --vivado C:/AMDDesignTools/2026.1/Vivado/bin/vivado.bat --output C:/glitchscope_runs/ax7010_run1
python -B build/reproduce_fpga.py --board ax7020 --vivado C:/AMDDesignTools/2026.1/Vivado/bin/vivado.bat --output C:/glitchscope_runs/ax7020_run1
```

入口仅解析实际时序数值，仍要求人工核对DRC、覆盖范围和异步边界。新生成的检查点不自动替换已验收固件。7020采用100MHz约束；当前环境PYNQ名义150/推算100的关系见 `clock_reference.md`。

## STM32入口

使用已安装的Keil ARM工具链6.24和STM32F1xx_DFP2.4.1。不要直接靠关闭编译警告绕过大小写问题。下面入口把源码复制到新的外部目录，仅在生成副本中恢复 `RTE_Components.h` 的Keil/CMSIS固定拼写，保留公开源码文件名及内容；不会擦除、下载或复位STM32。

```powershell
python -B build/rebuild_stm32.py --keil C:/Keil_v5/UV4/UV4.exe --output C:/glitchscope_runs/stm32_run1
```

Keil路径依本机安装修改。输出报告记录工具、源文件SHA和产物，并校验HEX与 `board/firmware/stm32/` 原件一致。不同编译器版本可能产生不同机器码，应保留失败报告并单独评估，不能放宽哈希条件自动采用。

## 板端统一软件复现入口

将整个本发行版源码目录复制到 `/home/xilinx/jupyter_notebooks/test_10_14/` 下的新目录，不覆盖正在运行的旧包，不复制旧软件通过凭据。进入新的 `glitchscope` 目录后：

```bash
/usr/local/share/pynq-venv/bin/python3 -B board/reproduce_software.py --output /home/xilinx/jupyter_notebooks/test_10_14/reproduction_result_01
```

输出目录必须不存在，并位于源码目录外。需要当前PYNQ armv7l/32位环境、NumPy、Pillow及gcc。脚本依次验证发布清单、检查依赖、运行软件测试、编译原生库、加载并核对9个导出符号；不会调用导出函数、启动接收线程、映射设备、加载Overlay、生成授权或发送START。每15秒提示阶段进度；失败保留全部日志，不自动重试。

成功后回传结果目录中的 `report.json`。重新编译的库仅保存在输出目录，不能直接替代执行器绑定哈希的已验收库。这个PASS仅覆盖板端软件及构建，不等于新固件/最终包实板功能验收；后者须使用各自安装绑定的真实注册表与账本、操作者明确的任务范围/预算；新安装从0开始，旧安装不重建历史。


## 板端软件原件补充

2026-10-29已归档操作者提供的result原件15文件，来源和SHA可追溯，工作台运行manifest与当前正式版一致。该结果对应原复现发行包；新首次安装候选未被本报告替代。依赖日志的Pillow7.0.0为实际观察值，须与requirements声明及后续干净环境测试区分记录。
