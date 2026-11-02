`timescale 1ns / 1ps
// Isolated H1 + real W19 TX. Evidence owner and retirement authorization remain external.
module h1_w19_profile_owner_core_bram_v0_5 #(
    parameter integer CLK_HZ=50000000, BAUD=2000000, CAP_TIMEOUT_CLKS=500000, W19_BAUD=1000000
)(
    input wire clk,rst_n,h1_rx_pin,
    output wire h1_tx_pin,
    input wire hello_authorized,new_item_capacity,management_idle,
    input wire [7:0] expected_route,
    input wire start_request,start_authorized,
    input wire [31:0] start_session,start_seq,
    input wire retire_request,retire_authorized,
    input wire [31:0] retire_session,retire_seq,
    input wire [9:0] current_read_addr,
    output wire [7:0] current_read_data,
    output wire start_pulse,start_rejected,retired,slot_busy,current_valid,current_started,current_done,
    output wire [31:0] active_session,current_seq,commit_count,start_count,validation_count,
    output wire cfg_valid,
    output wire [15:0] cfg_chunk,
    output wire link_fault,
    input wire evidence_ack,
    input wire [31:0] evidence_ack_session,evidence_ack_seq,evidence_ack_ticket,
    input wire [9:0] evidence_read_addr,
    output wire [7:0] evidence_read_data,evidence_kind,
    output wire evidence_read_valid,evidence_ready,
    output wire [31:0] evidence_session,evidence_seq,evidence_ticket,
    output wire [15:0] evidence_len,
    output wire control_fault,
    output wire [7:0] control_error,
    output wire w19_tx,w19_busy,w19_physical_start,w19_physical_done,w19_fault,
    output wire [31:0] w19_start_count,w19_done_count,
    input wire [31:0] route_epoch,
    input wire external_owner_fault,stm_item_eligible,
    output wire [15:0] accepted_frame_len,
    output wire current_commit,
    output wire [7:0] current_commit_kind,accepted_frame_kind,
    input wire injection_enable,
    input wire [8:0] injection_count,
    output wire [8:0] fault_points_expected,fault_points_emitted,
    input wire [15:0] injection_byte,injection_phase,injection_width,
    input wire [2:0] injection_bit,
    output wire raw_w19_tx,fault_active,fault_mark,fault_configuration_ok,actual_mark_required,
    output wire [31:0] fault_mark_count,
    output reg fault_policy_required,
    output reg [255:0] fault_snapshot_identity,
    output wire [255:0] fault_mark_identity,
    output wire [31:0] next_start_generation,
    output wire [255:0] prestart_full_identity,
    output wire actual_start_accept,
    output wire [255:0] current_window_identity,actual_start_identity,
    output reg [255:0] physical_identity,
    output reg tx_done_fenced,
    output wire owner_retire_ready,
    output wire runtime_h1_idle,runtime_raw_held
);
    // Module-scope nets are explicitly typed before their first use.
    wire cap_valid;
    wire [7:0] r_image;
    wire [15:0] r_item;
    wire [7:0] r_route;
    wire [31:0] response_seq;
    wire [7:0] response_state;
    wire [31:0] w19_saved_session,w19_saved_seq;
    wire [15:0] current_len;
    wire ingress_idle;
    wire new_commit;
    wire [7:0] r_kind;
    wire [31:0] r_run;
    wire [15:0] r_trial;
    wire [7:0] request_kind;
    wire response_ack;
    wire [31:0] response_session;
    wire semantic_request;
    wire capture_idle;
    wire overlay_fault,sender_fault,overlay_active,saved_fault_enable;
    wire [15:0] saved_target_byte,saved_phase,saved_width;
    wire [8:0] saved_target_count;
    wire point_mark,sender_physical_done;
    assign fault_points_expected=saved_fault_enable ? saved_target_count : 9'd0;
    assign w19_physical_done=sender_physical_done && (!saved_fault_enable || fault_points_emitted==saved_target_count) && !overlay_fault;
    wire [2:0] saved_target_bit,data_bit_index;
    wire [9:0] frame_byte_index;
    wire [31:0] data_bit_clock;
    wire data_bit_active,physical_start_take;
    wire [255:0] guard_mark_identity,guard_snapshot_identity;
    wire [9:0] w19_read_addr;
    wire [15:0] w19_saved_len,w19_completed_bytes;
    wire [7:0] w19_saved_kind,w19_error;
    wire [2:0] w19_state;
    wire w19_launch_taken,w19_launch_rejected,w19_rearm_taken,w19_rearm_rejected;
    wire abort_validation;
    wire adapter_busy;
    wire [7:0] adapter_error;
    wire adapter_fault;
    wire [3:0] adapter_state;
    wire [7:0] byte_data;
    wire byte_valid;
    wire [9:0] cap_addr;
    wire [15:0] cap_crc;
    wire [7:0] cap_data;
    wire [7:0] cap_error;
    wire cap_error_valid;
    wire [31:0] cap_errors;
    wire cap_fault;
    wire [7:0] cap_first_error;
    wire [7:0] cap_kind;
    wire [15:0] cap_len;
    wire cap_release;
    wire [31:0] cap_seq;
    wire [31:0] cap_session;
    wire [15:0] cfg_height;
    wire [7:0] cfg_image;
    wire [15:0] cfg_items;
    wire [31:0] cfg_run;
    wire [255:0] cfg_sha;
    wire [31:0] cfg_total;
    wire [15:0] cfg_width;
    wire core_retire_request;
    wire core_start_rejected;
    wire core_start_request;
    wire [7:0] decision_code;
    wire [9:0] delivered_index;
    wire fault_latched;
    wire [7:0] first_fault;
    wire forward_status;
    wire ingress_activity;
    wire [3:0] ingress_state;
    wire [31:0] last_seq;
    wire outer_crc_ok;
    wire q_accepted;
    wire [31:0] q_accepted_count;
    wire q_active;
    wire [31:0] q_completed_count;
    wire [2:0] q_count;
    wire [103:0] q_diag_payload;
    wire q_diag_valid;
    wire q_done;
    wire [31:0] q_done_seq;
    wire [31:0] q_done_session;
    wire [7:0] q_done_state;
    wire q_fault;
    wire [7:0] q_fault_code;
    wire [103:0] q_first_payload;
    wire [31:0] q_format_count;
    wire [31:0] q_overflow_count;
    wire q_ready;
    wire q_take;
    wire q_valid;
    wire qualified_capacity;
    wire [7:0] r_attempt;
    wire [15:0] r_payload;
    wire [31:0] recent_seq;
    wire recent_valid;
    wire [31:0] replay_count;
    wire request_end;
    wire [15:0] request_len;
    wire request_ready;
    wire [31:0] request_seq;
    wire [31:0] request_session;
    wire request_start;
    wire [7:0] response_code;
    wire response_credit;
    wire [15:0] response_inner_crc;
    wire response_valid;
    wire return_tx;
    wire rx_busy;
    wire [7:0] rx_data;
    wire rx_fe;
    wire rx_valid;
    wire semantic_crc_trusted;
    wire [7:0] semantic_kind;
    wire [15:0] semantic_len;
    wire semantic_ok;
    wire semantic_reply;
    wire [31:0] semantic_reply_seq;
    wire [31:0] semantic_reply_session;
    wire [31:0] semantic_reply_ticket;
    wire [31:0] semantic_seq;
    wire [31:0] semantic_session;
    wire [31:0] semantic_ticket;
    wire session_valid;
    wire [31:0] silent_count;
    wire silent_drop;
    wire [9:0] staging_read_addr;
    wire [7:0] staging_read_data;
    wire [2:0] state;
    wire v_ack;
    wire v_busy;
    wire v_byte_valid;
    wire [7:0] v_code;
    wire v_commit;
    wire v_commit_enable;
    wire [7:0] v_data;
    wire v_end;
    wire v_fault;
    wire [7:0] v_kind;
    wire [15:0] v_len;
    wire v_management;
    wire v_ok;
    wire v_ready;
    wire v_result_valid;
    wire [7:0] v_route;
    wire v_start;
    wire validation_done;








    // Explicit internal declarations precede every use.

    reg [7:0] accepted_kind;




















    reg mark_binding_fault;
    reg [255:0] last_mark_identity;
    wire mask_enable;
    h1_multipoint_window_v0_1 point_window(
        .enabled(overlay_active && saved_fault_enable && !overlay_fault),
        .first_byte(saved_target_byte),.count(saved_target_count),.byte_index(frame_byte_index),
        .point_mark(point_mark),.mask_enable(mask_enable),.first_mark(fault_mark));
    function [31:0] unpack32;
        input [31:0] value;
        begin unpack32={value[7:0],value[15:8],value[23:16],value[31:24]};end
    endfunction
    // P1 byte encoding is NOT the old guard's concatenated bit layout.
    function [255:0] guard_binding;
        input [255:0] value;
        begin guard_binding={37'd0,unpack32(value[31:0]),unpack32(value[63:32]),
            unpack32(value[95:64]),value[98:96],unpack32(value[135:104]),
            unpack32(value[167:136]),value[175:168],
            value[183:176],value[191:184],value[199:192],value[207:200],
            value[215:208],value[223:216]};end
    endfunction
    assign actual_mark_required=(injection_enable===1'b1) && accepted_kind==3;
    assign w19_fault=sender_fault || overlay_fault || mark_binding_fault;
    assign fault_mark_identity=fault_mark ? physical_identity : last_mark_identity;
    always @(posedge clk) begin
        if(!rst_n) begin
            fault_policy_required<=0;fault_snapshot_identity<=0;
            last_mark_identity<=0;mark_binding_fault<=0;
        end else begin
            if(actual_start_accept) begin
                fault_policy_required<=actual_mark_required;
                fault_snapshot_identity<=actual_start_identity;
            end
            if(fault_mark) begin
                if(!fault_policy_required || guard_mark_identity!==guard_binding(physical_identity))
                    mark_binding_fault<=1;
                else last_mark_identity<=physical_identity;
            end
        end
    end
    reg [31:0] generation_counter,saved_epoch,saved_run,pending_epoch;
    reg semantic_seen;
    reg [7:0] saved_image,saved_attempt,saved_route;
    reg [15:0] saved_trial,saved_item;
    reg identity_fault;
    function [31:0] packed32;
        input [31:0] value;
        begin packed32={value[7:0],value[15:8],value[23:16],value[31:24]};end
    endfunction
    function [255:0] identity;
        input [31:0] session,seq,epoch,generation,run;
        input [7:0] image,attempt,route;
        input [15:0] trial,item;
        begin
            identity=0;
            identity[31:0]=packed32(session);identity[63:32]=packed32(seq);
            identity[95:64]=packed32(epoch);identity[135:104]=packed32(generation);
            identity[167:136]=packed32(run);identity[175:168]=image;
            identity[191:176]={trial[7:0],trial[15:8]};
            identity[207:192]={item[7:0],item[15:8]};
            identity[215:208]=attempt;identity[223:216]=route;
        end
    endfunction
    assign current_window_identity=identity(active_session,current_seq,saved_epoch,0,
        saved_run,saved_image,saved_attempt,saved_route,saved_trial,saved_item);
    assign next_start_generation=generation_counter==32'hffffffff ? 32'd0 : generation_counter+1'b1;
    assign prestart_full_identity=guard_binding(actual_start_identity);
    assign actual_start_identity=identity(active_session,current_seq,saved_epoch,generation_counter+1'b1,
        saved_run,saved_image,saved_attempt,saved_route,saved_trial,saved_item);
    assign accepted_frame_len=current_len;
    assign current_commit=new_commit;
    assign current_commit_kind=request_kind;
    assign accepted_frame_kind=accepted_kind;
    assign owner_retire_ready=ingress_idle && !cap_valid && !response_valid &&
        current_done && !w19_busy && !link_fault && tx_done_fenced;
    always @(posedge clk) begin
        if(!rst_n) begin
            generation_counter<=0;saved_epoch<=0;saved_run<=0;saved_image<=0;
            pending_epoch<=0;semantic_seen<=0;
            saved_trial<=0;saved_item<=0;saved_attempt<=0;saved_route<=0;
            physical_identity<=0;tx_done_fenced<=0;identity_fault<=0;
        end else begin
            if(!semantic_request) semantic_seen<=0;
            if(semantic_request && !semantic_seen) begin
                pending_epoch<=route_epoch;semantic_seen<=1;
            end
            if(new_commit) begin
                saved_epoch<=pending_epoch;saved_run<=r_run;saved_image<=r_image;
                saved_trial<=r_trial;saved_item<=r_item;saved_attempt<=r_attempt;
                saved_route<=(r_kind==3 ? r_route : v_route);tx_done_fenced<=0;
            end
            if(actual_start_accept) begin
                generation_counter<=generation_counter+1'b1;
                physical_identity<=actual_start_identity;tx_done_fenced<=0;
            end
            if(start_request && start_authorized && generation_counter==32'hffffffff)
                identity_fault<=1;
            if(response_ack && response_state==8'h83 &&
                response_session==active_session && response_seq==current_seq)
                tx_done_fenced<=1;
            if(retired) tx_done_fenced<=0;
        end
    end
    wire tx_done=w19_physical_done;
    wire [31:0] done_session=w19_saved_session,done_seq=w19_saved_seq;







    reg w19_armed,integration_fault;
    always @(posedge clk) begin
        if(!rst_n) begin accepted_kind<=0;w19_armed<=1;integration_fault<=0;end
        else begin
            if(new_commit) accepted_kind<=request_kind;
            if(start_pulse) w19_armed<=0;
            if(w19_rearm_taken) w19_armed<=1;
            if(w19_launch_rejected || w19_rearm_rejected) integration_fault<=1;
        end
    end




















    











































    
    


    
















    

    











































    assign ingress_activity=rx_busy || rx_valid || rx_fe || !h1_rx_pin;
    assign qualified_capacity=new_item_capacity && !external_owner_fault && !identity_fault && !control_fault && !cap_fault && !adapter_fault && !q_fault && !w19_fault && !integration_fault;
    assign abort_validation=external_owner_fault || identity_fault || control_fault || cap_fault || (!ingress_idle && ingress_activity) ||
        (semantic_request && (start_request || tx_done || retire_request || response_ack));
    assign core_start_request=start_request && ingress_idle && !cap_valid && !link_fault && w19_armed && !w19_busy && generation_counter!=32'hffffffff && fault_configuration_ok && (accepted_kind!=3 || stm_item_eligible);
    assign core_retire_request=retire_request && ingress_idle && !cap_valid && !link_fault && !w19_busy;
    assign start_rejected=core_start_rejected || (start_request && !core_start_request);
    assign q_valid=response_valid && forward_status && !control_fault && !cap_fault && !adapter_fault && !q_fault && !w19_fault && !integration_fault;
    assign response_ack=q_take;
    assign h1_tx_pin=return_tx;
    assign link_fault=external_owner_fault || identity_fault || control_fault || cap_fault || adapter_fault || fault_latched || q_fault || w19_fault || integration_fault;

    h1_ax_frame_capture_runtime_v0_1 #(.TIMEOUT_CLKS(CAP_TIMEOUT_CLKS)) u_capture(
        .clk(clk),
        .rst_n(rst_n),
        .rx_data(rx_data),
        .rx_valid(rx_valid),
        .rx_fe(rx_fe),
        .candidate_release(cap_release),
        .read_addr(cap_addr),
        .read_data(cap_data),
        .candidate_valid(cap_valid),
        .candidate_kind(cap_kind),
        .candidate_session(cap_session),
        .candidate_seq(cap_seq),
        .candidate_len(cap_len),
        .candidate_inner_crc(cap_crc),
        .error_valid(cap_error_valid),
        .error_code(cap_error),
        .first_error_code(cap_first_error),
        .error_count(cap_errors),
        .fault_latched(cap_fault),.capture_idle(capture_idle)
    );
    h1_session_dedup_bram_v0_6 u_session(
        .clk(clk),
        .rst_n(rst_n),
        .request_start(request_start),
        .request_kind(request_kind),
        .request_session(request_session),
        .request_seq(request_seq),
        .request_len(request_len),
        .hello_authorized(hello_authorized),
        .new_item_capacity(qualified_capacity),
        .byte_valid(byte_valid),
        .byte_data(byte_data),
        .request_end(request_end),
        .outer_crc_ok(outer_crc_ok),
        .request_ready(request_ready),
        .semantic_request(semantic_request),
        .semantic_kind(semantic_kind),
        .semantic_session(semantic_session),
        .semantic_seq(semantic_seq),
        .semantic_len(semantic_len),
        .semantic_ticket(semantic_ticket),
        .staging_read_addr(staging_read_addr),
        .staging_read_data(staging_read_data),
        .semantic_reply(semantic_reply),
        .semantic_ok(semantic_ok),
        .semantic_crc_trusted(semantic_crc_trusted),
        .semantic_reply_session(semantic_reply_session),
        .semantic_reply_seq(semantic_reply_seq),
        .semantic_reply_ticket(semantic_reply_ticket),
        .new_commit(new_commit),
        .response_valid(response_valid),
        .response_state(response_state),
        .response_code(response_code),
        .response_session(response_session),
        .response_seq(response_seq),
        .response_inner_crc(response_inner_crc),
        .response_credit(response_credit),
        .response_ack(response_ack),
        .start_request(core_start_request),
        .start_authorized(start_authorized),
        .start_session(start_session),
        .start_seq(start_seq),
        .start_pulse(start_pulse),
        .start_accept(actual_start_accept),
        .start_rejected(core_start_rejected),
        .tx_done(tx_done),
        .done_session(done_session),
        .done_seq(done_seq),
        .retire_request(core_retire_request),
        .retire_authorized(retire_authorized),
        .retire_session(retire_session),
        .retire_seq(retire_seq),
        .retired(retired),
        .current_read_addr(w19_busy ? w19_read_addr : current_read_addr),
        .current_read_data(current_read_data),
        .session_valid(session_valid),
        .active_session(active_session),
        .last_seq(last_seq),
        .slot_busy(slot_busy),
        .current_valid(current_valid),
        .current_started(current_started),
        .current_done(current_done),
        .recent_valid(recent_valid),
        .current_seq(current_seq),
        .recent_seq(recent_seq),
        .current_len(current_len),
        .fault_latched(fault_latched),
        .first_fault(first_fault),
        .commit_count(commit_count),
        .start_count(start_count),
        .replay_count(replay_count),
        .silent_count(silent_count),
        .silent_drop(silent_drop),
        .state(state)
    );
    h1_inner_validator_v0_1 u_validator(
        .clk(clk),
        .rst_n(rst_n),
        .frame_start(v_start),
        .frame_kind(v_kind),
        .frame_len(v_len),
        .management_idle(v_management),
        .expected_route(v_route),
        .byte_valid(v_byte_valid),
        .byte_data(v_data),
        .frame_end(v_end),
        .result_ack(v_ack),
        .commit_enable(v_commit_enable),
        .input_ready(v_ready),
        .busy(v_busy),
        .result_valid(v_result_valid),
        .result_ok(v_ok),
        .result_code(v_code),
        .result_kind(r_kind),
        .result_run(r_run),
        .result_image(r_image),
        .result_trial(r_trial),
        .result_item(r_item),
        .result_payload_len(r_payload),
        .result_attempt(r_attempt),
        .result_route(r_route),
        .commit_done(v_commit),
        .protocol_fault(v_fault),
        .cfg_valid(cfg_valid),
        .cfg_run(cfg_run),
        .cfg_image(cfg_image),
        .cfg_width(cfg_width),
        .cfg_height(cfg_height),
        .cfg_items(cfg_items),
        .cfg_chunk(cfg_chunk),
        .cfg_total(cfg_total),
        .cfg_sha(cfg_sha)
    );
    h1_real_semantic_adapter_v0_1 u_adapter(
        .clk(clk),
        .rst_n(rst_n),
        .semantic_request(semantic_request),
        .semantic_kind(semantic_kind),
        .semantic_session(semantic_session),
        .semantic_seq(semantic_seq),
        .semantic_ticket(semantic_ticket),
        .semantic_len(semantic_len),
        .staging_read_addr(staging_read_addr),
        .staging_read_data(staging_read_data),
        .new_item_capacity(qualified_capacity),
        .slot_busy(slot_busy),
        .session_fault(fault_latched),
        .session_new_commit(new_commit),
        .management_idle(management_idle),
        .expected_route(expected_route),
        .abort_validation(abort_validation),
        .checker_ready(v_ready),
        .checker_busy(v_busy),
        .checker_result_valid(v_result_valid),
        .checker_result_ok(v_ok),
        .checker_result_code(v_code),
        .checker_fault(v_fault),
        .checker_commit_done(v_commit),
        .checker_start(v_start),
        .checker_kind(v_kind),
        .checker_len(v_len),
        .checker_management_idle(v_management),
        .checker_expected_route(v_route),
        .checker_byte_valid(v_byte_valid),
        .checker_byte_data(v_data),
        .checker_end(v_end),
        .checker_ack(v_ack),
        .checker_commit_enable(v_commit_enable),
        .semantic_reply(semantic_reply),
        .semantic_ok(semantic_ok),
        .semantic_crc_trusted(semantic_crc_trusted),
        .reply_session(semantic_reply_session),
        .reply_seq(semantic_reply_seq),
        .reply_ticket(semantic_reply_ticket),
        .busy(adapter_busy),
        .adapter_fault(adapter_fault),
        .first_error(adapter_error),
        .last_decision_code(decision_code),
        .validation_done(validation_done),
        .validation_count(validation_count),
        .state(adapter_state),
        .delivered_index(delivered_index)
    );
    h1_status_uart_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_return(
        .clk(clk),
        .rst_n(rst_n),
        .status_valid(q_valid),
        .status_no_wait(1'b0),
        .status_state(response_state),
        .status_code(response_code),
        .status_credit({7'd0,response_credit}),
        .status_session(response_session),
        .status_seq(response_seq),
        .status_inner_crc(response_inner_crc),
        .status_ready(q_ready),
        .status_take(q_take),
        .status_accepted(q_accepted),
        .tx_enable(1'b1),
        .uart_tx(return_tx),
        .frame_active(q_active),
        .frame_done(q_done),
        .done_state(q_done_state),
        .done_session(q_done_session),
        .done_seq(q_done_seq),
        .queue_count(q_count),
        .fault_latched(q_fault),
        .first_fault_code(q_fault_code),
        .first_fault_payload(q_first_payload),
        .accepted_count(q_accepted_count),
        .completed_count(q_completed_count),
        .overflow_count(q_overflow_count),
        .format_count(q_format_count),
        .diag_index(16'd0),
        .diag_valid(q_diag_valid),
        .diag_payload(q_diag_payload)
    );
    ctrl_uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_rx(
        .clk(clk),
        .rst_n(rst_n),
        .uart_rx(h1_rx_pin),
        .rx_data(rx_data),
        .rx_valid(rx_valid),
        .framing_error(rx_fe),
        .rx_busy(rx_busy)
    );
    h1_ingress_control_v0_1 u_ingress(
        .clk(clk),
        .rst_n(rst_n),
        .candidate_valid(cap_valid),
        .capture_fault(cap_fault),
        .ingress_activity(ingress_activity),
        .candidate_kind(cap_kind),
        .candidate_session(cap_session),
        .candidate_seq(cap_seq),
        .candidate_len(cap_len),
        .candidate_crc(cap_crc),
        .candidate_release(cap_release),
        .capture_read_addr(cap_addr),
        .capture_read_data(cap_data),
        .core_ready(request_ready),
        .core_response_valid(response_valid),
        .semantic_adapter_busy(adapter_busy),
        .semantic_adapter_fault(adapter_fault),
        .core_response_session(response_session),
        .core_response_seq(response_seq),
        .core_state(state),
        .core_request_start(request_start),
        .core_byte_valid(byte_valid),
        .core_request_end(request_end),
        .core_kind(request_kind),
        .core_byte_data(byte_data),
        .core_session(request_session),
        .core_seq(request_seq),
        .core_len(request_len),
        .core_outer_ok(outer_crc_ok),
        .response_forward(forward_status),
        .evidence_ready(evidence_ready),
        .evidence_kind(evidence_kind),
        .evidence_session(evidence_session),
        .evidence_seq(evidence_seq),
        .evidence_ticket(evidence_ticket),
        .evidence_len(evidence_len),
        .evidence_ack(evidence_ack),
        .ack_session(evidence_ack_session),
        .ack_seq(evidence_ack_seq),
        .ack_ticket(evidence_ack_ticket),
        .evidence_read_addr(evidence_read_addr),
        .evidence_read_data(evidence_read_data),
        .evidence_read_valid(evidence_read_valid),
        .idle(ingress_idle),
        .control_fault(control_fault),
        .first_error(control_error),
        .state(ingress_state)
    );
    h1_w19_frame_tx_v0_3 #(.CLK_HZ(CLK_HZ),.BAUD(W19_BAUD)) u_w19(
        .clk(clk),.rst_n(rst_n),.launch(start_pulse),
        .launch_authorized(current_started && !link_fault),.current_valid(current_valid),
        // launch is already the session core's accepted START, not a second request.
        .current_started(1'b0),.current_done(current_done),
        .frame_kind(accepted_kind),.frame_session(active_session),.frame_seq(current_seq),.frame_len(current_len),
        .abort_request(overlay_fault || mark_binding_fault || external_owner_fault || identity_fault || control_fault || cap_fault || adapter_fault || fault_latched || q_fault || integration_fault),
        .rearm_request(retired),.rearm_authorized(1'b1),.rearm_session(w19_saved_session),.rearm_seq(w19_saved_seq),
        .read_addr(w19_read_addr),.read_data(current_read_data),.w19_tx(raw_w19_tx),.masked_tx(w19_tx),.mask_active(fault_active),.mask_mark(point_mark),
        .mask_enable(mask_enable),.mask_bit(saved_target_bit),.mask_phase(saved_phase),.mask_width(saved_width),
        .physical_start_take(physical_start_take),.launch_accept(),.data_bit_active(data_bit_active),
        .frame_byte_index(frame_byte_index),.data_bit_index(data_bit_index),.data_bit_clock(data_bit_clock),.busy(w19_busy),
        .launch_taken(w19_launch_taken),.launch_rejected(w19_launch_rejected),
        .rearm_taken(w19_rearm_taken),.rearm_rejected(w19_rearm_rejected),
        .physical_start(w19_physical_start),.physical_done(sender_physical_done),
        .saved_session(w19_saved_session),.saved_seq(w19_saved_seq),.saved_len(w19_saved_len),
        .completed_bytes(w19_completed_bytes),.saved_kind(w19_saved_kind),.fault_latched(sender_fault),
        .first_error(w19_error),.start_count(w19_start_count),.done_count(w19_done_count),.state(w19_state)
    );
    h1_payload_fault_overlay_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(W19_BAUD)) overlay (
        .clk(clk),.rst_n(rst_n),.configure_take(actual_start_accept),
        .physical_start_take(physical_start_take),.physical_done(sender_physical_done),
        .frame_abort(w19_fault || link_fault || integration_fault),
        .frame_kind(accepted_kind),.frame_len(current_len),.frame_session(active_session),.frame_seq(current_seq),
        .frame_identity(guard_binding(actual_start_identity)),.fault_enable(injection_enable),.target_count(injection_count),
        .target_byte(injection_byte),.phase_clks(injection_phase),.width_clks(injection_width),.target_bit(injection_bit),
        .raw_tx(raw_w19_tx),.data_bit_active(data_bit_active),.observed_fault_mark(point_mark),
        .byte_index(frame_byte_index),.bit_index(data_bit_index),.bit_clock(data_bit_clock),
        .configuration_ok(fault_configuration_ok),.w19_tx(),.fault_active(),.fault_mark(),
        .frame_active(overlay_active),.configuration_pending(),.policy_ignored(),
        .mark_identity(guard_mark_identity),.snapshot_identity(guard_snapshot_identity),
        .saved_target_byte(saved_target_byte),.saved_phase(saved_phase),.saved_width(saved_width),
        .saved_target_bit(saved_target_bit),.saved_enable(saved_fault_enable),.saved_count(saved_target_count),.frame_point_count(fault_points_emitted),
        .mark_count(fault_mark_count),.interface_fault(overlay_fault)
    );

    assign runtime_h1_idle=capture_idle && ingress_idle && !cap_valid && !response_valid &&
        !rx_busy && !rx_valid && !rx_fe && h1_rx_pin && !adapter_busy && !v_busy && !q_active && q_count==0;
    assign runtime_raw_held=cap_valid && evidence_ticket!=0 && (ingress_state==4'd7 || ingress_state==4'd15) &&
        cap_kind==evidence_kind && cap_session==evidence_session && cap_seq==evidence_seq && cap_len==evidence_len;
endmodule
