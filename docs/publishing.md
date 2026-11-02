# GitHub发布说明

仓库：https://github.com/caoc30255-eng/glitchscope

发布者于2026-11-03授权将此公开工程推送到个人账号，提交作者和提交邮箱采用正常账号信息。工程文件继续保持既有参赛身份限制；私有原始证据、旧压缩包和个人关键词表不上传。

仓库设置了`.gitattributes`禁用自动换行转换，冻结模型和SHA绑定文件按原字节克隆。`build/verify_release.py`忽略Git自身元数据，仍检查源码、文档及其他交付文件。

首次克隆后先运行`python -B build/create_empty_directories.py`，再校验发布清单。软件测试的保留输出由gitignore排除，运行输出应放在源码目录之外。

自有代码采用MIT，第三方许可遵循各文件原条款。此仓库不附带完整演示图片或私有评审原件；可使用自备图像和合成测试数据。
