# OOC core analysis only. Board I/O/reset/CDC constraints remain a separate review.
create_clock -name core_clk -period 10.000 [get_ports s_axi_aclk]
