# Re-check the exact STA-reviewed DCP, then export simulation sources only.
# No optimization, place/route, bitstream, JTAG or hardware operations.
proc ax7010_multipoint_signoff_export_review {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set checkpoint [file join $root build route12_1792249299054 routed_mp12.dcp]
 if {![file isfile $checkpoint] || ![file isfile [file join $root evidence route_user_review.json]]} {
  error "Reviewed v0.12 routed STA result missing"
 }
 set snapshot [file join $root build source_1792243702793 source_snapshot]
 set inputs [glob -nocomplain -directory $snapshot -tails rtl/* constraints/*]
 if {[llength $inputs]!=52} {error "Expected52 frozen inputs"}
 foreach relative $inputs {
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $snapshot $relative] rb];set frozen [read $fd];close $fd
  if {$actual ne $frozen} {error "Input differs from STA-reviewed revision: $relative"}
 }
 source [file join $root scripts close_owned_projects.tcl]
 ax7010_close_owned_projects $root
 create_project -in_memory ax7010_multipoint_signoff_v0_12 -part xc7z010clg400-1
 open_checkpoint $checkpoint
 source [file join $root scripts restore_candidate_message_defaults.tcl]
 foreach {clock period} {PL_INPUT_50 20.0 ctrl_unbuf 10.0 life_unbuf 20.0} {
  set object [get_clocks -quiet $clock]
  if {[llength $object]!=1 || [get_property PERIOD $object]!=$period} {error "Clock contract changed"}
 }
 foreach {port pin} {pl_clk_50m U18 key_n N15 ctrl_rx_pin F17 ctrl_tx_pin F16 h1_rx_pin Y14 h1_tx_pin W14 w19_tx W19 fault_mark W18} {
  set object [get_ports -quiet $port]
  if {[llength $object]!=1 || [get_property PACKAGE_PIN $object] ne $pin || [get_property IOSTANDARD $object] ne "LVCMOS33"} {
   error "Reviewed pin contract differs: $port"
  }
 }
 if {[llength [get_ports -quiet]]!=8} {error "Unexpected top-level ports"}
 set out [file join $root build signoff12_[clock milliseconds]]
 file mkdir $out
 puts "MULTIPOINT_V12_SIGNOFF_EXPORT_DIR $out"
 report_timing_summary -report_unconstrained -max_paths 30 -file [file join $out timing.txt]
 set fd [open [file join $out timing.txt] r];set text [read $fd];close $fd
 # Check the aggregate table, not the first per-clock Setup/Hold detail block.
 set pattern {WNS\(ns\)[^\n]*\n[^\n]*\n\s*([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)\s+([0-9]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)\s+([0-9]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)}
 if {![regexp $pattern $text match wns tns setup_count setup_total whs ths hold_count hold_total wpws tpws pw_count] ||
     $wns<0 || $tns!=0 || $setup_count!=0 || $whs<0 || $ths!=0 || $hold_count!=0 ||
     $wpws<0 || $tpws!=0 || $pw_count!=0} {
  error "Aggregate setup/hold/pulse-width timing failed; no export"
 }
 report_route_status -file [file join $out route_status.txt]
 set fd [open [file join $out route_status.txt] r];set text [read $fd];close $fd
 if {![regexp {nets with routing errors[^:]*:\s*([0-9]+)} $text match errors] || $errors!=0 ||
     ![regexp {# of routable nets[^:]*:\s*([0-9]+)} $text match total] ||
     ![regexp {# of fully routed nets[^:]*:\s*([0-9]+)} $text match done] || $done!=$total} {
  error "Routing incomplete or unreadable report"
 }
 report_bus_skew -file [file join $out bus_skew.txt]
 set fd [open [file join $out bus_skew.txt] r];set text [read $fd];close $fd
 if {[string first "VIOLATED" $text]>=0} {error "Bus skew failed"}
 set rows [regexp -all -inline {Slack \(MET\)\s*:\s*([-0-9.]+)ns} $text]
 if {[llength $rows]!=32} {error "Expected16 met bus skew constraints"}
 foreach {row slack} $rows {if {$slack<0} {error "Bus skew failed"}}
 check_timing -verbose -file [file join $out check_timing.txt]
 report_drc -file [file join $out drc.txt]
 report_drc -ruledeck bitstream_checks -file [file join $out bitstream_checks.txt]
 report_drc -checks {LUTLP-1} -file [file join $out combinational_loops.txt]
 report_methodology -file [file join $out methodology.txt]
 report_exceptions -file [file join $out exceptions.txt]
 report_utilization -file [file join $out utilization.txt]
 report_clocks -file [file join $out clocks.txt]
 write_verilog -mode funcsim [file join $out routed_functional_netlist.v]
 write_xdc [file join $out effective_constraints.xdc]
 puts "MULTIPOINT_V12_FUNCTIONAL_NETLIST_EXPORTED $out NETLIST_REGRESSION_AND_FULL_START_PENDING_NO_BITSTREAM_NO_HARDWARE"
}
ax7010_multipoint_signoff_export_review
