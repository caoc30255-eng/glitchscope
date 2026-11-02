`timescale 1ns / 1ps

module ctrl_packet_parser_runtime_v0_1 #(
    parameter integer MAX_PAYLOAD       = 32,
    parameter integer BYTE_TIMEOUT_CLKS = 1_000_000
)(
    input  wire                         clk,
    input  wire                         rst_n,

    // Byte stream from ctrl_uart_rx
    input  wire                         byte_valid,
    input  wire [7:0]                   byte_data,

    // Valid packet output
    output reg                          packet_valid,
    output reg  [7:0]                   packet_type,
    output reg  [7:0]                   packet_len,

    // payload byte i is:
    // packet_payload[i*8 +: 8]
    output reg  [MAX_PAYLOAD*8-1:0]     packet_payload,

    // Parser error pulse
    output reg                          parser_error,
    output reg  [2:0]                   error_code,
    output wire parser_idle
);

    // ============================================================
    // Protocol constants
    // ============================================================

    localparam [7:0] SOF0    = 8'hA5;
    localparam [7:0] SOF1    = 8'h5A;
    localparam [7:0] VERSION = 8'h01;


    // ============================================================
    // Error codes
    // ============================================================

    localparam [2:0]
        ERR_NONE    = 3'd0,
        ERR_VERSION = 3'd1,
        ERR_LENGTH  = 3'd2,
        ERR_CRC     = 3'd3,
        ERR_TIMEOUT = 3'd4;


    // ============================================================
    // Parser states
    // ============================================================

    localparam [3:0]
        S_SOF0    = 4'd0,
        S_SOF1    = 4'd1,
        S_VERSION = 4'd2,
        S_TYPE    = 4'd3,
        S_LENGTH  = 4'd4,
        S_PAYLOAD = 4'd5,
        S_CRC_H   = 4'd6,
        S_CRC_L   = 4'd7;

    reg [3:0] state;


    // ============================================================
    // Temporary packet storage
    //
    // Only copied to public outputs after CRC passes.
    // ============================================================

    reg [7:0] type_buf;
    reg [7:0] len_buf;

    reg [MAX_PAYLOAD*8-1:0] payload_buf;

    reg [7:0] payload_index;


    // ============================================================
    // CRC state
    // ============================================================

    reg [15:0] crc_reg;
    reg [7:0]  crc_rx_hi;


    // ============================================================
    // Packet timeout
    // ============================================================

    reg [31:0] timeout_cnt;


    // ============================================================
    // CRC-16/CCITT-FALSE byte update
    //
    // poly   = 0x1021
    // init   = 0xFFFF
    // refin  = false
    // refout = false
    // ============================================================

    function [15:0] crc16_next;

        input [15:0] crc_in;
        input [7:0]  data_in;

        integer i;
        reg [15:0] c;

        begin

            c = crc_in;

            for (i = 0; i < 8; i = i + 1) begin

                if (c[15] ^ data_in[7-i]) begin
                    c = {c[14:0], 1'b0} ^ 16'h1021;
                end
                else begin
                    c = {c[14:0], 1'b0};
                end

            end

            crc16_next = c;

        end

    endfunction


    // ============================================================
    // Main parser
    // ============================================================

    always @(posedge clk) begin

        if (!rst_n) begin

            state          <= S_SOF0;

            type_buf       <= 8'h00;
            len_buf        <= 8'h00;
            payload_buf    <= {MAX_PAYLOAD*8{1'b0}};
            payload_index  <= 8'h00;

            crc_reg        <= 16'hFFFF;
            crc_rx_hi      <= 8'h00;

            timeout_cnt    <= 32'd0;

            packet_valid   <= 1'b0;
            packet_type    <= 8'h00;
            packet_len     <= 8'h00;
            packet_payload <= {MAX_PAYLOAD*8{1'b0}};

            parser_error   <= 1'b0;
            error_code     <= ERR_NONE;

        end
        else begin

            // ----------------------------------------------------
            // Event outputs are one-clock pulses
            // ----------------------------------------------------

            packet_valid <= 1'b0;
            parser_error <= 1'b0;
            error_code   <= ERR_NONE;


            // ====================================================
            // New input byte
            // ====================================================

            if (byte_valid) begin

                timeout_cnt <= 32'd0;

                case (state)

                    // ============================================
                    // Search SOF0 = A5
                    // ============================================

                    S_SOF0: begin

                        if (byte_data == SOF0) begin
                            state <= S_SOF1;
                        end

                    end


                    // ============================================
                    // Search SOF1 = 5A
                    //
                    // A5 A5 5A is accepted:
                    // second A5 becomes a new SOF0 candidate.
                    // ============================================

                    S_SOF1: begin

                        if (byte_data == SOF1) begin

                            state <= S_VERSION;

                            crc_reg <= 16'hFFFF;

                            type_buf      <= 8'h00;
                            len_buf       <= 8'h00;
                            payload_buf   <= {MAX_PAYLOAD*8{1'b0}};
                            payload_index <= 8'h00;

                        end
                        else if (byte_data == SOF0) begin

                            // remain waiting for SOF1
                            state <= S_SOF1;

                        end
                        else begin

                            state <= S_SOF0;

                        end

                    end


                    // ============================================
                    // VERSION
                    // ============================================

                    S_VERSION: begin

                        if (byte_data == VERSION) begin

                            crc_reg <= crc16_next(
                                16'hFFFF,
                                byte_data
                            );

                            state <= S_TYPE;

                        end
                        else begin

                            parser_error <= 1'b1;
                            error_code   <= ERR_VERSION;

                            state <= S_SOF0;

                        end

                    end


                    // ============================================
                    // TYPE
                    // ============================================

                    S_TYPE: begin

                        type_buf <= byte_data;

                        crc_reg <= crc16_next(
                            crc_reg,
                            byte_data
                        );

                        state <= S_LENGTH;

                    end


                    // ============================================
                    // LENGTH
                    // ============================================

                    S_LENGTH: begin

                        if (byte_data > MAX_PAYLOAD) begin

                            parser_error <= 1'b1;
                            error_code   <= ERR_LENGTH;

                            state <= S_SOF0;

                        end
                        else begin

                            len_buf <= byte_data;

                            crc_reg <= crc16_next(
                                crc_reg,
                                byte_data
                            );

                            payload_index <= 8'h00;

                            if (byte_data == 8'h00) begin
                                state <= S_CRC_H;
                            end
                            else begin
                                state <= S_PAYLOAD;
                            end

                        end

                    end


                    // ============================================
                    // PAYLOAD
                    // ============================================

                    S_PAYLOAD: begin

                        payload_buf[
                            payload_index*8 +: 8
                        ] <= byte_data;

                        crc_reg <= crc16_next(
                            crc_reg,
                            byte_data
                        );


                        if (payload_index == len_buf - 1'b1) begin

                            state <= S_CRC_H;

                        end
                        else begin

                            payload_index <= payload_index + 1'b1;

                        end

                    end


                    // ============================================
                    // CRC high byte
                    // ============================================

                    S_CRC_H: begin

                        crc_rx_hi <= byte_data;

                        state <= S_CRC_L;

                    end


                    // ============================================
                    // CRC low byte
                    // ============================================

                    S_CRC_L: begin

                        if ({crc_rx_hi, byte_data} == crc_reg) begin

                            packet_type    <= type_buf;
                            packet_len     <= len_buf;
                            packet_payload <= payload_buf;

                            packet_valid   <= 1'b1;

                        end
                        else begin

                            parser_error <= 1'b1;
                            error_code   <= ERR_CRC;

                        end

                        state <= S_SOF0;

                    end


                    default: begin

                        state <= S_SOF0;

                    end

                endcase

            end


            // ====================================================
            // No new byte: timeout handling
            // ====================================================

            else begin

                if (state != S_SOF0) begin

                    if (timeout_cnt >= BYTE_TIMEOUT_CLKS - 1) begin

                        timeout_cnt <= 32'd0;

                        parser_error <= 1'b1;
                        error_code   <= ERR_TIMEOUT;

                        state <= S_SOF0;

                    end
                    else begin

                        timeout_cnt <= timeout_cnt + 1'b1;

                    end

                end
                else begin

                    timeout_cnt <= 32'd0;

                end

            end

        end

    end

    assign parser_idle=state==S_SOF0 && !packet_valid && !byte_valid && !parser_error;
endmodule