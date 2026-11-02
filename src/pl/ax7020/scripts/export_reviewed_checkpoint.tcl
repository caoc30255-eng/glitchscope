# Export only the exact routed candidate accepted by the recorded STA/DRC review.
# Recheck actual timing, routing and DRC before bit generation. No board access.
proc export_h1_qualified_candidate {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 set work $root
 set checkpoint [file join $work qualified_controlled_route_1791889593354 03_clock_clean_route.dcp]
 set hwh [file join $root bit_hwh h1_7020_evidence_candidate_v0_1.hwh]
 foreach path [list $checkpoint $hwh] {if {![file isfile $path]} {error "Missing reviewed artifact $path"}}
 # Check all new register banks in metadata from this exact logical build.
 set fd [open $hwh r];set xml [read $fd];close $fd
 set ranges [regexp -all -inline {<MEMRANGE[^>]*>} $xml]
 foreach {bus base high} {S_H1 0x43C30000 0x43C30FFF S_CTRL 0x43C40000 0x43C40FFF S_MAIN 0x43C50000 0x43C53FFF S_AUX 0x43C60000 0x43C60FFF S_MAP 0x43C70000 0x43C70FFF S_CH0 0x43C80000 0x43C87FFF S_PROFILE 0x43C90000 0x43C90FFF S_SYS 0x43CA0000 0x43CA0FFF} {
  set found 0
  foreach range $ranges {
   if {[string first {INSTANCE="h1_evidence_system_0"} $range]>=0 && [string first [format {SLAVEBUSINTERFACE="%s"} $bus] $range]>=0 && [string first [format {BASEVALUE="%s"} $base] $range]>=0 && [string first [format {HIGHVALUE="%s"} $high] $range]>=0} {incr found}
  }
  if {$found!=1} {error "HWH bank/address mismatch $bus"}
 }
 set old "";catch {set old [current_project -quiet]}
 set opened "";catch {set opened [current_design -quiet]}
 if {$old ne ""} {
  set known [expr {[get_property NAME $old] eq "h1_7020_bit_export_candidate_v0_1"}]
  if {[get_property NAME $old] eq "h1_7020_evidence_system_v0_1"} {set known [expr {[file normalize [get_property DIRECTORY $old]] eq [file join $work p]}]}
  if {!$known} {error "Save and close unrelated project before reviewed candidate export"}
  if {$opened ne ""} {close_design}
  set remaining "";catch {set remaining [current_project -quiet]}
  if {$remaining ne ""} {close_project}
 }
 create_project -in_memory h1_7020_bit_export_candidate_v0_1 -part xc7z020clg400-2
 open_checkpoint $checkpoint
 set clock [get_clocks -quiet clk_fpga_0]
 if {[llength $clock]!=1 || [get_property PERIOD $clock]!=10.0} {error "Reviewed 100MHz clock missing"}
 set out [file join $root exports candidate_[clock milliseconds]]
 file mkdir $out
 puts "H1_7020_QUALIFIED_BIT_HWH_EXPORT_DIR $out"
 report_timing_summary -report_unconstrained -max_paths 20 -file [file join $out final_timing.txt]
 set fd [open [file join $out final_timing.txt] r];set timing [read $fd];close $fd
 foreach kind {Setup Hold PW} {
  set pattern [format {%s\s*:\s+([0-9]+)\s+Failing Endpoints,\s+Worst Slack\s+([-0-9.]+)ns,\s+Total Violation\s+([-0-9.]+)ns} $kind]
  if {![regexp $pattern $timing match failures slack violation]} {error "Cannot parse final $kind timing; export denied"}
  if {$failures!=0 || $slack<0 || $violation!=0} {error "Final $kind timing failed; export denied"}
 }
 check_timing -verbose -file [file join $out final_check_timing.txt]
 set fd [open [file join $out final_check_timing.txt] r];set coverage [read $fd];close $fd
 foreach check {no_clock unconstrained_internal_endpoints loops} {
  if {![regexp [format {checking %s \(([0-9]+)\)} $check] $coverage match failures] || $failures!=0} {error "Final timing coverage failed $check"}
 }
 report_route_status -file [file join $out final_route_status.txt]
 set fd [open [file join $out final_route_status.txt] r];set routes [read $fd];close $fd
 if {![regexp {nets with routing errors[^:\r\n]*:\s*([0-9]+)} $routes match errors] || $errors!=0} {error "Routing errors or unreadable route report; export denied"}
 if {![regexp {# of routable nets[^:\r\n]*:\s*([0-9]+)} $routes match total] || ![regexp {# of fully routed nets[^:\r\n]*:\s*([0-9]+)} $routes match routed] || $total!=$routed} {error "Not all nets routed; export denied"}
 report_drc -file [file join $out final_drc.txt]
 if {[llength [get_drc_violations -quiet]]!=0} {error "Final DRC contains violations; export denied"}
 report_exceptions -file [file join $out final_exceptions.txt]
 report_clocks -file [file join $out final_clocks.txt]
 set stem h1_7020_evidence_candidate_v0_1
 file copy $hwh [file join $out $stem.hwh]
 write_bitstream -force [file join $out $stem.bit]
 if {![file isfile [file join $out $stem.bit]] || [file size [file join $out $stem.bit]]==0} {error "Bitstream was not created"}
 file copy [file join $root review route_acceptance review.json] [file join $out source_route_review.json]
 file copy [file join $root review route_acceptance source_dependencies_at_review.json] [file join $out source_dependencies.json]
 file copy [file join $root candidate_export_notes.md] [file join $out README_candidate.md]
 set fd [open [file join $out export_inventory.txt] w]
 puts $fd "SOURCE_ROUTED_DCP=$checkpoint"
 puts $fd "SOURCE_HWH=$hwh BIT=[file join $out $stem.bit] HWH=[file join $out $stem.hwh]"
 puts $fd "BIT_BYTES=[file size [file join $out $stem.bit]] HWH_BYTES=[file size [file join $out $stem.hwh]]"
 puts $fd "CANDIDATE_FILES_ONLY_NEW_ARM_AND_RETIRE_RECEIPT_LATENCIES_HOST_SYS_INTEGRATION_AND_BOARD_TEST_PENDING"
 puts $fd "NO_BOARD_DOWNLOAD_NO_HARDWARE_IMAGE64_OR_REAL_MCU_ACCEPTANCE"
 close $fd
 puts "H1_7020_QUALIFIED_CANDIDATE_BIT_HWH_CREATED REVIEW_REQUIRED NO_BOARD_DOWNLOAD NO_HARDWARE"
}
export_h1_qualified_candidate
