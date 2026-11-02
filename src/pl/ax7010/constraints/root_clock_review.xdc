# Only the verified board oscillator is a primary clock. MMCM outputs must
# become related generated 100/50MHz clocks; do not blanket-cut them.
create_clock -name PL_INPUT_50 -period 20.000 [get_ports pl_clk_50m]
