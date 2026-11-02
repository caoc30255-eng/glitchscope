# Match the earlier best clean candidate's implementation sequence.
# Record initial route, post-route physical optimization and clock-clean route.
# No RTL changes, no internal timing exceptions, no bitstream or hardware.
proc h1_qualified_arm_route_reports {directory prefix} {
 report_timing_summary -report_unconstrained -max_paths 20 -file [file join $directory ${prefix}_timing.txt]
 report_drc -file [file join $directory ${prefix}_drc.txt]
 report_route_status -file [file join $directory ${prefix}_route_status.txt]
 report_exceptions -file [file join $directory ${prefix}_exceptions.txt]
 write_checkpoint -force [file join $directory ${prefix}.dcp]
}
proc run_h1_qualified_arm_controlled_route {} {
 set root [file normalize [file join [file dirname [info script]] ..]]
 if {![info exists ::h1_package_rebuild_work]} {error "First run scripts/rebuild_project.tcl in this Vivado session"}
 set work $::h1_package_rebuild_work
 set project [file join $work p h1_7020_evidence_system_v0_1.xpr]
 if {![file isfile $project]} {error "Reviewed feedback full-synthesis project missing"}
 set old "";catch {set old [current_project -quiet]}
 if {$old ne ""} {
  if {[get_property NAME $old] ne "h1_7020_evidence_system_v0_1" || [file normalize [get_property DIRECTORY $old]] ne [file join $work p]} {error "Save and close unrelated project before reviewed ACK implementation"}
 } else {open_project $project}
 if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Reviewed synthesis must be complete"}
 if {[get_property STATUS [get_runs impl_1]] ne "Not started"} {error "Implementation already started; inspect reports before any retry/reset"}
 set opened "";catch {set opened [current_design -quiet]}
 if {$opened ne ""} {close_design}
 open_run synth_1
 set out [file join $work qualified_controlled_route_[clock milliseconds]]
 file mkdir $out
 puts "H1_7020_QUALIFIED_ARM_CONTROLLED_ROUTE_REPORTS $out"
 # Validate all first-stage endpoints with normal Tcl before using literal XDC.
 source [file join $root constraints_review apply_async_first_stage_reviewed_v0_2.tcl]
 report_exceptions -file [file join $out validated_synth_exceptions.txt]
 set literal [file join $out async_first_stage_literal_v0_3.xdc]
 file copy [file join $root constraints_review async_first_stage_literal_v0_3.xdc] $literal
 add_files -fileset constrs_1 -norecurse $literal
 set_property USED_IN_SYNTHESIS false [get_files $literal]
 set_property USED_IN_IMPLEMENTATION true [get_files $literal]
 set_property PROCESSING_ORDER LATE [get_files $literal]
 close_design
 set_property strategy Performance_Explore [get_runs impl_1]
 launch_runs impl_1 -to_step route_design -jobs 2
 wait_on_run impl_1
 set status [get_property STATUS [get_runs impl_1]]
 if {![string match {*route_design Complete*} $status]} {error "Initial feedback routing did not complete: $status"}
 open_run impl_1
 set clock [get_clocks -quiet clk_fpga_0]
 if {[llength $clock]!=1 || [get_property PERIOD $clock]!=10.0} {error "Expected unchanged 100MHz clock"}
 h1_qualified_arm_route_reports $out 01_initial_route
 phys_opt_design -directive AggressiveExplore
 route_design -directive MoreGlobalIterations
 h1_qualified_arm_route_reports $out 02_postroute_opt
 # If this optimization adds the known cascaded BUFG, normalize it to the
 # same parallel topology as the earlier clean -0.125ns candidate.
 set base system_i/processing_system7_0/inst/buffer_fclk_clk_0.FCLK_CLK_0_BUFG
 set input_a [get_pins -quiet $base/I]
 set replica [get_cells -quiet ${base}_replica]
 set fd [open [file join $out clock_normalization.txt] w]
 if {[llength $replica]==1} {
  set input_b [get_pins -quiet ${base}_replica/I]
  set output_b [get_pins -quiet ${base}_replica/O]
  set net_a [get_nets -quiet -of_objects $input_a]
  set net_b [get_nets -quiet -of_objects $input_b]
  if {[llength $input_a]!=1 || [llength $input_b]!=1 || [llength $output_b]!=1 || [llength $net_a]!=1 || [llength $net_b]!=1} {close $fd;error "Unexpected optimized BUFG structure"}
  if {$net_a ne $net_b} {
   set drivers [get_pins -leaf -quiet -of_objects $net_a -filter {DIRECTION == OUT}]
   set source_drivers [get_pins -leaf -quiet -of_objects $net_b -filter {DIRECTION == OUT}]
   set ps_pin [get_pins -quiet {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
   if {[llength $drivers]!=1 || [lindex $drivers 0] ne $output_b || [llength $source_drivers]!=1 || [llength $ps_pin]!=1 || [lindex $source_drivers 0] ne $ps_pin} {close $fd;error "Clock sources differ from reviewed cascade; no automatic ECO allowed"}
   puts $fd "ONE_PIN_ECO=$input_a OLD_NET=$net_a NEW_NET=$net_b SAME_PS_FCLK0=$ps_pin"
   disconnect_net -net $net_a -pinlist $input_a
   connect_net -hierarchical -net $net_b -objects $input_a
   if {[get_nets -quiet -of_objects $input_a] ne [get_nets -quiet -of_objects $input_b]} {close $fd;error "Clock parallel normalization failed"}
   route_design -directive MoreGlobalIterations
  } else {puts $fd "ALREADY_PARALLEL_NO_CLOCK_ECO"}
 } elseif {[llength $replica]==0} {
  puts $fd "NO_REPLICA_NO_CLOCK_ECO"
 } else {close $fd;error "Unexpected multiple replica clock buffers"}
 close $fd
 h1_qualified_arm_route_reports $out 03_clock_clean_route
 report_utilization -file [file join $out utilization_final.txt]
 report_methodology -file [file join $out methodology_final.txt]
 check_timing -verbose -file [file join $out check_timing_final.txt]
 report_clocks -file [file join $out clocks_final.txt]
 report_clock_utilization -file [file join $out clock_utilization_final.txt]
 write_xdc -force [file join $out effective_constraints.xdc]
 puts "H1_7020_QUALIFIED_ARM_CONTROLLED_ROUTE_REVIEW_REQUIRED ALL_STAGE_REPORTS_PRESERVED TIMING_DRC_NOT_YET_ACCEPTED NO_BITSTREAM NO_HARDWARE"
}
run_h1_qualified_arm_controlled_route
