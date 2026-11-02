`timescale 1ns / 1ps
module h1_uart_tx_byte_v0_1 #(
    parameter integer CLK_HZ=50000000,
    parameter integer BAUD=2000000
)(
    input wire clk,rst_n,
    input wire byte_valid,
    input wire [7:0] byte_data,
    output wire byte_ready,
    output reg uart_tx,busy,byte_done
);
    localparam integer PERIOD=CLK_HZ/BAUD;
    localparam [1:0] START=0,DATA=1,STOP=2;
    reg [1:0] phase;
    reg [2:0] bit_index;
    reg [7:0] saved_byte;
    reg [31:0] cycles_left;
    assign byte_ready=!busy;
    initial begin
        if(BAUD<=0 || PERIOD<2 || CLK_HZ%BAUD!=0)
            $fatal(1,"UART TX requires a positive integer clocks-per-bit profile");
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            uart_tx<=1;busy<=0;byte_done<=0;phase<=START;
            bit_index<=0;saved_byte<=0;cycles_left<=0;
        end else begin
            byte_done<=0;
            if(!busy) begin
                uart_tx<=1;
                if(byte_valid) begin
                    saved_byte<=byte_data;bit_index<=0;phase<=START;
                    uart_tx<=0;busy<=1;cycles_left<=PERIOD-1;
                end
            end else if(cycles_left!=0) cycles_left<=cycles_left-1'b1;
            else begin
                cycles_left<=PERIOD-1;
                case(phase)
                    START: begin uart_tx<=saved_byte[0];phase<=DATA;bit_index<=0;end
                    DATA: if(bit_index==7) begin uart_tx<=1;phase<=STOP;end
                          else begin bit_index<=bit_index+1'b1;uart_tx<=saved_byte[bit_index+1'b1];end
                    STOP: begin uart_tx<=1;busy<=0;byte_done<=1;end
                    default: begin uart_tx<=1;busy<=0;end
                endcase
            end
        end
    end
endmodule
