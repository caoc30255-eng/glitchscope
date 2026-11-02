# Physical H1 mapping only. Procedural guards and timing are in native Tcl hook.
set_property PACKAGE_PIN T16 [get_ports h1_tx_pin]
set_property PACKAGE_PIN U17 [get_ports h1_rx_pin]
set_property IOSTANDARD LVCMOS33 [get_ports {h1_tx_pin h1_rx_pin}]
set_property DRIVE 8 [get_ports h1_tx_pin]
set_property SLEW SLOW [get_ports h1_tx_pin]
