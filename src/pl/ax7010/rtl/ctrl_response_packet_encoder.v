`timescale 1ns / 1ps

module ctrl_response_packet_encoder #(
    parameter integer MAX_PAYLOAD = 32
)(
    input  wire                         clk,
    input  wire                         rst_n,

    // ============================================================
    // Packet request
    //
    // packet_start:
    //     one-clock request pulse
    //
    // Packet format:
    //
    // A5 5A | 01 | TYPE | LEN | PAYLOAD | CRC_H CRC_L
    //
    // CRC range:
    //
    // VER + TYPE + LEN + PAYLOAD
    //
    // SOF bytes are NOT included.
    // ============================================================

    input  wire                         packet_start,
    input  wire [7:0]                   packet_type,
    input  wire [7:0]                   packet_len,
    input  wire [MAX_PAYLOAD*8-1:0]     packet_payload,


    // ============================================================
    // Byte-stream output
    //
    // byte_valid remains asserted and byte_data remains stable
    // until byte_ready = 1.
    //
    // A byte is consumed on:
    //
    //     byte_valid && byte_ready
    // ============================================================

    output reg                          byte_valid,
    output reg [7:0]                    byte_data,

    input  wire                         byte_ready,


    // ============================================================
    // Encoder lifecycle
    // ============================================================

    output wire                         packet_busy,

    output reg                          packet_accepted,
    output reg                          packet_done,


    // ============================================================
    // Request error
    //
    // error_code:
    //
    // 0 = NONE
    // 1 = LENGTH_TOO_LARGE
    // 2 = BUSY
    // ============================================================

    output reg                          packet_error,
    output reg [2:0]                    packet_error_code
);


    // ============================================================
    // Protocol constants
    // ============================================================

    localparam [7:0]
        SOF0 = 8'hA5,
        SOF1 = 8'h5A,
        VER  = 8'h01;


    localparam [2:0]
        ERR_NONE             = 3'd0,
        ERR_LENGTH_TOO_LARGE = 3'd1,
        ERR_BUSY             = 3'd2;


    localparam [7:0]
        MAX_PAYLOAD_U8 = MAX_PAYLOAD;


    // ============================================================
    // FSM
    // ============================================================

    localparam [3:0]
        ST_IDLE     = 4'd0,
        ST_SOF0     = 4'd1,
        ST_SOF1     = 4'd2,
        ST_VER      = 4'd3,
        ST_TYPE     = 4'd4,
        ST_LEN      = 4'd5,
        ST_PAYLOAD  = 4'd6,
        ST_CRC_WAIT = 4'd7,
        ST_CRC_H    = 4'd8,
        ST_CRC_L    = 4'd9;


    reg [3:0] state;


    // ============================================================
    // Atomic packet snapshot
    // ============================================================

    reg [7:0] type_latched;
    reg [7:0] len_latched;

    reg [MAX_PAYLOAD*8-1:0] payload_latched;

    reg [5:0] payload_index;


    // ============================================================
    // CRC
    // ============================================================

    wire       crc_init;
    wire       crc_data_valid;
    wire [7:0] crc_data_byte;

    wire [15:0] crc_out;

    reg  [15:0] crc_latched;


    // Initialize CRC on the exact clock that a legal packet request
    // is accepted.

    assign crc_init =
        (state == ST_IDLE) &&
        packet_start &&
        (packet_len <= MAX_PAYLOAD_U8);


    // CRC consumes a byte only when that protocol byte is actually
    // accepted by the downstream byte-stream consumer.

    assign crc_data_valid =
        byte_valid &&
        byte_ready &&
        (
            (state == ST_VER)     ||
            (state == ST_TYPE)    ||
            (state == ST_LEN)     ||
            (state == ST_PAYLOAD)
        );


    assign crc_data_byte =
        byte_data;


    crc16_ccitt u_crc16_ccitt (
        .clk        (clk),
        .rst_n      (rst_n),

        .crc_init   (crc_init),

        .data_valid (crc_data_valid),
        .data_byte  (crc_data_byte),

        .crc_out    (crc_out)
    );


    // ============================================================
    // Busy
    // ============================================================

    assign packet_busy =
        (state != ST_IDLE);


    // ============================================================
    // Byte-stream output decode
    // ============================================================

    always @(*) begin

        byte_valid = 1'b0;
        byte_data  = 8'h00;


        case (state)

            ST_SOF0: begin

                byte_valid = 1'b1;
                byte_data  = SOF0;

            end


            ST_SOF1: begin

                byte_valid = 1'b1;
                byte_data  = SOF1;

            end


            ST_VER: begin

                byte_valid = 1'b1;
                byte_data  = VER;

            end


            ST_TYPE: begin

                byte_valid = 1'b1;
                byte_data  = type_latched;

            end


            ST_LEN: begin

                byte_valid = 1'b1;
                byte_data  = len_latched;

            end


            ST_PAYLOAD: begin

                byte_valid = 1'b1;

                byte_data =
                    payload_latched[
                        payload_index*8 +: 8
                    ];

            end


            ST_CRC_H: begin

                byte_valid = 1'b1;
                byte_data  = crc_latched[15:8];

            end


            ST_CRC_L: begin

                byte_valid = 1'b1;
                byte_data  = crc_latched[7:0];

            end


            default: begin

                byte_valid = 1'b0;
                byte_data  = 8'h00;

            end

        endcase

    end


    // ============================================================
    // Main FSM
    // ============================================================

    always @(posedge clk) begin

        if (!rst_n) begin

            state <= ST_IDLE;

            type_latched <= 8'h00;
            len_latched  <= 8'h00;

            payload_latched <=
                {MAX_PAYLOAD*8{1'b0}};

            payload_index <= 6'd0;

            crc_latched <= 16'hFFFF;


            packet_accepted <= 1'b0;
            packet_done     <= 1'b0;

            packet_error      <= 1'b0;
            packet_error_code <= ERR_NONE;

        end
        else begin

            // ----------------------------------------------------
            // Event outputs are one-clock pulses
            // ----------------------------------------------------

            packet_accepted <= 1'b0;
            packet_done     <= 1'b0;

            packet_error      <= 1'b0;
            packet_error_code <= ERR_NONE;


            // ====================================================
            // Idle / request acceptance
            // ====================================================

            if (state == ST_IDLE) begin

                if (packet_start) begin

                    if (packet_len > MAX_PAYLOAD_U8) begin

                        packet_error <= 1'b1;

                        packet_error_code <=
                            ERR_LENGTH_TOO_LARGE;

                    end
                    else begin

                        type_latched <=
                            packet_type;

                        len_latched <=
                            packet_len;

                        payload_latched <=
                            packet_payload;

                        payload_index <=
                            6'd0;

                        packet_accepted <=
                            1'b1;

                        state <=
                            ST_SOF0;

                    end

                end

            end


            // ====================================================
            // Busy request rejection
            // ====================================================

            else begin

                if (packet_start) begin

                    packet_error <=
                        1'b1;

                    packet_error_code <=
                        ERR_BUSY;

                end


                // =================================================
                // Packet byte FSM
                // =================================================

                case (state)

                    ST_SOF0: begin

                        if (byte_ready)
                            state <= ST_SOF1;

                    end


                    ST_SOF1: begin

                        if (byte_ready)
                            state <= ST_VER;

                    end


                    ST_VER: begin

                        if (byte_ready)
                            state <= ST_TYPE;

                    end


                    ST_TYPE: begin

                        if (byte_ready)
                            state <= ST_LEN;

                    end


                    ST_LEN: begin

                        if (byte_ready) begin

                            if (len_latched == 8'd0) begin

                                state <=
                                    ST_CRC_WAIT;

                            end
                            else begin

                                payload_index <=
                                    6'd0;

                                state <=
                                    ST_PAYLOAD;

                            end

                        end

                    end


                    ST_PAYLOAD: begin

                        if (byte_ready) begin

                            if (
                                payload_index + 6'd1 >=
                                len_latched
                            ) begin

                                state <=
                                    ST_CRC_WAIT;

                            end
                            else begin

                                payload_index <=
                                    payload_index + 6'd1;

                            end

                        end

                    end


                    // ------------------------------------------------
                    // The final CRC-covered byte was consumed on the
                    // previous clock.
                    //
                    // Wait one clock so crc_out contains the updated
                    // CRC, then freeze it for transmission.
                    // ------------------------------------------------

                    ST_CRC_WAIT: begin

                        crc_latched <=
                            crc_out;

                        state <=
                            ST_CRC_H;

                    end


                    ST_CRC_H: begin

                        if (byte_ready)
                            state <= ST_CRC_L;

                    end


                    ST_CRC_L: begin

                        if (byte_ready) begin

                            state <=
                                ST_IDLE;

                            packet_done <=
                                1'b1;

                        end

                    end


                    default: begin

                        state <=
                            ST_IDLE;

                    end

                endcase

            end

        end

    end

endmodule