# Native Tcl: source after checkpoint load, not read_xdc.
foreach pair {{h1_rx_pin image/core/u_rx/rx_ff1_reg/D} {ctrl_rx_pin image/ctrl_rx/rx_ff1_reg/D}} {
    lassign $pair port target
    set pins [get_pins -quiet $target]
    if {[llength $pins]!=1} {error "Expected UART first synchronizer pin: $target"}
    set_false_path -from [get_ports $port] -to $pins
}
set reset_pins [get_pins -hier -quiet -filter {NAME =~ *life_release_reg*/CLR || NAME =~ *ctrl_release_reg*/CLR}]
if {[llength $reset_pins]!=6} {error "Expected six release-chain CLR pins."}
set_false_path -from [get_ports key_n] -to $reset_pins
# MMCM RST is not a sequential data endpoint. No exception is added to it.
# No blanket clock cuts, internal-reset cuts or artificial interface delays.
