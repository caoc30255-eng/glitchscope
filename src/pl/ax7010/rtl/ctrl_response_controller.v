`timescale 1ns / 1ps

// ============================================================================
// Control Response Controller
// V1.0
//
// Responsibilities:
//
//   1. Convert protocol / lifecycle events into ACK / NACK responses.
//
//   2. Capture RESULT mailbox data exactly once when result_ready rises.
//
//   3. Queue one command response while the UART response path is busy.
//
//   4. Independently queue one RESULT response.
//
//   5. Command responses have priority over RESULT responses.
//
//   6. RESULT is preserved while an earlier ACK/NACK is physically
//      transmitted on the UART.
//
// External response formatter convention:
//
//   response_kind:
//       0 = ACK
//       1 = NACK
//       2 = RESULT
//
// Error layers:
//
//       1 = Parser
//       2 = Router / Command Decoder
//       3 = Trial ID Guard
//       4 = Configuration Validator
//       5 = Configuration Apply
//       6 = START / Handshake
//       7 = ABORT
//       8 = Mailbox / Result
//
// Protocol command types:
//
//       0x10 CONFIG_APPLY
//       0x11 START
//       0x12 ABORT
//       0x13 RESULT_ACK
//
// IMPORTANT:
//
//   result_ready is LEVEL based and remains asserted until RESULT_ACK.
//   Therefore this controller detects its rising edge and snapshots the
//   result only once.
//
// ============================================================================

module ctrl_response_controller #(
    parameter integer MAX_PAYLOAD = 32
)(
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire                         soft_reset,


    // ========================================================================
    // Most recent CRC-verified packet
    //
    // Used to preserve command identity for error / response generation.
    // ========================================================================

    input  wire                         packet_valid,
    input  wire [7:0]                   packet_type,
    input  wire [7:0]                   packet_len,
    input  wire [MAX_PAYLOAD*8-1:0]     packet_payload,


    // ========================================================================
    // Parser error
    // ========================================================================

    input  wire                         parser_error,
    input  wire [2:0]                   parser_error_code,


    // ========================================================================
    // Router error
    // ========================================================================

    input  wire                         router_error,
    input  wire [2:0]                   router_error_code,


    // ========================================================================
    // CONFIG command decoder
    //
    // decoder_command_error means the CONFIG packet itself could not be
    // legally decoded.
    //
    // config_cmd_valid means a CONFIG command has been successfully decoded
    // and is being presented to the RefDUT shadow configuration interface.
    // ========================================================================

    input  wire                         decoder_command_error,
    input  wire [3:0]                   decoder_command_error_code,

    input  wire                         config_cmd_valid,


    // ========================================================================
    // RefDUT configuration validator visibility
    //
    // validator_error_code is captured while config_cmd_valid is asserted,
    // because it may no longer be meaningful when apply_done arrives later.
    // ========================================================================

    input  wire                         validator_config_valid,
    input  wire [2:0]                   validator_error_code,


    // ========================================================================
    // RefDUT CONFIG APPLY response
    //
    // apply_status:
    //
    //   0 NONE
    //   1 APPLIED
    //   2 IDEMPOTENT
    //   3 REJECT_BUSY
    //   4 REJECT_INVALID
    //   5 CONFIG_CONFLICT
    // ========================================================================

    input  wire                         apply_done,
    input  wire [2:0]                   apply_status,


    // ========================================================================
    // Trial-ID Guard rejection
    // ========================================================================

    input  wire                         guard_reject,
    input  wire [2:0]                   guard_status,


    // ========================================================================
    // START response
    //
    // start_status:
    //
    //   0 NONE
    //   1 ACCEPTED
    //   2 REJECT_BUSY
    //   3 REJECT_NOCFG
    // ========================================================================

    input  wire                         start_done,
    input  wire [1:0]                   start_status,


    // ========================================================================
    // ABORT response
    //
    // abort_status:
    //
    //   0 NONE
    //   1 ACCEPTED
    //   2 IDEMPOTENT
    //   3 REJECT_ILLEGAL
    // ========================================================================

    input  wire                         abort_done,
    input  wire [1:0]                   abort_status,


    // ========================================================================
    // RESULT_ACK accepted by Trial-ID Guard
    //
    // The Guard already guarantees:
    //
    //   result_ready == 1
    //   command Trial ID == mailbox Trial ID
    //
    // Therefore safe_result_ack itself represents an accepted RESULT_ACK.
    // ========================================================================

    input  wire                         safe_result_ack,


    // ========================================================================
    // Result mailbox
    // ========================================================================

    input  wire                         result_ready,

    input  wire [31:0]                  result_trial_id,

    input  wire [2:0]                   result_a_code,
    input  wire [7:0]                   result_a_byte,
    input  wire                         result_a_fe,
    input  wire [1:0]                   result_a_event_count,

    input  wire [2:0]                   result_b_code,
    input  wire [7:0]                   result_b_byte,
    input  wire                         result_b_fe,
    input  wire [1:0]                   result_b_event_count,

    input  wire                         result_fault_seen,


    // ========================================================================
    // ctrl_response_uart_tx handshake
    // ========================================================================

    input  wire                         response_busy,

    input  wire                         response_accepted,

    input  wire                         response_error,
    input  wire [2:0]                   response_error_code,


    // ========================================================================
    // Request toward ctrl_response_uart_tx
    // ========================================================================

    output reg                          response_start,

    output reg  [1:0]                   response_kind,

    output reg  [7:0]                   response_original_cmd_type,

    output reg  [15:0]                  response_trial_id,

    output reg  [7:0]                   response_status_code,

    output reg  [7:0]                   response_error_layer,
    output reg  [7:0]                   response_error_code_out,


    // ========================================================================
    // RESULT fields toward ctrl_response_uart_tx
    // ========================================================================

    output reg  [2:0]                   response_a_result,
    output reg  [7:0]                   response_a_byte,
    output reg                          response_a_fe,
    output reg  [1:0]                   response_a_event_count,

    output reg  [2:0]                   response_b_result,
    output reg  [7:0]                   response_b_byte,
    output reg                          response_b_fe,
    output reg  [1:0]                   response_b_event_count,

    output reg                          response_fault_seen,


    // ========================================================================
    // Debug / diagnostics
    // ========================================================================

    output wire                         command_response_pending,

    output wire                         result_response_pending,

    output reg                          response_queue_overflow,

    output reg                          transport_error_seen,

    output reg  [2:0]                   last_transport_error_code
);


    // ========================================================================
    // Protocol constants
    // ========================================================================

    localparam [7:0]
        CMD_CONFIG_APPLY = 8'h10,
        CMD_START        = 8'h11,
        CMD_ABORT        = 8'h12,
        CMD_RESULT_ACK   = 8'h13;


    // ========================================================================
    // Response kinds
    // ========================================================================

    localparam [1:0]
        RESP_ACK    = 2'd0,
        RESP_NACK   = 2'd1,
        RESP_RESULT = 2'd2;


    // ========================================================================
    // Error layers
    // ========================================================================

    localparam [7:0]
        ERR_LAYER_NONE      = 8'd0,
        ERR_LAYER_PARSER    = 8'd1,
        ERR_LAYER_COMMAND   = 8'd2,
        ERR_LAYER_GUARD     = 8'd3,
        ERR_LAYER_VALIDATOR = 8'd4,
        ERR_LAYER_CFG_APPLY = 8'd5,
        ERR_LAYER_START     = 8'd6,
        ERR_LAYER_ABORT     = 8'd7,
        ERR_LAYER_RESULT    = 8'd8;


    // ========================================================================
    // Common ACK status
    // ========================================================================

    localparam [7:0]
        STATUS_ACCEPTED = 8'h01;


    // ========================================================================
    // Last CRC-valid packet identity
    //
    // Protocol Trial ID is:
    //
    //   payload[0] = Trial ID low byte
    //   payload[1] = Trial ID high byte
    //
    // Since packet_payload byte 0 occupies [7:0] and byte 1 occupies [15:8],
    // packet_payload[15:0] is already the correct 16-bit Trial ID value.
    // ========================================================================

    reg [7:0]  last_packet_type;
    reg [15:0] last_packet_trial_id;


    wire [15:0] packet_trial_id_now;

    assign packet_trial_id_now =
        (packet_len >= 8'd2)
        ?
        packet_payload[15:0]
        :
        16'h0000;


    wire [7:0] current_command_type;

    wire [15:0] current_command_trial_id;


    assign current_command_type =
        packet_valid
        ?
        packet_type
        :
        last_packet_type;


    assign current_command_trial_id =
        packet_valid
        ?
        packet_trial_id_now
        :
        last_packet_trial_id;


    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            last_packet_type <=
                8'h00;

            last_packet_trial_id <=
                16'h0000;

        end

        else if (soft_reset)
        begin

            last_packet_type <=
                8'h00;

            last_packet_trial_id <=
                16'h0000;

        end

        else if (packet_valid)
        begin

            last_packet_type <=
                packet_type;

            last_packet_trial_id <=
                packet_trial_id_now;

        end

    end


    // ========================================================================
    // Preserve validator error
    //
    // cfg_validator error_code may only be meaningful while the CONFIG
    // shadow-valid event exists.
    //
    // Capture it here for a later APPLY REJECT_INVALID response.
    // ========================================================================

    reg [2:0] saved_validator_error_code;


    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            saved_validator_error_code <=
                3'd0;

        end

        else if (soft_reset)
        begin

            saved_validator_error_code <=
                3'd0;

        end

        else if (config_cmd_valid)
        begin

            saved_validator_error_code <=
                validator_error_code;

        end

    end


    wire [2:0] validator_error_for_response;

    assign validator_error_for_response =
        config_cmd_valid
        ?
        validator_error_code
        :
        saved_validator_error_code;


    // ========================================================================
    // Command response event encoder
    //
    // Converts all command / error events into one canonical response event.
    //
    // Priority:
    //
    //   Parser
    //   Router
    //   Decoder
    //   Guard
    //   CONFIG APPLY
    //   START
    //   ABORT
    //   RESULT_ACK
    //
    // These events should normally be mutually exclusive.
    // ========================================================================

    reg        cmd_event_valid;

    reg [1:0]  cmd_event_kind;

    reg [7:0]  cmd_event_original_cmd_type;

    reg [15:0] cmd_event_trial_id;

    reg [7:0]  cmd_event_status_code;

    reg [7:0]  cmd_event_error_layer;

    reg [7:0]  cmd_event_error_code;


    always @*
    begin

        cmd_event_valid =
            1'b0;

        cmd_event_kind =
            RESP_ACK;

        cmd_event_original_cmd_type =
            current_command_type;

        cmd_event_trial_id =
            current_command_trial_id;

        cmd_event_status_code =
            8'h00;

        cmd_event_error_layer =
            ERR_LAYER_NONE;

        cmd_event_error_code =
            8'h00;


        // ====================================================================
        // Parser error
        //
        // Packet identity cannot be trusted.
        // ====================================================================

        if (parser_error)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_kind =
                RESP_NACK;

            cmd_event_original_cmd_type =
                8'h00;

            cmd_event_trial_id =
                16'h0000;

            cmd_event_error_layer =
                ERR_LAYER_PARSER;

            cmd_event_error_code =
                {
                    5'd0,
                    parser_error_code
                };

        end


        // ====================================================================
        // Router error
        // ====================================================================

        else if (router_error)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_kind =
                RESP_NACK;

            cmd_event_original_cmd_type =
                current_command_type;

            cmd_event_trial_id =
                current_command_trial_id;

            cmd_event_error_layer =
                ERR_LAYER_COMMAND;

            cmd_event_error_code =
                {
                    5'd0,
                    router_error_code
                };

        end


        // ====================================================================
        // CONFIG command decoder error
        //
        // 0x1X range is reserved here for CONFIG-decoder-specific errors,
        // while Router errors remain 0x0X.
        // ====================================================================

        else if (decoder_command_error)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_kind =
                RESP_NACK;

            cmd_event_original_cmd_type =
                CMD_CONFIG_APPLY;

            cmd_event_trial_id =
                current_command_trial_id;

            cmd_event_error_layer =
                ERR_LAYER_COMMAND;

            cmd_event_error_code =
                {
                    4'h1,
                    decoder_command_error_code
                };

        end


        // ====================================================================
        // Trial-ID Guard rejection
        // ====================================================================

        else if (guard_reject)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_kind =
                RESP_NACK;

            cmd_event_original_cmd_type =
                current_command_type;

            cmd_event_trial_id =
                current_command_trial_id;

            cmd_event_error_layer =
                ERR_LAYER_GUARD;

            cmd_event_error_code =
                {
                    5'd0,
                    guard_status
                };

        end


        // ====================================================================
        // CONFIG APPLY completion
        // ====================================================================

        else if (apply_done)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_original_cmd_type =
                CMD_CONFIG_APPLY;

            cmd_event_trial_id =
                current_command_trial_id;


            case (apply_status)

                // ------------------------------------------------------------
                // APPLIED
                // ------------------------------------------------------------

                3'd1:
                begin

                    cmd_event_kind =
                        RESP_ACK;

                    cmd_event_status_code =
                        8'd1;

                end


                // ------------------------------------------------------------
                // IDEMPOTENT
                // ------------------------------------------------------------

                3'd2:
                begin

                    cmd_event_kind =
                        RESP_ACK;

                    cmd_event_status_code =
                        8'd2;

                end


                // ------------------------------------------------------------
                // REJECT_BUSY
                // ------------------------------------------------------------

                3'd3:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_CFG_APPLY;

                    cmd_event_error_code =
                        8'd3;

                end


                // ------------------------------------------------------------
                // REJECT_INVALID
                //
                // Give the actual validator reason rather than only the
                // generic APPLY status.
                // ------------------------------------------------------------

                3'd4:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_VALIDATOR;

                    cmd_event_error_code =
                        {
                            5'd0,
                            validator_error_for_response
                        };

                end


                // ------------------------------------------------------------
                // CONFIG_CONFLICT
                // ------------------------------------------------------------

                3'd5:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_CFG_APPLY;

                    cmd_event_error_code =
                        8'd5;

                end


                // ------------------------------------------------------------
                // Defensive fallback
                // ------------------------------------------------------------

                default:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_CFG_APPLY;

                    cmd_event_error_code =
                        {
                            5'd0,
                            apply_status
                        };

                end

            endcase

        end


        // ====================================================================
        // START response
        // ====================================================================

        else if (start_done)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_original_cmd_type =
                CMD_START;

            cmd_event_trial_id =
                current_command_trial_id;


            case (start_status)

                // ACCEPTED
                2'd1:
                begin

                    cmd_event_kind =
                        RESP_ACK;

                    cmd_event_status_code =
                        8'd1;

                end


                // REJECT_BUSY
                2'd2:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_START;

                    cmd_event_error_code =
                        8'd2;

                end


                // REJECT_NOCFG
                2'd3:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_START;

                    cmd_event_error_code =
                        8'd3;

                end


                default:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_START;

                    cmd_event_error_code =
                        {
                            6'd0,
                            start_status
                        };

                end

            endcase

        end


        // ====================================================================
        // ABORT response
        // ====================================================================

        else if (abort_done)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_original_cmd_type =
                CMD_ABORT;

            cmd_event_trial_id =
                current_command_trial_id;


            case (abort_status)

                // ACCEPTED
                2'd1:
                begin

                    cmd_event_kind =
                        RESP_ACK;

                    cmd_event_status_code =
                        8'd1;

                end


                // IDEMPOTENT is still a successful command.
                2'd2:
                begin

                    cmd_event_kind =
                        RESP_ACK;

                    cmd_event_status_code =
                        8'd2;

                end


                // REJECT_ILLEGAL
                2'd3:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_ABORT;

                    cmd_event_error_code =
                        8'd3;

                end


                default:
                begin

                    cmd_event_kind =
                        RESP_NACK;

                    cmd_event_error_layer =
                        ERR_LAYER_ABORT;

                    cmd_event_error_code =
                        {
                            6'd0,
                            abort_status
                        };

                end

            endcase

        end


        // ====================================================================
        // Accepted RESULT_ACK
        // ====================================================================

        else if (safe_result_ack)
        begin

            cmd_event_valid =
                1'b1;

            cmd_event_kind =
                RESP_ACK;

            cmd_event_original_cmd_type =
                CMD_RESULT_ACK;

            cmd_event_trial_id =
                current_command_trial_id;

            cmd_event_status_code =
                STATUS_ACCEPTED;

        end

    end


    // ========================================================================
    // One-entry command-response queue
    //
    // This permits:
    //
    //   response #1 currently transmitting
    //   +
    //   one command response waiting behind it.
    //
    // The host protocol should still operate request -> response rather than
    // flooding commands.
    // ========================================================================

    reg cmd_pending;

    reg [1:0]  cmd_pending_kind;

    reg [7:0]  cmd_pending_original_cmd_type;

    reg [15:0] cmd_pending_trial_id;

    reg [7:0]  cmd_pending_status_code;

    reg [7:0]  cmd_pending_error_layer;

    reg [7:0]  cmd_pending_error_code;


    assign command_response_pending =
        cmd_pending;


    // ========================================================================
    // RESULT snapshot queue
    // ========================================================================

    reg result_ready_d;

    reg result_pending;


    reg [15:0] result_pending_trial_id;


    reg [2:0] result_pending_a_result;

    reg [7:0] result_pending_a_byte;

    reg result_pending_a_fe;

    reg [1:0] result_pending_a_event_count;


    reg [2:0] result_pending_b_result;

    reg [7:0] result_pending_b_byte;

    reg result_pending_b_fe;

    reg [1:0] result_pending_b_event_count;


    reg result_pending_fault_seen;


    assign result_response_pending =
        result_pending;


    // ========================================================================
    // Sender FSM
    // ========================================================================

    localparam [0:0]
        SEND_IDLE        = 1'b0,
        SEND_WAIT_ACCEPT = 1'b1;


    reg send_state;


    localparam [0:0]
        SOURCE_COMMAND = 1'b0,
        SOURCE_RESULT  = 1'b1;


    reg send_source;


    // ========================================================================
    // Queue dequeue events
    //
    // A pending object is removed only after ctrl_response_uart_tx has
    // actually accepted and snapshotted it.
    // ========================================================================

    wire command_dequeue;

    wire result_dequeue;


    assign command_dequeue =
        (send_state == SEND_WAIT_ACCEPT)
        &&
        response_accepted
        &&
        (send_source == SOURCE_COMMAND);


    assign result_dequeue =
        (send_state == SEND_WAIT_ACCEPT)
        &&
        response_accepted
        &&
        (send_source == SOURCE_RESULT);


    // ========================================================================
    // Command response queue
    // ========================================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            cmd_pending <=
                1'b0;

            cmd_pending_kind <=
                RESP_ACK;

            cmd_pending_original_cmd_type <=
                8'h00;

            cmd_pending_trial_id <=
                16'h0000;

            cmd_pending_status_code <=
                8'h00;

            cmd_pending_error_layer <=
                ERR_LAYER_NONE;

            cmd_pending_error_code <=
                8'h00;

            response_queue_overflow <=
                1'b0;

        end

        else if (soft_reset)
        begin

            cmd_pending <=
                1'b0;

            cmd_pending_kind <=
                RESP_ACK;

            cmd_pending_original_cmd_type <=
                8'h00;

            cmd_pending_trial_id <=
                16'h0000;

            cmd_pending_status_code <=
                8'h00;

            cmd_pending_error_layer <=
                ERR_LAYER_NONE;

            cmd_pending_error_code <=
                8'h00;

            response_queue_overflow <=
                1'b0;

        end

        else
        begin

            // ------------------------------------------------------------
            // Current command response has been accepted by UART wrapper.
            // ------------------------------------------------------------

            if (command_dequeue)
            begin

                cmd_pending <=
                    1'b0;

            end


            // ------------------------------------------------------------
            // New command response event
            //
            // If the previous entry is being dequeued on this exact clock,
            // the new entry may immediately replace it.
            // ------------------------------------------------------------

            if (cmd_event_valid)
            begin

                if (
                    !cmd_pending
                    ||
                    command_dequeue
                )
                begin

                    cmd_pending <=
                        1'b1;

                    cmd_pending_kind <=
                        cmd_event_kind;

                    cmd_pending_original_cmd_type <=
                        cmd_event_original_cmd_type;

                    cmd_pending_trial_id <=
                        cmd_event_trial_id;

                    cmd_pending_status_code <=
                        cmd_event_status_code;

                    cmd_pending_error_layer <=
                        cmd_event_error_layer;

                    cmd_pending_error_code <=
                        cmd_event_error_code;

                end

                else
                begin

                    // Host violated the intended request/response pacing,
                    // or multiple unexpected internal events collided.

                    response_queue_overflow <=
                        1'b1;

                end

            end

        end

    end


    // ========================================================================
    // RESULT snapshot
    // ========================================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            result_ready_d <=
                1'b0;

            result_pending <=
                1'b0;

            result_pending_trial_id <=
                16'h0000;

            result_pending_a_result <=
                3'd0;

            result_pending_a_byte <=
                8'h00;

            result_pending_a_fe <=
                1'b0;

            result_pending_a_event_count <=
                2'd0;

            result_pending_b_result <=
                3'd0;

            result_pending_b_byte <=
                8'h00;

            result_pending_b_fe <=
                1'b0;

            result_pending_b_event_count <=
                2'd0;

            result_pending_fault_seen <=
                1'b0;

        end

        else if (soft_reset)
        begin

            result_ready_d <=
                1'b0;

            result_pending <=
                1'b0;

            result_pending_trial_id <=
                16'h0000;

            result_pending_a_result <=
                3'd0;

            result_pending_a_byte <=
                8'h00;

            result_pending_a_fe <=
                1'b0;

            result_pending_a_event_count <=
                2'd0;

            result_pending_b_result <=
                3'd0;

            result_pending_b_byte <=
                8'h00;

            result_pending_b_fe <=
                1'b0;

            result_pending_b_event_count <=
                2'd0;

            result_pending_fault_seen <=
                1'b0;

        end

        else
        begin

            result_ready_d <=
                result_ready;


            // ------------------------------------------------------------
            // RESULT response was accepted by UART wrapper.
            // ------------------------------------------------------------

            if (result_dequeue)
            begin

                result_pending <=
                    1'b0;

            end


            // ------------------------------------------------------------
            // Rising edge of result_ready:
            //
            // Atomically snapshot the mailbox.
            // ------------------------------------------------------------

            if (
                result_ready
                &&
                !result_ready_d
            )
            begin

                result_pending <=
                    1'b1;

                result_pending_trial_id <=
                    result_trial_id[15:0];


                result_pending_a_result <=
                    result_a_code;

                result_pending_a_byte <=
                    result_a_byte;

                result_pending_a_fe <=
                    result_a_fe;

                result_pending_a_event_count <=
                    result_a_event_count;


                result_pending_b_result <=
                    result_b_code;

                result_pending_b_byte <=
                    result_b_byte;

                result_pending_b_fe <=
                    result_b_fe;

                result_pending_b_event_count <=
                    result_b_event_count;


                result_pending_fault_seen <=
                    result_fault_seen;

            end


            // ------------------------------------------------------------
            // Defensive behavior:
            //
            // If the host has already issued a legal RESULT_ACK before a
            // queued RESULT could be launched, do not later transmit an
            // already-acknowledged stale RESULT.
            // ------------------------------------------------------------

            if (safe_result_ack)
            begin

                result_pending <=
                    1'b0;

            end

        end

    end


    // ========================================================================
    // Transport diagnostics
    // ========================================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            transport_error_seen <=
                1'b0;

            last_transport_error_code <=
                3'd0;

        end

        else if (soft_reset)
        begin

            transport_error_seen <=
                1'b0;

            last_transport_error_code <=
                3'd0;

        end

        else if (response_error)
        begin

            transport_error_seen <=
                1'b1;

            last_transport_error_code <=
                response_error_code;

        end

    end


    // ========================================================================
    // Sender FSM
    //
    // Priority:
    //
    //       1. command ACK / NACK
    //       2. RESULT
    //
    // This guarantees that a START/ABORT ACK can be sent before a result that
    // became ready only a few clocks later.
    // ========================================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            send_state <=
                SEND_IDLE;

            send_source <=
                SOURCE_COMMAND;


            response_start <=
                1'b0;

            response_kind <=
                RESP_ACK;

            response_original_cmd_type <=
                8'h00;

            response_trial_id <=
                16'h0000;

            response_status_code <=
                8'h00;

            response_error_layer <=
                ERR_LAYER_NONE;

            response_error_code_out <=
                8'h00;


            response_a_result <=
                3'd0;

            response_a_byte <=
                8'h00;

            response_a_fe <=
                1'b0;

            response_a_event_count <=
                2'd0;


            response_b_result <=
                3'd0;

            response_b_byte <=
                8'h00;

            response_b_fe <=
                1'b0;

            response_b_event_count <=
                2'd0;


            response_fault_seen <=
                1'b0;

        end

        else if (soft_reset)
        begin

            send_state <=
                SEND_IDLE;

            send_source <=
                SOURCE_COMMAND;


            response_start <=
                1'b0;

            response_kind <=
                RESP_ACK;

            response_original_cmd_type <=
                8'h00;

            response_trial_id <=
                16'h0000;

            response_status_code <=
                8'h00;

            response_error_layer <=
                ERR_LAYER_NONE;

            response_error_code_out <=
                8'h00;


            response_a_result <=
                3'd0;

            response_a_byte <=
                8'h00;

            response_a_fe <=
                1'b0;

            response_a_event_count <=
                2'd0;


            response_b_result <=
                3'd0;

            response_b_byte <=
                8'h00;

            response_b_fe <=
                1'b0;

            response_b_event_count <=
                2'd0;


            response_fault_seen <=
                1'b0;

        end

        else
        begin

            // One-clock request pulse.
            response_start <=
                1'b0;


            case (send_state)

                // ============================================================
                // Nothing currently waiting for acceptance.
                // ============================================================

                SEND_IDLE:
                begin

                    if (!response_busy)
                    begin

                        // ----------------------------------------------------
                        // Command ACK / NACK has priority.
                        // ----------------------------------------------------

                        if (cmd_pending)
                        begin

                            response_kind <=
                                cmd_pending_kind;

                            response_original_cmd_type <=
                                cmd_pending_original_cmd_type;

                            response_trial_id <=
                                cmd_pending_trial_id;

                            response_status_code <=
                                cmd_pending_status_code;

                            response_error_layer <=
                                cmd_pending_error_layer;

                            response_error_code_out <=
                                cmd_pending_error_code;


                            // RESULT-only fields are irrelevant for ACK/NACK.
                            response_a_result <=
                                3'd0;

                            response_a_byte <=
                                8'h00;

                            response_a_fe <=
                                1'b0;

                            response_a_event_count <=
                                2'd0;


                            response_b_result <=
                                3'd0;

                            response_b_byte <=
                                8'h00;

                            response_b_fe <=
                                1'b0;

                            response_b_event_count <=
                                2'd0;


                            response_fault_seen <=
                                1'b0;


                            response_start <=
                                1'b1;

                            send_source <=
                                SOURCE_COMMAND;

                            send_state <=
                                SEND_WAIT_ACCEPT;

                        end


                        // ----------------------------------------------------
                        // No command response pending -> send RESULT.
                        // ----------------------------------------------------

                        else if (result_pending)
                        begin

                            response_kind <=
                                RESP_RESULT;

                            response_original_cmd_type <=
                                8'h00;

                            response_trial_id <=
                                result_pending_trial_id;

                            response_status_code <=
                                8'h00;

                            response_error_layer <=
                                ERR_LAYER_NONE;

                            response_error_code_out <=
                                8'h00;


                            response_a_result <=
                                result_pending_a_result;

                            response_a_byte <=
                                result_pending_a_byte;

                            response_a_fe <=
                                result_pending_a_fe;

                            response_a_event_count <=
                                result_pending_a_event_count;


                            response_b_result <=
                                result_pending_b_result;

                            response_b_byte <=
                                result_pending_b_byte;

                            response_b_fe <=
                                result_pending_b_fe;

                            response_b_event_count <=
                                result_pending_b_event_count;


                            response_fault_seen <=
                                result_pending_fault_seen;


                            response_start <=
                                1'b1;

                            send_source <=
                                SOURCE_RESULT;

                            send_state <=
                                SEND_WAIT_ACCEPT;

                        end

                    end

                end


                // ============================================================
                // response_start was issued.
                //
                // Wait until ctrl_response_uart_tx confirms that the response
                // was actually snapshotted.
                // ============================================================

                SEND_WAIT_ACCEPT:
                begin

                    if (response_accepted)
                    begin

                        send_state <=
                            SEND_IDLE;

                    end

                    else if (response_error)
                    begin

                        // Keep the queued object alive.
                        //
                        // The queue is only dequeued on response_accepted.
                        // Therefore after returning to IDLE it may retry.

                        send_state <=
                            SEND_IDLE;

                    end

                end


                default:
                begin

                    send_state <=
                        SEND_IDLE;

                end

            endcase

        end

    end


endmodule