`timescale 1ns / 1ps

module ctrl_command_router #(
    parameter integer MAX_PAYLOAD = 32
)(
    input  wire                         clk,
    input  wire                         rst_n,

    // ============================================================
    // CRC-verified packet input
    // From ctrl_packet_parser
    // ============================================================

    input  wire                         packet_valid,
    input  wire [7:0]                   packet_type,
    input  wire [7:0]                   packet_len,
    input  wire [MAX_PAYLOAD*8-1:0]     packet_payload,


    // ============================================================
    // CONFIG_APPLY route
    //
    // CONFIG_APPLY has its own ctrl_command_decoder.
    //
    // Router intentionally does NOT check CONFIG payload length.
    // CONFIG-specific format checking remains owned by
    // ctrl_command_decoder.
    // ============================================================

    output reg                          config_packet_valid,


    // ============================================================
    // START command
    //
    // Payload:
    //
    // Byte0 = trial_id[7:0]
    // Byte1 = trial_id[15:8]
    // ============================================================

    output reg                          start_cmd_valid,
    output reg [15:0]                   start_trial_id,


    // ============================================================
    // ABORT command
    // ============================================================

    output reg                          abort_cmd_valid,
    output reg [15:0]                   abort_trial_id,


    // ============================================================
    // RESULT_ACK command
    // ============================================================

    output reg                          result_ack_cmd_valid,
    output reg [15:0]                   result_ack_trial_id,


    // ============================================================
    // Router error
    //
    // One-clock pulse.
    //
    // 0 = NONE
    // 1 = BAD_LENGTH
    // 2 = UNSUPPORTED_TYPE
    // ============================================================

    output reg                          router_error,
    output reg [2:0]                    router_error_code
);


    // ============================================================
    // Command TYPE values
    // ============================================================

    localparam [7:0]
        CMD_CONFIG_APPLY = 8'h10,
        CMD_START        = 8'h11,
        CMD_ABORT        = 8'h12,
        CMD_RESULT_ACK   = 8'h13;


    // ============================================================
    // Command lengths
    //
    // CONFIG length is deliberately checked downstream by the
    // existing ctrl_command_decoder.
    //
    // START / ABORT / RESULT_ACK all contain a 16-bit trial_id.
    // ============================================================

    localparam [7:0]
        ACTION_LEN = 8'd2;


    // ============================================================
    // Error codes
    // ============================================================

    localparam [2:0]
        ERR_NONE             = 3'd0,
        ERR_BAD_LENGTH       = 3'd1,
        ERR_UNSUPPORTED_TYPE = 3'd2;


    // ============================================================
    // Common 16-bit command trial ID
    //
    // Protocol V1.0:
    //
    // Byte0 = low byte
    // Byte1 = high byte
    // ============================================================

    wire [15:0] packet_trial_id;

    assign packet_trial_id = {
        packet_payload[15:8],
        packet_payload[7:0]
    };


    // ============================================================
    // Main router
    // ============================================================

    always @(posedge clk) begin

        if (!rst_n) begin

            config_packet_valid <= 1'b0;

            start_cmd_valid     <= 1'b0;
            start_trial_id      <= 16'h0000;

            abort_cmd_valid     <= 1'b0;
            abort_trial_id      <= 16'h0000;

            result_ack_cmd_valid <= 1'b0;
            result_ack_trial_id  <= 16'h0000;

            router_error        <= 1'b0;
            router_error_code   <= ERR_NONE;

        end
        else begin

            // ----------------------------------------------------
            // All event outputs are one-clock pulses
            // ----------------------------------------------------

            config_packet_valid  <= 1'b0;

            start_cmd_valid      <= 1'b0;
            abort_cmd_valid      <= 1'b0;
            result_ack_cmd_valid <= 1'b0;

            router_error         <= 1'b0;
            router_error_code    <= ERR_NONE;


            // ====================================================
            // Process one CRC-verified packet
            // ====================================================

            if (packet_valid) begin

                case (packet_type)


                    // =================================================
                    // CONFIG_APPLY
                    //
                    // Route complete packet to ctrl_command_decoder.
                    //
                    // Do NOT validate CONFIG length here.
                    // =================================================

                    CMD_CONFIG_APPLY: begin

                        config_packet_valid <= 1'b1;

                    end


                    // =================================================
                    // START
                    // =================================================

                    CMD_START: begin

                        if (packet_len != ACTION_LEN) begin

                            router_error      <= 1'b1;
                            router_error_code <= ERR_BAD_LENGTH;

                        end
                        else begin

                            start_trial_id  <= packet_trial_id;
                            start_cmd_valid <= 1'b1;

                        end

                    end


                    // =================================================
                    // ABORT
                    // =================================================

                    CMD_ABORT: begin

                        if (packet_len != ACTION_LEN) begin

                            router_error      <= 1'b1;
                            router_error_code <= ERR_BAD_LENGTH;

                        end
                        else begin

                            abort_trial_id  <= packet_trial_id;
                            abort_cmd_valid <= 1'b1;

                        end

                    end


                    // =================================================
                    // RESULT_ACK
                    // =================================================

                    CMD_RESULT_ACK: begin

                        if (packet_len != ACTION_LEN) begin

                            router_error      <= 1'b1;
                            router_error_code <= ERR_BAD_LENGTH;

                        end
                        else begin

                            result_ack_trial_id  <= packet_trial_id;
                            result_ack_cmd_valid <= 1'b1;

                        end

                    end


                    // =================================================
                    // Unknown command
                    // =================================================

                    default: begin

                        router_error      <= 1'b1;
                        router_error_code <= ERR_UNSUPPORTED_TYPE;

                    end

                endcase

            end

        end

    end

endmodule