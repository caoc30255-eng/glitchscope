`timescale 1ns / 1ps
// Image-profile legacy START adapter. Old router/guard/response controller are
// reused verbatim; legacy CONFIG/ABORT/RESULT_ACK effects are not enabled here.
module h1_p1_v1_start_path_runtime_v0_1(
    input wire ctrl_clk,life_clk,rst_n,
    input wire legacy_valid,
    input wire [7:0] legacy_type,legacy_len,
    input wire [255:0] legacy_payload,
    output wire legacy_ready,
    input wire response_busy,response_accepted,response_done,
    output wire response_request_pulse,
    output wire [78:0] response_desc,
    input wire current_valid,
    input wire [255:0] current_window_identity,
    input wire core_start_accept,
    input wire ctrl_fault,life_fault,
    output wire core_start_request,
    output wire [31:0] core_start_session,core_start_seq,
    output reg path_fault_ctrl,
    output wire quiet_ctrl,quiet_life
);
    localparam [1:0] C_IDLE=0,C_WAIT=1,C_REPLY=2;
    reg [1:0] ctrl_state;
    reg [31:0] ticket,held_ticket;
    reg [271:0] ctrl_packet;
    wire req_ready,req_valid_dst,result_ready_src,result_valid_dst;
    wire [303:0] req_data_dst;
    wire [319:0] result_data_dst;
    reg life_busy,route_pulse,result_valid;
    reg [31:0] life_ticket;
    reg [271:0] life_packet;
    reg [255:0] identity_snapshot;
    reg [7:0] result_category,result_code;
    wire request_send=legacy_valid && ctrl_state==C_IDLE && !ctrl_fault && !path_fault_ctrl && ticket!=32'hffffffff;
    wire request_take=request_send && req_ready;
    wire result_match=result_data_dst[319:288]==held_ticket &&
        result_data_dst[287:16]==ctrl_packet &&
        ctrl_packet=={legacy_type,legacy_len,legacy_payload};
    wire result_take=result_valid_dst && ctrl_state==C_WAIT && result_match && !ctrl_fault && !path_fault_ctrl;
    assign legacy_ready=result_take;
    wire life_request_take=req_valid_dst && !life_busy && !result_valid && !life_fault;
    wire [7:0] routed_type=life_packet[271:264],routed_len=life_packet[263:256];
    wire [255:0] routed_payload=life_packet[255:0];
    wire routed_start,routed_abort,routed_result_ack,routed_config,route_error;
    wire [15:0] start_trial,abort_trial,ack_trial;
    wire [2:0] route_error_code,guard_status;
    wire safe_start,safe_abort,safe_ack,guard_reject;
    wire [1:0] guard_command;
    wire [15:0] expected_trial={identity_snapshot[183:176],identity_snapshot[191:184]};
    wire binding_stable=current_valid && current_window_identity==identity_snapshot;
    assign core_start_request=safe_start && binding_stable && !life_fault;
    assign core_start_session={identity_snapshot[7:0],identity_snapshot[15:8],identity_snapshot[23:16],identity_snapshot[31:24]};
    assign core_start_seq={identity_snapshot[39:32],identity_snapshot[47:40],identity_snapshot[55:48],identity_snapshot[63:56]};
    h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(304)) commands (
        .src_clk(ctrl_clk),.dst_clk(life_clk),.rst_n(rst_n),
        .src_valid(request_send),.src_data({ticket+1'b1,legacy_type,legacy_len,legacy_payload}),
        .src_ready(req_ready),.dst_valid(req_valid_dst),.dst_data(req_data_dst),.dst_ready(life_request_take)
    );
    h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(320)) responses (
        .src_clk(life_clk),.dst_clk(ctrl_clk),.rst_n(rst_n),
        .src_valid(result_valid),.src_data({life_ticket,life_packet,result_category,result_code}),
        .src_ready(result_ready_src),.dst_valid(result_valid_dst),
        .dst_data(result_data_dst),.dst_ready(result_take)
    );
    ctrl_command_router #(.MAX_PAYLOAD(32)) legacy_router (
        .clk(life_clk),.rst_n(rst_n),.packet_valid(route_pulse),
        .packet_type(routed_type),.packet_len(routed_len),.packet_payload(routed_payload),
        .config_packet_valid(routed_config),.start_cmd_valid(routed_start),.start_trial_id(start_trial),
        .abort_cmd_valid(routed_abort),.abort_trial_id(abort_trial),
        .result_ack_cmd_valid(routed_result_ack),.result_ack_trial_id(ack_trial),
        .router_error(route_error),.router_error_code(route_error_code)
    );
    ctrl_trial_id_guard trial_guard (
        .clk(life_clk),.rst_n(rst_n),.soft_reset(1'b0),
        .start_cmd_valid(routed_start),.start_cmd_trial_id(start_trial),
        .abort_cmd_valid(routed_abort),.abort_cmd_trial_id(abort_trial),
        .result_ack_cmd_valid(routed_result_ack),.result_ack_cmd_trial_id(ack_trial),
        .active_trial_id({16'd0,expected_trial}),.current_trial_id({16'd0,expected_trial}),
        .result_ready(1'b0),.mailbox_trial_id(32'd0),
        .start_req(safe_start),.abort_req(safe_abort),.result_ack(safe_ack),
        .guard_reject(guard_reject),.guard_command(guard_command),.guard_status(guard_status)
    );
    always @(posedge life_clk) begin
        if(!rst_n) begin
            life_busy<=0;route_pulse<=0;result_valid<=0;life_ticket<=0;life_packet<=0;
            identity_snapshot<=0;result_category<=0;result_code<=0;
        end else begin
            route_pulse<=0;
            if(life_request_take) begin
                life_busy<=1;life_ticket<=req_data_dst[303:272];life_packet<=req_data_dst[271:0];
                identity_snapshot<=current_window_identity;route_pulse<=1;
            end
            if(life_busy && !result_valid && !life_fault) begin
                if(route_error) begin result_valid<=1;result_category<=1;result_code<={5'd0,route_error_code};end
                else if(guard_reject) begin result_valid<=1;result_category<=2;result_code<={5'd0,guard_status};end
                else if(safe_start) begin
                    result_valid<=1;result_category<=0;
                    result_code<=core_start_accept ? 8'd1 : (!current_valid ? 8'd3 : 8'd2);
                end else if(routed_config || safe_abort || safe_ack) begin
                    result_valid<=1;result_category<=1;result_code<=8'd2;
                end
            end
            if(result_valid && result_ready_src) begin result_valid<=0;life_busy<=0;end
        end
    end
    wire response_queue_overflow;
    always @(posedge ctrl_clk) begin
        if(!rst_n) begin ctrl_state<=C_IDLE;ticket<=0;held_ticket<=0;ctrl_packet<=0;path_fault_ctrl<=0;end
        else begin
            if(ctrl_fault || response_queue_overflow) path_fault_ctrl<=1;
            if(legacy_valid && ctrl_state==C_IDLE && ticket==32'hffffffff) path_fault_ctrl<=1;
            if(request_take) begin
                ctrl_state<=C_WAIT;ticket<=ticket+1'b1;held_ticket<=ticket+1'b1;
                ctrl_packet<={legacy_type,legacy_len,legacy_payload};
            end
            if(result_valid_dst && ctrl_state==C_WAIT) begin
                if(!result_match) path_fault_ctrl<=1;
                else if(result_take) ctrl_state<=C_REPLY;
            end
            if(ctrl_state==C_REPLY && response_done) ctrl_state<=C_IDLE;
        end
    end
    wire [1:0] rc_response_kind;
    wire [7:0] rc_response_original_cmd_type;
    wire [15:0] rc_response_trial_id;
    wire [7:0] rc_response_status_code;
    wire [7:0] rc_response_error_layer;
    wire [7:0] rc_response_error_code_out;
    wire [2:0] rc_response_a_result;
    wire [7:0] rc_response_a_byte;
    wire rc_response_a_fe;
    wire [1:0] rc_response_a_event_count;
    wire [2:0] rc_response_b_result;
    wire [7:0] rc_response_b_byte;
    wire rc_response_b_fe;
    wire [1:0] rc_response_b_event_count;
    wire rc_response_fault_seen;
    wire rc_command_response_pending;
    wire rc_result_response_pending;
    wire rc_transport_error_seen;
    wire [2:0] rc_last_transport_error_code;
    assign response_desc={rc_response_kind,rc_response_original_cmd_type,rc_response_trial_id,rc_response_status_code,rc_response_error_layer,rc_response_error_code_out,rc_response_a_result,rc_response_a_byte,rc_response_a_fe,rc_response_a_event_count,rc_response_b_result,rc_response_b_byte,rc_response_b_fe,rc_response_b_event_count,rc_response_fault_seen};
    ctrl_response_controller #(.MAX_PAYLOAD(32)) original_response_controller (
        .clk(ctrl_clk),
        .rst_n(rst_n),
        .soft_reset(1'b0),
        .packet_valid(request_take),
        .packet_type(legacy_type),
        .packet_len(legacy_len),
        .packet_payload(legacy_payload),
        .parser_error(1'b0),
        .parser_error_code(3'd0),
        .router_error(result_take && result_data_dst[15:8]==8'd1),
        .router_error_code(result_data_dst[2:0]),
        .decoder_command_error(1'b0),
        .decoder_command_error_code(4'd0),
        .config_cmd_valid(1'b0),
        .validator_config_valid(1'b0),
        .validator_error_code(3'd0),
        .apply_done(1'b0),
        .apply_status(3'd0),
        .guard_reject(result_take && result_data_dst[15:8]==8'd2),
        .guard_status(result_data_dst[2:0]),
        .start_done(result_take && result_data_dst[15:8]==8'd0),
        .start_status(result_data_dst[1:0]),
        .abort_done(1'b0),
        .abort_status(2'd0),
        .safe_result_ack(1'b0),
        .result_ready(1'b0),
        .result_trial_id(32'd0),
        .result_a_code(3'd0),
        .result_a_byte(8'd0),
        .result_a_fe(1'b0),
        .result_a_event_count(2'd0),
        .result_b_code(3'd0),
        .result_b_byte(8'd0),
        .result_b_fe(1'b0),
        .result_b_event_count(2'd0),
        .result_fault_seen(1'b0),
        .response_busy(response_busy),
        .response_accepted(response_accepted),
        .response_error(1'b0),
        .response_error_code(3'd0),
        .response_start(response_request_pulse),
        .response_kind(rc_response_kind),
        .response_original_cmd_type(rc_response_original_cmd_type),
        .response_trial_id(rc_response_trial_id),
        .response_status_code(rc_response_status_code),
        .response_error_layer(rc_response_error_layer),
        .response_error_code_out(rc_response_error_code_out),
        .response_a_result(rc_response_a_result),
        .response_a_byte(rc_response_a_byte),
        .response_a_fe(rc_response_a_fe),
        .response_a_event_count(rc_response_a_event_count),
        .response_b_result(rc_response_b_result),
        .response_b_byte(rc_response_b_byte),
        .response_b_fe(rc_response_b_fe),
        .response_b_event_count(rc_response_b_event_count),
        .response_fault_seen(rc_response_fault_seen),
        .command_response_pending(rc_command_response_pending),
        .result_response_pending(rc_result_response_pending),
        .response_queue_overflow(response_queue_overflow),
        .transport_error_seen(rc_transport_error_seen),
        .last_transport_error_code(rc_last_transport_error_code)
    );
    assign quiet_ctrl=ctrl_state==C_IDLE && !legacy_valid && !result_valid_dst && !response_request_pulse && !path_fault_ctrl;
    assign quiet_life=!life_busy && !result_valid && !req_valid_dst && !route_pulse;
endmodule
