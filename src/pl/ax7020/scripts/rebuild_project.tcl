proc rebuild_ax7020_packaged_project {} {

 set root [file normalize [file join [file dirname [info script]] ..]]

 set existing "";catch {set existing [current_project -quiet]}

 if {$existing ne ""} {error "Save and close the current project before rebuilding"}

 set work [file join $root rebuild build_[clock milliseconds]]
 if {[info exists ::env(GLITCHSCOPE_BUILD_OUTPUT)]} {set work [file normalize $::env(GLITCHSCOPE_BUILD_OUTPUT)];if {[file exists $work]} {error "BUILD_OUTPUT_MUST_BE_NEW"}}

 file mkdir $work

 set ::h1_package_rebuild_work $work

 create_project h1_7020_evidence_system_v0_1 [file join $work p] -part xc7z020clg400-2

 set_property source_mgmt_mode All [current_project]

 set_property XPM_LIBRARIES {XPM_CDC XPM_MEMORY XPM_FIFO} [current_project]

 set files [glob -directory [file join $root rtl] *.v]

 if {[llength $files]!=49} {error "Expected the 49 reviewed RTL files"}

 add_files -norecurse $files

 add_files -fileset constrs_1 -norecurse [glob -directory [file join $root xdc] *.xdc]

 update_compile_order -fileset sources_1
 source [file join $root scripts recreate_bd.tcl]
 foreach {instance module} {raw_snapshot_axi_lite_0 raw_snapshot_axi_lite_cap06_bd dut_response_axi_lite_0 dut_response_axi_lite_bd receiver_axi_lite_0 receiver_axi_bd_7020_v2_2 h1_evidence_system_0 h1_7020_evidence_bd_v0_1} {
  set cell [get_bd_cells -quiet $instance]
  if {[llength $cell] != 1 || ![string match "*:$module:*" [get_property VLNV $cell]]} {error "BD_MODULE_MISSING: $module"}
 }
 validate_bd_design

 save_bd_design

 set design [get_files -quiet */system.bd]

 if {[llength $design]!=1} {error "Expected exactly one system BD"}

 generate_target all $design

 set wrappers [make_wrapper -files $design -top]

 add_files -norecurse $wrappers

 set_property top system_wrapper [get_filesets sources_1]

 update_compile_order -fileset sources_1

 if {[info exists ::h1_source_only] && $::h1_source_only} {puts "AX7020_SOURCE_PROJECT_READY_NO_SYNTH_NO_HARDWARE $work";return}
 launch_runs synth_1 -jobs 2

 wait_on_run synth_1

 if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Synthesis incomplete"}

 open_run synth_1

 report_timing_summary -report_unconstrained -file [file join $work full_timing_synth.txt]

 report_utilization -file [file join $work full_utilization.txt]

 report_drc -file [file join $work full_drc.txt]

 write_checkpoint [file join $work full_synth.dcp]

 puts "AX7020_PACKAGED_REBUILD_SYNTH_REPORTS $work REVIEW_REQUIRED_NO_BITSTREAM_NO_HARDWARE"

}

rebuild_ax7020_packaged_project

