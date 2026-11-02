# Close only this mainline's known projects, using fresh project enumeration.
# close_sim may change the current GUI project: reselect the intended project
# afterwards, then close_project directly. Never use -delete or close_design.
proc ax7010_close_owned_projects {package_root} {
 set workspace [file dirname [file normalize $package_root]]
 set roots [list \
  [file normalize $package_root] \
  [file join $workspace AX7010_MultiPoint_Glitch_v0_11_2026-10-17] \
  [file join $workspace AX7010_Control_CompareLUT_v0_10_2026-10-15] \
  [file join $workspace AX7010_Control_CompareTree_v0_9_2026-10-15] \
  [file join $workspace AX7010_Control_HostTiming_v0_8_2026-10-15]]
 for {set attempt 0} {$attempt<16} {incr attempt} {
  set projects [get_projects -quiet]
  if {[llength $projects]==0} {puts "AX7010_AUTO_CLOSE_VERIFIED OPEN_PROJECTS=0";return}
  set selected [lindex $projects 0]
  set name [get_property NAME $selected]
  set directory [get_property DIRECTORY $selected]
  set known 0
  if {$directory ne "."} {
   set directory [file normalize $directory]
   foreach base $roots {
    set prefix [string tolower "[file normalize $base]/build/"]
    if {[string first $prefix [string tolower "${directory}/"]]==0} {set known 1;break}
   }
  } elseif {$name eq "project_routed_v0_9" ||
            [regexp {^ax7010_(compare_tree|compare_lut|host_timing|multipoint)_.*v0_(8|9|10|11|12)$} $name]} {
   # Exact Vivado container name observed when opening our routed_v0_9.dcp.
   # Do not accept other project_* containers by wildcard.
   set known 1
  }
  if {!$known && $directory eq "." &&
      $name in {project_full_synth project_optimized project_placed_v0_10 project_routed_v0_10 project_multipoint_synth project_optimized_mp11 project_placed_mp11 project_routed_mp11 project_postopt_mp11 project_repair_mp11 project_optimized_mp12 project_placed_mp12 project_routed_mp12 project_postopt_mp12 project_repair_mp12}} {
   # open_checkpoint can leave an additional container named after the DCP.
   # Generic checkpoint names require the actual mainline design fingerprint.
   current_project $selected
   set opened "";catch {set opened [current_design -quiet]}
   if {$opened ne ""} {
    current_instance
    set known [expr {[llength [get_ports -quiet]]==8 &&
     [llength [get_ports -quiet {pl_clk_50m key_n h1_rx_pin ctrl_rx_pin h1_tx_pin ctrl_tx_pin w19_tx fault_mark}]]==8 &&
     [llength [get_cells -quiet image]]==1 &&
     [llength [get_cells -quiet observer]]==1 &&
     [llength [get_cells -quiet route]]==1}]
   }
  }
  if {!$known} {error "Unrecognized project preserved: NAME=$name DIRECTORY=$directory OPEN=[get_projects -quiet]"}
  current_project $selected
  catch {close_sim}
  # Look up the target again: close_sim may have closed or switched projects.
  set live [get_projects -quiet -filter [format {NAME == "%s"} $name]]
  if {[llength $live]==0} {continue}
  if {[llength $live]!=1} {error "Ambiguous close target preserved: $name"}
  current_project [lindex $live 0]
  puts "AX7010_AUTO_CLOSE_REQUEST NAME=$name DIRECTORY=$directory"
  close_project
  update
  set still_open [get_projects -quiet -filter [format {NAME == "%s"} $name]]
  if {[llength $still_open]!=0} {
   error "close_project did not close or the GUI reopened target: NAME=$name DIRECTORY=$directory OPEN=[get_projects -quiet]"
  }
 }
 error "Project close loop budget exhausted; remaining projects preserved: [get_projects -quiet]"
}
