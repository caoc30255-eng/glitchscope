`timescale 1ns / 1ps

// ============================================================
// CAP-06D Formal AXI Snapshot Synthesis Wrapper
//
// Complete formal chain:
//
// asynchronous 8-channel inputs
//          |
//          v
// two-stage synchronizer and FAULT_MARK trigger
//          |
//          v
// 4096 x 8 Raw Snapshot BRAM
//          |
//          v
// AXI4-Lite control and read interface
//
// Formal parameters:
//
//     SNAP_ADDR_WIDTH = 12
//     SNAP_DEPTH      = 4096
//     PRE_COUNT       = 2048
//     POST_COUNT      = 2047
// ============================================================

module raw_snapshot_axi_lite_cap06_synth_top
(
    input  wire         s_axi_aclk,
    input  wire         s_axi_aresetn,

    input  wire [5:0]   s_axi_awaddr,
    input  wire         s_axi_awvalid,
    output wire         s_axi_awready,

    input  wire [31:0]  s_axi_wdata,
    input  wire [3:0]   s_axi_wstrb,
    input  wire         s_axi_wvalid,
    output wire         s_axi_wready,

    output wire [1:0]   s_axi_bresp,
    output wire         s_axi_bvalid,
    input  wire         s_axi_bready,

    input  wire [5:0]   s_axi_araddr,
    input  wire         s_axi_arvalid,
    output wire         s_axi_arready,

    output wire [31:0]  s_axi_rdata,
    output wire [1:0]   s_axi_rresp,
    output wire         s_axi_rvalid,
    input  wire         s_axi_rready,

    input  wire [7:0]   async_i,

    output wire         snapshot_done,
    output wire         snapshot_busy,
    output wire         snapshot_trigger_seen,

    output wire         frontend_trigger_pulse_o,
    output wire [7:0]   synchronized_sample_o
);

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
            snapshot_done
        ),

        .snapshot_busy
        (
            snapshot_busy
        ),

        .snapshot_trigger_seen
        (
            snapshot_trigger_seen
        ),

        .frontend_trigger_pulse_o
        (
            frontend_trigger_pulse_o
        ),

        .synchronized_sample_o
        (
            synchronized_sample_o
        )
    );

endmodule