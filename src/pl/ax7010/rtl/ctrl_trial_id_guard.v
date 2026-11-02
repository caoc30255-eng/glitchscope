`timescale 1ns / 1ps

module ctrl_trial_id_guard
(
    input  wire        clk,
    input  wire        rst_n,

    input  wire        soft_reset,


    // ====================================================================
    // Routed START command
    // ====================================================================

    input  wire        start_cmd_valid,
    input  wire [15:0] start_cmd_trial_id,


    // ====================================================================
    // Routed ABORT command
    // ====================================================================

    input  wire        abort_cmd_valid,
    input  wire [15:0] abort_cmd_trial_id,


    // ====================================================================
    // Routed RESULT_ACK command
    // ====================================================================

    input  wire        result_ack_cmd_valid,
    input  wire [15:0] result_ack_cmd_trial_id,


    // ====================================================================
    // Current system identities
    //
    // Protocol V1.0 uses 16-bit Trial IDs.
    //
    // Internal core uses 32-bit IDs.
    //
    // CONFIG path zero-extends:
    //
    //     protocol 0x1234
    //          ¡ý
    //     32'h00001234
    // ====================================================================

    input  wire [31:0] active_trial_id,

    // Top supplies:
    //
    //     busy ? running_trial_id : active_trial_id
    //
    // This preserves the exact identity that ABORT is allowed to target.
    input  wire [31:0] current_trial_id,


    // ====================================================================
    // Result mailbox identity
    // ====================================================================

    input  wire        result_ready,
    input  wire [31:0] mailbox_trial_id,


    // ====================================================================
    // Safe command pulses to existing core
    //
    // Each is one system-clock pulse.
    // ====================================================================

    output reg         start_req,

    output reg         abort_req,

    output reg         result_ack,


    // ====================================================================
    // Identity-guard rejection event
    //
    // guard_reject:
    //     one-clock pulse
    //
    // guard_command:
    //
    // 0 NONE
    // 1 START
    // 2 ABORT
    // 3 RESULT_ACK
    //
    // guard_status:
    //
    // 0 NONE
    // 1 ID_MISMATCH
    // 2 NO_RESULT
    // ====================================================================

    output reg         guard_reject,
    output reg [1:0]   guard_command,
    output reg [2:0]   guard_status
);


    // ====================================================================
    // Command identifiers
    // ====================================================================

    localparam [1:0]
        GUARD_CMD_NONE       = 2'd0,
        GUARD_CMD_START      = 2'd1,
        GUARD_CMD_ABORT      = 2'd2,
        GUARD_CMD_RESULT_ACK = 2'd3;


    // ====================================================================
    // Guard status
    // ====================================================================

    localparam [2:0]
        GUARD_NONE        = 3'd0,
        GUARD_ID_MISMATCH = 3'd1,
        GUARD_NO_RESULT   = 3'd2;


    // ====================================================================
    // Zero-extended command Trial IDs
    // ====================================================================

    wire [31:0] start_id_32;
    wire [31:0] abort_id_32;
    wire [31:0] result_ack_id_32;


    assign start_id_32 = {
        16'h0000,
        start_cmd_trial_id
    };


    assign abort_id_32 = {
        16'h0000,
        abort_cmd_trial_id
    };


    assign result_ack_id_32 = {
        16'h0000,
        result_ack_cmd_trial_id
    };


    // ====================================================================
    // Main guard
    //
    // Router guarantees command route exclusivity.
    //
    // Priority is still explicitly defined for defensive behavior:
    //
    // START > ABORT > RESULT_ACK
    // ====================================================================

    always @(posedge clk) begin

        if (!rst_n) begin

            start_req     <= 1'b0;
            abort_req     <= 1'b0;
            result_ack    <= 1'b0;

            guard_reject  <= 1'b0;
            guard_command <= GUARD_CMD_NONE;
            guard_status  <= GUARD_NONE;

        end
        else if (soft_reset) begin

            start_req     <= 1'b0;
            abort_req     <= 1'b0;
            result_ack    <= 1'b0;

            guard_reject  <= 1'b0;
            guard_command <= GUARD_CMD_NONE;
            guard_status  <= GUARD_NONE;

        end
        else begin

            // ------------------------------------------------------------
            // All command / response outputs are one-clock events
            // ------------------------------------------------------------

            start_req  <= 1'b0;
            abort_req  <= 1'b0;
            result_ack <= 1'b0;

            guard_reject  <= 1'b0;
            guard_command <= GUARD_CMD_NONE;
            guard_status  <= GUARD_NONE;


            // ============================================================
            // START
            //
            // Identity target:
            //
            // active_trial_id
            //
            // State legality such as configured_valid / BUSY remains
            // handshake_ctrl's responsibility.
            // ============================================================

            if (start_cmd_valid) begin

                if (start_id_32 == active_trial_id) begin

                    start_req <= 1'b1;

                end
                else begin

                    guard_reject  <= 1'b1;
                    guard_command <= GUARD_CMD_START;
                    guard_status  <= GUARD_ID_MISMATCH;

                end

            end


            // ============================================================
            // ABORT
            //
            // Identity target:
            //
            // current_trial_id
            //
            // Top later defines current_trial_id as the identity that the
            // current lifecycle state exposes to ABORT.
            //
            // Whether ABORT itself is legal remains the responsibility of
            // abort_cleanup_ctrl through abort_allowed.
            // ============================================================

            else if (abort_cmd_valid) begin

                if (abort_id_32 == current_trial_id) begin

                    abort_req <= 1'b1;

                end
                else begin

                    guard_reject  <= 1'b1;
                    guard_command <= GUARD_CMD_ABORT;
                    guard_status  <= GUARD_ID_MISMATCH;

                end

            end


            // ============================================================
            // RESULT_ACK
            //
            // ACK may clear persistent mailbox state.
            //
            // Therefore two conditions are required:
            //
            //   1. result_ready = 1
            //   2. command ID equals mailbox_trial_id
            //
            // A stale or wrong ACK must never clear another Trial result.
            // ============================================================

            else if (result_ack_cmd_valid) begin

                if (!result_ready) begin

                    guard_reject  <= 1'b1;
                    guard_command <= GUARD_CMD_RESULT_ACK;
                    guard_status  <= GUARD_NO_RESULT;

                end
                else if (result_ack_id_32 != mailbox_trial_id) begin

                    guard_reject  <= 1'b1;
                    guard_command <= GUARD_CMD_RESULT_ACK;
                    guard_status  <= GUARD_ID_MISMATCH;

                end
                else begin

                    result_ack <= 1'b1;

                end

            end

        end

    end

endmodule