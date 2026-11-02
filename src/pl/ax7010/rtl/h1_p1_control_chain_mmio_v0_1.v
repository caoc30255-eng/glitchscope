`timescale 1ns / 1ps

// One 100MHz control-clock-domain integration candidate. RX byte_valid/data
// comes from the existing control UART RX; PL/PS storage remains external.
module h1_p1_control_chain_mmio_v0_1 #(
    parameter integer CLK_HZ=100000000,
    parameter integer BAUD=230400,
    parameter integer TX_TIMEOUT_CLKS=1000000,
    parameter integer RX_BYTE_TIMEOUT_CLKS=1000000
)(
    input wire clk,life_clk,rst_n,
    input wire control_byte_valid,
    input wire [7:0] control_byte_data,
    output wire legacy_valid,
    output wire [7:0] legacy_type,legacy_len,
    output wire [255:0] legacy_payload,
    input wire legacy_ready,
    output wire store_valid,
    output wire [7:0] store_type,
    output wire [255:0] store_payload,
    input wire store_result_valid,
    input wire [7:0] store_result_type,
    input wire [255:0] store_result_payload,
    output wire peer_ack_valid,
    output wire [7:0] peer_ack_type,
    output wire [255:0] peer_ack_payload,
    input wire peer_ack_ready,
    input wire notification_valid,
    input wire [7:0] notification_type,
    input wire [255:0] notification_payload,
    output wire notification_take,notification_done,
    input wire legacy_request_pulse,
    input wire [78:0] legacy_request_desc,
    output wire legacy_response_accepted,
    output wire legacy_response_done,
    output wire legacy_response_busy,
    output wire control_tx_pin,
    output wire parser_error,
    output wire [2:0] parser_error_code,
    output wire fault,
    output wire [7:0] router_error,owner_error,tx_error,
    output wire quiet_ctrl,
 output wire [11:0] m_axi_awaddr,output wire m_axi_awvalid,input wire m_axi_awready,
 output wire [31:0] m_axi_wdata,output wire [3:0] m_axi_wstrb,output wire m_axi_wvalid,input wire m_axi_wready,
 input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
 output wire [11:0] m_axi_araddr,output wire m_axi_arvalid,input wire m_axi_arready,
 input wire [31:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rvalid,output wire m_axi_rready
);
    wire [7:0] bypass_type,bypass_len;
    wire [255:0] bypass_payload;

    // Explicit internal declarations precede every use.
    wire bypass_valid;
    wire parser_idle;

    wire packet_valid;
    wire [7:0] packet_type,packet_len;
    wire [255:0] packet_payload;
    wire event_valid,event_ready;
    wire [7:0] event_type;
    wire [255:0] event_payload;
    wire router_fault,owner_fault,tx_fault;
    wire [7:0] first_type;
    wire request_kind=event_type==8'h30 || event_type==8'h39 || event_type==8'h3a || event_type==8'h3c ||
        (event_type>=8'h34 && event_type<=8'h37);
    wire owner_rx_ready,owner_ack_valid,owner_ack_take,owner_ack_done;
    wire [7:0] owner_ack_type;
    wire [255:0] owner_ack_payload;
    wire shared_event_valid,shared_event_take,shared_event_done,source_mux_fault;
    wire [7:0] shared_event_type;
    wire [255:0] shared_event_payload;
    wire old_tx_error;
    wire [2:0] old_tx_error_code;
    assign peer_ack_valid=event_valid && !request_kind;
    assign peer_ack_type=event_type;
    assign peer_ack_payload=event_payload;
    assign event_ready=request_kind ? owner_rx_ready : peer_ack_ready;
    assign fault=router_fault || owner_fault || tx_fault || source_mux_fault;

    ctrl_packet_parser_runtime_v0_1 #(.MAX_PAYLOAD(32),.BYTE_TIMEOUT_CLKS(RX_BYTE_TIMEOUT_CLKS)) parser (
        .clk(clk),.rst_n(rst_n),.byte_valid(control_byte_valid),
        .byte_data(control_byte_data),.packet_valid(packet_valid),
        .packet_type(packet_type),.packet_len(packet_len),
        .packet_payload(packet_payload),.parser_error(parser_error),
        .error_code(parser_error_code),.parser_idle(parser_idle)
    );
    h1_p1_control_event_router_profile_v0_1 #(.IS_AX(1)) router (
        .clk(clk),.rst_n(rst_n),.packet_valid(bypass_valid),
        .packet_type(bypass_type),.packet_len(bypass_len),
        .packet_payload(bypass_payload),.event_valid(event_valid),
        .event_ready(event_ready),.event_type(event_type),
        .event_payload(event_payload),.legacy_valid(legacy_valid),
        .legacy_ready(legacy_ready),.legacy_type(legacy_type),
        .legacy_len(legacy_len),.legacy_payload(legacy_payload),
        .route_fault(router_fault),.route_error(router_error),
        .first_type(first_type)
    );
    h1_p1_event_commit_ack_profile_v0_1 #(.IS_AX(1)) owner (
        .clk(clk),.rst_n(rst_n),.rx_valid(event_valid && request_kind),
        .rx_type(event_type),.rx_payload(event_payload),
        .rx_ready(owner_rx_ready),.store_valid(store_valid),
        .store_type(store_type),.store_payload(store_payload),
        .store_result_valid(store_result_valid),
        .store_result_type(store_result_type),
        .store_result_payload(store_result_payload),
        .ack_valid(owner_ack_valid),.ack_type(owner_ack_type),
        .ack_payload(owner_ack_payload),.ack_take(owner_ack_take),
        .ack_done(owner_ack_done),.fault(owner_fault),
        .fault_code(owner_error)
    );

    wire mmio_executor_fault;wire [7:0] mmio_executor_fault_code;
    h1_uart_mmio_packet_transport_v0_1 #(.CTRL_CLK_HZ(CLK_HZ),.BAUD(BAUD),.TX_TIMEOUT_CLKS(TX_TIMEOUT_CLKS)) mmio (
      .ctrl_clk(clk),.life_clk(life_clk),.rst_n(rst_n),.external_fault(1'b0),
      .packet_valid(packet_valid),.packet_type(packet_type),.packet_len(packet_len),.packet_payload(packet_payload),
      .legacy_packet_valid(bypass_valid),.legacy_packet_ready(1'b1),.legacy_packet_type(bypass_type),.legacy_packet_len(bypass_len),.legacy_packet_payload(bypass_payload),
      .legacy_response_pulse(legacy_request_pulse),.legacy_response_desc(legacy_request_desc),
      .legacy_response_accepted(legacy_response_accepted),.legacy_response_done(legacy_response_done),.legacy_response_busy(legacy_response_busy),
      .auxiliary_valid(shared_event_valid),.auxiliary_type(shared_event_type),.auxiliary_payload(shared_event_payload),.auxiliary_take(shared_event_take),.auxiliary_done(shared_event_done),
      .ctrl_tx_pin(control_tx_pin),.control_fault(tx_fault),.control_fault_code(tx_error),.executor_fault(mmio_executor_fault),.executor_fault_code(mmio_executor_fault_code),
      .accepted_count(),.axi_read_count(),.axi_write_count(),.replay_count(),
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
    h1_p1_event_source_mux_v0_1 #(.TIMEOUT_CLKS(TX_TIMEOUT_CLKS)) source_mux (
        .clk(clk),.rst_n(rst_n),.ack_valid(owner_ack_valid),.ack_type(owner_ack_type),
        .ack_payload(owner_ack_payload),.ack_take(owner_ack_take),.ack_done(owner_ack_done),
        .notification_valid(notification_valid),.notification_type(notification_type),
        .notification_payload(notification_payload),.notification_take(notification_take),
        .notification_done(notification_done),.request_valid(shared_event_valid),
        .request_type(shared_event_type),.request_payload(shared_event_payload),
        .request_take(shared_event_take),.request_done(shared_event_done),.fault(source_mux_fault)
    );

    assign quiet_ctrl=parser_idle && !packet_valid && !bypass_valid && !event_valid && !legacy_valid && !store_valid &&
        !owner_ack_valid && !legacy_response_busy && !notification_valid && !fault;
endmodule
