# Route the exact fitted candidate once. No placement rerun, bitstream or JTAG.
proc ax7010_multipoint_route_review {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set checkpoint [file join $root build place12_1792249026603 placed_mp12.dcp]
 if {![file isfile $checkpoint] || ![file isfile [file join $root evidence placement_user_review.json]]} {
  error "Reviewed fitted multi-point placement is missing"
 }
 set snapshot [file join $root build source_1792243702793 source_snapshot]
 set inputs [glob -nocomplain -directory $snapshot -tails rtl/* constraints/*]
 if {[llength $inputs]!=52} {error "Expected52 frozen implementation inputs"}
 foreach relative $inputs {
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $snapshot $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "Input changed after placement: $relative"}
 }
 source [file join $root scripts close_owned_projects.tcl]
 ax7010_close_owned_projects $root
 create_project -in_memory ax7010_multipoint_route_v0_12 -part xc7z010clg400-1
 open_checkpoint $checkpoint
 source [file join $root scripts restore_candidate_message_defaults.tcl]
 source [file join $root constraints async_entry_review_v0_1_2.tcl]
 foreach {name period} {PL_INPUT_50 20.0 ctrl_unbuf 10.0 life_unbuf 20.0} {
  set clock [get_clocks -quiet $name]
  if {[llength $clock]!=1 || [get_property PERIOD $clock]!=$period} {error "Clock mismatch: $name"}
 }
 set out [file join $root build route12_[clock milliseconds]]
 file mkdir $out
 puts "MULTIPOINT_V12_ROUTE_REPORTS $out"
 set registers [dict create]
 set brams [get_cells -hier -quiet -filter {REF_NAME =~ RAMB*}]
 if {[llength $brams]!=47} {error "Expected47 actual BRAM cells"}
 foreach cell $brams {dict set registers $cell [list [get_property DOA_REG $cell] [get_property DOB_REG $cell]]}
 report_exceptions -file [file join $out exceptions_before.txt]
 report_timing_summary -report_unconstrained -max_paths 20 -file [file join $out timing_before.txt]
 # The design consumes4400/4400 slices. Preserve its exact fitted placement.
 route_design -directive Explore
 report_route_status -file [file join $out route_status.txt]
 report_timing_summary -report_unconstrained -max_paths 30 -file [file join $out timing_routed.txt]
 report_bus_skew -file [file join $out bus_skew_routed.txt]
 check_timing -verbose -file [file join $out check_timing_routed.txt]
 report_utilization -file [file join $out utilization_routed.txt]
 report_utilization -hierarchical -file [file join $out utilization_hierarchical_routed.txt]
 report_control_sets -verbose -file [file join $out control_sets_routed.txt]
 report_drc -file [file join $out drc_routed.txt]
 report_methodology -file [file join $out methodology_routed.txt]
 report_drc -checks [get_drc_checks -quiet LUTLP-1] -file [file join $out combinational_loops.txt]
 report_drc -ruledeck bitstream_checks -file [file join $out bitstream_checks.txt]
 report_clocks -file [file join $out clocks_routed.txt]
 report_clock_utilization -file [file join $out clock_utilization_routed.txt]
 report_exceptions -file [file join $out exceptions_routed.txt]
 write_xdc [file join $out effective_constraints_routed.xdc]
 write_checkpoint [file join $out routed_mp12.dcp]
 set fd [open [file join $out bram_registers_routed.txt] w]
 dict for {cell before} $registers {
  if {[llength [get_cells -quiet $cell]]!=1} {close $fd;error "BRAM disappeared: $cell"}
  set after [list [get_property DOA_REG $cell] [get_property DOB_REG $cell]]
  puts $fd "$cell DOA_DOB=$after"
  if {$after ne $before} {close $fd;error "BRAM register setting changed: $cell"}
 }
 close $fd
 puts "MULTIPOINT_V12_ROUTE_REVIEW_REQUIRED $out ACTUAL_SETUP_HOLD_SKEW_DRC_PENDING_NO_BITSTREAM_NO_HARDWARE"
}
ax7010_multipoint_route_review
