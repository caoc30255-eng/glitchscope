# Implement placement only, using the successful baseline no-PSIP strategy.
# No clock relaxation, new timing exceptions, routing, bitstream or JTAG.
proc ax7010_multipoint_placement_review {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set work [file join $root build source_1792243702793]
 set checkpoint [file join $work multipoint_synth.dcp]
 if {![file isfile $checkpoint] || ![file isfile [file join $root evidence synthesis_user_review.json]]} {
  error "Reviewed successful multi-point synthesis is missing"
 }
 set snapshot [file join $work source_snapshot]
 set inputs [glob -nocomplain -directory $snapshot -tails rtl/* constraints/*]
 if {[llength $inputs]!=52} {error "Expected49RTL+3constraints frozen synthesis inputs"}
 foreach relative $inputs {
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $snapshot $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "Input changed since synthesis: $relative"}
 }
 source [file join $root scripts close_owned_projects.tcl]
 ax7010_close_owned_projects $root
 create_project -in_memory ax7010_multipoint_place_v0_12 -part xc7z010clg400-1
 open_checkpoint $checkpoint
 source [file join $root scripts restore_candidate_message_defaults.tcl]
 source [file join $root constraints async_entry_review_v0_1_2.tcl]
 foreach {name period} {PL_INPUT_50 20.0 ctrl_unbuf 10.0 life_unbuf 20.0} {
  set clock [get_clocks -quiet $name]
  if {[llength $clock]!=1 || [get_property PERIOD $clock]!=$period} {error "Clock mismatch: $name"}
 }
 set out [file join $root build place12_[clock milliseconds]]
 file mkdir $out
 puts "MULTIPOINT_V12_PLACEMENT_REPORTS $out STRATEGY=NO_PSIP_EXPLORE"
 report_exceptions -file [file join $out exceptions_before.txt]
 report_clocks -file [file join $out clocks_before.txt]
 opt_design
 opt_design -control_set_merge -merge_equivalent_drivers
 opt_design -remap
 report_utilization -file [file join $out utilization_optimized.txt]
 report_utilization -hierarchical -file [file join $out utilization_hierarchical_optimized.txt]
 report_control_sets -verbose -file [file join $out control_sets_optimized.txt]
 write_checkpoint [file join $out optimized_mp12.dcp]
 # -no_psip is the same placement option used by the accepted fitted v0.10.
 if {[catch {place_design -directive Explore -no_psip} failure options]} {
  set fd [open [file join $out placement_failure.txt] w]
  puts $fd $failure
  if {[dict exists $options -errorinfo]} {puts $fd [dict get $options -errorinfo]}
  close $fd
  puts "MULTIPOINT_V12_PLACEMENT_FAILED_REPORTS_SAVED $out NO_RETRY_NO_ROUTE_NO_BITSTREAM"
  return -options $options $failure
 }
 report_utilization -file [file join $out utilization_placed.txt]
 report_utilization -hierarchical -file [file join $out utilization_hierarchical_placed.txt]
 report_control_sets -verbose -file [file join $out control_sets_placed.txt]
 report_timing_summary -report_unconstrained -max_paths 30 -file [file join $out timing_placed.txt]
 report_bus_skew -file [file join $out bus_skew_placed.txt]
 check_timing -verbose -file [file join $out check_timing_placed.txt]
 report_drc -file [file join $out drc_placed.txt]
 report_methodology -file [file join $out methodology_placed.txt]
 report_exceptions -file [file join $out exceptions_placed.txt]
 report_clocks -file [file join $out clocks_placed.txt]
 write_xdc [file join $out effective_constraints_placed.xdc]
 write_checkpoint [file join $out placed_mp12.dcp]
 puts "MULTIPOINT_V12_PLACEMENT_REVIEW_REQUIRED $out RESOURCE_TIMING_PENDING_NO_ROUTE_NO_BITSTREAM_NO_HARDWARE"
}
ax7010_multipoint_placement_review
