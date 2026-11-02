# Fresh source build and reports only. No hardware download.
set root [file normalize [file join [file dirname [info script]] ..]]
source [file join $root src pl ax7010 scripts create_project.tcl]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Synthesis incomplete"}
open_run synth_1
set out [file join $ax_work reports]
file mkdir $out
report_utilization -file [file join $out utilization_synth.txt]
report_timing_summary -report_unconstrained -file [file join $out timing_synth.txt]
# Preserve the reviewed dense-device implementation sequence.
opt_design
opt_design -control_set_merge -merge_equivalent_drivers
opt_design -remap
report_control_sets -verbose -file [file join $out control_sets_optimized.txt]
place_design -directive Explore -no_psip
write_checkpoint [file join $out placed.dcp]
route_design -directive Explore
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file [file join $out timing_route.txt]
report_utilization -file [file join $out utilization_route.txt]
report_drc -file [file join $out drc.txt]
report_drc -ruledeck bitstream_checks -file [file join $out bitstream_checks.txt]
report_bus_skew -file [file join $out bus_skew.txt]
report_methodology -file [file join $out methodology.txt]
check_timing -verbose -file [file join $out check_timing.txt]
report_clocks -file [file join $out clocks.txt]
report_exceptions -file [file join $out exceptions.txt]
report_route_status -file [file join $out route_status.txt]
write_checkpoint [file join $out routed.dcp]
write_xdc [file join $out effective_constraints.xdc]
puts "BUILD_REPORTS_ONLY_REVIEW_REQUIRED_NO_BITSTREAM_NO_DOWNLOAD $out"
