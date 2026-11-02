`timescale 1ns / 1ps
// Frame-level ownership between incoming-event ACKs and outgoing events.
// This mux precedes the existing legacy/event physical-pin arbiter.
module h1_p1_event_source_mux_v0_1 #(
    parameter integer TIMEOUT_CLKS=2000000
)(
    input wire clk,rst_n,
    input wire ack_valid,
    input wire [7:0] ack_type,
    input wire [255:0] ack_payload,
    output wire ack_take,ack_done,
    input wire notification_valid,
    input wire [7:0] notification_type,
    input wire [255:0] notification_payload,
    output wire notification_take,notification_done,
    output wire request_valid,
    output wire [7:0] request_type,
    output wire [255:0] request_payload,
    input wire request_take,request_done,
    output reg fault
);
    localparam [1:0] IDLE=0,OFFER=1,ACTIVE=2;
    reg [1:0] state;
    reg selected,last_selected;
    reg [31:0] timer;
    wire source_valid=selected ? notification_valid : ack_valid;
    assign request_valid=state==OFFER && source_valid && !fault;
    assign request_type=selected ? notification_type : ack_type;
    assign request_payload=selected ? notification_payload : ack_payload;
    assign ack_take=state==OFFER && !selected && request_take && !fault;
    assign notification_take=state==OFFER && selected && request_take && !fault;
    assign ack_done=state==ACTIVE && !selected && request_done && !fault;
    assign notification_done=state==ACTIVE && selected && request_done && !fault;
    always @(posedge clk) begin
        if(!rst_n) begin state<=IDLE;selected<=0;last_selected<=1;timer<=0;fault<=0;end
        else if(!fault) begin
            if((request_take && state!=OFFER) || (request_done && state!=ACTIVE)) fault<=1;
            else case(state)
                IDLE:if(ack_valid || notification_valid) begin
                    selected<=(ack_valid && notification_valid) ? !last_selected : notification_valid;
                    state<=OFFER;timer<=0;
                end
                OFFER:if(!source_valid) fault<=1;
                    else if(request_take) begin state<=ACTIVE;timer<=0;end
                    else if(timer>=TIMEOUT_CLKS-1) fault<=1;
                    else timer<=timer+1'b1;
                ACTIVE:if(request_done) begin state<=IDLE;last_selected<=selected;timer<=0;end
                    else if(timer>=TIMEOUT_CLKS-1) fault<=1;
                    else timer<=timer+1'b1;
            endcase
        end
    end
endmodule
