`timescale 1ns/1ps
// Eight-pin pure-PL physical candidate. MMIO and evidence remain internal.
// No ARM/PS software, DDR/MIO or persistence bypass is introduced.
module h1_ax7010_uart_cdc_sync_board_top_v0_7(
    input wire pl_clk_50m,key_n,h1_rx_pin,ctrl_rx_pin,
    output wire h1_tx_pin,ctrl_tx_pin,w19_tx,fault_mark
);
    wire [255:0] prestart_full_identity;
    wire [15:0] observed_len;

    // Explicit internal declarations precede every use.
    wire core_runtime_quiet,core_management_idle,core_raw_held,diag_enable,diag_address_ready;
    wire [9:0] diag_addr;
    wire [31:0] next_start_generation;
    wire [7:0] observed_kind;
    wire [11:0] l_axi_awaddr;
    wire  l_axi_awvalid;
    wire  l_axi_awready;
    wire [31:0] l_axi_wdata;
    wire [3:0] l_axi_wstrb;
    wire  l_axi_wvalid;
    wire  l_axi_wready;
    wire [1:0] l_axi_bresp;
    wire  l_axi_bvalid;
    wire  l_axi_bready;
    wire [11:0] l_axi_araddr;
    wire  l_axi_arvalid;
    wire  l_axi_arready;
    wire [31:0] l_axi_rdata;
    wire [1:0] l_axi_rresp;
    wire  l_axi_rvalid;
    wire  l_axi_rready;

    localparam integer CLK_HZ=50000000,BAUD=2000000,CAP_TIMEOUT_CLKS=500000,
        W19_BAUD=1000000,CTRL_CLK_HZ=100000000,CTRL_BAUD=230400;
    wire clock_locked;
    wire reset_released;
    wire ctrl_tx_busy;
    wire control_backend_fault;
    wire ctrl_uart_fault;
    wire profile_prepared;
    wire profile_permitted;
    wire profile_fault;
    wire [7:0] profile_fault_code;
    wire [31:0] profile_program_count;
    wire [255:0] held_profile_payload;
    wire [255:0] profile_first_bad;
    wire stm_cfg_ready;
    wire stm_item_eligible;
    wire [31:0] stm_cfg_approval_count;
    wire [31:0] stm_cfg_approved_record;
    wire [255:0] stm_cfg_approved_identity;
    wire notification_fault;
    wire [7:0] notification_fault_code;
    wire [2:0] notification_pending;
    wire [31:0] notification_retries;
    wire notification_confirmed;
    wire [7:0] notification_confirmed_type;
    wire [255:0] notification_confirmed_payload;
    wire notification_capture_fault;
    wire [7:0] notification_capture_error;
    wire [7:0] notification_first_lost_type;
    wire [255:0] notification_first_lost_payload;
    wire owner_active;
    wire owner_event_valid;
    wire owner_commit_valid;
    wire owner_commit_ready;
    wire [7:0] owner_event_type;
    wire [7:0] owner_commit_type;
    wire [7:0] owner_fault_code;
    wire [255:0] owner_event_payload;
    wire [255:0] owner_commit_payload;
    wire hello_authorized;
    wire new_item_capacity;
    wire management_idle;
    wire [7:0] expected_route;
    wire start_request;
    wire start_authorized;
    wire [31:0] start_session;
    wire [31:0] start_seq;
    wire retire_request;
    wire [9:0] current_read_addr=10'd0;
    wire [7:0] current_read_data;
    wire start_pulse;
    wire start_rejected;
    wire retired;
    wire slot_busy;
    wire current_valid;
    wire current_started;
    wire current_done;
    wire [31:0] active_session;
    wire [31:0] current_seq;
    wire [31:0] commit_count;
    wire [31:0] start_count;
    wire [31:0] validation_count;
    wire cfg_valid;
    wire [15:0] cfg_chunk;
    wire link_fault;
    wire evidence_ack;
    wire [31:0] evidence_ack_session;
    wire [31:0] evidence_ack_seq;
    wire [31:0] evidence_ack_ticket;
    wire [9:0] evidence_read_addr;
    wire [7:0] evidence_read_data;
    wire [7:0] evidence_kind;
    wire evidence_read_valid;
    wire evidence_ready;
    wire [31:0] evidence_session;
    wire [31:0] evidence_seq;
    wire [31:0] evidence_ticket;
    wire [15:0] evidence_len;
    wire control_fault;
    wire [7:0] control_error;
    wire w19_busy;
    wire w19_physical_start;
    wire w19_physical_done;
    wire w19_fault;
    wire [31:0] w19_start_count;
    wire [31:0] w19_done_count;
    wire [31:0] route_epoch;
    wire owner_fault;
    wire injection_enable;
    wire [8:0] injection_count,fault_points_expected,fault_points_emitted;
    wire [15:0] injection_byte;
    wire [15:0] injection_phase;
    wire [15:0] injection_width;
    wire [2:0] injection_bit;
    wire raw_w19_tx;
    wire fault_active;
    wire fault_configuration_ok;
    wire actual_mark_required;
    wire [31:0] fault_mark_count;
    wire fault_policy_required;
    wire [255:0] fault_snapshot_identity;
    wire [255:0] fault_mark_identity;
    wire actual_start_accept;
    wire [255:0] current_window_identity;
    wire [255:0] actual_start_identity;
    wire [255:0] physical_identity;
    wire tx_done_fenced;
    wire owner_retire_ready;
    wire raw_external_fault=1'b0;
    wire raw_record_valid;
    wire raw_record_ready;
    wire [7:0] raw_record_kind;
    wire [31:0] raw_record_epoch;
    wire [31:0] raw_record_session;
    wire [31:0] raw_record_seq;
    wire [31:0] raw_record_ticket;
    wire [15:0] raw_record_len;
    wire raw_byte_valid;
    wire raw_byte_ready;
    wire [9:0] raw_byte_index;
    wire [7:0] raw_byte_data;
    wire raw_byte_last;
    wire raw_finish_valid;
    wire raw_finish_ready;
    wire [15:0] raw_crc;
    wire raw_store_valid;
    wire [7:0] raw_store_kind;
    wire [31:0] raw_store_epoch;
    wire [31:0] raw_store_session;
    wire [31:0] raw_store_seq;
    wire [31:0] raw_store_ticket;
    wire [31:0] raw_store_record_id;
    wire [15:0] raw_store_len;
    wire [15:0] raw_store_crc;
    wire raw_store_ready;
    wire raw_ack_issued;
    wire [31:0] raw_saved_record_id;
    wire raw_owner_fault;
    wire [7:0] raw_owner_fault_code;
    wire [11:0] s_axi_awaddr;
    wire s_axi_awvalid;
    wire s_axi_awready;
    wire [31:0] s_axi_wdata;
    wire [3:0] s_axi_wstrb;
    wire s_axi_wvalid;
    wire s_axi_wready;
    wire [1:0] s_axi_bresp;
    wire s_axi_bvalid;
    wire s_axi_bready;
    wire [11:0] s_axi_araddr;
    wire s_axi_arvalid;
    wire s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0] s_axi_rresp;
    wire s_axi_rvalid;
    wire s_axi_rready;
    wire runtime_quiescent;
    wire runtime_backend_fault;
    wire [7:0] runtime_backend_fault_code;
    wire [31:0] runtime_authorized_session;

    wire feedback_unbuf,feedback_buf,ctrl_unbuf,life_unbuf,ctrl_clk,life_clk;
    wire core_h1_tx,core_ctrl_tx,core_w19_tx,core_mark;
    MMCME2_BASE #(.CLKIN1_PERIOD(20.0),.DIVCLK_DIVIDE(1),.CLKFBOUT_MULT_F(20.0),
        .CLKOUT0_DIVIDE_F(10.0),.CLKOUT1_DIVIDE(20),.STARTUP_WAIT("FALSE")) u_mmcm (
        .CLKIN1(pl_clk_50m),.CLKFBIN(feedback_buf),.CLKFBOUT(feedback_unbuf),.CLKFBOUTB(),
        .CLKOUT0(ctrl_unbuf),.CLKOUT0B(),.CLKOUT1(life_unbuf),.CLKOUT1B(),
        .CLKOUT2(),.CLKOUT2B(),.CLKOUT3(),.CLKOUT3B(),.CLKOUT4(),.CLKOUT5(),.CLKOUT6(),
        .LOCKED(clock_locked),.PWRDWN(1'b0),.RST(!key_n)
    );
    BUFG u_feedback_buf (.I(feedback_unbuf),.O(feedback_buf));
    BUFG u_ctrl_buf (.I(ctrl_unbuf),.O(ctrl_clk));
    BUFG u_life_buf (.I(life_unbuf),.O(life_clk));
    wire core_reset_n;
    h1_board_reset_handoff_v0_2 reset_handoff (
        .life_clk(life_clk),.ctrl_clk(ctrl_clk),.key_n(key_n),
        .clock_locked(clock_locked),.core_reset_n(core_reset_n),.io_ready(reset_released)
    );
    // reset_released qualifies ALL logical sidebands as well as physical pins.
    // It may fall asynchronously. Only core_reset_n drives the core/RAM reset.
    assign h1_tx_pin=reset_released ? core_h1_tx : 1'b1;
    assign ctrl_tx_pin=reset_released ? core_ctrl_tx : 1'b1;
    assign w19_tx=reset_released ? core_w19_tx : 1'b1;
    assign fault_mark=reset_released && core_mark;
    h1_ax_profile_pipeline_bram_top_v0_5 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),.CAP_TIMEOUT_CLKS(CAP_TIMEOUT_CLKS),
        .W19_BAUD(W19_BAUD),.CTRL_CLK_HZ(CTRL_CLK_HZ),.CTRL_BAUD(CTRL_BAUD)) image (
        .next_start_generation(next_start_generation),.prestart_full_identity(prestart_full_identity),
        .observed_current_kind(observed_kind),.observed_current_len(observed_len),
        .clk(life_clk),
        .ctrl_clk(ctrl_clk),
        .rst_n(core_reset_n),
        .h1_rx_pin(reset_released ? h1_rx_pin : 1'b1),
        .ctrl_rx_pin(reset_released ? ctrl_rx_pin : 1'b1),
        .ctrl_tx_pin(core_ctrl_tx),
        .ctrl_tx_busy(ctrl_tx_busy),
        .control_backend_fault(control_backend_fault),
        .ctrl_uart_fault(ctrl_uart_fault),
        .profile_prepared(profile_prepared),
        .profile_permitted(profile_permitted),
        .profile_fault(profile_fault),
        .profile_fault_code(profile_fault_code),
        .profile_program_count(profile_program_count),
        .held_profile_payload(held_profile_payload),
        .profile_first_bad(profile_first_bad),
        .stm_cfg_ready(stm_cfg_ready),
        .stm_item_eligible(stm_item_eligible),
        .stm_cfg_approval_count(stm_cfg_approval_count),
        .stm_cfg_approved_record(stm_cfg_approved_record),
        .stm_cfg_approved_identity(stm_cfg_approved_identity),
        .notification_fault(notification_fault),
        .notification_fault_code(notification_fault_code),
        .notification_pending(notification_pending),
        .notification_retries(notification_retries),
        .notification_confirmed(notification_confirmed),
        .notification_confirmed_type(notification_confirmed_type),
        .notification_confirmed_payload(notification_confirmed_payload),
        .notification_capture_fault(notification_capture_fault),
        .notification_capture_error(notification_capture_error),
        .notification_first_lost_type(notification_first_lost_type),
        .notification_first_lost_payload(notification_first_lost_payload),
        .owner_active(owner_active),
        .owner_event_valid(owner_event_valid),
        .owner_commit_valid(owner_commit_valid),
        .owner_commit_ready(owner_commit_ready),
        .owner_event_type(owner_event_type),
        .owner_commit_type(owner_commit_type),
        .owner_fault_code(owner_fault_code),
        .owner_event_payload(owner_event_payload),
        .owner_commit_payload(owner_commit_payload),
        .h1_tx_pin(core_h1_tx),
        .hello_authorized(hello_authorized && reset_released),
        .new_item_capacity(new_item_capacity && reset_released),
        .management_idle(management_idle && reset_released),
        .expected_route(expected_route),
        .start_request(start_request),
        .start_authorized(start_authorized),
        .start_session(start_session),
        .start_seq(start_seq),
        .retire_request(retire_request),
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
        .evidence_ack(evidence_ack && reset_released),
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
        .w19_tx(core_w19_tx),
        .w19_busy(w19_busy),
        .w19_physical_start(w19_physical_start),
        .w19_physical_done(w19_physical_done),
        .w19_fault(w19_fault),
        .w19_start_count(w19_start_count),
        .w19_done_count(w19_done_count),
        .route_epoch(route_epoch),
        .owner_fault(owner_fault),
        .injection_enable(injection_enable),.injection_count(injection_count),.fault_points_expected(fault_points_expected),.fault_points_emitted(fault_points_emitted),
        .injection_byte(injection_byte),
        .injection_phase(injection_phase),
        .injection_width(injection_width),
        .injection_bit(injection_bit),
        .raw_w19_tx(raw_w19_tx),
        .fault_active(fault_active),
        .fault_mark(core_mark),
        .fault_configuration_ok(fault_configuration_ok),
        .actual_mark_required(actual_mark_required),
        .fault_mark_count(fault_mark_count),
        .fault_policy_required(fault_policy_required),
        .fault_snapshot_identity(fault_snapshot_identity),
        .fault_mark_identity(fault_mark_identity),
        .actual_start_accept(actual_start_accept),
        .current_window_identity(current_window_identity),
        .actual_start_identity(actual_start_identity),
        .physical_identity(physical_identity),
        .tx_done_fenced(tx_done_fenced),
        .owner_retire_ready(owner_retire_ready),.runtime_external_fault(runtime_backend_fault || raw_owner_fault || raw_external_fault),.runtime_quiescent(core_runtime_quiet),.runtime_management_idle(core_management_idle),.runtime_raw_held(core_raw_held),
        .m_axi_awaddr(s_axi_awaddr),
        .m_axi_awvalid(s_axi_awvalid),
        .m_axi_awready(s_axi_awready),
        .m_axi_wdata(s_axi_wdata),
        .m_axi_wstrb(s_axi_wstrb),
        .m_axi_wvalid(s_axi_wvalid),
        .m_axi_wready(s_axi_wready),
        .m_axi_bresp(s_axi_bresp),
        .m_axi_bvalid(s_axi_bvalid),
        .m_axi_bready(s_axi_bready),
        .m_axi_araddr(s_axi_araddr),
        .m_axi_arvalid(s_axi_arvalid),
        .m_axi_arready(s_axi_arready),
        .m_axi_rdata(s_axi_rdata),
        .m_axi_rresp(s_axi_rresp),
        .m_axi_rvalid(s_axi_rvalid),
        .m_axi_rready(s_axi_rready)
    );
    // Only this owner drives the real ingress RAM read/ACK channel.
    wire owner_header_valid,owner_byte_valid,owner_finish_valid,owner_store_ready;
    assign raw_record_valid=owner_header_valid && reset_released;
    assign raw_byte_valid=owner_byte_valid && reset_released;
    assign raw_finish_valid=owner_finish_valid && reset_released;
    assign raw_store_ready=owner_store_ready && reset_released;
    h1_raw_evidence_owner_diag_v0_2 raw_owner (
        .clk(life_clk),.rst_n(core_reset_n),.external_fault(raw_external_fault || control_fault || runtime_backend_fault),
        .route_epoch(route_epoch),.evidence_ready(evidence_ready && reset_released),
        .evidence_read_valid(evidence_read_valid),.evidence_kind(evidence_kind),.evidence_read_data(evidence_read_data),
        .evidence_session(evidence_session),.evidence_seq(evidence_seq),.evidence_ticket(evidence_ticket),
        .evidence_len(evidence_len),.evidence_read_addr(evidence_read_addr),
        .record_valid(owner_header_valid),.record_ready(raw_record_ready && reset_released),.record_kind(raw_record_kind),
        .record_epoch(raw_record_epoch),.record_session(raw_record_session),.record_seq(raw_record_seq),
        .record_ticket(raw_record_ticket),.record_len(raw_record_len),
        .byte_valid(owner_byte_valid),.byte_ready(raw_byte_ready && reset_released),.byte_index(raw_byte_index),
        .byte_data(raw_byte_data),.byte_last(raw_byte_last),
        .finish_valid(owner_finish_valid),.finish_ready(raw_finish_ready && reset_released),.raw_crc(raw_crc),
        .store_valid(raw_store_valid && reset_released),.store_kind(raw_store_kind),.store_epoch(raw_store_epoch),
        .store_session(raw_store_session),.store_seq(raw_store_seq),.store_ticket(raw_store_ticket),
        .store_record_id(raw_store_record_id),.store_len(raw_store_len),.store_raw_crc(raw_store_crc),
        .store_ready(owner_store_ready),.evidence_ack(evidence_ack),
        .ack_session(evidence_ack_session),.ack_seq(evidence_ack_seq),.ack_ticket(evidence_ack_ticket),
        .ack_issued(raw_ack_issued),.saved_record_id(raw_saved_record_id),
        .fault(raw_owner_fault),.fault_code(raw_owner_fault_code),.diagnostic_enable(diag_enable),.diagnostic_addr(diag_addr),.diagnostic_address_ready(diag_address_ready)
    );


    wire axi_authorized,axi_capacity,axi_management_idle;
    assign runtime_quiescent=reset_released && core_runtime_quiet;
    assign hello_authorized=axi_authorized && reset_released && evidence_session==runtime_authorized_session;
    assign new_item_capacity=axi_capacity && reset_released && evidence_session==runtime_authorized_session && !link_fault;
    assign management_idle=axi_authorized && axi_capacity && reset_released && core_management_idle;
    h1_runtime_evidence_axi_diag_v0_2 #(.CLOCK_HZ(CLK_HZ)) runtime_backend (
        .s_axi_aclk(life_clk),.s_axi_aresetn(core_reset_n),
        .s_axi_awaddr(l_axi_awaddr),.s_axi_awvalid(l_axi_awvalid),.s_axi_awready(l_axi_awready),
        .s_axi_wdata(l_axi_wdata),.s_axi_wstrb(l_axi_wstrb),.s_axi_wvalid(l_axi_wvalid),.s_axi_wready(l_axi_wready),
        .s_axi_bresp(l_axi_bresp),.s_axi_bvalid(l_axi_bvalid),.s_axi_bready(l_axi_bready),
        .s_axi_araddr(l_axi_araddr),.s_axi_arvalid(l_axi_arvalid),.s_axi_arready(l_axi_arready),
        .s_axi_rdata(l_axi_rdata),.s_axi_rresp(l_axi_rresp),.s_axi_rvalid(l_axi_rvalid),.s_axi_rready(l_axi_rready),
        .core_quiescent(runtime_quiescent),.core_fault(control_fault || raw_owner_fault),.external_fault(raw_external_fault),
        .hello_authorized(axi_authorized),.new_item_capacity(axi_capacity),.management_idle(axi_management_idle),
        .active_epoch(route_epoch),.authorized_session(runtime_authorized_session),.expected_route(expected_route),
        .record_valid(raw_record_valid),.record_ready(raw_record_ready),.record_kind(raw_record_kind),
        .record_epoch(raw_record_epoch),.record_session(raw_record_session),.record_seq(raw_record_seq),
        .record_ticket(raw_record_ticket),.record_len(raw_record_len),
        .byte_valid(raw_byte_valid),.byte_ready(raw_byte_ready),.byte_index(raw_byte_index),.byte_data(raw_byte_data),.byte_last(raw_byte_last),
        .finish_valid(raw_finish_valid),.finish_ready(raw_finish_ready),.finish_raw_crc(raw_crc),
        .store_valid(raw_store_valid),.store_ready(raw_store_ready),.store_kind(raw_store_kind),
        .store_epoch(raw_store_epoch),.store_session(raw_store_session),.store_seq(raw_store_seq),.store_ticket(raw_store_ticket),
        .store_record_id(raw_store_record_id),.store_len(raw_store_len),.store_raw_crc(raw_store_crc),
        .fault(runtime_backend_fault),.fault_code(runtime_backend_fault_code),
        .diag_available(reset_released && core_raw_held && (raw_owner_fault || control_fault || runtime_backend_fault)),
        .diag_kind(evidence_kind),.diag_epoch(route_epoch),.diag_session(evidence_session),.diag_seq(evidence_seq),
        .diag_ticket(evidence_ticket),.diag_len(evidence_len),.diag_read_valid(evidence_read_valid),.diag_read_data(evidence_read_data),
        .diag_enable(diag_enable),.diag_addr(diag_addr),.diag_address_ready(diag_address_ready)
    );


    wire [11:0] o_axi_awaddr;
    wire  o_axi_awvalid;
    wire  o_axi_awready;
    wire [31:0] o_axi_wdata;
    wire [3:0] o_axi_wstrb;
    wire  o_axi_wvalid;
    wire  o_axi_wready;
    wire [1:0] o_axi_bresp;
    wire  o_axi_bvalid;
    wire  o_axi_bready;
    wire [11:0] o_axi_araddr;
    wire  o_axi_arvalid;
    wire  o_axi_arready;
    wire [31:0] o_axi_rdata;
    wire [1:0] o_axi_rresp;
    wire  o_axi_rvalid;
    wire  o_axi_rready;


















h1_7010_prestart_axi_route_v0_1 route(
.clk(life_clk),
.rst_n(core_reset_n),
.s_axi_awaddr(s_axi_awaddr),
.s_axi_awvalid(s_axi_awvalid),
.s_axi_awready(s_axi_awready),
.s_axi_wdata(s_axi_wdata),
.s_axi_wstrb(s_axi_wstrb),
.s_axi_wvalid(s_axi_wvalid),
.s_axi_wready(s_axi_wready),
.s_axi_bresp(s_axi_bresp),
.s_axi_bvalid(s_axi_bvalid),
.s_axi_bready(s_axi_bready),
.s_axi_araddr(s_axi_araddr),
.s_axi_arvalid(s_axi_arvalid),
.s_axi_arready(s_axi_arready),
.s_axi_rdata(s_axi_rdata),
.s_axi_rresp(s_axi_rresp),
.s_axi_rvalid(s_axi_rvalid),
.s_axi_rready(s_axi_rready),
.legacy_awaddr(l_axi_awaddr),
.legacy_awvalid(l_axi_awvalid),
.legacy_awready(l_axi_awready),
.legacy_wdata(l_axi_wdata),
.legacy_wstrb(l_axi_wstrb),
.legacy_wvalid(l_axi_wvalid),
.legacy_wready(l_axi_wready),
.legacy_bresp(l_axi_bresp),
.legacy_bvalid(l_axi_bvalid),
.legacy_bready(l_axi_bready),
.legacy_araddr(l_axi_araddr),
.legacy_arvalid(l_axi_arvalid),
.legacy_arready(l_axi_arready),
.legacy_rdata(l_axi_rdata),
.legacy_rresp(l_axi_rresp),
.legacy_rvalid(l_axi_rvalid),
.legacy_rready(l_axi_rready),
.observer_awaddr(o_axi_awaddr),
.observer_awvalid(o_axi_awvalid),
.observer_awready(o_axi_awready),
.observer_wdata(o_axi_wdata),
.observer_wstrb(o_axi_wstrb),
.observer_wvalid(o_axi_wvalid),
.observer_wready(o_axi_wready),
.observer_bresp(o_axi_bresp),
.observer_bvalid(o_axi_bvalid),
.observer_bready(o_axi_bready),
.observer_araddr(o_axi_araddr),
.observer_arvalid(o_axi_arvalid),
.observer_arready(o_axi_arready),
.observer_rdata(o_axi_rdata),
.observer_rresp(o_axi_rresp),
.observer_rvalid(o_axi_rvalid),
.observer_rready(o_axi_rready));
h1_7010_prestart_observer_axi_v0_1 observer(
.clk(life_clk),
.rst_n(core_reset_n),
.authorized(axi_authorized && reset_released),
.source_fault(link_fault || control_fault || runtime_backend_fault || raw_owner_fault || owner_fault || profile_fault),
.source_idle(image.runtime_h1_idle && !w19_busy),
.current_valid(current_valid),
.current_started(current_started),
.slot_busy(slot_busy),
.runtime_epoch(route_epoch),
.runtime_session(runtime_authorized_session),
.next_start_generation(next_start_generation),
.prestart_full_identity(prestart_full_identity),
.current_kind(observed_kind),
.current_len(observed_len),
.mp_expected(fault_points_expected),.mp_emitted(fault_points_emitted),
.mp_identity(physical_identity),.mp_done(tx_done_fenced),
.s_axi_awaddr(o_axi_awaddr),
.s_axi_awvalid(o_axi_awvalid),
.s_axi_awready(o_axi_awready),
.s_axi_wdata(o_axi_wdata),
.s_axi_wstrb(o_axi_wstrb),
.s_axi_wvalid(o_axi_wvalid),
.s_axi_wready(o_axi_wready),
.s_axi_bresp(o_axi_bresp),
.s_axi_bvalid(o_axi_bvalid),
.s_axi_bready(o_axi_bready),
.s_axi_araddr(o_axi_araddr),
.s_axi_arvalid(o_axi_arvalid),
.s_axi_arready(o_axi_arready),
.s_axi_rdata(o_axi_rdata),
.s_axi_rresp(o_axi_rresp),
.s_axi_rvalid(o_axi_rvalid),
.s_axi_rready(o_axi_rready));
endmodule
