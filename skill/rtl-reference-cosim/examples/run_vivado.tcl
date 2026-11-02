# Run from a fresh Vivado process. No synth/implementation/download commands.
# vivado -mode batch -source run_vivado.tcl -tclargs NEW_OUTPUT_DIR
if {$argc < 1 || $argc > 3} {error "Provide NEW_OUTPUT_DIR and optional PART and inject_stall_bug"}
if {[llength [get_projects -quiet]] != 0} {error "Use an independent Vivado process"}
set root [file dirname [file normalize [info script]]]
set out [file normalize [lindex $argv 0]]
if {[file exists $out]} {error "Output must not already exist"}
set part xc7z020clg400-1
if {$argc >= 2} {set part [lindex $argv 1]}
create_project skill_demo $out -part $part
add_files [file join $root accumulator.sv]
add_files -fileset sim_1 [file join $root tb_accumulator.sv]
set_property top tb_accumulator [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
if {$argc == 3} {
 if {[lindex $argv 2] ne "inject_stall_bug"} {error "Unknown third argument"}
 set_property verilog_define {INJECT_STALL_BUG} [get_filesets sim_1]
}
launch_simulation
run all
puts "FINITE_SIMULATION_FINISHED_REVIEW_LOG_AND_COMPARE_CSV"
# The PASS marker and exact CSV comparison are checked outside this Tcl.
