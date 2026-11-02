`timescale 1ns / 1ps

module crc16_ccitt (
    input  wire        clk,
    input  wire        rst_n,

    // Pulse for one clock before starting a new packet.
    // CRC becomes 16'hFFFF.
    input  wire        crc_init,

    // One byte is consumed when data_valid = 1.
    input  wire        data_valid,
    input  wire [7:0]  data_byte,

    output reg  [15:0] crc_out
);

    integer i;
    reg [15:0] crc_next;


    // ============================================================
    // Byte-wise CRC-16/CCITT-FALSE
    //
    // poly    = 0x1021
    // init    = 0xFFFF
    // refin   = false
    // refout  = false
    // xorout  = 0x0000
    //
    // Bits are processed MSB first.
    // ============================================================

    always @(*) begin

        crc_next = crc_out;

        for (i = 0; i < 8; i = i + 1) begin

            if (crc_next[15] ^ data_byte[7-i]) begin
                crc_next =
                    {crc_next[14:0], 1'b0} ^ 16'h1021;
            end
            else begin
                crc_next =
                    {crc_next[14:0], 1'b0};
            end

        end

    end


    // ============================================================
    // CRC register
    // ============================================================

    always @(posedge clk) begin

        if (!rst_n) begin
            crc_out <= 16'hFFFF;
        end
        else begin

            // init has priority
            if (crc_init) begin
                crc_out <= 16'hFFFF;
            end
            else if (data_valid) begin
                crc_out <= crc_next;
            end

        end

    end

endmodule