# User-run Vivado simulation only. No synthesis, bitstream or hardware access.
set mp_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $mp_root scripts close_owned_projects.tcl]
set mp_tops {tb_multipoint_owner_sender_v0_11 tb_multipoint_control_profile_v0_11}
if {[info exists mp_selected_tops]} {
 foreach mp_selected $mp_selected_tops {
  if {$mp_selected ni $mp_tops} {error "Unknown component top: $mp_selected"}
 }
 set mp_tops $mp_selected_tops
 unset mp_selected_tops
}
foreach mp_top $mp_tops {
 ax7010_close_owned_projects $mp_root
 if {[llength [get_projects -quiet]]!=0} {error "Current projects preserved; close check failed"}
 # Keep both build/project names short: XSim-generated Windows .obj paths
 # otherwise exceed MAX_PATH even while xsim_1.c itself still exists.
 set mp_tag [expr {$mp_top eq "tb_multipoint_owner_sender_v0_11" ? "mps11" : "mpc11"}]
 set mp_work [file join $mp_root build ${mp_tag}_[clock milliseconds]]
 create_project $mp_tag [file join $mp_work p] -part xc7z010clg400-1
 set_property target_simulator XSim [current_project]
 set_property source_mgmt_mode None [current_project]
 set mp_sources {}
 if {$mp_top eq "tb_multipoint_owner_sender_v0_11"} {
  set mp_names {h1_item_profile_owner_v0_1.v h1_payload_fault_overlay_v0_1.v h1_multipoint_window_v0_1.v h1_w19_frame_tx_v0_3.v h1_uart_tx_byte_v0_2.v}
 } else {
  set mp_names {ctrl_packet_parser_runtime_v0_1.v h1_p1_control_event_router_profile_v0_1.v h1_control_equal_tree_v0_1.v h1_p1_event_commit_ack_profile_v0_1.v h1_item_profile_owner_v0_1.v h1_p1_event_uart_tx_mmio_v0_1.v h1_p1_control_tx_arbiter_v0_1.v ctrl_uart_tx.v}
 }
 foreach mp_name $mp_names {lappend mp_sources [file join $mp_root rtl $mp_name]}
 lappend mp_sources [file join $mp_root sim ${mp_top}.v]
 add_files -fileset sim_1 -norecurse $mp_sources
 set_property top $mp_top [get_filesets sim_1]
 set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
 puts "MULTIPOINT_COMPONENT_WORK TOP=$mp_top DIRECTORY=$mp_work"
 launch_simulation -simset sim_1 -mode behavioral
 run all
 puts "MULTIPOINT_COMPONENT_LOG_REVIEW_REQUIRED TOP=$mp_top NO_SYNTH_NO_BITSTREAM_NO_HARDWARE"
}
