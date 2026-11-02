`timescale 1ns / 1ps
// Single-clock RX migration and tagged evidence ownership. No W19/DUT evidence is invented.
module h1_ingress_control_v0_1 (
    input wire clk,rst_n,
    input wire candidate_valid,capture_fault,ingress_activity,
    input wire [7:0] candidate_kind,
    input wire [31:0] candidate_session,candidate_seq,
    input wire [15:0] candidate_len,candidate_crc,
    output wire candidate_release,
    output wire [9:0] capture_read_addr,
    input wire [7:0] capture_read_data,
    input wire core_ready,core_response_valid,semantic_adapter_busy,semantic_adapter_fault,
    input wire [31:0] core_response_session,core_response_seq,
    input wire [2:0] core_state,
    output wire core_request_start,core_byte_valid,core_request_end,
    output wire [7:0] core_kind,core_byte_data,
    output wire [31:0] core_session,core_seq,
    output wire [15:0] core_len,
    output wire core_outer_ok,response_forward,
    output wire evidence_ready,
    output wire [7:0] evidence_kind,
    output wire [31:0] evidence_session,evidence_seq,evidence_ticket,
    output wire [15:0] evidence_len,
    input wire evidence_ack,
    input wire [31:0] ack_session,ack_seq,ack_ticket,
    input wire [9:0] evidence_read_addr,
    output wire [7:0] evidence_read_data,
    output reg evidence_read_valid,
    output wire idle,
    output reg control_fault,
    output reg [7:0] first_error,
    output reg [3:0] state
);
    localparam [3:0] IDLE=0,START=1,ADDRESS=2,WAIT_READ=3,SEND=4,
        END_FRAME=5,WAIT_RESPONSE=6,EVIDENCE=7,RELEASE=8,CLEAR=9,FAULT=15;
    reg [7:0] saved_kind;
    reg [31:0] saved_session,saved_seq,ticket,next_ticket;
    reg [15:0] saved_len,saved_crc;
    reg [9:0] index,ram_addr;
    reg [7:0] clear_wait;
    wire active=state!=IDLE && state!=CLEAR && state!=FAULT;
    wire matches=candidate_valid && candidate_kind==saved_kind && candidate_session==saved_session &&
        candidate_seq==saved_seq && candidate_len==saved_len && candidate_crc==saved_crc;
    wire safe=!control_fault && !capture_fault && !ingress_activity && matches && !semantic_adapter_fault;
    wire bad_ack=evidence_ack && (state!=EVIDENCE || ack_session!==saved_session || ack_seq!==saved_seq || ack_ticket!==ticket);
    assign idle=state==IDLE && !control_fault;
    assign core_request_start=state==START && core_ready && safe && !bad_ack;
    assign core_kind=saved_kind;assign core_session=saved_session;assign core_seq=saved_seq;assign core_len=saved_len;
    assign core_byte_valid=state==SEND && safe && !bad_ack;
    assign core_byte_data=capture_read_data;
    assign core_request_end=state==END_FRAME && safe && !bad_ack;
    assign core_outer_ok=safe;
    assign candidate_release=state==RELEASE && safe && !bad_ack;
    // Before launch old asynchronous responses may drain; current reply waits for evidence and RX release.
    assign response_forward=!control_fault && (state==IDLE || state==START);
    assign evidence_ready=state==EVIDENCE && safe;
    assign evidence_kind=saved_kind;assign evidence_session=saved_session;assign evidence_seq=saved_seq;
    assign evidence_ticket=ticket;assign evidence_len=saved_len;
    assign capture_read_addr=(state==EVIDENCE || state==FAULT) ? evidence_read_addr : ram_addr;
    assign evidence_read_data=capture_read_data;
    always @(posedge clk) begin
        if(!rst_n) evidence_read_valid<=0;
        else evidence_read_valid<=candidate_valid && (state==EVIDENCE || state==FAULT) && evidence_read_addr<saved_len;
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;control_fault<=0;first_error<=0;saved_kind<=0;saved_session<=0;saved_seq<=0;
            saved_len<=0;saved_crc<=0;index<=0;ram_addr<=0;ticket<=0;next_ticket<=0;clear_wait<=0;
        end else if(control_fault) state<=FAULT;
        else if((active && (capture_fault || ingress_activity)) || capture_fault) begin
            control_fault<=1;first_error<=1;state<=FAULT;
        end else if(active && !matches) begin
            control_fault<=1;first_error<=2;state<=FAULT;
        end else if(semantic_adapter_fault) begin
            control_fault<=1;first_error<=3;state<=FAULT;
        end else if(bad_ack) begin
            control_fault<=1;first_error<=4;state<=FAULT;
        end else case(state)
            IDLE: if(candidate_valid && !ingress_activity) begin
                if(next_ticket==32'hffffffff) begin control_fault<=1;first_error<=5;state<=FAULT;end
                else begin
                    saved_kind<=candidate_kind;saved_session<=candidate_session;saved_seq<=candidate_seq;
                    saved_len<=candidate_len;saved_crc<=candidate_crc;index<=0;ram_addr<=0;
                    next_ticket<=next_ticket+1'b1;ticket<=next_ticket+1'b1;state<=START;
                end
            end
            START: if(core_ready && safe) begin
                if(saved_len==0) state<=END_FRAME;else state<=ADDRESS;
            end
            ADDRESS: begin ram_addr<=index;state<=WAIT_READ;end
            WAIT_READ: state<=SEND;
            SEND: if(core_state!=1) begin control_fault<=1;first_error<=6;state<=FAULT;end
                  else if({6'd0,index}+16'd1>=saved_len) state<=END_FRAME;
                  else begin index<=index+1'b1;state<=ADDRESS;end
            END_FRAME: state<=WAIT_RESPONSE;
            WAIT_RESPONSE: if(core_response_valid && core_response_session==saved_session &&
                core_response_seq==saved_seq && !semantic_adapter_busy) state<=EVIDENCE;
            EVIDENCE: if(evidence_ack) state<=RELEASE;
            RELEASE: begin state<=CLEAR;clear_wait<=0;end
            CLEAR: begin
                if(!candidate_valid) state<=IDLE;
                else if(clear_wait==8) begin control_fault<=1;first_error<=7;state<=FAULT;end
                else clear_wait<=clear_wait+1'b1;
            end
            default: begin control_fault<=1;first_error<=6;state<=FAULT;end
        endcase
    end
endmodule
