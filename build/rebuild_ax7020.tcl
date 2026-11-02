# Reuse the original reviewed reconstruction and implementation sequence.
set root [file normalize [file join [file dirname [info script]] ..]]
source [file join $root src pl ax7020 scripts rebuild_project.tcl]
source [file join $root src pl ax7020 scripts route_rebuilt_project.tcl]
puts "BUILD_REPORTS_ONLY_REVIEW_REQUIRED_NO_HARDWARE"
