`timescale 1ns / 1ps
// Real V1 START and outbound lifecycle events, shared control UART candidate.
module h1_ax_profile_pipeline_bram_top_v0_5 #(
    parameter integer CLK_HZ=50000000, BAUD=2000000, CAP_TIMEOUT_CLKS=500000, W19_BAUD=1000000, CTRL_CLK_HZ=100000000, CTRL_BAUD=230400,
    parameter integer CTRL_RX_BYTE_TIMEOUT_CLKS=10000000, CTRL_EVENT_ACK_TIMEOUT_CLKS=50000000
)(
    output wire [31:0] next_start_generation,
    output wire [255:0] prestart_full_identity,
    output wire [7:0] observed_current_kind,
    output wire [15:0] observed_current_len,
    input wire clk,ctrl_clk,rst_n,h1_rx_pin,ctrl_rx_pin,
    output wire ctrl_tx_pin,ctrl_tx_busy,control_backend_fault,
    output reg ctrl_uart_fault,
    output wire profile_prepared,profile_permitted,profile_fault,
    output wire [7:0] profile_fault_code,
    output wire [31:0] profile_program_count,
    output wire [255:0] held_profile_payload,profile_first_bad,
    output wire stm_cfg_ready,stm_item_eligible,
    output wire [31:0] stm_cfg_approval_count,stm_cfg_approved_record,
    output wire [255:0] stm_cfg_approved_identity,
    output wire notification_fault,
    output wire [7:0] notification_fault_code,
    output wire [2:0] notification_pending,
    output wire [31:0] notification_retries,
    output wire notification_confirmed,
    output wire [7:0] notification_confirmed_type,
    output wire [255:0] notification_confirmed_payload,
    output wire notification_capture_fault,
    output wire [7:0] notification_capture_error,notification_first_lost_type,
    output wire [255:0] notification_first_lost_payload,
    output wire owner_active,owner_event_valid,owner_commit_valid,owner_commit_ready,
    output wire [7:0] owner_event_type,owner_commit_type,owner_fault_code,
    output wire [255:0] owner_event_payload,owner_commit_payload,
    output wire h1_tx_pin,
    input wire hello_authorized,new_item_capacity,management_idle,
    input wire [7:0] expected_route,
    output wire start_request,
    output wire start_authorized,
    output wire [31:0] start_session,start_seq,
    output wire retire_request,
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
    output wire owner_fault,
    output wire injection_enable,
    output wire [8:0] injection_count,fault_points_expected,fault_points_emitted,
    output wire [15:0] injection_byte,injection_phase,injection_width,
    output wire [2:0] injection_bit,
    output wire raw_w19_tx,fault_active,fault_mark,fault_configuration_ok,actual_mark_required,
    output wire [31:0] fault_mark_count,
    output wire fault_policy_required,
    output wire [255:0] fault_snapshot_identity,
    output wire [255:0] fault_mark_identity,
    output wire actual_start_accept,
    output wire [255:0] current_window_identity,actual_start_identity,
    output wire [255:0] physical_identity,
    output wire tx_done_fenced,
    output wire owner_retire_ready,
    input wire runtime_external_fault,output wire runtime_quiescent,runtime_management_idle,runtime_raw_held,
 output wire [11:0] m_axi_awaddr,output wire m_axi_awvalid,input wire m_axi_awready,
 output wire [31:0] m_axi_wdata,output wire [3:0] m_axi_wstrb,output wire m_axi_wvalid,input wire m_axi_wready,
 input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
 output wire [11:0] m_axi_araddr,output wire m_axi_arvalid,input wire m_axi_arready,
 input wire [31:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rvalid,output wire m_axi_rready
);
    // Explicit internal declarations precede every use.
    wire [15:0] accepted_len;
    wire [7:0] commit_kind,accepted_frame_kind;
    wire ctrl_rx_busy,control_quiet_ctrl,control_quiet_life,v1_quiet_ctrl,v1_quiet_life,runtime_h1_idle;


    assign observed_current_kind=accepted_frame_kind;
    assign observed_current_len=accepted_len;
    wire owner_event_ready,control_fault_life;
    wire core_commit,owner_cfg_success;
    wire profile_event_ready,profile_commit_valid,profile_commit_ready,profile_fault_ctrl;
    wire [255:0] profile_commit_payload;
    wire [7:0] profile_commit_type;
    wire life_owner_event_ready,life_owner_commit_valid,life_owner_commit_ready;
    wire [7:0] life_owner_commit_type;
    wire [255:0] life_owner_commit_payload;
    wire is_profile=owner_event_type==8'h3a || owner_event_type==8'h3c;
    assign owner_event_ready=is_profile ? profile_event_ready : life_owner_event_ready;
    assign owner_commit_valid=profile_commit_valid || life_owner_commit_valid;
    assign owner_commit_type=profile_commit_valid ? profile_commit_type : life_owner_commit_type;
    assign owner_commit_payload=profile_commit_valid ? profile_commit_payload : life_owner_commit_payload;
    assign profile_commit_ready=owner_commit_ready && profile_commit_valid;
    assign life_owner_commit_ready=owner_commit_ready && !profile_commit_valid;


    wire capture_valid,capture_ready,capture_fault,capture_fault_ctrl;
    wire [7:0] capture_type;
    wire [255:0] capture_payload;
    wire [2:0] capture_pending;
    wire [31:0] retirement_record;
    wire cdc_valid,cdc_ready;
    wire [263:0] cdc_data;
    wire notify_tx_valid,notify_tx_take,notify_tx_done;
    wire [7:0] notify_tx_type,peer_ack_type;
    wire [255:0] notify_tx_payload,peer_ack_payload;
    wire peer_ack_valid,peer_ack_ready;
    wire [255:0] retirement_identity;
    function [31:0] byte_pack32;
        input [31:0] value;
        begin byte_pack32={value[7:0],value[15:8],value[23:16],value[31:24]};end
    endfunction
    assign notification_capture_fault=capture_fault;
    assign retirement_identity={byte_pack32(retirement_record),physical_identity[223:0]};
    wire legacy_packet_valid,legacy_packet_ready,v1_response_pulse;
    wire [7:0] legacy_packet_type,legacy_packet_len;
    wire [255:0] legacy_packet_payload;
    wire [78:0] v1_response_desc;
    wire v1_tx_accepted,v1_tx_done,v1_path_fault;
    wire [7:0] ctrl_rx_data;
    wire ctrl_rx_valid,ctrl_rx_fe;
    ctrl_uart_rx #(.CLK_HZ(CTRL_CLK_HZ),.BAUD(CTRL_BAUD)) ctrl_rx (
        .clk(ctrl_clk),.rst_n(rst_n),.uart_rx(ctrl_rx_pin),.rx_data(ctrl_rx_data),
        .rx_valid(ctrl_rx_valid),.framing_error(ctrl_rx_fe),.rx_busy(ctrl_rx_busy)
    );
    always @(posedge ctrl_clk) begin
        if(!rst_n) ctrl_uart_fault<=0;
        else if(ctrl_rx_fe) ctrl_uart_fault<=1;
    end
    xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(1)) fault_sync (
        .src_clk(ctrl_clk),.src_in(control_backend_fault || ctrl_uart_fault || v1_path_fault || notification_fault || capture_fault_ctrl || profile_fault_ctrl),
        .dest_clk(clk),.dest_out(control_fault_life)
    );
    h1_p1_control_lifecycle_mmio_v0_1 #(.CTRL_CLK_HZ(CTRL_CLK_HZ),.CTRL_BAUD(CTRL_BAUD),.TX_TIMEOUT_CLKS(2000000),
        .RX_BYTE_TIMEOUT_CLKS(CTRL_RX_BYTE_TIMEOUT_CLKS)) control_backend (
        .ctrl_clk(ctrl_clk),.life_clk(clk),.rst_n(rst_n),
        .control_byte_valid(ctrl_rx_valid && !ctrl_rx_fe && !ctrl_uart_fault),
        .control_byte_data(ctrl_rx_data),.legacy_valid(legacy_packet_valid),.legacy_type(legacy_packet_type),.legacy_len(legacy_packet_len),
        .legacy_payload(legacy_packet_payload),.legacy_ready(legacy_packet_ready),.legacy_request_pulse(v1_response_pulse),
        .legacy_request_desc(v1_response_desc),.legacy_response_accepted(v1_tx_accepted),.legacy_response_done(v1_tx_done),
        .legacy_response_busy(ctrl_tx_busy),.peer_ack_valid(peer_ack_valid),.peer_ack_type(peer_ack_type),
        .peer_ack_payload(peer_ack_payload),.peer_ack_ready(peer_ack_ready),
        .notification_valid(notify_tx_valid),.notification_type(notify_tx_type),
        .notification_payload(notify_tx_payload),.notification_take(notify_tx_take),
        .notification_done(notify_tx_done),
        .app_event_valid(owner_event_valid),.app_event_type(owner_event_type),
        .app_event_payload(owner_event_payload),.app_event_ready(owner_event_ready),
        .app_commit_valid(owner_commit_valid),.app_commit_type(owner_commit_type),
        .app_commit_payload(owner_commit_payload),.app_commit_ready(owner_commit_ready),
        .control_tx_pin(ctrl_tx_pin),.fault(control_backend_fault),.app_fault(),
        .control_bridge_fault(),.parser_error(),.parser_error_code(),
        .router_error(),.owner_error(),.tx_error(),.quiet_ctrl(control_quiet_ctrl),.quiet_life(control_quiet_life),
 .m_axi_awaddr(m_axi_awaddr),
 .m_axi_awvalid(m_axi_awvalid),
 .m_axi_awready(m_axi_awready),
 .m_axi_wdata(m_axi_wdata),
 .m_axi_wstrb(m_axi_wstrb),
 .m_axi_wvalid(m_axi_wvalid),
 .m_axi_wready(m_axi_wready),
 .m_axi_bresp(m_axi_bresp),
 .m_axi_bvalid(m_axi_bvalid),
 .m_axi_bready(m_axi_bready),
 .m_axi_araddr(m_axi_araddr),
 .m_axi_arvalid(m_axi_arvalid),
 .m_axi_arready(m_axi_arready),
 .m_axi_rdata(m_axi_rdata),
 .m_axi_rresp(m_axi_rresp),
 .m_axi_rvalid(m_axi_rvalid),
 .m_axi_rready(m_axi_rready)
    );
    h1_p1_v1_start_path_runtime_v0_1 v1_start_path (
        .ctrl_clk(ctrl_clk),.life_clk(clk),.rst_n(rst_n),
        .legacy_valid(legacy_packet_valid),.legacy_type(legacy_packet_type),
        .legacy_len(legacy_packet_len),.legacy_payload(legacy_packet_payload),
        .legacy_ready(legacy_packet_ready),.response_busy(ctrl_tx_busy),
        .response_accepted(v1_tx_accepted),.response_done(v1_tx_done),
        .response_request_pulse(v1_response_pulse),.response_desc(v1_response_desc),
        .current_valid(current_valid),.current_window_identity(current_window_identity),
        .core_start_accept(actual_start_accept),.ctrl_fault(control_backend_fault || ctrl_uart_fault),
        .life_fault(link_fault),.core_start_request(start_request),
        .core_start_session(start_session),.core_start_seq(start_seq),.path_fault_ctrl(v1_path_fault),.quiet_ctrl(v1_quiet_ctrl),.quiet_life(v1_quiet_life)
    );

    h1_p1_ax_event_owner_offer_v0_2 owner (
        .clk(clk),.rst_n(rst_n),.current_valid(current_valid),
        .current_kind(accepted_frame_kind),.cfg_success_seen(owner_cfg_success),
        .current_window_identity(current_window_identity),
        .actual_start(actual_start_accept),.start_offer(start_request),.actual_identity(actual_start_identity),
        .actual_mark_required(actual_mark_required),.physical_done(w19_physical_done),
        .physical_mark(fault_mark),.physical_identity(physical_identity),
        .tx_done_fenced(tx_done_fenced),.core_retire_ready(owner_retire_ready && capture_pending<4 && !capture_fault),
        .core_retired(retired),.external_fault(link_fault || control_fault_life),
        .event_valid(owner_event_valid && !is_profile),.event_type(owner_event_type),
        .event_payload(owner_event_payload),.event_ready(life_owner_event_ready),
        .commit_valid(life_owner_commit_valid),.commit_type(life_owner_commit_type),
        .commit_payload(life_owner_commit_payload),.commit_ready(life_owner_commit_ready),
        .start_authorized(start_authorized),.retire_request(retire_request),
        .window_armed(),.active(owner_active),.done_seen(),.mark_seen(),
        .terminal_seen(),.stored_seen(),.mark_stored(),.active_identity(),
        .ch1_record(retirement_record),.mark_record(),.fault(owner_fault),.fault_code(owner_fault_code)
    );
    h1_w19_profile_owner_core_bram_v0_5 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),
        .CAP_TIMEOUT_CLKS(CAP_TIMEOUT_CLKS),.W19_BAUD(W19_BAUD)) core (
        .clk(clk),
        .rst_n(rst_n),
        .next_start_generation(next_start_generation),
        .prestart_full_identity(prestart_full_identity),
        .h1_rx_pin(h1_rx_pin),
        .h1_tx_pin(h1_tx_pin),
        .hello_authorized(hello_authorized),
        .new_item_capacity(new_item_capacity),
        .management_idle(management_idle),
        .expected_route(expected_route),
        .start_request(start_request),
        .start_authorized(start_authorized && capture_pending<=(actual_mark_required ? 1 : 2) && !capture_fault),
        .start_session(start_session),
        .start_seq(start_seq),
        .retire_request(retire_request),
        .retire_authorized(1'b1),
        .retire_session(active_session),
        .retire_seq(current_seq),
        .current_read_addr(current_read_addr),
        .current_read_data(current_read_data),
        .start_pulse(start_pulse),
        .start_rejected(start_rejected),
        .retired(retired),
        .slot_busy(slot_busy),
        .current_valid(current_valid),
        .current_started(current_started),
        .current_done(current_done),
        .active_session(active_session),
        .current_seq(current_seq),
        .commit_count(commit_count),
        .start_count(start_count),
        .validation_count(validation_count),
        .cfg_valid(cfg_valid),
        .cfg_chunk(cfg_chunk),
        .link_fault(link_fault),
        .evidence_ack(evidence_ack),
        .evidence_ack_session(evidence_ack_session),
        .evidence_ack_seq(evidence_ack_seq),
        .evidence_ack_ticket(evidence_ack_ticket),
        .evidence_read_addr(evidence_read_addr),
        .evidence_read_data(evidence_read_data),
        .evidence_kind(evidence_kind),
        .evidence_read_valid(evidence_read_valid),
        .evidence_ready(evidence_ready),
        .evidence_session(evidence_session),
        .evidence_seq(evidence_seq),
        .evidence_ticket(evidence_ticket),
        .evidence_len(evidence_len),
        .control_fault(control_fault),
        .control_error(control_error),
        .w19_tx(w19_tx),
        .w19_busy(w19_busy),
        .w19_physical_start(w19_physical_start),
        .w19_physical_done(w19_physical_done),
        .w19_fault(w19_fault),
        .w19_start_count(w19_start_count),
        .w19_done_count(w19_done_count),
        .route_epoch(route_epoch),
        .external_owner_fault(owner_fault || control_fault_life || profile_fault || runtime_external_fault),
        .stm_item_eligible(stm_item_eligible && profile_permitted),.current_commit(core_commit),
        .current_commit_kind(commit_kind),.accepted_frame_len(accepted_len),.accepted_frame_kind(accepted_frame_kind),
        .injection_enable(injection_enable),.injection_count(injection_count),.fault_points_expected(fault_points_expected),.fault_points_emitted(fault_points_emitted),.injection_byte(injection_byte),
        .injection_phase(injection_phase),.injection_width(injection_width),.injection_bit(injection_bit),
        .raw_w19_tx(raw_w19_tx),.fault_active(fault_active),.fault_mark(fault_mark),
        .fault_configuration_ok(fault_configuration_ok),.actual_mark_required(actual_mark_required),
        .fault_mark_count(fault_mark_count),.fault_policy_required(fault_policy_required),
        .fault_snapshot_identity(fault_snapshot_identity),.fault_mark_identity(fault_mark_identity),
        .actual_start_accept(actual_start_accept),
        .current_window_identity(current_window_identity),
        .actual_start_identity(actual_start_identity),
        .physical_identity(physical_identity),
        .tx_done_fenced(tx_done_fenced),
        .owner_retire_ready(owner_retire_ready),.runtime_h1_idle(runtime_h1_idle),.runtime_raw_held(runtime_raw_held)
    );
    h1_p1_notification_capture_v0_1 notification_capture (
        .clk(clk),.rst_n(rst_n),.external_fault(link_fault || control_fault_life),
        .actual_start(actual_start_accept),.physical_done(w19_physical_done),
        .physical_mark(fault_mark),.actual_retired(retired),
        .start_identity(actual_start_identity),.physical_identity(physical_identity),
        .retired_identity(retirement_identity),.event_valid(capture_valid),
        .event_type(capture_type),.event_payload(capture_payload),.event_ready(capture_ready),
        .pending_count(capture_pending),.fault(capture_fault),.fault_code(notification_capture_error),
        .first_lost_type(notification_first_lost_type),.first_lost_payload(notification_first_lost_payload)
    );
    h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(264)) notifications (
        .src_clk(clk),.dst_clk(ctrl_clk),.rst_n(rst_n),.src_valid(capture_valid),
        .src_data({capture_type,capture_payload}),.src_ready(capture_ready),
        .dst_valid(cdc_valid),.dst_data(cdc_data),.dst_ready(cdc_ready)
    );
    xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) capture_fault_sync (
        .src_clk(clk),.src_in(capture_fault),.dest_clk(ctrl_clk),.dest_out(capture_fault_ctrl)
    );
    h1_p1_event_reliable_tx_v0_2 #(
        .ACK_TIMEOUT_CLKS(CTRL_EVENT_ACK_TIMEOUT_CLKS)
    ) notification_transport (
        .clk(ctrl_clk),.rst_n(rst_n),
        .external_fault(control_backend_fault || ctrl_uart_fault || capture_fault_ctrl || profile_fault_ctrl),
        .event_valid(cdc_valid),.event_type(cdc_data[263:256]),.event_payload(cdc_data[255:0]),
        .event_ready(cdc_ready),.tx_valid(notify_tx_valid),.tx_type(notify_tx_type),
        .tx_payload(notify_tx_payload),.tx_take(notify_tx_take),.tx_done(notify_tx_done),
        .ack_valid(peer_ack_valid),.ack_type(peer_ack_type),.ack_payload(peer_ack_payload),
        .ack_ready(peer_ack_ready),.confirmed(notification_confirmed),
        .confirmed_type(notification_confirmed_type),.confirmed_payload(notification_confirmed_payload),
        .fault(notification_fault),.fault_code(notification_fault_code),
        .pending_count(notification_pending),.retry_count(notification_retries)
    );
    h1_stm_cfg_qualification_v0_1 qualification (
        .clk(clk),.rst_n(rst_n),.external_fault(link_fault || control_fault_life),
        .new_commit(core_commit),.commit_kind(commit_kind),.current_kind(accepted_frame_kind),
        .active_session(active_session),.route_epoch(route_epoch),
        .current_identity(current_window_identity),.physical_identity(physical_identity),
        .actual_retired(retired),.cfg_success_seen(owner_cfg_success),.ch1_record(retirement_record),
        .ready(stm_cfg_ready),.item_eligible(stm_item_eligible),
        .approved_identity(stm_cfg_approved_identity),.approved_record(stm_cfg_approved_record),
        .approval_count(stm_cfg_approval_count)
    );
    h1_item_profile_owner_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(W19_BAUD)) profile_owner (
        .clk(clk),.rst_n(rst_n),.external_fault(link_fault || control_fault_life),
        .current_valid(current_valid),.current_started(current_started),.new_commit(core_commit),
        .actual_start(actual_start_accept),.actual_retired(retired),.current_kind(accepted_frame_kind),
        .current_len(accepted_len),.current_identity(current_window_identity),
        .event_valid(owner_event_valid && is_profile),.event_type(owner_event_type),.event_payload(owner_event_payload),
        .event_ready(profile_event_ready),.commit_valid(profile_commit_valid),.commit_type(profile_commit_type),.held_profile_type(),.injection_count(injection_count),
        .commit_payload(profile_commit_payload),.commit_ready(profile_commit_ready),
        .prepared(profile_prepared),.permitted(profile_permitted),
        .injection_enable(injection_enable),.injection_byte(injection_byte),.injection_phase(injection_phase),
        .injection_width(injection_width),.injection_bit(injection_bit),.held_profile_payload(held_profile_payload),
        .program_count(profile_program_count),.fault(profile_fault),.fault_code(profile_fault_code),
        .first_bad_payload(profile_first_bad)
    );
    xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) profile_fault_sync (
        .src_clk(clk),.src_in(profile_fault),.dest_clk(ctrl_clk),.dest_out(profile_fault_ctrl)
    );

    wire control_quiet_life_sync;
    xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(1)) runtime_quiet_sync (
        .src_clk(ctrl_clk),.src_in(control_quiet_ctrl && v1_quiet_ctrl && !ctrl_rx_busy && !ctrl_rx_valid && !ctrl_rx_fe && notification_pending==0),
        .dest_clk(clk),.dest_out(control_quiet_life_sync)
    );
    assign runtime_quiescent=runtime_h1_idle && control_quiet_life_sync && control_quiet_life && v1_quiet_life &&
        !slot_busy && !owner_active && !w19_busy && !owner_event_valid && !owner_commit_valid &&
        capture_pending==0 && capture_ready && !link_fault && !profile_fault && !control_fault_life;
    // CONFIG validation is itself ingress-active. Its management-idle gate
    // describes physical lifecycle resources, not the ARM-only all-parser idle.
    assign runtime_management_idle=!slot_busy && !owner_active && !w19_busy && capture_pending==0 &&
        !owner_event_valid && !owner_commit_valid && !profile_fault && !link_fault && !control_fault_life;
endmodule
