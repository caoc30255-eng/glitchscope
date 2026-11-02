`timescale 1ns / 1ps

module ctrl_response_uart_tx #(
    parameter integer MAX_PAYLOAD = 32,
    parameter integer CLK_HZ      = 100_000_000,
    parameter integer BAUD        = 1_000_000
)(
    input  wire                         clk,
    input  wire                         rst_n,

    // ============================================================
    // Response request
    //
    // response_kind:
    //
    // 0 = ACK
    // 1 = NACK
    // 2 = RESULT
    // 3 = invalid
    //
    // response_start is a one-clock request pulse.
    // ============================================================

    input  wire                         response_start,
    input  wire [1:0]                   response_kind,


    // ============================================================
    // ACK / NACK information
    // ============================================================

    input  wire [7:0]                   original_cmd_type,
    input  wire [15:0]                  trial_id,

    input  wire [7:0]                   status_code,

    input  wire [7:0]                   error_layer,
    input  wire [7:0]                   error_code,


    // ============================================================
    // RESULT information
    // ============================================================

    input  wire [2:0]                   a_result,
    input  wire [7:0]                   a_byte,
    input  wire                         a_fe,
    input  wire [1:0]                   a_event_count,

    input  wire [2:0]                   b_result,
    input  wire [7:0]                   b_byte,
    input  wire                         b_fe,
    input  wire [1:0]                   b_event_count,

    input  wire                         fault_seen,


    // ============================================================
    // Physical UART TX
    // ============================================================

    output wire                         uart_tx,


    // ============================================================
    // Response lifecycle
    //
    // response_accepted:
    //     response request has been accepted and snapshotted
    //
    // response_done:
    //     FINAL UART byte has physically completed transmission
    //
    // response_busy:
    //     entire response path is occupied
    // ============================================================

    output wire                         response_accepted,
    output reg                          response_done,
    output wire                         response_busy,


    // ============================================================
    // Request error
    //
    // 0 NONE
    // 1 INVALID_KIND
    // 2 BUSY
    // 3 ENCODER_ERROR
    // ============================================================

    output reg                          response_error,
    output reg [2:0]                    response_error_code,


    // ============================================================
    // Debug
    // ============================================================

    output wire                         encoder_packet_busy,
    output wire                         uart_tx_busy,
    output wire                         uart_tx_done
);


    // ============================================================
    // Error codes
    // ============================================================

    localparam [2:0]
        ERR_NONE          = 3'd0,
        ERR_INVALID_KIND  = 3'd1,
        ERR_BUSY          = 3'd2,
        ERR_ENCODER       = 3'd3;


    // ============================================================
    // Formatter outputs
    // ============================================================

    wire                         format_valid;

    wire [7:0]                   formatted_type;
    wire [7:0]                   formatted_len;

    wire [MAX_PAYLOAD*8-1:0]     formatted_payload;


    // ============================================================
    // Encoder byte stream
    // ============================================================

    wire                         encoder_byte_valid;
    wire [7:0]                   encoder_byte_data;

    wire                         encoder_byte_ready;

    wire                         encoder_packet_accepted;
    wire                         encoder_packet_done;

    wire                         encoder_packet_error;
    wire [2:0]                   encoder_packet_error_code;


    // ============================================================
    // UART TX control
    // ============================================================

    wire                         uart_tx_start;


    // ============================================================
    // Final-byte tracking
    //
    // ctrl_response_packet_encoder asserts packet_done when CRC_L
    // has been ACCEPTED by ctrl_uart_tx.
    //
    // That does not mean CRC_L has finished on the physical wire.
    //
    // Therefore response_done waits for the following tx_done.
    // ============================================================

    reg waiting_final_uart_done;


    // ============================================================
    // Formatter
    // ============================================================

    ctrl_response_formatter #(
        .MAX_PAYLOAD(MAX_PAYLOAD)
    ) u_response_formatter (
        .response_kind     (response_kind),

        .original_cmd_type (original_cmd_type),

        .trial_id          (trial_id),

        .status_code       (status_code),

        .error_layer       (error_layer),
        .error_code        (error_code),

        .a_result          (a_result),
        .a_byte            (a_byte),
        .a_fe              (a_fe),
        .a_event_count     (a_event_count),

        .b_result          (b_result),
        .b_byte            (b_byte),
        .b_fe              (b_fe),
        .b_event_count     (b_event_count),

        .fault_seen        (fault_seen),

        .format_valid      (format_valid),

        .packet_type       (formatted_type),
        .packet_len        (formatted_len),
        .packet_payload    (formatted_payload)
    );


    // ============================================================
    // End-to-end busy
    //
    // No second response request is accepted until the current
    // UART response has physically completed.
    //
    // This deliberately provides a simple one-response-at-a-time
    // contract for V1.0.
    //
    // A later response arbiter will queue / prioritize events.
    // ============================================================

    assign response_busy =
        encoder_packet_busy
        |
        uart_tx_busy
        |
        waiting_final_uart_done;


    // ============================================================
    // Encoder request
    //
    // Only legal response kinds are forwarded.
    //
    // Busy requests are rejected at THIS wrapper and therefore do
    // not disturb the packet encoder.
    // ============================================================

    wire encoder_start;

    assign encoder_start =
        response_start
        &&
        format_valid
        &&
        !response_busy;


    // ============================================================
    // Packet Encoder
    // ============================================================

    ctrl_response_packet_encoder #(
        .MAX_PAYLOAD(MAX_PAYLOAD)
    ) u_packet_encoder (
        .clk               (clk),
        .rst_n             (rst_n),

        .packet_start      (encoder_start),

        .packet_type       (formatted_type),
        .packet_len        (formatted_len),
        .packet_payload    (formatted_payload),

        .byte_valid        (encoder_byte_valid),
        .byte_data         (encoder_byte_data),

        .byte_ready        (encoder_byte_ready),

        .packet_busy       (encoder_packet_busy),

        .packet_accepted   (encoder_packet_accepted),
        .packet_done       (encoder_packet_done),

        .packet_error      (encoder_packet_error),
        .packet_error_code (encoder_packet_error_code)
    );


    assign response_accepted =
        encoder_packet_accepted;


    // ============================================================
    // Encoder -> UART byte handshake
    //
    // The next encoder byte may be consumed only while UART TX is
    // idle.
    //
    // On exactly the same cycle:
    //
    // encoder sees byte_ready = 1
    // uart_tx sees tx_start = 1
    //
    // Therefore one encoder byte corresponds to exactly one UART
    // frame.
    // ============================================================

    assign encoder_byte_ready =
        !uart_tx_busy;


    assign uart_tx_start =
        encoder_byte_valid
        &&
        !uart_tx_busy;


    // ============================================================
    // Physical control UART TX
    // ============================================================

    ctrl_uart_tx #(
        .CLK_HZ (CLK_HZ),
        .BAUD   (BAUD)
    ) u_ctrl_uart_tx (
        .clk      (clk),
        .rst_n    (rst_n),

        .tx_data  (encoder_byte_data),

        .tx_start (uart_tx_start),

        .uart_tx  (uart_tx),

        .tx_busy  (uart_tx_busy),
        .tx_done  (uart_tx_done)
    );


    // ============================================================
    // Response completion + wrapper request errors
    // ============================================================

    always @(posedge clk) begin

        if (!rst_n) begin

            waiting_final_uart_done <=
                1'b0;

            response_done <=
                1'b0;

            response_error <=
                1'b0;

            response_error_code <=
                ERR_NONE;

        end
        else begin

            // ----------------------------------------------------
            // One-clock event defaults
            // ----------------------------------------------------

            response_done <=
                1'b0;

            response_error <=
                1'b0;

            response_error_code <=
                ERR_NONE;


            // ====================================================
            // Request-side errors
            // ====================================================

            if (response_start) begin

                if (response_busy) begin

                    response_error <=
                        1'b1;

                    response_error_code <=
                        ERR_BUSY;

                end
                else if (!format_valid) begin

                    response_error <=
                        1'b1;

                    response_error_code <=
                        ERR_INVALID_KIND;

                end

            end


            // ====================================================
            // Unexpected packet-encoder error
            // ====================================================

            if (encoder_packet_error) begin

                response_error <=
                    1'b1;

                response_error_code <=
                    ERR_ENCODER;

            end


            // ====================================================
            // Packet encoder has handed CRC_L to UART.
            //
            // Wait for that UART byte to physically finish.
            // ====================================================

            if (encoder_packet_done) begin

                waiting_final_uart_done <=
                    1'b1;

            end


            // ====================================================
            // Physical response complete
            // ====================================================

            if (
                waiting_final_uart_done
                &&
                uart_tx_done
            ) begin

                waiting_final_uart_done <=
                    1'b0;

                response_done <=
                    1'b1;

            end

        end

    end

endmodule