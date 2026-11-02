`timescale 1ns/1ps
// Single complete wire packet, byte ready/valid staging, synchronous RAM read.
// This transport cannot authorize H1 admission or W19 START. Host/AX own these.
module h1_7020_packet_tx_v0_1 #(
    parameter integer CLK_HZ=100000000,
    parameter integer BAUD=2000000
)(
    input wire clk,rst_n,
    input wire load_valid,
    input wire [7:0] load_data,
    input wire load_last,
    output wire load_ready,
    input wire launch_valid,
    output wire launch_ready,
    output wire launch_take,
    output wire uart_tx,
    output reg frame_active,frame_done,
    output reg [9:0] saved_length,
    output reg length_fault
);
    (* ram_style="block" *) reg [7:0] packet_ram[0:549];
    reg [9:0] count,index;
    reg sealed;
    localparam IDLE=0,READ=1,OFFER=2,WAIT_DONE=3;
    reg [1:0] state;
    reg [7:0] read_byte;
    wire byte_ready,byte_done,byte_busy;
    assign load_ready=!frame_active && !sealed && !length_fault && count<550;
    assign launch_ready=sealed && !frame_active && !length_fault;
    assign launch_take=launch_valid && launch_ready;
    // Memory has no reset on the data/write process; metadata gates stale bytes.
    always @(posedge clk) begin
        if(load_valid && load_ready) packet_ram[count]<=load_data;
        if(state==READ && frame_active) read_byte<=packet_ram[index];
    end
    h1_uart_tx_byte_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) byte_tx(
        .clk(clk),.rst_n(rst_n),.byte_valid(state==OFFER && frame_active),
        .byte_data(read_byte),.byte_ready(byte_ready),.uart_tx(uart_tx),
        .busy(byte_busy),.byte_done(byte_done)
    );
    always @(posedge clk) begin
        if(!rst_n) begin
            count<=0;index<=0;sealed<=0;state<=IDLE;saved_length<=0;
            frame_active<=0;frame_done<=0;length_fault<=0;
        end else begin
            frame_done<=0;
            if(load_valid && load_ready) begin
                count<=count+1'b1;
                if(load_last) begin
                    saved_length<=count+1'b1;sealed<=1;
                    if(count<15) length_fault<=1;
                end else if(count==549) length_fault<=1;
            end
            if(launch_take) begin
                frame_active<=1;index<=0;state<=READ;
            end else if(frame_active) begin
                case(state)
                    READ:state<=OFFER;
                    OFFER:if(byte_ready) state<=WAIT_DONE;
                    WAIT_DONE:if(byte_done) begin
                        if(index+1==saved_length) begin
                            frame_done<=1;frame_active<=0;state<=IDLE;
                            count<=0;sealed<=0;
                        end else begin index<=index+1'b1;state<=READ;end
                    end
                    default:begin length_fault<=1;state<=WAIT_DONE;end
                endcase
            end
        end
    end
endmodule
