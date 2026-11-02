`timescale 1ns / 1ps

// Holds the existing controller's one-clock response_start and 79-bit tuple
// until the old UART response engine actually accepts that tuple.
module h1_p1_legacy_pulse_hold_v0_1(
    input wire clk,rst_n,
    input wire request_pulse,
    input wire [78:0] request_desc,
    output reg valid,
    output reg [78:0] held_desc,
    input wire take,
    output reg fault
);
    always @(posedge clk) begin
        if(!rst_n) begin
            valid<=0;held_desc<=0;fault<=0;
        end else begin
            if(valid && take) valid<=0;
            if(request_pulse && !fault) begin
                if(valid && !take) fault<=1;
                else begin valid<=1;held_desc<=request_desc;end
            end
        end
    end
endmodule
