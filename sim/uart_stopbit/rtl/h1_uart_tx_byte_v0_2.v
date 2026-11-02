`timescale 1ns / 1ps
module h1_uart_tx_byte_v0_2 #(
    parameter integer CLK_HZ=50000000,
    parameter integer BAUD=2000000
)(
    input wire clk,rst_n,
    input wire byte_valid,
    input wire [7:0] byte_data,
    output wire byte_ready,
    input wire mask_enable,
    input wire [2:0] mask_bit,
    input wire [15:0] mask_phase,mask_width,
    output reg masked_tx,mask_active,mask_mark,
    output reg uart_tx,busy,byte_done,
    output wire data_bit_active,
    output wire [2:0] data_bit_index,
    output wire [31:0] data_bit_clock
);
    localparam integer PERIOD=CLK_HZ/BAUD;
    localparam [1:0] START=0,DATA=1,STOP=2;
    reg [1:0] phase;
    reg [2:0] bit_index;
    reg [7:0] saved_byte;
    reg [31:0] cycles_left;
    assign byte_ready=!busy;
    assign data_bit_active=busy && phase==DATA;
    assign data_bit_index=bit_index;
    assign data_bit_clock=PERIOD-1-cycles_left;
    reg next_data,next_raw;
    reg [2:0] next_bit;
    reg [31:0] next_clock;
    wire [16:0] mask_end={1'b0,mask_phase}+{1'b0,mask_width};
    wire next_mask=mask_enable && next_data && next_bit==mask_bit && next_clock>=mask_phase && next_clock<mask_end;
    always @* begin
        next_data=busy && phase==DATA;next_raw=uart_tx;next_bit=bit_index;next_clock=PERIOD-1-cycles_left;
        if(!busy) begin next_data=0;next_raw=byte_valid ? 0 : 1;end
        else if(cycles_left!=0) next_clock=PERIOD-cycles_left;
        else begin
            next_clock=0;
            case(phase)
                START: begin next_data=1;next_bit=0;next_raw=saved_byte[0];end
                DATA: if(bit_index==7) begin next_data=0;next_raw=1;end
                      else begin next_bit=bit_index+1'b1;next_data=1;next_raw=saved_byte[bit_index+1'b1];end
                default: begin next_data=0;next_raw=1;end
            endcase
        end
    end
    // Both raw and masked GPIO waveforms change on the same clock edge.
    always @(posedge clk) begin
        if(!rst_n) begin masked_tx<=1;mask_active<=0;mask_mark<=0;end
        else begin masked_tx<=next_raw ^ next_mask;mask_active<=next_mask;mask_mark<=next_mask && next_clock==mask_phase;end
    end
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
