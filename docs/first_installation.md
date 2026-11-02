# 领航者7020：从零安装正式指南

已合入与备用SD成功session7版本哈希一致的fresh分支。已验证环境：领航者7020、PYNQ2.7.0、Python3.8.2、Linux armv7l/32bit。时钟口径保持PYNQ名义150MHz、按板载参考和寄存器推导约100MHz，详见clock_reference.md。

## 1. 准备系统和源码

保留原工作卡，将匹配领航者7020的PYNQ镜像烧录到备用SD，断电换卡并启动，核对网络与软件环境。OS镜像及厂商工具不随工程分发。

将整个glitchscope源码复制或解压到一个新目录，不复制旧会话、账本、授权或旧软件通过凭据。下例假定源码位于/home/xilinx/jupyter_notebooks/test_10_14/glitchscope。结果目录和runs必须在源码外，且尚不存在。

## 2. 软件及原生库复现

```bash
cd /home/xilinx/jupyter_notebooks/test_10_14/glitchscope
/usr/local/share/pynq-venv/bin/python3 -B board/reproduce_software.py \
  --output /home/xilinx/jupyter_notebooks/test_10_14/reproduction_result_01
```

脚本校验源码、检查依赖、运行工作台回归并编译/加载原生库，但不安装新库、不调用接收线程、不映射设备、不加载Overlay、不发送START。保留报告和全部日志；仅当前manifest对应的目标板PASS可用于安装。

## 3. 创建0历史、0额度的新安装

```bash
/usr/local/share/pynq-venv/bin/python3 -B src/ps/workbench/bootstrap_fresh_install.py \
  --runs /home/xilinx/jupyter_notebooks/test_10_14/fresh_runs_01 \
  --assets board/firmware \
  --receipt /home/xilinx/jupyter_notebooks/test_10_14/reproduction_result_01/software/report.json \
  --confirm '创建全新安装，不导入旧会话或额度'

/usr/local/share/pynq-venv/bin/python3 -B src/ps/workbench/prepare_demo_install.py \
  --config /home/xilinx/jupyter_notebooks/test_10_14/fresh_runs_01/live_config.json
```

产生安装ID、fresh_installation.json、0条namespace分配和空trial_registry；初始批准额度为0。旧安装继续核对原历史，不能放入fresh标记重解释旧数据、删除旧账本或伪造79个编号。初始化中断时保留部分目录进行核对，不在同一路径自动重试。

## 4. 启动工作台

停止旧网页和控制服务后，在板卡终端执行；加载原系统环境脚本时不启用set -u，以免未定义变量导致启动失败。

```bash
sudo bash <<'SH'
set -e
set -a
. /etc/environment
set +a
for profile_file in /etc/profile.d/*.sh; do
    if [ -r "$profile_file" ]; then . "$profile_file"; fi
done
project=/home/xilinx/jupyter_notebooks/test_10_14/glitchscope
runs=/home/xilinx/jupyter_notebooks/test_10_14/fresh_runs_01
web=$(mktemp -d /home/xilinx/jupyter_notebooks/test_10_14/glitchscope_web_XXXXXXXX)
/usr/local/share/pynq-venv/bin/python3 -B "$project/src/ps/workbench/server.py" \
  --port 8765 --runs "$runs" --data "$web" --live-config "$runs/live_config.json"
SH
```

保持终端运行，电脑SSH转发本地18768到板侧127.0.0.1:8765，浏览器访问http://127.0.0.1:18768/。先确认会话与任务为空、未授予额度。由操作者在网页确认本轮范围和预算，再预览并确认单任务。

每个新硬件会话前手动重载原7010，STM32保持运行。CONFIG、无扰动参照和真实试验均计入硬件记录；软件修复、分析和导出不消耗硬件额度。

## 5. 异常和更新

UNKNOWN保留，不自动退款或续跑。版本更新前结束旧轮次、关闭旧服务。合作进程使用/run/lock/glitchscope_pl_runtime.lock；它不能阻止不遵守锁协议的软件直接访问设备。资源关闭不确定产生quarantine时保留现场核对，不能直接删除标记绕过。

模型预检同时校验外层清单、内层清单和冻结模型原始LF字节。共同可用窗口为1至64块可提供局部参考，0块或完整性异常不提供；仍不替代全64推荐或硬件验证。

## 验收范围

备用SD启动和首次0记录来自操作者实际启动/初始化输出；fresh_runs/session7完整原件验证图片65条全部完成、64/64窗口ARM分析通过。d4/s=-2是本轮统一软件候选，没有在本轮新增推荐配置的实板复核，也不证明任意参数或图片泛化。详见fresh_sd_acceptance_20261101.md。完整原件另存评审包，公开源码不放入用户图片源数据。
