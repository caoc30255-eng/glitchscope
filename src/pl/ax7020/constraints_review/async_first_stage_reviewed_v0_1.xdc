# Reviewed full synthesis: evidence_1791856608199/input_audit_1791857911995.
# Only external asynchronous input -> exact first synchronizer D pins.
# Remove legacy input-port exceptions before applying explicit reviewed endpoints.
# UART output pins have no external common-clock timing contract; only their
# external output paths are excluded. All internal UART logic remains timed.
reset_path -from [get_ports {raw_snapshot_async_i[*]}]
foreach {name destinations} {
 {raw_snapshot_async_i[0]} {
  {system_i/receiver_axi_lite_0/inst/core/core/frontend/rx_sync_ff1_reg/D}
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[0]/D}
  {system_i/h1_evidence_system_0/inst/receiver/frontend/rx_sync_ff1_reg/D}
 }
 {raw_snapshot_async_i[1]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[1]/D}
  {system_i/dut_response_axi_lite_0/inst/u_dut_response_axi_lite/u_dut_response_receiver/u_dut_uart_rx/rx_ff1_reg/D}
  {system_i/dut_response_axi_lite_0/inst/u_dut_response_axi_lite/live_sync1_reg/D}
  {system_i/h1_evidence_system_0/inst/evidence/core/chain/core/receiver/rx_ff1_reg/D}
 }
 {raw_snapshot_async_i[2]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[2]/D}
 }
 {raw_snapshot_async_i[3]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[3]/D}
 }
 {raw_snapshot_async_i[4]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[4]/D}
 }
 {raw_snapshot_async_i[5]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[5]/D}
 }
 {raw_snapshot_async_i[6]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[6]/D}
 }
 {raw_snapshot_async_i[7]} {
  {system_i/raw_snapshot_axi_lite_0/inst/u_axi_snapshot/u_snapshot_tester/u_capture_frontend/sync_stage1_reg[7]/D}
 }
 {h1_rx_pin} {
  {system_i/h1_evidence_system_0/inst/evidence/core/transport/rx/u_rx/rx_ff1_reg/D}
 }
 {uart_rtl_0_rxd} {
  {system_i/axi_uartlite_0/U0/UARTLITE_CORE_I/UARTLITE_RX_I/INPUT_DOUBLE_REGS3/syncstages_ff_reg[0]/D}
 }
} {
 set source [get_ports -quiet $name]
 if {[llength $source]!=1} {error "Expected one reviewed input $name"}
 set targets {}
 foreach name_pin $destinations {
  set pins [get_pins -quiet $name_pin]
  if {[llength $pins]!=1} {error "Expected one reviewed first-stage D pin $name_pin"}
  set cell [get_cells -quiet -of_objects $pins]
  if {[llength $cell]!=1 || [get_property ASYNC_REG $cell]!=1} {error "Reviewed endpoint is not an ASYNC_REG cell $name_pin"}
  lappend targets [lindex $pins 0]
 }
 set actual [all_fanout -flat -endpoints_only -from $source]
 if {[lsort $actual] ne [lsort $targets]} {error "Asynchronous input fanout changed $name; review before applying constraints"}
 set_false_path -from $source -to $targets
}
foreach name {h1_tx_pin uart_rtl_0_txd} {
 set target [get_ports -quiet $name]
 if {[llength $target]!=1} {error "Expected one asynchronous UART output $name"}
 set_false_path -to $target
}
