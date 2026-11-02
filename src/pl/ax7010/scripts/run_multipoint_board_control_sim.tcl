# Full RTL eight-pin regression, not a routed netlist, timing sim or START test.
set mb_root [file normalize [file join [file dirname [info script]] ..]]
set mb_review [file join $mb_root evidence reset_component_pass_20261017]
if {![file isfile [file join $mb_review review.json]]} {error "Reviewed reset-component log missing"}
set mb_fd [open [file join $mb_root rtl sources.txt] r]
set mb_names [split [read $mb_fd] "\n"];close $mb_fd
set mb_sources {}
foreach mb_name $mb_names {
 set mb_name [string trim $mb_name];if {$mb_name eq ""} {continue}
 set mb_path [file join $mb_root rtl $mb_name]
 set mb_frozen [file join $mb_review reviewed_inputs rtl $mb_name]
 if {![file isfile $mb_frozen]} {error "Unreviewed RTL file $mb_name"}
 set mb_fd [open $mb_path rb];set mb_actual [read $mb_fd];close $mb_fd
 set mb_fd [open $mb_frozen rb];set mb_saved [read $mb_fd];close $mb_fd
 if {$mb_actual ne $mb_saved} {error "RTL changed after reset-component review: $mb_name"}
 lappend mb_sources $mb_path
}
if {[llength $mb_sources]!=49} {error "Expected 49 frozen RTL inputs"}
source [file join $mb_root scripts close_owned_projects.tcl]
ax7010_close_owned_projects $mb_root
set mb_work [file join $mb_root build mpb12_[clock milliseconds]]
create_project mpb12 [file join $mb_work p] -part xc7z010clg400-1
set_property target_simulator XSim [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
set_property source_mgmt_mode None [current_project]
set mb_top tb_mp_board_v0_12
set mb_fd [open [file join $mb_root sim ${mb_top}.v] r];set mb_tb [read $mb_fd];close $mb_fd
set mb_tb [string map [list {"vectors/} "\"$mb_root/sim/vectors/"] $mb_tb]
set mb_local [file join $mb_work ${mb_top}.v]
set mb_fd [open $mb_local w];puts -nonewline $mb_fd $mb_tb;close $mb_fd
file mkdir [file join $mb_work vector_snapshot]
foreach mb_vector [glob -directory [file join $mb_root sim vectors] *.mem] {
 file copy $mb_vector [file join $mb_work vector_snapshot [file tail $mb_vector]]
}
add_files -fileset sim_1 -norecurse [concat $mb_sources [list $mb_local]]
set_property top $mb_top [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
puts "MULTIPOINT_V12_BOARD_CONTROL_WORK $mb_work FULL_RTL_MMCM_CDC_AXI_EXPECTED_49_REPLIES_WATCHDOG_300MS"
launch_simulation -simset sim_1 -mode behavioral
run all
puts "MULTIPOINT_V12_BOARD_CONTROL_REVIEW_REQUIRED NO_H1_UPLOAD_NO_START_NO_SYNTH_NO_BITSTREAM_NO_HARDWARE"
