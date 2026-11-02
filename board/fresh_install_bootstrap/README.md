# 从零安装入口

已合入正式主线，支持新安装0历史、0额度初始化。

先运行board/reproduce_software.py取得当前目标板软件报告，再运行src/ps/workbench/bootstrap_fresh_install.py和prepare_demo_install.py。

完整启动命令见docs/first_installation.md。初始化本身不加载Overlay、不启动接收器、不发送START。旧安装和UNKNOWN历史不被重建或清空。
