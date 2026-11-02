# -------------------------EMIO------------------- 
#PL_KEY 54 55 
set_property -dict { PACKAGE_PIN L14 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[0] }] 
set_property -dict { PACKAGE_PIN K16 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[1] }] 
#TPAD 56 
set_property -dict { PACKAGE_PIN F16 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[2] }] 
#BEEP  57 
set_property -dict { PACKAGE_PIN M14 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[3] }] 
#PL_LED 58-60 
set_property -dict { PACKAGE_PIN J16 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[4] }] 
set_property -dict { PACKAGE_PIN H15 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[5] }] 
set_property -dict { PACKAGE_PIN L15 IOSTANDARD LVCMOS33 } [get_ports { GPIO_tri_io[6] }]
# ============================================================
# UART3 - PL UART for 7020 <-> AX7010 communication
# P5 Pin5 = UART3_TX
# P5 Pin6 = UART3_RX
# ============================================================

# UART3 TX -> P5 Pin5
set_property PACKAGE_PIN J15 [get_ports uart_rtl_0_txd]
set_property IOSTANDARD LVCMOS33 [get_ports uart_rtl_0_txd]

# UART3 RX <- P5 Pin6
set_property PACKAGE_PIN T19 [get_ports uart_rtl_0_rxd]
set_property IOSTANDARD LVCMOS33 [get_ports uart_rtl_0_rxd]
# ============================================================
# Raw Snapshot asynchronous inputs
#
# Navigator V2 camera connector P2:
#
# CH0 P2-8  CMOS_D0
# CH1 P2-9  CMOS_D1
# CH2 P2-10 CMOS_D2
# CH3 P2-11 CMOS_D3
# CH4 P2-12 CMOS_D4
# CH5 P2-13 CMOS_D5
# CH6 P2-14 CMOS_D6
# CH7 P2-15 CMOS_D7
# ============================================================

set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[0]}]

set_property -dict {PACKAGE_PIN U13 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[1]}]

set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[2]}]

set_property -dict {PACKAGE_PIN U15 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[3]}]

set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[4]}]

set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[5]}]

set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[6]}]

set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} \
    [get_ports {raw_snapshot_async_i[7]}]

# Currently connected:
#
# CH0 = UART_STIM
# CH1 = STM32 DUT_RESP
# CH2 = FAULT_MARK
#
# CH1 is driven by STM32 PA9 and must not have the old weak pull-down.
# Other channels remain physically unconnected during the
# first dual-board test. Enable weak internal pull-downs so
# that they do not float.

set_property PULLDOWN TRUE \
    [get_ports {
        raw_snapshot_async_i[3]
        raw_snapshot_async_i[4]
        raw_snapshot_async_i[5]
        raw_snapshot_async_i[6]
        raw_snapshot_async_i[7]
    }]

# These eight inputs are asynchronous to FCLK_CLK0.
# The false path ends at the first synchronizer register;
# register boundaries prevent it from masking sync1-to-sync2
# timing.

set_false_path \
    -from \
    [get_ports {raw_snapshot_async_i[*]}]
