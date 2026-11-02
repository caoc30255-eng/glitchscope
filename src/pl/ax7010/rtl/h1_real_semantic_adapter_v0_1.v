`timescale 1ns / 1ps
// Real session-staging RAM -> real validator. No fabricated semantic decision.
// Semantic reply and validator commit are sampled on the SAME clock edge.
module h1_real_semantic_adapter_v0_1 (
    input wire clk,rst_n,
    input wire semantic_request,
    input wire [7:0] semantic_kind,
    input wire [31:0] semantic_session,semantic_seq,semantic_ticket,
    input wire [15:0] semantic_len,
    output reg [9:0] staging_read_addr,
    input wire [7:0] staging_read_data,
    input wire new_item_capacity,slot_busy,session_fault,
    input wire session_new_commit,
    input wire management_idle,
    input wire [7:0] expected_route,
    input wire abort_validation,
    input wire checker_ready,checker_busy,checker_result_valid,checker_result_ok,
    input wire [7:0] checker_result_code,
    input wire checker_fault,checker_commit_done,
    output wire checker_start,
    output wire [7:0] checker_kind,
    output wire [15:0] checker_len,
    output wire checker_management_idle,
    output wire [7:0] checker_expected_route,
    output wire checker_byte_valid,
    output wire [7:0] checker_byte_data,
    output wire checker_end,checker_ack,checker_commit_enable,
    output wire semantic_reply,semantic_ok,semantic_crc_trusted,
    output wire [31:0] reply_session,reply_seq,reply_ticket,
    output wire busy,
    output reg adapter_fault,
    output reg [7:0] first_error,last_decision_code,
    output reg validation_done,
    output reg [31:0] validation_count,
    output reg [3:0] state,
    output reg [9:0] delivered_index
);
    localparam [3:0] IDLE=0,START=1,WAIT_READY=2,ADDRESS=3,
        WAIT_READ=4,SEND_BYTE=5,END_FRAME=6,WAIT_RESULT=7,DECIDE=8,POST=9,FAULT=15;
    reg [7:0] saved_kind,saved_route;
    reg [31:0] saved_session,saved_seq,saved_ticket;
    reg [15:0] saved_len;
    reg saved_idle,expected_accept;
    reg [9:0] index;
    reg [7:0] wait_count;
    wire needs_context=state!=IDLE && state!=POST && state!=FAULT;
    wire context_matches=semantic_request && semantic_kind==saved_kind && semantic_len==saved_len &&
        semantic_session==saved_session && semantic_seq==saved_seq && semantic_ticket==saved_ticket;
    wire safe_now=!adapter_fault && !checker_fault && !abort_validation && !session_fault &&
        (!needs_context || context_matches);
    // Conservative CRC qualification: never accept unknown/format/length/CRC/interface failure as proof.
    wire known_crc_reason=((checker_result_code==0) || (checker_result_code>=4 && checker_result_code<=13))===1'b1;
    wire live_management_ok=saved_kind==3 || management_idle===1'b1;
    wire accept_now=checker_result_ok===1'b1 && known_crc_reason && live_management_ok &&
        new_item_capacity===1'b1 && slot_busy===1'b0;
    assign busy=state!=IDLE;
    assign checker_start=state==START && safe_now;
    assign checker_kind=saved_kind;
    assign checker_len=saved_len;
    assign checker_management_idle=state==START ? saved_idle : management_idle;
    assign checker_expected_route=saved_route;
    assign checker_byte_valid=state==SEND_BYTE && safe_now && checker_ready;
    assign checker_byte_data=staging_read_data;
    assign checker_end=state==END_FRAME && safe_now;
    assign semantic_reply=state==DECIDE && safe_now && checker_result_valid;
    assign semantic_ok=checker_result_ok===1'b1 && known_crc_reason && live_management_ok;
    assign semantic_crc_trusted=known_crc_reason && checker_result_valid===1'b1;
    assign reply_session=saved_session;
    assign reply_seq=saved_seq;
    assign reply_ticket=saved_ticket;
    assign checker_ack=semantic_reply;
    assign checker_commit_enable=semantic_reply && accept_now;

    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;staging_read_addr<=0;index<=0;delivered_index<=0;
            saved_kind<=0;saved_route<=0;saved_session<=0;saved_seq<=0;saved_ticket<=0;saved_len<=0;saved_idle<=0;
            expected_accept<=0;wait_count<=0;adapter_fault<=0;first_error<=0;
            validation_done<=0;validation_count<=0;last_decision_code<=0;
        end else begin
            validation_done<=0;
            if(adapter_fault) state<=FAULT;
            else if(state!=IDLE && (abort_validation || checker_fault || session_fault ||
                (needs_context && !context_matches))) begin
                adapter_fault<=1;first_error<=1;state<=FAULT;
            end else case(state)
                IDLE: if(semantic_request) begin
                    if(checker_busy || checker_result_valid || checker_fault || abort_validation || session_fault ||
                        semantic_kind<2 || semantic_kind>4 || semantic_len<12 || semantic_len>534) begin
                        adapter_fault<=1;first_error<=2;state<=FAULT;
                    end else begin
                        saved_kind<=semantic_kind;saved_len<=semantic_len;
                        saved_session<=semantic_session;saved_seq<=semantic_seq;saved_ticket<=semantic_ticket;
                        saved_route<=expected_route;saved_idle<=management_idle;
                        index<=0;wait_count<=0;state<=START;
                    end
                end
                START: begin state<=WAIT_READY;wait_count<=0;end
                WAIT_READY: begin
                    if(checker_ready) begin state<=ADDRESS;wait_count<=0;end
                    else if(wait_count==8) begin adapter_fault<=1;first_error<=3;state<=FAULT;end
                    else wait_count<=wait_count+1'b1;
                end
                ADDRESS: begin staging_read_addr<=index;state<=WAIT_READ;end
                WAIT_READ: begin delivered_index<=index;state<=SEND_BYTE;end
                SEND_BYTE: begin
                    if(!checker_ready) begin adapter_fault<=1;first_error<=3;state<=FAULT;end
                    else if({6'd0,index}+16'd1>=saved_len) state<=END_FRAME;
                    else begin index<=index+1'b1;state<=ADDRESS;end
                end
                END_FRAME: begin state<=WAIT_RESULT;wait_count<=0;end
                WAIT_RESULT: begin
                    if(checker_result_valid) state<=DECIDE;
                    else if(wait_count==8) begin adapter_fault<=1;first_error<=3;state<=FAULT;end
                    else wait_count<=wait_count+1'b1;
                end
                DECIDE: begin
                    expected_accept<=accept_now;
                    last_decision_code <= (checker_result_ok && saved_kind!=3 && !management_idle) ? 8'd9 : checker_result_code;
                    state<=POST;
                end
                POST: begin
                    if(checker_result_valid || session_new_commit!==expected_accept || checker_commit_done!==expected_accept) begin
                        adapter_fault<=1;first_error<=4;state<=FAULT;
                    end else begin
                        validation_done<=1;
                        if(validation_count!=32'hffffffff) validation_count<=validation_count+1'b1;
                        state<=IDLE;
                    end
                end
                default: begin adapter_fault<=1;first_error<=3;state<=FAULT;end
            endcase
        end
    end
endmodule
