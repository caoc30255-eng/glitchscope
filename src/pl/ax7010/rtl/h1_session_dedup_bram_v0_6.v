`timescale 1ns / 1ps
// Isolated complete-request core. Caller proves outer CRC and supplies staged semantic decision.
// Three banks rotate atomically: RX staging / current / recent. No physical UART or W19.
module h1_session_dedup_bram_v0_6 (
    input wire clk,rst_n,
    input wire request_start,
    input wire [7:0] request_kind,
    input wire [31:0] request_session,request_seq,
    input wire [15:0] request_len,
    input wire hello_authorized,
    input wire new_item_capacity,
    input wire byte_valid,
    input wire [7:0] byte_data,
    input wire request_end,outer_crc_ok,
    output wire request_ready,
    output wire semantic_request,
    output wire [7:0] semantic_kind,
    output wire [31:0] semantic_session,semantic_seq,
    output wire [15:0] semantic_len,
    output reg [31:0] semantic_ticket,
    input wire [9:0] staging_read_addr,
    output wire [7:0] staging_read_data,
    input wire semantic_reply,semantic_ok,semantic_crc_trusted,
    input wire [31:0] semantic_reply_session,semantic_reply_seq,semantic_reply_ticket,
    output reg new_commit,
    output reg response_valid,
    output reg [7:0] response_state,response_code,
    output reg [31:0] response_session,response_seq,
    output reg [15:0] response_inner_crc,
    output reg response_credit,
    input wire response_ack,
    input wire start_request,start_authorized,
    input wire [31:0] start_session,start_seq,
    output reg start_pulse,start_rejected,
    output wire start_accept,
    input wire tx_done,
    input wire [31:0] done_session,done_seq,
    input wire retire_request,retire_authorized,
    input wire [31:0] retire_session,retire_seq,
    output reg retired,
    input wire [9:0] current_read_addr,
    output wire [7:0] current_read_data,
    output reg session_valid,
    output reg [31:0] active_session,last_seq,
    output reg slot_busy,current_valid,current_started,current_done,recent_valid,
    output reg [31:0] current_seq,recent_seq,
    output reg [15:0] current_len,
    output reg fault_latched,
    output reg [7:0] first_fault,
    output reg [31:0] commit_count,start_count,replay_count,silent_count,
    output reg silent_drop,
    output reg [2:0] state
);
    localparam [2:0] IDLE=0,RX=1,DISPATCH=2,COMPARE_CURRENT=3,COMPARE_RECENT=4,WAIT_SEMANTIC=5,COMPARE_CURRENT_CHECK=6,COMPARE_RECENT_CHECK=7;
    localparam [7:0] READY=8'h80,ACCEPTED=8'h81,REJECTED=8'h82,TX_DONE=8'h83;
    reg [1:0] staging_bank,current_bank,recent_bank;
    reg [7:0] rq_kind,current_kind,recent_kind;
    reg [31:0] rq_session,rq_seq;
    reg [15:0] rq_len,received,rq_crc,current_crc,recent_crc,recent_len;
    reg rq_hello_authorized,rq_outer_ok,overlength,recent_done;
    reg [9:0] compare_index;
    reg done_pending;
    reg [31:0] pending_done_session,pending_done_seq;
    reg [15:0] pending_done_crc;
    reg [31:0] ticket_count;
    wire bad_completion = tx_done && !(current_valid && slot_busy && current_started && !current_done &&
        done_session==active_session && done_seq==current_seq && !done_pending);
    wire interface_bad =
        (request_start && (!request_ready || byte_valid || request_end || semantic_reply || retire_request)) ||
        (byte_valid && (state!=RX || request_end)) || (request_end && state!=RX) ||
        (semantic_reply && state!=WAIT_SEMANTIC) || (response_ack && !response_valid) ||
        (retire_request && (state!=IDLE || response_valid || done_pending || request_start));
    assign start_accept=start_request && !fault_latched && !interface_bad && !tx_done && state==IDLE && !response_valid && !done_pending &&
                    current_valid && slot_busy && !current_started && !current_done && start_authorized &&
                    start_session==active_session && start_seq==current_seq;
    assign request_ready=state==IDLE && !response_valid && !done_pending;
    assign semantic_request=state==WAIT_SEMANTIC && !fault_latched;
    assign semantic_kind=rq_kind;
    assign semantic_session=rq_session;
    assign semantic_seq=rq_seq;
    assign semantic_len=rq_len;

    function [15:0] crc_next;
        input [15:0] previous;
        input [7:0] value;
        reg [15:0] crc;
        integer bit_no;
        begin
            crc=previous ^ {value,8'd0};
            for(bit_no=0;bit_no<8;bit_no=bit_no+1)
                if(crc[15]) crc=(crc<<1)^16'h1021;
                else crc=crc<<1;
            crc_next=crc;
        end
    endfunction
    // Four mirrored SDP copies per bank isolate semantic, W19 and both replay reads.
    wire memory_write=rst_n && !interface_bad && !bad_completion && !retire_request && state==RX && byte_valid && received<534;
    wire staging_read_en=rst_n && staging_read_addr<534 && state==WAIT_SEMANTIC;
    wire current_read_en=rst_n && current_read_addr<current_len && current_valid && slot_busy;
    wire compare_read_en=rst_n && (state==COMPARE_CURRENT || state==COMPARE_RECENT);
    wire [1:0] compare_target_bank=state==COMPARE_CURRENT ? current_bank : recent_bank;
    reg staging_out_valid,current_out_valid;
    wire [7:0] staging_bank_data[0:2];
    reg [1:0] staging_out_bank;
    reg [7:0] staging_mux;
    wire [7:0] current_bank_data[0:2];
    reg [1:0] current_out_bank;
    reg [7:0] current_mux;
    wire [7:0] compare_staging_bank_data[0:2];
    reg [1:0] compare_staging_out_bank;
    reg [7:0] compare_staging_mux;
    wire [7:0] compare_target_bank_data[0:2];
    reg [1:0] compare_target_out_bank;
    reg [7:0] compare_target_mux;
    genvar bank_no;
    generate for(bank_no=0;bank_no<3;bank_no=bank_no+1) begin:physical_banks
        h1_bank_sdp_bram_v0_2 staging_copy(.clk(clk),.rst_n(rst_n),.write_en(memory_write && staging_bank==bank_no),
            .write_addr(received[9:0]),.write_data(byte_data),.read_en(staging_read_en && staging_bank==bank_no),
            .read_addr(staging_read_addr),.read_data(staging_bank_data[bank_no]));
        h1_bank_sdp_bram_v0_2 current_copy(.clk(clk),.rst_n(rst_n),.write_en(memory_write && staging_bank==bank_no),
            .write_addr(received[9:0]),.write_data(byte_data),.read_en(current_read_en && current_bank==bank_no),
            .read_addr(current_read_addr),.read_data(current_bank_data[bank_no]));
        h1_bank_sdp_bram_v0_2 compare_staging_copy(.clk(clk),.rst_n(rst_n),.write_en(memory_write && staging_bank==bank_no),
            .write_addr(received[9:0]),.write_data(byte_data),.read_en(compare_read_en && staging_bank==bank_no),
            .read_addr(compare_index),.read_data(compare_staging_bank_data[bank_no]));
        h1_bank_sdp_bram_v0_2 compare_target_copy(.clk(clk),.rst_n(rst_n),.write_en(memory_write && staging_bank==bank_no),
            .write_addr(received[9:0]),.write_data(byte_data),.read_en(compare_read_en && compare_target_bank==bank_no),
            .read_addr(compare_index),.read_data(compare_target_bank_data[bank_no]));
    end endgenerate
    always @(posedge clk) begin
        if(!rst_n) begin
            staging_out_valid<=0;current_out_valid<=0;
            staging_out_bank<=0;
            current_out_bank<=0;
            compare_staging_out_bank<=0;
            compare_target_out_bank<=0;
        end else begin
            if(staging_read_en) begin staging_out_bank<=staging_bank;staging_out_valid<=1;end
            if(current_read_en) begin current_out_bank<=current_bank;current_out_valid<=1;end
            if(compare_read_en) begin compare_staging_out_bank<=staging_bank;end
            if(compare_read_en) begin compare_target_out_bank<=compare_target_bank;end
        end
    end
    always @* begin
        case(staging_out_bank)
            0:staging_mux=staging_bank_data[0];
            1:staging_mux=staging_bank_data[1];
            2:staging_mux=staging_bank_data[2];
            default:staging_mux=8'hxx;
        endcase
        case(current_out_bank)
            0:current_mux=current_bank_data[0];
            1:current_mux=current_bank_data[1];
            2:current_mux=current_bank_data[2];
            default:current_mux=8'hxx;
        endcase
        case(compare_staging_out_bank)
            0:compare_staging_mux=compare_staging_bank_data[0];
            1:compare_staging_mux=compare_staging_bank_data[1];
            2:compare_staging_mux=compare_staging_bank_data[2];
            default:compare_staging_mux=8'hxx;
        endcase
        case(compare_target_out_bank)
            0:compare_target_mux=compare_target_bank_data[0];
            1:compare_target_mux=compare_target_bank_data[1];
            2:compare_target_mux=compare_target_bank_data[2];
            default:compare_target_mux=8'hxx;
        endcase
    end
    assign staging_read_data=staging_out_valid ? staging_mux : 8'd0;
    assign current_read_data=current_out_valid ? current_mux : 8'd0;
    task reply;
        input [7:0] msg_state,code;
        input [31:0] session_id,sequence_id;
        input [15:0] inner_crc;
        input credit;
        begin
            response_valid<=1;response_state<=msg_state;response_code<=code;
            response_session<=session_id;response_seq<=sequence_id;
            response_inner_crc<=inner_crc;response_credit<=credit;state<=IDLE;
        end
    endtask
    task lock_fault;
        input [7:0] reason;
        begin
            fault_latched<=1;
            if(!fault_latched) first_fault<=reason;
        end
    endtask
    wire free_credit=session_valid && new_item_capacity && !slot_busy && !fault_latched;

    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;staging_bank<=0;current_bank<=1;recent_bank<=2;
            rq_kind<=0;rq_session<=0;rq_seq<=0;rq_len<=0;received<=0;
            rq_crc<=16'hffff;rq_hello_authorized<=0;rq_outer_ok<=0;overlength<=0;
            current_kind<=0;current_crc<=0;recent_kind<=0;recent_crc<=0;recent_len<=0;recent_done<=0;
            compare_index<=0;session_valid<=0;active_session<=0;last_seq<=0;
            slot_busy<=0;current_valid<=0;current_started<=0;current_done<=0;
            recent_valid<=0;current_seq<=0;recent_seq<=0;current_len<=0;
            response_valid<=0;response_state<=0;response_code<=0;response_session<=0;response_seq<=0;
            response_inner_crc<=0;response_credit<=0;
            done_pending<=0;pending_done_session<=0;pending_done_seq<=0;pending_done_crc<=0;
            ticket_count<=0;semantic_ticket<=0;
            new_commit<=0;start_pulse<=0;start_rejected<=0;retired<=0;silent_drop<=0;
            fault_latched<=0;first_fault<=0;commit_count<=0;start_count<=0;replay_count<=0;silent_count<=0;
        end else begin
            new_commit<=0;start_pulse<=0;start_rejected<=0;retired<=0;silent_drop<=0;
            if(response_valid && response_ack) response_valid<=0;
            // One reserved completion record survives a still-pending ACCEPTED/replay reply.
            if(!response_valid && done_pending && state==IDLE) begin
                reply(TX_DONE,fault_latched ? 8 : 0,pending_done_session,pending_done_seq,pending_done_crc,0);
                done_pending<=0;
            end
            if(tx_done) begin
                if(current_valid && slot_busy && current_started && !current_done &&
                    done_session==active_session && done_seq==current_seq && !done_pending) begin
                    current_done<=1;done_pending<=1;
                    pending_done_session<=active_session;pending_done_seq<=current_seq;pending_done_crc<=current_crc;
                end else lock_fault(8);
            end
            if(start_request) begin
                if(start_accept) begin
                    current_started<=1;start_pulse<=1;
                    if(start_count!=32'hffffffff) start_count<=start_count+1'b1;
                end else start_rejected<=1;
            end
            if(interface_bad || bad_completion) begin
                lock_fault(8);state<=IDLE;
            end else if(retire_request) begin
                if(!fault_latched && !tx_done && current_valid && slot_busy && current_done && retire_authorized &&
                    retire_session==active_session && retire_seq==current_seq) begin
                    slot_busy<=0;retired<=1;
                    reply(READY,0,active_session,0,0,new_item_capacity);
                end else begin
                    lock_fault(8);
                end
            end else begin
                case(state)
                    IDLE: if(request_start) begin
                        rq_kind<=request_kind;rq_session<=request_session;rq_seq<=request_seq;rq_len<=request_len;
                        rq_hello_authorized<=hello_authorized;received<=0;overlength<=0;
                        rq_crc<=16'hffff;state<=RX;
                    end
                    RX: begin
                        if(byte_valid) begin
                            if(received<534) begin
                                // All SDP copies write through memory_write.
                            end else overlength<=1;
                            if(received!=16'hffff) received<=received+1'b1;
                            else overlength<=1;
                            rq_crc<=crc_next(rq_crc,byte_data);
                        end
                        if(request_end) begin rq_outer_ok<=outer_crc_ok;state<=DISPATCH;end
                    end
                    DISPATCH: begin
                        if(!rq_outer_ok) begin
                            silent_drop<=1;state<=IDLE;
                            if(silent_count!=32'hffffffff) silent_count<=silent_count+1'b1;
                        end else if(fault_latched) reply(REJECTED,8,rq_session,rq_seq,0,0);
                        else if(overlength || received!=rq_len || rq_len>534)
                            reply(REJECTED,6,rq_session,rq_seq,0,0);
                        else if(rq_kind<1 || rq_kind>4 || (rq_kind==1 && (rq_len!=0 || rq_seq!=0)))
                            reply(REJECTED,1,rq_session,rq_seq,0,0);
                        else if(rq_kind==1) begin
                            if(session_valid && rq_session==active_session)
                                reply(READY,0,active_session,0,0,free_credit);
                            else if(!slot_busy && rq_hello_authorized && hello_authorized) begin
                                session_valid<=1;active_session<=rq_session;last_seq<=0;
                                current_valid<=0;recent_valid<=0;current_started<=0;current_done<=0;
                                reply(READY,0,rq_session,0,0,new_item_capacity);
                            end else reply(REJECTED,5,rq_session,0,0,0);
                        end else if(!session_valid || rq_session!=active_session)
                            reply(REJECTED,5,rq_session,rq_seq,0,0);
                        else if(rq_len==0) reply(REJECTED,6,rq_session,rq_seq,0,0);
                        else if(current_valid && rq_seq==current_seq) begin
                            if(rq_kind!=current_kind || rq_len!=current_len) begin
                                lock_fault(4);reply(REJECTED,4,rq_session,rq_seq,0,0);
                            end else begin compare_index<=0;state<=COMPARE_CURRENT;end
                        end else if(recent_valid && rq_seq==recent_seq) begin
                            if(rq_kind!=recent_kind || rq_len!=recent_len) begin
                                lock_fault(4);reply(REJECTED,4,rq_session,rq_seq,0,0);
                            end else begin compare_index<=0;state<=COMPARE_RECENT;end
                        end else if(rq_seq!=last_seq+32'd1 || rq_seq==32'hffffffff) begin
                            lock_fault(4);reply(REJECTED,4,rq_session,rq_seq,0,0);
                        end else if(slot_busy || !new_item_capacity)
                            reply(REJECTED,3,rq_session,rq_seq,0,0);
                        else if(ticket_count==32'hffffffff) begin
                            lock_fault(8);reply(REJECTED,8,rq_session,rq_seq,0,0);
                        end else begin
                            ticket_count<=ticket_count+1'b1;semantic_ticket<=ticket_count+1'b1;
                            state<=WAIT_SEMANTIC;
                        end
                    end
                    COMPARE_CURRENT: state<=COMPARE_CURRENT_CHECK;
                    COMPARE_CURRENT_CHECK: begin
                        if(compare_staging_mux!==compare_target_mux) begin
                            lock_fault(4);reply(REJECTED,4,rq_session,rq_seq,0,0);
                        end else if(compare_index==rq_len-1) begin
                            if(replay_count!=32'hffffffff) replay_count<=replay_count+1'b1;
                            reply(current_done ? TX_DONE : ACCEPTED,0,rq_session,rq_seq,current_crc,free_credit);
                        end else begin compare_index<=compare_index+1'b1;state<=COMPARE_CURRENT;end
                    end
                    COMPARE_RECENT: state<=COMPARE_RECENT_CHECK;
                    COMPARE_RECENT_CHECK: begin
                        if(compare_staging_mux!==compare_target_mux) begin
                            lock_fault(4);reply(REJECTED,4,rq_session,rq_seq,0,0);
                        end else if(compare_index==rq_len-1) begin
                            if(replay_count!=32'hffffffff) replay_count<=replay_count+1'b1;
                            reply(recent_done ? TX_DONE : ACCEPTED,0,rq_session,rq_seq,recent_crc,free_credit);
                        end else begin compare_index<=compare_index+1'b1;state<=COMPARE_RECENT;end
                    end
                    WAIT_SEMANTIC: if(semantic_reply) begin
                        if(fault_latched) reply(REJECTED,8,rq_session,rq_seq,0,0);
                        else if(semantic_reply_session!==rq_session || semantic_reply_seq!==rq_seq ||
                                semantic_reply_ticket!==semantic_ticket) begin
                            lock_fault(8);reply(REJECTED,8,rq_session,rq_seq,0,0);
                        end
                        else if(semantic_ok!==1'b1 || semantic_crc_trusted!==1'b1)
                            reply(REJECTED,2,rq_session,rq_seq,(semantic_crc_trusted===1'b1) ? rq_crc : 0,free_credit);
                        else if(slot_busy || !new_item_capacity)
                            reply(REJECTED,3,rq_session,rq_seq,0,0);
                        else begin
                            // Atomic role rotation; neither saved bank is overwritten before acceptance.
                            recent_bank<=current_bank;current_bank<=staging_bank;staging_bank<=recent_bank;
                            recent_valid<=current_valid;recent_seq<=current_seq;recent_len<=current_len;
                            recent_kind<=current_kind;recent_crc<=current_crc;recent_done<=current_done;
                            current_valid<=1;slot_busy<=1;current_started<=0;current_done<=0;
                            current_seq<=rq_seq;current_len<=rq_len;current_kind<=rq_kind;current_crc<=rq_crc;
                            last_seq<=rq_seq;new_commit<=1;
                            if(commit_count!=32'hffffffff) commit_count<=commit_count+1'b1;
                            reply(ACCEPTED,0,rq_session,rq_seq,rq_crc,0);
                        end
                    end
                    default: begin lock_fault(8);state<=IDLE;end
                endcase
            end
        end
    end
endmodule
