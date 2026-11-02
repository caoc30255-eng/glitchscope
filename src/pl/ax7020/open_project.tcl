# Source-only recreation; this source release does not ship a stale .xpr.
set package_root [file dirname [file normalize [info script]]]
set ::h1_source_only 1
set code [catch {source [file join $package_root scripts rebuild_project.tcl]} result options]
unset ::h1_source_only
if {$code} {return -options $options $result}
puts "AX7020_SOURCE_PROJECT_OPENED_NO_SYNTH_NO_DOWNLOAD"
