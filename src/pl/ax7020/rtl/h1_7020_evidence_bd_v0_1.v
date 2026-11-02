`timescale 1ns/1ps
module h1_7020_evidence_bd_v0_1 (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_H1:S_CTRL:S_MAIN:S_AUX:S_MAP:S_CH0:S_PROFILE:S_SYS, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input wire s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input wire s_axi_aresetn,
    input wire ch0_rx_pin,ch1_rx_pin,h1_rx_pin,
    output wire h1_tx_pin,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_H1, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] h1_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 AWVALID" *)
    input wire h1_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 AWREADY" *)
    output wire h1_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 WDATA" *)
    input wire [31:0] h1_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 WSTRB" *)
    input wire [3:0] h1_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 WVALID" *)
    input wire h1_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 WREADY" *)
    output wire h1_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 BRESP" *)
    output wire [1:0] h1_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 BVALID" *)
    output wire h1_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 BREADY" *)
    input wire h1_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 ARADDR" *)
    input wire [11:0] h1_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 ARVALID" *)
    input wire h1_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 ARREADY" *)
    output wire h1_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 RDATA" *)
    output wire [31:0] h1_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 RRESP" *)
    output wire [1:0] h1_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 RVALID" *)
    output wire h1_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 RREADY" *)
    input wire h1_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 AWPROT" *)
    input wire [2:0] h1_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_H1 ARPROT" *)
    input wire [2:0] h1_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_CTRL, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] ctrl_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL AWVALID" *)
    input wire ctrl_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL AWREADY" *)
    output wire ctrl_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL WDATA" *)
    input wire [31:0] ctrl_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL WSTRB" *)
    input wire [3:0] ctrl_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL WVALID" *)
    input wire ctrl_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL WREADY" *)
    output wire ctrl_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL BRESP" *)
    output wire [1:0] ctrl_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL BVALID" *)
    output wire ctrl_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL BREADY" *)
    input wire ctrl_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL ARADDR" *)
    input wire [11:0] ctrl_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL ARVALID" *)
    input wire ctrl_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL ARREADY" *)
    output wire ctrl_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL RDATA" *)
    output wire [31:0] ctrl_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL RRESP" *)
    output wire [1:0] ctrl_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL RVALID" *)
    output wire ctrl_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL RREADY" *)
    input wire ctrl_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL AWPROT" *)
    input wire [2:0] ctrl_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CTRL ARPROT" *)
    input wire [2:0] ctrl_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_MAIN, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 14, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [13:0] main_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN AWVALID" *)
    input wire main_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN AWREADY" *)
    output wire main_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN WDATA" *)
    input wire [31:0] main_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN WSTRB" *)
    input wire [3:0] main_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN WVALID" *)
    input wire main_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN WREADY" *)
    output wire main_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN BRESP" *)
    output wire [1:0] main_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN BVALID" *)
    output wire main_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN BREADY" *)
    input wire main_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN ARADDR" *)
    input wire [13:0] main_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN ARVALID" *)
    input wire main_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN ARREADY" *)
    output wire main_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN RDATA" *)
    output wire [31:0] main_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN RRESP" *)
    output wire [1:0] main_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN RVALID" *)
    output wire main_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN RREADY" *)
    input wire main_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN AWPROT" *)
    input wire [2:0] main_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAIN ARPROT" *)
    input wire [2:0] main_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AUX, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] aux_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX AWVALID" *)
    input wire aux_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX AWREADY" *)
    output wire aux_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX WDATA" *)
    input wire [31:0] aux_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX WSTRB" *)
    input wire [3:0] aux_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX WVALID" *)
    input wire aux_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX WREADY" *)
    output wire aux_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX BRESP" *)
    output wire [1:0] aux_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX BVALID" *)
    output wire aux_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX BREADY" *)
    input wire aux_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX ARADDR" *)
    input wire [11:0] aux_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX ARVALID" *)
    input wire aux_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX ARREADY" *)
    output wire aux_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX RDATA" *)
    output wire [31:0] aux_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX RRESP" *)
    output wire [1:0] aux_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX RVALID" *)
    output wire aux_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX RREADY" *)
    input wire aux_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX AWPROT" *)
    input wire [2:0] aux_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AUX ARPROT" *)
    input wire [2:0] aux_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_MAP, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] map_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP AWVALID" *)
    input wire map_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP AWREADY" *)
    output wire map_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP WDATA" *)
    input wire [31:0] map_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP WSTRB" *)
    input wire [3:0] map_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP WVALID" *)
    input wire map_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP WREADY" *)
    output wire map_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP BRESP" *)
    output wire [1:0] map_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP BVALID" *)
    output wire map_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP BREADY" *)
    input wire map_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP ARADDR" *)
    input wire [11:0] map_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP ARVALID" *)
    input wire map_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP ARREADY" *)
    output wire map_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP RDATA" *)
    output wire [31:0] map_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP RRESP" *)
    output wire [1:0] map_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP RVALID" *)
    output wire map_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP RREADY" *)
    input wire map_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP AWPROT" *)
    input wire [2:0] map_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_MAP ARPROT" *)
    input wire [2:0] map_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_CH0, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 15, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [14:0] ch0_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 AWVALID" *)
    input wire ch0_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 AWREADY" *)
    output wire ch0_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 WDATA" *)
    input wire [31:0] ch0_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 WSTRB" *)
    input wire [3:0] ch0_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 WVALID" *)
    input wire ch0_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 WREADY" *)
    output wire ch0_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 BRESP" *)
    output wire [1:0] ch0_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 BVALID" *)
    output wire ch0_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 BREADY" *)
    input wire ch0_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 ARADDR" *)
    input wire [14:0] ch0_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 ARVALID" *)
    input wire ch0_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 ARREADY" *)
    output wire ch0_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 RDATA" *)
    output wire [31:0] ch0_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 RRESP" *)
    output wire [1:0] ch0_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 RVALID" *)
    output wire ch0_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 RREADY" *)
    input wire ch0_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 AWPROT" *)
    input wire [2:0] ch0_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_CH0 ARPROT" *)
    input wire [2:0] ch0_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_PROFILE, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] profile_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE AWVALID" *)
    input wire profile_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE AWREADY" *)
    output wire profile_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE WDATA" *)
    input wire [31:0] profile_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE WSTRB" *)
    input wire [3:0] profile_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE WVALID" *)
    input wire profile_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE WREADY" *)
    output wire profile_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE BRESP" *)
    output wire [1:0] profile_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE BVALID" *)
    output wire profile_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE BREADY" *)
    input wire profile_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE ARADDR" *)
    input wire [11:0] profile_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE ARVALID" *)
    input wire profile_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE ARREADY" *)
    output wire profile_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE RDATA" *)
    output wire [31:0] profile_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE RRESP" *)
    output wire [1:0] profile_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE RVALID" *)
    output wire profile_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE RREADY" *)
    input wire profile_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE AWPROT" *)
    input wire [2:0] profile_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_PROFILE ARPROT" *)
    input wire [2:0] profile_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_SYS, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1" *)
    input wire [11:0] sys_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS AWVALID" *)
    input wire sys_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS AWREADY" *)
    output wire sys_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS WDATA" *)
    input wire [31:0] sys_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS WSTRB" *)
    input wire [3:0] sys_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS WVALID" *)
    input wire sys_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS WREADY" *)
    output wire sys_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS BRESP" *)
    output wire [1:0] sys_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS BVALID" *)
    output wire sys_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS BREADY" *)
    input wire sys_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS ARADDR" *)
    input wire [11:0] sys_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS ARVALID" *)
    input wire sys_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS ARREADY" *)
    output wire sys_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS RDATA" *)
    output wire [31:0] sys_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS RRESP" *)
    output wire [1:0] sys_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS RVALID" *)
    output wire sys_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS RREADY" *)
    input wire sys_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS AWPROT" *)
    input wire [2:0] sys_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_SYS ARPROT" *)
    input wire [2:0] sys_arprot
);
 wire [7:0] profile_core_awaddr;
 wire profile_core_awvalid;
 wire profile_core_awready;
 wire [31:0] profile_core_wdata;
 wire [3:0] profile_core_wstrb;
 wire profile_core_wvalid;
 wire profile_core_wready;
 wire [1:0] profile_core_bresp;
 wire profile_core_bvalid;
 wire profile_core_bready;
 wire [7:0] profile_core_araddr;
 wire profile_core_arvalid;
 wire profile_core_arready;
 wire [31:0] profile_core_rdata;
 wire [1:0] profile_core_rresp;
 wire profile_core_rvalid;
 wire profile_core_rready;
 wire [31:0] epoch,ch0_id,ch1_retire_count;wire [7:0] ch0_fault_code;
 wire ch0_active,ch0_closed,ch0_fault,profile_fault,ch1_fault,matcher_fault,mapping_fault,owner_fault;
 wire record_active,record_valid,matcher_done,retired_take,capacity,system_stop;
 wire fault_summary=ch0_fault || profile_fault || ch1_fault || matcher_fault || mapping_fault || owner_fault;
 wire global_stop=system_stop; // sampled sticky fault stop; no combinational fault feedback loop
 h1_7020_ch0_uart_registration_top_v0_2 receiver(
  .clk(s_axi_aclk),
  .rst_n(s_axi_aresetn),
  .external_fault(global_stop),
  .ch0_async(ch0_rx_pin),
  .evidence_epoch(epoch),
  .registered_ready(),
  .active(ch0_active),
  .closed(ch0_closed),
  .fault_latched(ch0_fault),
  .first_fault(ch0_fault_code),
  .bound_epoch(),
  .bound_id(ch0_id),
  .bound_identity(),
  .tick(),
  .start_tick(),
  .deadline_tick(),
  .s_axi_awaddr(ch0_awaddr),
  .s_axi_awvalid(ch0_awvalid),
  .s_axi_awready(ch0_awready),
  .s_axi_wdata(ch0_wdata),
  .s_axi_wstrb(ch0_wstrb),
  .s_axi_wvalid(ch0_wvalid),
  .s_axi_wready(ch0_wready),
  .s_axi_bresp(ch0_bresp),
  .s_axi_bvalid(ch0_bvalid),
  .s_axi_bready(ch0_bready),
  .s_axi_araddr(ch0_araddr),
  .s_axi_arvalid(ch0_arvalid),
  .s_axi_arready(ch0_arready),
  .s_axi_rdata(ch0_rdata),
  .s_axi_rresp(ch0_rresp),
  .s_axi_rvalid(ch0_rvalid),
  .s_axi_rready(ch0_rready),
  .p_axi_awaddr(profile_core_awaddr),
  .p_axi_awvalid(profile_core_awvalid),
  .p_axi_awready(profile_core_awready),
  .p_axi_wdata(profile_core_wdata),
  .p_axi_wstrb(profile_core_wstrb),
  .p_axi_wvalid(profile_core_wvalid),
  .p_axi_wready(profile_core_wready),
  .p_axi_bresp(profile_core_bresp),
  .p_axi_bvalid(profile_core_bvalid),
  .p_axi_bready(profile_core_bready),
  .p_axi_araddr(profile_core_araddr),
  .p_axi_arvalid(profile_core_arvalid),
  .p_axi_arready(profile_core_arready),
  .p_axi_rdata(profile_core_rdata),
  .p_axi_rresp(profile_core_rresp),
  .p_axi_rvalid(profile_core_rvalid),
  .p_axi_rready(profile_core_rready),
  .paths_ready(),
  .profile_fault(profile_fault),
  .a_event(),
  .b_event(),
  .a_fe(),
  .b_fe(),
  .a_byte(),
  .b_byte(),
  .a_idle(),
  .b_idle()
 );
 h1_7020_ch1_mapping_top_v0_4 evidence(
  .clk(s_axi_aclk),
  .rst_n(s_axi_aresetn),
  .uart_rx(ch1_rx_pin),
  .h1_rx_pin(h1_rx_pin),
  .h1_tx_pin(h1_tx_pin),
  .physical_done(),
  .done_identity(),
  .matcher_fault(matcher_fault),
  .mapping_fault(mapping_fault),
  .matched_count(),
  .matcher_active(),
  .matcher_done(matcher_done),
  .external_fault(global_stop),
  .session_can_retire(capacity),
  .fault_latched(ch1_fault),
  .record_active(record_active),
  .record_valid(record_valid),
  .aux_pending(aux_pending),
  .retired_take(retired_take),
  .raw_count(),
  .terminal_reason(),
  .retire_count(ch1_retire_count),
  .evidence_epoch(epoch),
  .tick(),
  .main_awaddr(main_awaddr),
  .main_awvalid(main_awvalid),
  .main_awready(main_awready),
  .main_wdata(main_wdata),
  .main_wstrb(main_wstrb),
  .main_wvalid(main_wvalid),
  .main_wready(main_wready),
  .main_bresp(main_bresp),
  .main_bvalid(main_bvalid),
  .main_bready(main_bready),
  .main_araddr(main_araddr),
  .main_arvalid(main_arvalid),
  .main_arready(main_arready),
  .main_rdata(main_rdata),
  .main_rresp(main_rresp),
  .main_rvalid(main_rvalid),
  .main_rready(main_rready),
  .aux_awaddr(aux_awaddr),
  .aux_awvalid(aux_awvalid),
  .aux_awready(aux_awready),
  .aux_wdata(aux_wdata),
  .aux_wstrb(aux_wstrb),
  .aux_wvalid(aux_wvalid),
  .aux_wready(aux_wready),
  .aux_bresp(aux_bresp),
  .aux_bvalid(aux_bvalid),
  .aux_bready(aux_bready),
  .aux_araddr(aux_araddr),
  .aux_arvalid(aux_arvalid),
  .aux_arready(aux_arready),
  .aux_rdata(aux_rdata),
  .aux_rresp(aux_rresp),
  .aux_rvalid(aux_rvalid),
  .aux_rready(aux_rready),
  .ctrl_awaddr(ctrl_awaddr),
  .ctrl_awvalid(ctrl_awvalid),
  .ctrl_awready(ctrl_awready),
  .ctrl_wdata(ctrl_wdata),
  .ctrl_wstrb(ctrl_wstrb),
  .ctrl_wvalid(ctrl_wvalid),
  .ctrl_wready(ctrl_wready),
  .ctrl_bresp(ctrl_bresp),
  .ctrl_bvalid(ctrl_bvalid),
  .ctrl_bready(ctrl_bready),
  .ctrl_araddr(ctrl_araddr),
  .ctrl_arvalid(ctrl_arvalid),
  .ctrl_arready(ctrl_arready),
  .ctrl_rdata(ctrl_rdata),
  .ctrl_rresp(ctrl_rresp),
  .ctrl_rvalid(ctrl_rvalid),
  .ctrl_rready(ctrl_rready),
  .h1_awaddr(h1_awaddr),
  .h1_awvalid(h1_awvalid),
  .h1_awready(h1_awready),
  .h1_wdata(h1_wdata),
  .h1_wstrb(h1_wstrb),
  .h1_wvalid(h1_wvalid),
  .h1_wready(h1_wready),
  .h1_bresp(h1_bresp),
  .h1_bvalid(h1_bvalid),
  .h1_bready(h1_bready),
  .h1_araddr(h1_araddr),
  .h1_arvalid(h1_arvalid),
  .h1_arready(h1_arready),
  .h1_rdata(h1_rdata),
  .h1_rresp(h1_rresp),
  .h1_rvalid(h1_rvalid),
  .h1_rready(h1_rready),
  .owner_fault(owner_fault),
  .map_awaddr(map_awaddr),
  .map_awvalid(map_awvalid),
  .map_awready(map_awready),
  .map_wdata(map_wdata),
  .map_wstrb(map_wstrb),
  .map_wvalid(map_wvalid),
  .map_wready(map_wready),
  .map_bresp(map_bresp),
  .map_bvalid(map_bvalid),
  .map_bready(map_bready),
  .map_araddr(map_araddr),
  .map_arvalid(map_arvalid),
  .map_arready(map_arready),
  .map_rdata(map_rdata),
  .map_rresp(map_rresp),
  .map_rvalid(map_rvalid),
  .map_rready(map_rready)
 );
 h1_7020_system_control_axi_v0_1 system_control(
  .clk(s_axi_aclk),.rst_n(s_axi_aresetn),.ch0_active(ch0_active),.ch0_closed(ch0_closed),
  .record_active(record_active),.record_valid(record_valid),.matcher_done(matcher_done),
  .fault_summary(fault_summary),.retired_take(retired_take),.epoch(epoch),.ch0_id(ch0_id),
  .ch0_fault_code(ch0_fault_code),.retire_count(ch1_retire_count),.capacity(capacity),.stop(system_stop),
  .s_axi_awaddr(sys_awaddr),
  .s_axi_awvalid(sys_awvalid),
  .s_axi_awready(sys_awready),
  .s_axi_wdata(sys_wdata),
  .s_axi_wstrb(sys_wstrb),
  .s_axi_wvalid(sys_wvalid),
  .s_axi_wready(sys_wready),
  .s_axi_bresp(sys_bresp),
  .s_axi_bvalid(sys_bvalid),
  .s_axi_bready(sys_bready),
  .s_axi_araddr(sys_araddr),
  .s_axi_arvalid(sys_arvalid),
  .s_axi_arready(sys_arready),
  .s_axi_rdata(sys_rdata),
  .s_axi_rresp(sys_rresp),
  .s_axi_rvalid(sys_rvalid),
  .s_axi_rready(sys_rready)
 );
 h1_7020_profile_window_guard_v0_1 profile_window(.clk(s_axi_aclk),.rst_n(s_axi_aresetn),
  .s_awaddr(profile_awaddr),.m_awaddr(profile_core_awaddr),
  .s_awvalid(profile_awvalid),.m_awvalid(profile_core_awvalid),
  .s_awready(profile_awready),.m_awready(profile_core_awready),
  .s_wdata(profile_wdata),.m_wdata(profile_core_wdata),
  .s_wstrb(profile_wstrb),.m_wstrb(profile_core_wstrb),
  .s_wvalid(profile_wvalid),.m_wvalid(profile_core_wvalid),
  .s_wready(profile_wready),.m_wready(profile_core_wready),
  .s_bresp(profile_bresp),.m_bresp(profile_core_bresp),
  .s_bvalid(profile_bvalid),.m_bvalid(profile_core_bvalid),
  .s_bready(profile_bready),.m_bready(profile_core_bready),
  .s_araddr(profile_araddr),.m_araddr(profile_core_araddr),
  .s_arvalid(profile_arvalid),.m_arvalid(profile_core_arvalid),
  .s_arready(profile_arready),.m_arready(profile_core_arready),
  .s_rdata(profile_rdata),.m_rdata(profile_core_rdata),
  .s_rresp(profile_rresp),.m_rresp(profile_core_rresp),
  .s_rvalid(profile_rvalid),.m_rvalid(profile_core_rvalid),
  .s_rready(profile_rready),.m_rready(profile_core_rready)
 );
endmodule
