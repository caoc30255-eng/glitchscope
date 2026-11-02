`timescale 1ns / 1ps

// ============================================================================
// STM32 DUT response receiver V1
//
// Receives the fixed 13-byte response defined by DUT_PROTOCOL_V1.md:
//
//   A5 5A | 01 | A0 | 06 |
//   TRIAL_LO TRIAL_HI RX_LEN RX_PAYLOAD UART_FLAGS STATUS |
//   CRC_H CRC_L
//
// The module contains a one-entry mailbox.  A valid response remains stable
// until clear is pulsed.  A second valid response while the mailbox is full
// sets response_overrun and leaves the first response untouched.
// ============================================================================

module dut_response_receiver_v1 #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD = 1_000_000,
    parameter integer BYTE_TIMEOUT_CLKS = 1_000_000
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       uart_rx,
    input  wire       clear,

    output reg        response_valid,
    output reg [15:0] response_trial_id,
    output reg [7:0]  response_rx_len,
    output reg [7:0]  response_rx_payload,
    output reg [7:0]  response_uart_flags,
    output reg [7:0]  response_status,
    output reg        response_overrun,

    output reg        error_pulse,
    output reg [3:0]  error_code,
    output wire       rx_busy
);

    localparam [7:0]
        SOF0          = 8'hA5,
        SOF1          = 8'h5A,
        VERSION       = 8'h01,
        RESPONSE_TYPE = 8'hA0,
        RESPONSE_LEN  = 8'h06;

    localparam [3:0]
        ERR_NONE        = 4'd0,
        ERR_UART_FRAME  = 4'd1,
        ERR_VERSION     = 4'd2,
        ERR_TYPE        = 4'd3,
        ERR_LENGTH      = 4'd4,
        ERR_CRC         = 4'd5,
        ERR_TIMEOUT     = 4'd6,
        ERR_OVERRUN     = 4'd7;

    localparam [3:0]
        INDEX_SOF0       = 4'd0,
        INDEX_SOF1       = 4'd1,
        INDEX_VERSION    = 4'd2,
        INDEX_TYPE       = 4'd3,
        INDEX_LEN        = 4'd4,
        INDEX_TRIAL_LO   = 4'd5,
        INDEX_TRIAL_HI   = 4'd6,
        INDEX_RX_LEN     = 4'd7,
        INDEX_RX_PAYLOAD = 4'd8,
        INDEX_UART_FLAGS = 4'd9,
        INDEX_STATUS     = 4'd10,
        INDEX_CRC_H      = 4'd11,
        INDEX_CRC_L      = 4'd12;

    wire [7:0] rx_data;
    wire rx_valid;
    wire framing_error;

    reg [3:0] byte_index;
    reg [31:0] timeout_count;

    reg [7:0] version_buffer;
    reg [7:0] type_buffer;
    reg [7:0] len_buffer;
    reg [15:0] trial_id_buffer;
    reg [7:0] rx_len_buffer;
    reg [7:0] rx_payload_buffer;
    reg [7:0] uart_flags_buffer;
    reg [7:0] status_buffer;

    reg [15:0] crc_register;
    reg [7:0] crc_received_high;

    function [15:0] crc16_next;
        input [15:0] crc_in;
        input [7:0] data_in;
        integer bit_number;
        reg [15:0] crc_work;
        begin
            crc_work = crc_in;

            for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1)
            begin
                if (crc_work[15] ^ data_in[7-bit_number])
                    crc_work = {crc_work[14:0], 1'b0} ^ 16'h1021;
                else
                    crc_work = {crc_work[14:0], 1'b0};
            end

            crc16_next = crc_work;
        end
    endfunction

    ctrl_uart_rx #(
        .CLK_HZ (CLK_HZ),
        .BAUD   (BAUD)
    ) u_dut_uart_rx (
        .clk           (clk),
        .rst_n         (rst_n),
        .uart_rx       (uart_rx),
        .rx_data       (rx_data),
        .rx_valid      (rx_valid),
        .framing_error (framing_error),
        .rx_busy       (rx_busy)
    );

    always @(posedge clk)
    begin
        if (!rst_n)
        begin
            response_valid <= 1'b0;
            response_trial_id <= 16'h0000;
            response_rx_len <= 8'h00;
            response_rx_payload <= 8'h00;
            response_uart_flags <= 8'h00;
            response_status <= 8'h00;
            response_overrun <= 1'b0;

            error_pulse <= 1'b0;
            error_code <= ERR_NONE;

            byte_index <= INDEX_SOF0;
            timeout_count <= 32'd0;

            version_buffer <= 8'h00;
            type_buffer <= 8'h00;
            len_buffer <= 8'h00;
            trial_id_buffer <= 16'h0000;
            rx_len_buffer <= 8'h00;
            rx_payload_buffer <= 8'h00;
            uart_flags_buffer <= 8'h00;
            status_buffer <= 8'h00;

            crc_register <= 16'hFFFF;
            crc_received_high <= 8'h00;
        end
        else
        begin
            error_pulse <= 1'b0;
            error_code <= ERR_NONE;

            if (clear)
            begin
                response_valid <= 1'b0;
                response_overrun <= 1'b0;
            end

            if (framing_error)
            begin
                byte_index <= INDEX_SOF0;
                timeout_count <= 32'd0;
                crc_register <= 16'hFFFF;

                error_pulse <= 1'b1;
                error_code <= ERR_UART_FRAME;
            end
            else if (rx_valid)
            begin
                timeout_count <= 32'd0;

                case (byte_index)
                    INDEX_SOF0:
                    begin
                        if (rx_data == SOF0)
                            byte_index <= INDEX_SOF1;
                    end

                    INDEX_SOF1:
                    begin
                        if (rx_data == SOF1)
                        begin
                            byte_index <= INDEX_VERSION;
                            crc_register <= 16'hFFFF;
                        end
                        else if (rx_data == SOF0)
                        begin
                            byte_index <= INDEX_SOF1;
                        end
                        else
                        begin
                            byte_index <= INDEX_SOF0;
                        end
                    end

                    INDEX_VERSION:
                    begin
                        version_buffer <= rx_data;
                        crc_register <= crc16_next(16'hFFFF, rx_data);
                        byte_index <= INDEX_TYPE;
                    end

                    INDEX_TYPE:
                    begin
                        type_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_LEN;
                    end

                    INDEX_LEN:
                    begin
                        len_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_TRIAL_LO;
                    end

                    INDEX_TRIAL_LO:
                    begin
                        trial_id_buffer[7:0] <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_TRIAL_HI;
                    end

                    INDEX_TRIAL_HI:
                    begin
                        trial_id_buffer[15:8] <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_RX_LEN;
                    end

                    INDEX_RX_LEN:
                    begin
                        rx_len_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_RX_PAYLOAD;
                    end

                    INDEX_RX_PAYLOAD:
                    begin
                        rx_payload_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_UART_FLAGS;
                    end

                    INDEX_UART_FLAGS:
                    begin
                        uart_flags_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_STATUS;
                    end

                    INDEX_STATUS:
                    begin
                        status_buffer <= rx_data;
                        crc_register <= crc16_next(crc_register, rx_data);
                        byte_index <= INDEX_CRC_H;
                    end

                    INDEX_CRC_H:
                    begin
                        crc_received_high <= rx_data;
                        byte_index <= INDEX_CRC_L;
                    end

                    INDEX_CRC_L:
                    begin
                        byte_index <= INDEX_SOF0;
                        crc_register <= 16'hFFFF;

                        if ({crc_received_high, rx_data} != crc_register)
                        begin
                            error_pulse <= 1'b1;
                            error_code <= ERR_CRC;
                        end
                        else if (version_buffer != VERSION)
                        begin
                            error_pulse <= 1'b1;
                            error_code <= ERR_VERSION;
                        end
                        else if (type_buffer != RESPONSE_TYPE)
                        begin
                            error_pulse <= 1'b1;
                            error_code <= ERR_TYPE;
                        end
                        else if (len_buffer != RESPONSE_LEN)
                        begin
                            error_pulse <= 1'b1;
                            error_code <= ERR_LENGTH;
                        end
                        else if (response_valid && !clear)
                        begin
                            response_overrun <= 1'b1;
                            error_pulse <= 1'b1;
                            error_code <= ERR_OVERRUN;
                        end
                        else
                        begin
                            response_valid <= 1'b1;
                            response_trial_id <= trial_id_buffer;
                            response_rx_len <= rx_len_buffer;
                            response_rx_payload <= rx_payload_buffer;
                            response_uart_flags <= uart_flags_buffer;
                            response_status <= status_buffer;
                        end
                    end

                    default:
                    begin
                        byte_index <= INDEX_SOF0;
                        crc_register <= 16'hFFFF;
                    end
                endcase
            end
            else if (byte_index != INDEX_SOF0)
            begin
                if (timeout_count >= BYTE_TIMEOUT_CLKS - 1)
                begin
                    byte_index <= INDEX_SOF0;
                    timeout_count <= 32'd0;
                    crc_register <= 16'hFFFF;

                    error_pulse <= 1'b1;
                    error_code <= ERR_TIMEOUT;
                end
                else
                begin
                    timeout_count <= timeout_count + 1'b1;
                end
            end
            else
            begin
                timeout_count <= 32'd0;
            end
        end
    end

endmodule

