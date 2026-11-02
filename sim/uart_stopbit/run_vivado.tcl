set root [file normalize [file dirname [info script]]]
set build [file join $root build_[clock seconds]]
create_project h3_uart $build -part xc7z010clg400-1
add_files [glob [file join $root rtl *.v]]
add_files -fileset sim_1 [file join $root rtl tb_h3_uart_stop.sv]
add_files -fileset sim_1 [glob [file join $root vector*.mem]]
set_property top tb_h3_uart_stop [get_filesets sim_1]
set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
launch_simulation
run all
puts "Return full simulation transcript and scoreboard.log from: $build"
puts "H3_OFFLINE_LOG_REVIEW_REQUIRED NO_BITSTREAM_NO_HARDWARE"
