# 板侧软件与原生库复现原件

本目录15个result文件从操作者提供的共享目录只读复制，校验前后SHA一致，来源和文件哈希见provenance.json。软件报告绑定的工作台manifest与本正式版执行代码一致，重编库SHA与原验收库一致。

这是原glitchscope_source_20261029_reproduction.zip的板侧复现结果，不是新首次安装候选的结果；后者执行代码已变，需单独检查。hardware_acceptance=false，未启动接收器或发送START。日志记录NumPy1.20.3和Pillow7.0.0，作为这次实际环境保留，不改写为依赖文件声明的版本。
