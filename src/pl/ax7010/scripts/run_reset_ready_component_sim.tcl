# User-run old/new reset-contract simulation. No synthesis or board effects.
set rr_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $rr_root scripts close_owned_projects.tcl]
ax7010_close_owned_projects $rr_root
set rr_work [file join $rr_root build rr12_[clock milliseconds]]
create_project rr12 [file join $rr_work p] -part xc7z010clg400-1
set_property target_simulator XSim [current_project]
set_property source_mgmt_mode None [current_project]
add_files -fileset sim_1 -norecurse [list \
 [file join $rr_root sim golden h1_board_reset_handoff_golden_v0_2.v] \
 [file join $rr_root rtl h1_board_reset_handoff_v0_2.v] \
 [file join $rr_root sim tb_reset_ready_registered_v0_12.v]]
set_property top tb_reset_ready_registered_v0_12 [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
puts "RESET_READY_COMPONENT_WORK $rr_work WATCHDOG_100000_NS"
launch_simulation -simset sim_1 -mode behavioral
run all
puts "RESET_READY_COMPONENT_LOG_REVIEW_REQUIRED NO_SYNTH_NO_BITSTREAM_NO_HARDWARE"
