`timescale 1ns / 1ps

// ============================================================
// CAP-06B Synthesis Wrapper
//
// Formal Raw Snapshot configuration:
//
//     DATA WIDTH  = 8
//     DEPTH       = 4096
//     ADDRESS     = 12 bits
//     PRE_COUNT   = 2048
//     POST_COUNT  = 2047
//
// This wrapper adds no functional logic.
// It only fixes the formal synthesis parameters.
// ============================================================

module raw_snapshot_capture_8ch_cap06_synth_top
(
    input  wire         clk,
    input  wire         rst_n,

    input  wire         soft_reset,

    input  wire         arm,
    input  wire         trigger,

    input  wire [7:0]   sample_i,

    input  wire         rd_en,
    input  wire [11:0]  rd_index,

    output wire [7:0]   rd_data,
    output wire         rd_valid,

    output wire         armed,
    output wire         busy,
    output wire         done,
    output wire         trigger_seen,

    output wire [12:0]  sample_count,
    output wire [12:0]  trigger_offset,

    output wire [11:0]  window_start_addr,
    output wire [11:0]  trigger_addr
);

    raw_snapshot_capture_8ch_v1
    #(
        .SAMPLE_WIDTH
        (
            8
        ),

        .ADDR_WIDTH
        (
            12
        ),

        .DEPTH
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
            trigger
        ),

        .sample_i
        (
            sample_i
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