# Retry only the control component in a new short-path build.
# Old failure directory and successful sender log remain intact.
set mp_selected_tops {tb_multipoint_control_profile_v0_11}
source [file join [file dirname [info script]] run_multipoint_component_sim.tcl]
