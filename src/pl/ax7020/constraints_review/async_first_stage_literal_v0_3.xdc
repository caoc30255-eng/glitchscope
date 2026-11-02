# Literal XDC only; fanout/ASYNC_REG validation is executed separately by Tcl.
# Legacy RAW port exception remains redundant, not claimed removed.
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[0]}] -to [get_pins {system_i/receiver_axi_lite_0/inst/core/core/frontend/rx_sync_ff1_reg/D system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[0]/D system_i/h1_evidence_system_0/inst/receiver/frontend/rx_sync_ff1_reg/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[1]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[1]/D system_i/dut_response_axi_lite_0/inst/u_dut_response_axi_lite/u_dut_response_receiver/u_dut_uart_rx/rx_ff1_reg/D system_i/dut_response_axi_lite_0/inst/u_dut_response_axi_lite/live_sync1_reg/D system_i/h1_evidence_system_0/inst/evidence/core/chain/core/receiver/rx_ff1_reg/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[2]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[2]/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[3]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[3]/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[4]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[4]/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[5]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[5]/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[6]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[6]/D}]
set_false_path -reset_path -from [get_ports {raw_snapshot_async_i[7]}] -to [get_pins {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[7]/D}]
set_false_path -reset_path -from [get_ports {h1_rx_pin}] -to [get_pins {system_i/h1_evidence_system_0/inst/evidence/core/transport/rx/u_rx/rx_ff1_reg/D}]
set_false_path -reset_path -from [get_ports {uart_rtl_0_rxd}] -to [get_pins {system_i/axi_uartlite_0/U0/UARTLITE_CORE_I/UARTLITE_RX_I/INPUT_DOUBLE_REGS3/syncstages_ff_reg[0]/D}]
set_false_path -to [get_ports {h1_tx_pin}]
set_false_path -to [get_ports {uart_rtl_0_txd}]
