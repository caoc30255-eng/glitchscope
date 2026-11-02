`timescale 1ns / 1ps

// ============================================================================
// Block Design module-reference wrapper for DUT response AXI receiver V1.
// The complete Raw Snapshot input bus is shared with this wrapper; CH1 is the
// STM32 DUT_RESP signal and is selected internally.
// ============================================================================

module dut_response_axi_lite_bd
(
    (* X_INTERFACE_INFO =
       "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER =
       "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input wire s_axi_aclk,

    (* X_INTERFACE_INFO =
       "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER =
       "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input wire s_axi_aresetn,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER =
       "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 6, FREQ_HZ 100000000, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0, MAX_BURST_LENGTH 1, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *)
    input wire [5:0] s_axi_awaddr,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input wire [2:0] s_axi_awprot,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input wire s_axi_awvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire s_axi_awready,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input wire [31:0] s_axi_wdata,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input wire [3:0] s_axi_wstrb,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input wire s_axi_wvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire s_axi_wready,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output wire [1:0] s_axi_bresp,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output wire s_axi_bvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input wire s_axi_bready,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input wire [5:0] s_axi_araddr,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input wire [2:0] s_axi_arprot,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input wire s_axi_arvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire s_axi_arready,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output wire [31:0] s_axi_rdata,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output wire [1:0] s_axi_rresp,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output wire s_axi_rvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input wire s_axi_rready,

    input wire [7:0] async_i
);

    wire unused_prot;

    assign unused_prot =
        ^s_axi_awprot ^ ^s_axi_arprot;

    dut_response_axi_lite_v1 #(
        .C_S_AXI_DATA_WIDTH (32),
        .C_S_AXI_ADDR_WIDTH (6),
        .CLK_HZ             (100_000_000),
        .BAUD               (1_000_000),
        .BYTE_TIMEOUT_CLKS  (1_000_000)
    ) u_dut_response_axi_lite (
        .s_axi_aclk       (s_axi_aclk),
        .s_axi_aresetn    (s_axi_aresetn),
        .s_axi_awaddr     (s_axi_awaddr),
        .s_axi_awvalid    (s_axi_awvalid),
        .s_axi_awready    (s_axi_awready),
        .s_axi_wdata      (s_axi_wdata),
        .s_axi_wstrb      (s_axi_wstrb),
        .s_axi_wvalid     (s_axi_wvalid),
        .s_axi_wready     (s_axi_wready),
        .s_axi_bresp      (s_axi_bresp),
        .s_axi_bvalid     (s_axi_bvalid),
        .s_axi_bready     (s_axi_bready),
        .s_axi_araddr     (s_axi_araddr),
        .s_axi_arvalid    (s_axi_arvalid),
        .s_axi_arready    (s_axi_arready),
        .s_axi_rdata      (s_axi_rdata),
        .s_axi_rresp      (s_axi_rresp),
        .s_axi_rvalid     (s_axi_rvalid),
        .s_axi_rready     (s_axi_rready),
        .dut_response_i   (async_i[1])
    );

endmodule

