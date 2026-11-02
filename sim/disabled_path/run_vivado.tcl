set root [file normalize [file dirname [info script]]]
set build [file join $root build_[clock seconds]]
create_project h3_disabled $build -part xc7z010clg400-1
add_files [glob [file join $root rtl *.v]]
add_files -fileset sim_1 [file join $root rtl tb_h3_disabled_path.sv]
add_files -fileset sim_1 [glob [file join $root *.mem]]
set_property top tb_h3_disabled_path [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
launch_simulation
run all
puts "H3_DISABLED_PATH_LOG_REVIEW_REQUIRED NO_BITSTREAM_NO_HARDWARE"
puts "Return full transcript from build directory: $build"
