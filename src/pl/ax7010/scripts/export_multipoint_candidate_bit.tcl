# Engineering candidate export explicitly authorized by the user.
# Run in a SECOND EMPTY Vivado process; do not interrupt the netlist simulator.
# No JTAG/download/flash/Overlay operations and no diagnostic downgrades.
proc mp12_export_check_rules {report allowed} {
 set fd [open $report r];set text [read $fd];close $fd
 set rows [regexp -all -inline -line {^\|[ ]*([A-Z0-9-]+)[ ]*\|[ ]*([^|]+)\|[^|]+\|[ ]*([0-9]+)[ ]*\|} $text]
 set found 0
 foreach {row rule severity count} $rows {
  incr found
  if {[string trim $severity] ne "Warning" || $rule ni $allowed} {
   error "Unreviewed rule $rule severity=$severity; candidate export denied"
  }
 }
 if {$found==0 && ![regexp {Checks found:[ ]*0} $text]} {error "Unreadable rule report"}
}
proc export_multipoint_candidate_bit {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set routed [file join $root build route12_1792249299054 routed_mp12.dcp]
 foreach name {route_user_review.json signoff_user_review.json parallel_candidate_export_authorization.json} {
  if {![file isfile [file join $root evidence $name]]} {error "Export context missing: $name"}
 }
 if {![file isfile $routed]} {error "Reviewed routed checkpoint missing"}
 if {[llength [get_projects -quiet]]!=0} {
  error "Use a second EMPTY Vivado window; current project/simulation preserved"
 }
 set snapshot [file join $root build source_1792243702793 source_snapshot]
 set inputs [glob -nocomplain -directory $snapshot -tails rtl/* constraints/*]
 if {[llength $inputs]!=52} {error "Expected52 frozen source/constraint inputs"}
 foreach relative $inputs {
  set fd [open [file join $root $relative] rb];set actual [read $fd];close $fd
  set fd [open [file join $snapshot $relative] rb];set saved [read $fd];close $fd
  if {$actual ne $saved} {error "Input differs from reviewed v0.12 DCP: $relative"}
 }
 create_project -in_memory ax7010_multipoint_bit_export_v0_12 -part xc7z010clg400-1
 open_checkpoint $routed
 source [file join $root scripts restore_candidate_message_defaults.tcl]
 foreach {clock period} {PL_INPUT_50 20.0 ctrl_unbuf 10.0 life_unbuf 20.0} {
  set object [get_clocks -quiet $clock]
  if {[llength $object]!=1 || [get_property PERIOD $object]!=$period} {error "Clock contract differs"}
 }
 foreach {port pin} {pl_clk_50m U18 key_n N15 ctrl_rx_pin F17 ctrl_tx_pin F16 h1_rx_pin Y14 h1_tx_pin W14 w19_tx W19 fault_mark W18} {
  set object [get_ports -quiet $port]
  if {[llength $object]!=1 || [get_property PACKAGE_PIN $object] ne $pin || [get_property IOSTANDARD $object] ne "LVCMOS33"} {
   error "Pin contract differs: $port"
  }
 }
 if {[llength [get_ports -quiet]]!=8} {error "Unexpected physical ports"}
 set out [file join $root exports candidate12_[clock milliseconds]]
 file mkdir $out
 puts "MULTIPOINT_V12_BIT_EXPORT_DIR $out"
 report_timing_summary -report_unconstrained -max_paths 30 -file [file join $out final_timing.txt]
 set fd [open [file join $out final_timing.txt] r];set text [read $fd];close $fd
 set pattern {WNS\(ns\)[^\n]*\n[^\n]*\n\s*([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)\s+([0-9]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)\s+([0-9]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([0-9]+)}
 if {![regexp $pattern $text match wns tns sc st whs ths hc ht wpws tpws pc] ||
     $wns<0 || $tns!=0 || $sc!=0 || $whs<0 || $ths!=0 || $hc!=0 || $wpws<0 || $tpws!=0 || $pc!=0} {
  error "Aggregate setup/hold/pulse-width timing not accepted; no bitstream"
 }
 check_timing -verbose -file [file join $out final_check_timing.txt]
 set fd [open [file join $out final_check_timing.txt] r];set text [read $fd];close $fd
 foreach check {no_clock unconstrained_internal_endpoints loops} {
  if {![regexp [format {checking %s \(([0-9]+)\)} $check] $text match count] || $count!=0} {
   error "Clock/coverage/loop check failed: $check"
  }
 }
 report_bus_skew -file [file join $out final_bus_skew.txt]
 set fd [open [file join $out final_bus_skew.txt] r];set text [read $fd];close $fd
 if {[string first "VIOLATED" $text]>=0} {error "Bus skew failed"}
 set rows [regexp -all -inline {Slack \(MET\)\s*:\s*([-0-9.]+)ns} $text]
 if {[llength $rows]!=32} {error "Expected16 met bus-skew constraints"}
 foreach {row slack} $rows {if {$slack<0} {error "Bus skew failed"}}
 report_route_status -file [file join $out final_route_status.txt]
 set fd [open [file join $out final_route_status.txt] r];set text [read $fd];close $fd
 if {![regexp {nets with routing errors[^:]*:\s*([0-9]+)} $text match errors] || $errors!=0 ||
     ![regexp {# of routable nets[^:]*:\s*([0-9]+)} $text match total] ||
     ![regexp {# of fully routed nets[^:]*:\s*([0-9]+)} $text match done] || $total!=$done} {
  error "Routing incomplete or unreadable report"
 }
 report_drc -ruledeck bitstream_checks -file [file join $out final_bitstream_checks.txt]
 mp12_export_check_rules [file join $out final_bitstream_checks.txt] {DPIP-1 DPOP-1 DPOP-2 ZPS7-1}
 report_methodology -file [file join $out final_methodology.txt]
 mp12_export_check_rules [file join $out final_methodology.txt] {LUTAR-1 SYNTH-6 TIMING-18 ULMTCS-1}
 report_drc -checks {LUTLP-1} -file [file join $out final_combinational_loops.txt]
 set fd [open [file join $out final_combinational_loops.txt] r];set text [read $fd];close $fd
 if {![regexp {Checks found:[ ]*0} $text]} {error "Combinational-loop check failed"}
 report_exceptions -file [file join $out final_exceptions.txt]
 report_utilization -file [file join $out final_utilization.txt]
 set bit [file join $out ax7010_multipoint_candidate_v0_12.bit]
 write_bitstream $bit
 if {![file isfile $bit] || [file size $bit]==0} {error "Bitstream not produced"}
 file copy [file join $root candidate_parallel_test_notes.md] [file join $out README_candidate.md]
 foreach name {route_user_review.json signoff_user_review.json parallel_candidate_export_authorization.json} {
  file copy [file join $root evidence $name] [file join $out $name]
 }
 set fd [open [file join $out export_inventory.txt] w]
 puts $fd "SOURCE_ROUTED_DCP=$routed"
 puts $fd "BIT=$bit BYTES=[file size $bit] PURE_PL_NO_HWH_NO_ARM_APPLICATION"
 puts $fd "USER_REQUESTED_PARALLEL_CANDIDATE_EXPORT_NETLIST_SIMULATION_CONTINUES_SEPARATELY"
 puts $fd "FULL_MULTI_H1_START_AND_PS_MULTI_ADAPTER_PENDING_NO_BOARD_DOWNLOAD_NO_HARDWARE_ACCEPTANCE"
 close $fd
 puts "MULTIPOINT_V12_CANDIDATE_BIT_CREATED $bit SIMULATION_PARALLEL_NO_BOARD_DOWNLOAD_NO_HARDWARE_ACCEPTANCE"
}
export_multipoint_candidate_bit
