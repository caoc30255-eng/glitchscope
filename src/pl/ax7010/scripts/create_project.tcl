# Create a fresh, portable source project. No synthesis or hardware effects.
set ax_pkg [file normalize [file join [file dirname [info script]] ..]]
source [file join $ax_pkg scripts close_owned_projects.tcl]
ax7010_close_owned_projects $ax_pkg
if {[llength [get_projects -quiet]]!=0} {error "Project close verification failed; new project not created"}
set ax_work [file join $ax_pkg build source_[clock milliseconds]]
if {[info exists ::env(GLITCHSCOPE_BUILD_OUTPUT)]} {set ax_work [file normalize $::env(GLITCHSCOPE_BUILD_OUTPUT)];if {[file exists $ax_work]} {error "BUILD_OUTPUT_MUST_BE_NEW"}}
set ax_project [file join $ax_work p]
file mkdir $ax_work
create_project ax7010_multipoint_v0_12 $ax_project -part xc7z010clg400-1
source [file join $ax_pkg scripts restore_candidate_message_defaults.tcl]
set_property target_language Verilog [current_project]
set_property target_simulator XSim [current_project]
set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]
set ax_fd [open [file join $ax_pkg rtl sources.txt] r]
set ax_names [split [read $ax_fd] "\n"];close $ax_fd
set ax_sources {}
foreach name $ax_names {
 set name [string trim $name];if {$name eq ""} {continue}
 set path [file join $ax_pkg rtl $name]
 if {![file isfile $path]} {error "Missing candidate RTL $name"}
 lappend ax_sources $path
}
if {[llength $ax_sources]!=49} {error "Expected 49 candidate RTL files"}
add_files -fileset sources_1 -norecurse $ax_sources
add_files -fileset constrs_1 -norecurse [list [file join $ax_pkg constraints root_clock_review.xdc] [file join $ax_pkg constraints physical_pins.xdc]]
set_property top h1_ax7010_uart_cdc_sync_board_top_v0_7 [get_filesets sources_1]
set_property source_mgmt_mode All [current_project]
# Same hierarchy for the existing reviewed UART/reset input boundaries.
add_files -fileset utils_1 -norecurse [file join $ax_pkg constraints async_entry_review_v0_1_2.tcl]
set_property STEPS.SYNTH_DESIGN.TCL.POST [file join $ax_pkg constraints async_entry_review_v0_1_2.tcl] [get_runs synth_1]
update_compile_order -fileset sources_1
puts "AX7010_MULTIPOINT_SOURCE_PROJECT_READY [file join $ax_project ax7010_multipoint_v0_12.xpr] NO_SYNTH_NO_BITSTREAM_NO_HARDWARE"
