`timescale 1ns / 1ps

// ============================================================
// CAP-07A Block Design Module Reference Wrapper
//
// Formal configuration:
//
//     CHANNELS       = 8
//     SNAP_DEPTH     = 4096
//     PRE_COUNT      = 2048
//     POST_COUNT     = 2047
//     ADDRESS_WIDTH  = 12
//
// This wrapper adds AXI interface metadata required by
// Vivado Block Design Module Reference.
//
// AWPROT and ARPROT are accepted for AXI interface
// compatibility but are not used by the internal register bank.
// ============================================================

module raw_snapshot_axi_lite_cap06_bd
(
    // ========================================================
    // AXI clock and reset
    // ========================================================

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

    // ========================================================
    // AXI4-Lite write-address channel
    // ========================================================

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

    // ========================================================
    // AXI4-Lite write-data channel
    // ========================================================

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

    // ========================================================
    // AXI4-Lite write-response channel
    // ========================================================

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output wire [1:0] s_axi_bresp,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output wire s_axi_bvalid,

    (* X_INTERFACE_INFO =
       "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input wire s_axi_bready,

    // ========================================================
    // AXI4-Lite read-address channel
    // ========================================================

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

    // ========================================================
    // AXI4-Lite read-data channel
    // ========================================================

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

    // ========================================================
    // Eight asynchronous external capture channels
    // ========================================================

    input wire [7:0] async_i
);

    // ========================================================
    // Internal diagnostic signals
    //
    // These signals remain internal during CAP-07A.
    // They may later be connected to interrupt or ILA logic.
    // ========================================================

    wire snapshot_done_internal;
    wire snapshot_busy_internal;
    wire snapshot_trigger_seen_internal;

    wire frontend_trigger_pulse_internal;
    wire [7:0] synchronized_sample_internal;

    // AWPROT and ARPROT are intentionally unused because the
    // internal register bank does not implement privilege or
    // security-dependent behavior.

    wire unused_prot;

    assign unused_prot =
        ^s_axi_awprot
        ^
        ^s_axi_arprot;

    // ========================================================
    // Formal Snapshot AXI instance
    // ========================================================

    raw_snapshot_axi_lite_v1
    #(
        .C_S_AXI_DATA_WIDTH
        (
            32
        ),

        .C_S_AXI_ADDR_WIDTH
        (
            6
        ),

        .CHANNEL_COUNT
        (
            8
        ),

        .CHANNEL_INDEX_WIDTH
        (
            3
        ),

        .SNAP_ADDR_WIDTH
        (
            12
        ),

        .SNAP_DEPTH
        (
            4096
        ),

        .PRE_COUNT
        (
            2048
        ),

        .POST_COUNT
        (
            2047
        )
    )
    u_axi_snapshot
    (
        .s_axi_aclk
        (
            s_axi_aclk
        ),

        .s_axi_aresetn
        (
            s_axi_aresetn
        ),

        .s_axi_awaddr
        (
            s_axi_awaddr
        ),

        .s_axi_awvalid
        (
            s_axi_awvalid
        ),

        .s_axi_awready
        (
            s_axi_awready
        ),

        .s_axi_wdata
        (
            s_axi_wdata
        ),

        .s_axi_wstrb
        (
            s_axi_wstrb
        ),

        .s_axi_wvalid
        (
            s_axi_wvalid
        ),

        .s_axi_wready
        (
            s_axi_wready
        ),

        .s_axi_bresp
        (
            s_axi_bresp
        ),

        .s_axi_bvalid
        (
            s_axi_bvalid
        ),

        .s_axi_bready
        (
            s_axi_bready
        ),

        .s_axi_araddr
        (
            s_axi_araddr
        ),

        .s_axi_arvalid
        (
            s_axi_arvalid
        ),

        .s_axi_arready
        (
            s_axi_arready
        ),

        .s_axi_rdata
        (
            s_axi_rdata
        ),

        .s_axi_rresp
        (
            s_axi_rresp
        ),

        .s_axi_rvalid
        (
            s_axi_rvalid
        ),

        .s_axi_rready
        (
            s_axi_rready
        ),

        .async_i
        (
            async_i
        ),

        .snapshot_done
        (
            snapshot_done_internal
        ),

        .snapshot_busy
        (
            snapshot_busy_internal
        ),

        .snapshot_trigger_seen
        (
            snapshot_trigger_seen_internal
        ),

        .frontend_trigger_pulse_o
        (
            frontend_trigger_pulse_internal
        ),

        .synchronized_sample_o
        (
            synchronized_sample_internal
        )
    );

endmodule