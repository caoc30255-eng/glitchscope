# Profile字段与迁移

`schema=1`。`assets.bit/hwh`各有path和sha256；路径相对profile，绝对路径也支持。两文件须同目录同主文件名。`asset_kind=MOCK`禁止进入任何硬件阶段。

`registers`每项包含name、base、span、offset、access=RO、read_effect=none、expected，可选mask。只支持32位对齐读；拒绝read-clear、FIFO读取、越界和重复名称。不要为了让预检通过而把真实读副作用标成none。

`clock`可选：attribute为fclk0_mhz…fclk3_mhz，expected_mhz/tolerance_mhz表示配置读回门槛；configure_mhz仅load阶段使用。时钟门槛应来自该工程约束，而非照搬本项目150MHz。

`expected_machine`可选，如armv7l；机器类型不是板卡型号证明。目标阶段采用`Device.devices`、`MMIO.read`、`Overlay(download=True)`和`Clocks`接口，其他PYNQ版本须先核对接口。

返回`PASS_OFFLINE_PROFILE`或`PASS_TARGET_READBACK_ONLY`。BLOCKED时保留报告中的overlay_download_attempted/completed、clock_write_attempted和已完成读回。它不声称精确已加载bit身份、物理频率或应用功能通过。

每个寄存器必须给ip_name，可选hwh_interface消除多接口歧义。基址必须与HWH MEMRANGE一致，span允许为同一基址起的子范围，不可越过HWH跨度。mask必须非零。拒绝DTD/实体声明；HWH文件最大64MiB。

expected_hwh_device可核对元数据DEVICE；expected_board_model可精确匹配Device Tree model。后者缺失时默认只记录、不假称具体板卡已认证。REAL_BOARD_ASSET只是操作者声明，仍需正确原件和实际授权。

PYNQ官方说明：Overlay下载前会应用HWH时钟：https://pynq.readthedocs.io/en/latest/pynq_libraries/overlay.html 。所有load都需要时钟影响范围标记，内部写入未被插桩时如实记possible/unknown，不伪造已观测的硬件写入。
