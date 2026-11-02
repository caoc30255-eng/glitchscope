`timescale 1ns / 1ps

// ============================================================
// 8-Channel Capture Frontend
// CAP-02 V1.0
//
// Functions:
//
// 1. Synchronize eight external asynchronous inputs.
// 2. Produce an eight-bit stable sample bus.
// 3. Detect rising edges on all synchronized channels.
// 4. Select one channel as the snapshot trigger source.
// 5. Produce exactly one clock of trigger_pulse.
//
// Synchronizer structure:
//
//     async_i
//        |
//     sync_stage1
//        |
//     sync_stage2 ----> sample_o
//
// sync_stage1 is used only by sync_stage2.
//
// soft_reset does not clear the synchronizer stages.
// It suppresses trigger generation while allowing the
// synchronizer to continue tracking external levels.
// ============================================================

module capture_frontend_8ch_v1
#(
    parameter integer CHANNEL_COUNT = 8,
    parameter integer CHANNEL_INDEX_WIDTH = 3
)
(
    input  wire                             clk,
    input  wire                             rst_n,

    input  wire                             soft_reset,

    input  wire [CHANNEL_COUNT-1:0]         async_i,

    input  wire                             trigger_enable,
    input  wire [CHANNEL_INDEX_WIDTH-1:0]   trigger_channel,

    output wire [CHANNEL_COUNT-1:0]         sample_o,
    output wire [CHANNEL_COUNT-1:0]         rise_vector,

    output wire                             selected_level,
    output wire                             trigger_pulse
);

    // ========================================================
    // Two-stage input synchronizers
    // ========================================================

    (* ASYNC_REG = "TRUE" *)
    reg [CHANNEL_COUNT-1:0] sync_stage1;

    (* ASYNC_REG = "TRUE" *)
    reg [CHANNEL_COUNT-1:0] sync_stage2;

    // Previous stable sample, used only for edge detection.
    reg [CHANNEL_COUNT-1:0] sync_stage2_d;

    // ========================================================
    // Stable sampled bus
    // ========================================================

    assign sample_o =
        sync_stage2;

    // ========================================================
    // Per-channel rising-edge vector
    //
    // Because sync_stage2_d receives the previous stable
    // sample, rise_vector remains asserted for one full clock
    // whenever a synchronized input changes from 0 to 1.
    // ========================================================

    assign rise_vector =
        sync_stage2
        &
        ~sync_stage2_d;

    // ========================================================
    // Selected trigger channel
    // ========================================================

    assign selected_level =
        sync_stage2[trigger_channel];

    assign trigger_pulse =
        rst_n
        &&
        !soft_reset
        &&
        trigger_enable
        &&
        rise_vector[trigger_channel];

    // ========================================================
    // Synchronization and edge-history registers
    // ========================================================

    always @(posedge clk)
    begin
        if (!rst_n)
        begin
            sync_stage1 <=
                {CHANNEL_COUNT{1'b0}};

            sync_stage2 <=
                {CHANNEL_COUNT{1'b0}};

            sync_stage2_d <=
                {CHANNEL_COUNT{1'b0}};
        end

        else
        begin
            // First synchronizer stage.
            //
            // This register must not feed capture logic,
            // address logic or trigger logic directly.
            sync_stage1 <=
                async_i;

            // Stable synchronizer stage.
            sync_stage2 <=
                sync_stage1;

            // Previous stable level for edge detection.
            sync_stage2_d <=
                sync_stage2;
        end
    end

endmodule