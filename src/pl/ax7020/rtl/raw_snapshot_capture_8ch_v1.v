`timescale 1ns / 1ps

// ============================================================
// 8-Channel Raw Snapshot Capture
// CAP-01 V1.0
//
// Each bit of sample_i represents one digital input channel.
//
// Capture sequence:
//
//     IDLE
//       -> ARM
//       -> continuously retain the newest PRE_COUNT samples
//       -> accept one trigger
//       -> retain trigger sample
//       -> retain POST_COUNT samples after trigger
//       -> DONE
//
// Logical read order:
//
//     rd_index = 0
//         oldest retained pre-trigger sample
//
//     rd_index = trigger_offset
//         trigger-cycle sample
//
//     rd_index = sample_count - 1
//         final post-trigger sample
//
// Restrictions:
//
// 1. DEPTH must equal 2**ADDR_WIDTH.
// 2. PRE_COUNT + POST_COUNT + 1 must not exceed DEPTH.
// 3. Trigger is accepted only while waiting in PRE state.
// 4. done remains asserted until ARM, soft_reset or reset.
// ============================================================

module raw_snapshot_capture_8ch_v1
#(
    parameter integer SAMPLE_WIDTH = 8,
    parameter integer ADDR_WIDTH   = 5,
    parameter integer DEPTH        = 32,
    parameter integer PRE_COUNT    = 8,
    parameter integer POST_COUNT   = 4
)
(
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire                         soft_reset,

    // One-clock command pulse.
    input  wire                         arm,

    // One-clock trigger pulse.
    input  wire                         trigger,

    // Eight synchronous digital input channels.
    input  wire [SAMPLE_WIDTH-1:0]      sample_i,

    // Logical snapshot read interface.
    //
    // rd_index=0 reads the first sample in the retained window.
    // rd_valid is asserted for one clock after an accepted read.
    input  wire                         rd_en,
    input  wire [ADDR_WIDTH-1:0]        rd_index,

    output reg  [SAMPLE_WIDTH-1:0]      rd_data,
    output reg                          rd_valid,

    // Status.
    output wire                         armed,
    output wire                         busy,
    output reg                          done,
    output reg                          trigger_seen,

    // Snapshot metadata.
    output reg  [ADDR_WIDTH:0]          sample_count,
    output reg  [ADDR_WIDTH:0]          trigger_offset,

    // Physical RAM addresses, provided for diagnostics.
    output reg  [ADDR_WIDTH-1:0]        window_start_addr,
    output reg  [ADDR_WIDTH-1:0]        trigger_addr
);

    // ========================================================
    // State definitions
    // ========================================================

    localparam [1:0] STATE_IDLE = 2'd0;
    localparam [1:0] STATE_PRE  = 2'd1;
    localparam [1:0] STATE_POST = 2'd2;
    localparam [1:0] STATE_DONE = 2'd3;

    reg [1:0] state;

    assign armed =
        (state == STATE_PRE);

    assign busy =
        (state == STATE_PRE)
        ||
        (state == STATE_POST);

    // ========================================================
    // Capture memory
    // ========================================================

  // Force the formal large-depth snapshot memory to use
// FPGA block RAM during synthesis.
//
// This attribute does not change behavioral simulation.
(* ram_style = "block" *)
reg [SAMPLE_WIDTH-1:0] sample_mem [0:DEPTH-1];

    reg [ADDR_WIDTH-1:0] write_addr;

    // Number of valid samples that exist before the trigger.
    // Saturates at PRE_COUNT.
    reg [ADDR_WIDTH:0] pre_valid_count;

    // Number of post-trigger samples still to capture.
    reg [ADDR_WIDTH:0] post_remaining;

    // Logical read address translated into the physical
    // circular-buffer address.
    wire [ADDR_WIDTH-1:0] read_physical_addr;

    assign read_physical_addr =
        window_start_addr
        +
        rd_index;

    // ========================================================
    // Parameter checks
    // ========================================================

    initial
    begin
        if (DEPTH != (1 << ADDR_WIDTH))
        begin
            $display(
                "RAW SNAPSHOT PARAMETER ERROR: DEPTH must equal 2**ADDR_WIDTH"
            );

            $finish;
        end

        if (
            (PRE_COUNT + POST_COUNT + 1)
            >
            DEPTH
        )
        begin
            $display(
                "RAW SNAPSHOT PARAMETER ERROR: capture window exceeds DEPTH"
            );

            $finish;
        end
    end

    // ========================================================
    // Main capture and read logic
    // ========================================================

    always @(posedge clk)
    begin
        if (!rst_n)
        begin
            state <= STATE_IDLE;

            write_addr <= {ADDR_WIDTH{1'b0}};

            pre_valid_count <= {(ADDR_WIDTH+1){1'b0}};
            post_remaining <= {(ADDR_WIDTH+1){1'b0}};

            done <= 1'b0;
            trigger_seen <= 1'b0;

            sample_count <= {(ADDR_WIDTH+1){1'b0}};
            trigger_offset <= {(ADDR_WIDTH+1){1'b0}};

            window_start_addr <= {ADDR_WIDTH{1'b0}};
            trigger_addr <= {ADDR_WIDTH{1'b0}};

            rd_data <= {SAMPLE_WIDTH{1'b0}};
            rd_valid <= 1'b0;
        end

        else
        begin
            // rd_valid is a one-clock response pulse.
            rd_valid <= 1'b0;

            // =================================================
            // System cleanup
            // =================================================

            if (soft_reset)
            begin
                state <= STATE_IDLE;

                write_addr <= {ADDR_WIDTH{1'b0}};

                pre_valid_count <= {(ADDR_WIDTH+1){1'b0}};
                post_remaining <= {(ADDR_WIDTH+1){1'b0}};

                done <= 1'b0;
                trigger_seen <= 1'b0;

                sample_count <= {(ADDR_WIDTH+1){1'b0}};
                trigger_offset <= {(ADDR_WIDTH+1){1'b0}};

                window_start_addr <= {ADDR_WIDTH{1'b0}};
                trigger_addr <= {ADDR_WIDTH{1'b0}};

                rd_data <= {SAMPLE_WIDTH{1'b0}};
            end

            // =================================================
            // ARM starts a completely new snapshot
            // =================================================

            else if (arm)
            begin
                state <= STATE_PRE;

                write_addr <= {ADDR_WIDTH{1'b0}};

                pre_valid_count <= {(ADDR_WIDTH+1){1'b0}};
                post_remaining <= {(ADDR_WIDTH+1){1'b0}};

                done <= 1'b0;
                trigger_seen <= 1'b0;

                sample_count <= {(ADDR_WIDTH+1){1'b0}};
                trigger_offset <= {(ADDR_WIDTH+1){1'b0}};

                window_start_addr <= {ADDR_WIDTH{1'b0}};
                trigger_addr <= {ADDR_WIDTH{1'b0}};
            end

            else
            begin
                case (state)

                    // =========================================
                    // IDLE
                    // =========================================

                    STATE_IDLE:
                    begin
                        // Wait for ARM.
                    end

                    // =========================================
                    // PRE-TRIGGER CIRCULAR CAPTURE
                    // =========================================

                    STATE_PRE:
                    begin
                        // The current sample is always written.
                        sample_mem[write_addr] <= sample_i;

                        // -------------------------------------
                        // Trigger-cycle sample
                        // -------------------------------------

                        if (trigger)
                        begin
                            trigger_seen <= 1'b1;

                            trigger_addr <= write_addr;

                            // pre_valid_count is the number of
                            // samples preceding this trigger.
                            trigger_offset <= pre_valid_count;

                            window_start_addr <=
                                write_addr
                                -
                                pre_valid_count[ADDR_WIDTH-1:0];

                            sample_count <=
                                pre_valid_count
                                +
                                POST_COUNT
                                +
                                1;

                            write_addr <=
                                write_addr
                                +
                                1'b1;

                            post_remaining <=
                                POST_COUNT;

                            if (POST_COUNT == 0)
                            begin
                                state <= STATE_DONE;
                                done <= 1'b1;
                            end

                            else
                            begin
                                state <= STATE_POST;
                            end
                        end

                        // -------------------------------------
                        // Ordinary pre-trigger sample
                        // -------------------------------------

                        else
                        begin
                            write_addr <=
                                write_addr
                                +
                                1'b1;

                            if (
                                pre_valid_count
                                <
                                PRE_COUNT
                            )
                            begin
                                pre_valid_count <=
                                    pre_valid_count
                                    +
                                    1'b1;
                            end
                        end
                    end

                    // =========================================
                    // POST-TRIGGER CAPTURE
                    // =========================================

                    STATE_POST:
                    begin
                        sample_mem[write_addr] <= sample_i;

                        write_addr <=
                            write_addr
                            +
                            1'b1;

                        // Further trigger pulses are ignored.
                        if (
                            post_remaining
                            ==
                            1
                        )
                        begin
                            post_remaining <=
                                {(ADDR_WIDTH+1){1'b0}};

                            state <= STATE_DONE;
                            done <= 1'b1;
                        end

                        else
                        begin
                            post_remaining <=
                                post_remaining
                                -
                                1'b1;
                        end
                    end

                    // =========================================
                    // DONE
                    // =========================================

                    STATE_DONE:
                    begin
                        // Snapshot remains frozen until the next
                        // ARM or system cleanup.
                    end

                    default:
                    begin
                        state <= STATE_IDLE;
                        done <= 1'b0;
                        trigger_seen <= 1'b0;
                    end

                endcase

                // =============================================
                // Registered logical snapshot read
                // =============================================

                if (
                    rd_en
                    &&
                    done
                    &&
                    (
                        {1'b0, rd_index}
                        <
                        sample_count
                    )
                )
                begin
                    rd_data <=
                        sample_mem[read_physical_addr];

                    rd_valid <=
                        1'b1;
                end
            end
        end
    end

endmodule