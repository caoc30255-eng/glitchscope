`timescale 1ns/1ps
// Raw status evidence queue: CRC/format failure is saved, never converted to ACK.
// event_take means downstream has preserved the tuple, not semantic admission.
module h1_7020_status_rx_v0_2 #(
    parameter integer CLK_HZ=100000000,
    parameter integer BAUD=2000000,
    parameter integer PARTIAL_TIMEOUT_CYCLES=100000
)(
    input wire clk,rst_n,uart_rx,
    output wire event_valid,
    output wire stream_pending,
    input wire event_take,
    output wire [143:0] event_raw,
    output wire [4:0] event_length,
    output wire [2:0] event_reason,
    output reg [2:0] queue_count,
    output reg overflow_fault,
    output reg [151:0] first_lost_event,
    output reg [31:0] crc_errors,format_errors,framing_errors,partial_timeouts,
    output reg [31:0] completed_frames
);
    wire [7:0] byte_data;
    wire byte_valid,fe,rx_busy;
    ctrl_uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_rx(
        .clk(clk),.rst_n(rst_n),.uart_rx(uart_rx),.rx_data(byte_data),
        .rx_valid(byte_valid),.framing_error(fe),.rx_busy(rx_busy)
    );
    reg [151:0] fifo[0:3];
    reg [1:0] wr_ptr,rd_ptr;
    reg emit;
    reg [151:0] emitted;
    reg [143:0] raw;
    reg [4:0] count;
    reg [15:0] crc;
    reg [31:0] gap;
    wire [143:0] complete_raw={raw[135:0],byte_data};
    wire fields_ok=complete_raw[127:120]==1 &&
        complete_raw[119:112]>=8'h80 && complete_raw[119:112]<=8'h83 &&
        complete_raw[31:24]<=8 && complete_raw[23:16]<=1 &&
        (complete_raw[119:112]==8'h82 || complete_raw[31:24]==0);
    assign event_valid=queue_count!=0;
    assign {event_reason,event_length,event_raw}=event_valid ? fifo[rd_ptr] : 152'd0;
    assign stream_pending=event_valid || emit || count!=0 || rx_busy;
    wire pop=event_valid && event_take;
    wire push=emit && !overflow_fault && (queue_count<4 || pop);
    function [15:0] crc_byte;
        input [15:0] current_crc;input [7:0] data;
        reg [15:0] c;integer k;
        begin c=current_crc^{data,8'd0};
            for(k=0;k<8;k=k+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;
            crc_byte=c;
        end
    endfunction
    always @(posedge clk) begin
        if(!rst_n) begin
            wr_ptr<=0;rd_ptr<=0;queue_count<=0;overflow_fault<=0;first_lost_event<=0;
        end else begin
            if(push)begin fifo[wr_ptr]<=emitted;wr_ptr<=wr_ptr+1'b1;end
            if(pop)rd_ptr<=rd_ptr+1'b1;
            case({push,pop})
                2'b10:queue_count<=queue_count+1'b1;
                2'b01:queue_count<=queue_count-1'b1;
                default:queue_count<=queue_count;
            endcase
            if(emit && !overflow_fault && !push)begin
                overflow_fault<=1;first_lost_event<=emitted;
            end
        end
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            raw<=0;count<=0;crc<=16'hffff;gap<=0;emit<=0;emitted<=0;
            crc_errors<=0;format_errors<=0;framing_errors<=0;partial_timeouts<=0;completed_frames<=0;
        end else begin
            emit<=0;
            if(overflow_fault)begin count<=0;gap<=0;end
            else if(fe)begin
                emit<=1;emitted<={3'd4,count,raw};framing_errors<=framing_errors+1'b1;
                count<=0;raw<=0;gap<=0;crc<=16'hffff;
            end else if(byte_valid)begin
                gap<=0;
                if(count==0)begin
                    if(byte_data==8'ha6)begin raw<=byte_data;count<=1;end
                end else if(count==1)begin
                    if(byte_data==8'h6a)begin raw<=16'ha66a;count<=2;crc<=16'hffff;end
                    else if(byte_data==8'ha6)raw<=8'ha6;
                    else begin count<=0;raw<=0;end
                end else if(count==17)begin
                    emit<=1;count<=0;raw<=0;crc<=16'hffff;
                    completed_frames<=completed_frames+1'b1;
                    if(crc!={raw[7:0],byte_data})begin
                        emitted<={3'd2,5'd18,complete_raw};crc_errors<=crc_errors+1'b1;
                    end else if(!fields_ok)begin
                        emitted<={3'd3,5'd18,complete_raw};format_errors<=format_errors+1'b1;
                    end else emitted<={3'd1,5'd18,complete_raw};
                end else begin
                    raw<=complete_raw;count<=count+1'b1;
                    if(count>=2 && count<=15)crc<=crc_byte(crc,byte_data);
                end
            end else if(count!=0)begin
                if(gap>=PARTIAL_TIMEOUT_CYCLES-1)begin
                    emit<=1;emitted<={3'd5,count,raw};partial_timeouts<=partial_timeouts+1'b1;
                    count<=0;raw<=0;gap<=0;crc<=16'hffff;
                end else gap<=gap+1'b1;
            end else gap<=0;
        end
    end
    initial begin
        if(BAUD<=0 || CLK_HZ%BAUD!=0 || CLK_HZ/BAUD<4 || PARTIAL_TIMEOUT_CYCLES<20*(CLK_HZ/BAUD))
            $fatal(1,"Invalid status RX clock/timeout profile");
    end
endmodule
