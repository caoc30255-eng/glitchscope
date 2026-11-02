# Compact actual routed functional netlist regression. No SDF/bitstream/hardware.
set mn_root [file normalize [file join [file dirname [info script]] ..]]
set mn_netlist [file join $mn_root build signoff12_1792249770633 routed_functional_netlist.v]
if {![file isfile $mn_netlist] || ![file isfile [file join $mn_root evidence signoff_user_review.json]]} {
 error "Reviewed routed functional netlist export missing"
}
source [file join $mn_root scripts close_owned_projects.tcl]
ax7010_close_owned_projects $mn_root
set mn_work [file join $mn_root build mn12_[clock milliseconds]]
create_project mn12 [file join $mn_work p] -part xc7z010clg400-1
set_property target_simulator XSim [current_project]
set_property source_mgmt_mode None [current_project]
set mn_top tb_mp_net_v0_12
set mn_fd [open [file join $mn_root sim ${mn_top}.v] r];set mn_tb [read $mn_fd];close $mn_fd
set mn_tb [string map [list {"vectors/} "\"$mn_root/sim/vectors/"] $mn_tb]
set mn_local [file join $mn_work ${mn_top}.v]
set mn_fd [open $mn_local w];puts -nonewline $mn_fd $mn_tb;close $mn_fd
file mkdir [file join $mn_work vector_snapshot]
foreach mn_name {net_requests.mem net_replies.mem} {
 file copy [file join $mn_root sim vectors $mn_name] [file join $mn_work vector_snapshot $mn_name]
}
add_files -fileset sim_1 -norecurse [list $mn_netlist $mn_local]
set_property top $mn_top [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
puts "MULTIPOINT_ROUTED_CONTROL_WORK $mn_work EXPECTED_AROUND_32MS_WATCHDOG_80MS_7_FULL_REPLIES"
launch_simulation -simset sim_1 -mode behavioral
run all
puts "MULTIPOINT_ROUTED_CONTROL_LOG_REVIEW_REQUIRED NO_SDF_NO_UPLOAD_NO_START_NO_BITSTREAM_NO_HARDWARE"
