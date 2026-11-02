`timescale 1ns / 1ps

// ============================================================
// 8-Channel Raw Snapshot Tester
// CAP-03 V1.0
//
// Integration:
//
//     asynchronous board inputs
//               |
//               v
//     capture_frontend_8ch_v1
//       - two-stage synchronization
//       - stable 8-bit sample bus
//       - selected rising-edge trigger
//               |
//               v
//     raw_snapshot_capture_8ch_v1
//       - circular pre-trigger history
//       - trigger-cycle sample
//       - post-trigger samples
//       - logical snapshot read
// ============================================================

module raw_snapshot_tester_8ch_v1
#(
    parameter integer CHANNEL_COUNT       = 8,
    parameter integer CHANNEL_INDEX_WIDTH = 3,

    parameter integer ADDR_WIDTH          = 5,
    parameter integer DEPTH               = 32,
    parameter integer PRE_COUNT           = 8,
    parameter integer POST_COUNT          = 4
)
(
    input  wire                             clk,
    input  wire                             rst_n,

    input  wire                             soft_reset,

    // External asynchronous input pins.
    input  wire [CHANNEL_COUNT-1:0]         async_i,

    // Capture control.
    input  wire                             arm,

    // Trigger selection.
    input  wire                             trigger_enable,
    input  wire [CHANNEL_INDEX_WIDTH-1:0]   trigger_channel,

    // Logical snapshot read.
    input  wire                             rd_en,
    input  wire [ADDR_WIDTH-1:0]            rd_index,

    output wire [CHANNEL_COUNT-1:0]         rd_data,
    output wire                             rd_valid,

    // Capture status.
    output wire                             armed,
    output wire                             busy,
    output wire                             done,
    output wire                             trigger_seen,

    // Snapshot metadata.
    output wire [ADDR_WIDTH:0]              sample_count,
    output wire [ADDR_WIDTH:0]              trigger_offset,

    output wire [ADDR_WIDTH-1:0]            window_start_addr,
    output wire [ADDR_WIDTH-1:0]            trigger_addr,

    // Frontend diagnostics.
    output wire [CHANNEL_COUNT-1:0]         synchronized_sample,
    output wire [CHANNEL_COUNT-1:0]         rise_vector,
    output wire                             selected_level,
    output wire                             frontend_trigger_pulse
);

    // ========================================================
    // CDC and trigger frontend
    // ========================================================

    capture_frontend_8ch_v1
    #(
        .CHANNEL_COUNT
        (
            CHANNEL_COUNT
        ),

        .CHANNEL_INDEX_WIDTH
        (
            CHANNEL_INDEX_WIDTH
        )
    )
    u_capture_frontend
    (
        .clk
        (
            clk
        ),

        .rst_n
        (
            rst_n
        ),

        .soft_reset
        (
            soft_reset
        ),

        .async_i
        (
            async_i
        ),

        .trigger_enable
        (
            trigger_enable
        ),

        .trigger_channel
        (
            trigger_channel
        ),

        .sample_o
        (
            synchronized_sample
        ),

        .rise_vector
        (
            rise_vector
        ),

        .selected_level
        (
            selected_level
        ),

        .trigger_pulse
        (
            frontend_trigger_pulse
        )
    );

    // ========================================================
    // Raw snapshot capture core
    // ========================================================

    raw_snapshot_capture_8ch_v1
    #(
        .SAMPLE_WIDTH
        (
            CHANNEL_COUNT
        ),

        .ADDR_WIDTH
        (
            ADDR_WIDTH
        ),

        .DEPTH
        (
            DEPTH
        ),

        .PRE_COUNT
        (
            PRE_COUNT
        ),

        .POST_COUNT
        (
            POST_COUNT
        )
    )
    u_raw_snapshot
    (
        .clk
        (
            clk
        ),

        .rst_n
        (
            rst_n
        ),

        .soft_reset
        (
            soft_reset
        ),

        .arm
        (
            arm
        ),

        .trigger
        (
            frontend_trigger_pulse
        ),

        .sample_i
        (
            synchronized_sample
        ),

        .rd_en
        (
            rd_en
        ),

        .rd_index
        (
            rd_index
        ),

        .rd_data
        (
            rd_data
        ),

        .rd_valid
        (
            rd_valid
        ),

        .armed
        (
            armed
        ),

        .busy
        (
            busy
        ),

        .done
        (
            done
        ),

        .trigger_seen
        (
            trigger_seen
        ),

        .sample_count
        (
            sample_count
        ),

        .trigger_offset
        (
            trigger_offset
        ),

        .window_start_addr
        (
            window_start_addr
        ),

        .trigger_addr
        (
            trigger_addr
        )
    );

endmodule