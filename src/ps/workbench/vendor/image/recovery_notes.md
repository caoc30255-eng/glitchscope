# v0.2.1 Notebook 保存兼容修正

本次 session_00000026 已完成握手和 CH2/MPG1 预检，但网页服务在 Notebook 文本一致性检查处被拒绝，未封存图片 executor、未发送本次图片 CONFIG/ITEM。原异常处理调用 pause_receiver，并将接收器 fault 置为 True；不允许将该标志改回 False 或重跑初始化续用当前会话。

旧检查把 Notebook 的代码文本和固定 .py 逐字比较；本方已复现仅删去代码末尾换行即触发同一异常。新检查仍对固定文件执行精确 SHA256 校验，对可自动保存的 Notebook 比较 Python AST（不含位置）。输出、执行次数、元数据、格式和注释不影响代码校验；参数、字面值、调用、顺序、代码单元格数量或语法变化继续拒绝。

代码检查已移到第1步的 Overlay、MMIO、UART 和编号分配之前。新 v0.2.1 目录独立交付，旧 v0.2、session26、历史编号和上传图片仓库保留。

## 恢复顺序

1. 上传新 ZIP，按给出的哈希校验并解压到 test_10_14。先运行新包的11项兼容测试及 package_tools 预检；这两步不接触板卡。
2. 在仍保留的 session26 Jupyter 内核中新建单元格，执行：

```python
from pathlib import Path
exec((Path('/home/xilinx/jupyter_notebooks/test_10_14/PYNQ_Image_Web_v0_2_1_2026-10-19')/'preserve_failure_close.py').read_text(encoding='utf-8'))
```

脚本只在 session26、无图片 executor、无在途记录、实际退役/许可计数均为0时收尾。先保留原Notebook、AST差异和接收快照，再关闭软件接收器与日志；不复位、不发试验帧。不删除编号文件或释放出新额度。

3. 把收尾输出保存。若 AST_match=False，应核对原Notebook究竟改动了哪些实际代码，不将其当成普通换行问题。原件已保存，后续不覆盖它。
4. 关闭旧内核，保持 STM32 正常 Run，不复位 STM32。按此前方式重新下载同一个7010 v0.12 bit，使此前握手使用的命名空间回到新试验状态；不生成新 bit。
5. 打开新目录下的 `image_upload.ipynb`，使用全新内核，分别执行第1步、第2步，不 Run All。沿用当前7020 bit/hwh，保留旧会话和trial_registry。
6. 上传仓库仍为 `web_image_assets`，641.webp 的预览 SHA 应保持 `7e3a11c306653f3bd8c1881bd77840b68da67bbbd91c9fc48832b2530a9c6f34`。服务成功后再从网页选择并封存，不自动发送。

v0.2.1 不改变毛刺计划、65条上限、原始数据审查、修复算法或执行器。该修正不等于本轮图片硬件试验已通过。
