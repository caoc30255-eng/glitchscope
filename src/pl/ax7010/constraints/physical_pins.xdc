# Candidate actual AX7010 eight PL pins; no debug sideband GPIO.
set_property PACKAGE_PIN U18 [get_ports pl_clk_50m]
set_property PACKAGE_PIN N15 [get_ports key_n]
set_property PACKAGE_PIN F17 [get_ports ctrl_rx_pin]
set_property PACKAGE_PIN F16 [get_ports ctrl_tx_pin]
set_property PACKAGE_PIN Y14 [get_ports h1_rx_pin]
set_property PACKAGE_PIN W14 [get_ports h1_tx_pin]
set_property PACKAGE_PIN W19 [get_ports w19_tx]
set_property PACKAGE_PIN W18 [get_ports fault_mark]
set_property IOSTANDARD LVCMOS33 [get_ports {pl_clk_50m key_n ctrl_rx_pin ctrl_tx_pin h1_rx_pin h1_tx_pin w19_tx fault_mark}]
set_property DRIVE 8 [get_ports {w19_tx fault_mark}]
set_property SLEW SLOW [get_ports {w19_tx fault_mark}]
# W18 is one LIFE clock/20ns actual mark, NOT the old stretched marker.
# No invented external synchronous clock or zero-delay I/O waiver.
