# Offline behavioral simulation only. No synthesis, bitstream or hardware access.
set package_root [file normalize [file dirname [info script]]]
if {[llength [get_projects -quiet]] != 0} {
    error "An existing project is open. Close it manually or use a separate Vivado window, then source this script."
}
set build_dir [file join $package_root build run_[clock seconds]_[clock clicks]]
file mkdir $build_dir
set project_name b_rx_rtl
create_project $project_name $build_dir -part xc7z020clg400-1
set_property target_simulator XSim [current_project]
set sources [list [file join $package_root rtl uart_rx_b_7020_observe_v0_1.v] [file join $package_root rtl rx_ce_gen_7020_v2_2.v] [file join $package_root rtl tb_b_receiver_cosim.sv]]
add_files -fileset sim_1 -norecurse $sources
set_property file_type SystemVerilog [get_files tb_b_receiver_cosim.sv]
set_property top tb_b_receiver_cosim [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
# The initial block opens cases.txt at time zero, so stage data BEFORE launch.
set sim_dir [file join $build_dir ${project_name}.sim sim_1 behav xsim]
file mkdir $sim_dir
file copy [file join $package_root cases.txt] [file join $sim_dir cases.txt]
file copy [file join $package_root vectors] [file join $sim_dir vectors]
puts "B_RX_SIM_OUTPUT: $sim_dir"
puts "Expected: 1125 cases, 11389950 compared clocks. Running until testbench finish."
launch_simulation -simset sim_1 -mode behavioral
run all
set log_path [file join $sim_dir scoreboard.log]
if {![file exists $log_path]} { error "B_RX_REVIEW_REQUIRED: scoreboard.log missing; simulation did not complete." }
set fh [open $log_path r]
set text [read $fh]
close $fh
if {[string first "B_RX_RTL_FAIL" $text] >= 0} { error "B_RX_REVIEW_REQUIRED: RTL mismatch. Retain full build directory." }
if {![regexp {B_RX_RTL_COSIM_PASS cases=1125 cycles=11389950} $text]} {
    error "B_RX_REVIEW_REQUIRED: exact PASS marker missing. Retain full build directory."
}
puts "B_RX_RTL_COSIM_LOG_READY_FOR_REVIEW cases=1125 cycles=11389950"
puts "Send scoreboard.log and the simulation logs from: $sim_dir"
puts "SCOPE_OFFLINE_RTL_OUTPUT_COMPARISON_NO_BITSTREAM_NO_HARDWARE"
