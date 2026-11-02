`timescale 1ns / 1ps
// Four waiting tuples plus one immutable active 18-byte frame.
// Normal valid/!ready is backpressure, NOT overflow. no_wait marks a non-stallable event.
module h1_status_uart_v0_1 #(
    parameter integer CLK_HZ=50000000,
    parameter integer BAUD=2000000
)(
    input wire clk,rst_n,
    input wire status_valid,status_no_wait,
    input wire [7:0] status_state,status_code,status_credit,
    input wire [31:0] status_session,status_seq,
    input wire [15:0] status_inner_crc,
    output wire status_ready,status_take,
    output reg status_accepted,
    input wire tx_enable,
    output wire uart_tx,
    output reg frame_active,frame_done,
    output reg [7:0] done_state,
    output reg [31:0] done_session,done_seq,
    output reg [2:0] queue_count,
    output reg fault_latched,
    output reg [7:0] first_fault_code,
    output reg [103:0] first_fault_payload,
    output reg [31:0] accepted_count,completed_count,overflow_count,format_count,
    input wire [15:0] diag_index,
    output reg diag_valid,
    output reg [103:0] diag_payload
);
    reg [103:0] fifo [0:3];
    reg [1:0] write_ptr,read_ptr;
    reg [143:0] active_frame;
    reg [7:0] active_state;
    reg [31:0] active_session,active_seq;
    reg [4:0] byte_index;
    reg need_byte;
    wire [103:0] incoming={status_state,status_session,status_seq,status_inner_crc,status_code,status_credit};
    wire format_ok=((status_state>=8'h80 && status_state<=8'h83) && status_code<=8 && status_credit<=1)===1'b1;
    wire base_pop=!frame_active && tx_enable && !fault_latched && queue_count!=0;
    wire bad_attempt=status_valid && !fault_latched &&
        (!format_ok || (status_no_wait && !(queue_count<4 || base_pop)));
    wire will_pop=base_pop && !bad_attempt;
    assign status_ready=!fault_latched && format_ok && (queue_count<4 || will_pop);
    assign status_take=status_valid && status_ready;
    wire push=status_take;
    wire [1:0] diag_slot=read_ptr+diag_index[1:0];
    wire byte_ready,byte_done,byte_busy;
    wire send_byte=frame_active && need_byte;
    wire [7:0] selected_byte=active_frame[143-(byte_index*8) -: 8];

    function [143:0] make_frame;
        input [103:0] payload;
        reg [111:0] body;
        reg [15:0] crc;
        reg [7:0] data;
        integer i,b;
        begin
            body={8'h01,payload};crc=16'hffff;
            for(i=0;i<14;i=i+1) begin
                data=body[111-(i*8) -: 8];crc=crc^{data,8'd0};
                for(b=0;b<8;b=b+1)
                    if(crc[15]) crc=(crc<<1)^16'h1021;else crc=crc<<1;
            end
            make_frame={16'ha66a,body,crc};
        end
    endfunction
    h1_uart_tx_byte_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_tx(
        .clk(clk),.rst_n(rst_n),.byte_valid(send_byte),.byte_data(selected_byte),
        .byte_ready(byte_ready),.uart_tx(uart_tx),.busy(byte_busy),.byte_done(byte_done)
    );
    always @(posedge clk) begin
        if(!rst_n) begin diag_valid<=0;diag_payload<=0;end
        else begin
            diag_valid<=diag_index<queue_count;
            if(diag_index<queue_count) diag_payload<=fifo[diag_slot];
            else diag_payload<=0;
        end
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            write_ptr<=0;read_ptr<=0;queue_count<=0;active_frame<=0;active_state<=0;
            active_session<=0;active_seq<=0;byte_index<=0;need_byte<=0;
            frame_active<=0;frame_done<=0;done_state<=0;done_session<=0;done_seq<=0;
            status_accepted<=0;fault_latched<=0;first_fault_code<=0;first_fault_payload<=0;
            accepted_count<=0;completed_count<=0;overflow_count<=0;format_count<=0;
        end else begin
            frame_done<=0;status_accepted<=0;
            if(bad_attempt) begin
                fault_latched<=1;first_fault_payload<=incoming;
                if(!format_ok) begin
                    first_fault_code<=2;
                    if(format_count!=32'hffffffff) format_count<=format_count+1'b1;
                end else begin
                    first_fault_code<=1;
                    if(overflow_count!=32'hffffffff) overflow_count<=overflow_count+1'b1;
                end
            end
            if(push) begin
                fifo[write_ptr]<=incoming;write_ptr<=write_ptr+1'b1;
                status_accepted<=1;
                if(accepted_count!=32'hffffffff) accepted_count<=accepted_count+1'b1;
            end
            if(will_pop) begin
                active_frame<=make_frame(fifo[read_ptr]);
                active_state<=fifo[read_ptr][103:96];active_session<=fifo[read_ptr][95:64];active_seq<=fifo[read_ptr][63:32];
                read_ptr<=read_ptr+1'b1;byte_index<=0;need_byte<=1;frame_active<=1;
            end
            case({push,will_pop})
                2'b10:queue_count<=queue_count+1'b1;
                2'b01:queue_count<=queue_count-1'b1;
                default: ;
            endcase
            if(frame_active) begin
                if(send_byte && byte_ready) need_byte<=0;
                if(byte_done) begin
                    if(byte_index==17) begin
                        frame_active<=0;need_byte<=0;frame_done<=1;
                        done_state<=active_state;done_session<=active_session;done_seq<=active_seq;
                        if(completed_count!=32'hffffffff) completed_count<=completed_count+1'b1;
                    end else begin byte_index<=byte_index+1'b1;need_byte<=1;end
                end
            end
        end
    end
endmodule
