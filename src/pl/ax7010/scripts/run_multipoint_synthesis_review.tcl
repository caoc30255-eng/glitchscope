# Resource review only. Does not implement, create a bitstream, or access JTAG.
proc ax7010_multipoint_synthesis_review {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set reviewed [file join $root evidence reset_component_pass_20261017 reviewed_inputs]
 set board_review [file join $root evidence board_control_pass_20261017]
 if {![file isfile [file join $board_review review.json]]} {error "Full-board control simulation review missing"}
 set fd [open [file join $root rtl sources.txt] r];set names [split [read $fd] "\n"];close $fd
 set inputs {}
 foreach name $names {
  set name [string trim $name];if {$name eq ""} {continue}
  set relative [file join rtl $name]
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $reviewed $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "RTL changed since reviewed simulation: $relative"}
  lappend inputs $relative
 }
 if {[llength $inputs]!=49} {error "Expected 49 reviewed v0.12 RTL sources"}
 foreach name {root_clock_review.xdc physical_pins.xdc async_entry_review_v0_1_2.tcl} {
  set relative [file join constraints $name]
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $board_review reviewed_inputs $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "Constraint changed since board review: $name"}
  lappend inputs $relative
 }
 source [file join $root scripts create_project.tcl]
 set snapshot [file join $ax_work source_snapshot]
 file mkdir [file join $snapshot rtl]
 file mkdir [file join $snapshot constraints]
 foreach relative $inputs {file copy [file join $root $relative] [file join $snapshot $relative]}
 puts "MULTIPOINT_V12_SYNTH_WORK $ax_work"
 launch_runs synth_1 -scripts_only
 set generated [file join [get_property DIRECTORY [get_runs synth_1]] h1_ax7010_uart_cdc_sync_board_top_v0_7.tcl]
 if {![file isfile $generated]} {error "Generated synthesis script missing"}
 set fd [open $generated r];set script [read $fd];close $fd
 foreach line [split $script "\n"] {
  if {[string match {*set_msg_config*} $line] && [string match {*-severity*ERROR*} $line] && [string match {*-new_severity*} $line]} {
   error "ERROR severity downgrade exported; synthesis not launched: $line"
  }
 }
 file copy $generated [file join $ax_work reviewed_generated_synth.tcl]
 reset_runs synth_1
 launch_runs synth_1 -jobs 2
 wait_on_run synth_1
 if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
  error "Multi-point synthesis did not complete; no implementation or bitstream"
 }
 foreach relative $inputs {
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $snapshot $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "Source changed during synthesis; mixed revision rejected: $relative"}
 }
 open_run synth_1
 if {[llength [get_ports -quiet]]!=8} {error "Unexpected physical port count"}
 report_utilization -file [file join $ax_work utilization_synth.txt]
 report_utilization -hierarchical -file [file join $ax_work utilization_hierarchical.txt]
 report_control_sets -verbose -file [file join $ax_work control_sets_synth.txt]
 report_timing_summary -report_unconstrained -max_paths 30 -file [file join $ax_work timing_synth.txt]
 check_timing -verbose -file [file join $ax_work check_timing.txt]
 report_drc -file [file join $ax_work drc_synth.txt]
 report_methodology -file [file join $ax_work methodology_synth.txt]
 report_clocks -file [file join $ax_work clocks.txt]
 write_checkpoint [file join $ax_work multipoint_synth.dcp]
 puts "MULTIPOINT_V12_SYNTH_REVIEW_REQUIRED $ax_work RESOURCE_AND_TIMING_PENDING_NO_IMPLEMENTATION_NO_BITSTREAM_NO_HARDWARE"
}
ax7010_multipoint_synthesis_review
