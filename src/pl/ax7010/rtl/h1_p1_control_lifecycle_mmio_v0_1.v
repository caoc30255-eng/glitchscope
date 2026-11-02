`timescale 1ns / 1ps

// Control clock P2f + request/commit channels to a lifecycle clock owner.
// The application owns event effects; this wrapper never fabricates a commit.
module h1_p1_control_lifecycle_mmio_v0_1 #(
    parameter integer CTRL_CLK_HZ=100000000,
    parameter integer CTRL_BAUD=230400,
    parameter integer TX_TIMEOUT_CLKS=1000000,
    parameter integer RX_BYTE_TIMEOUT_CLKS=1000000
)(
    input wire ctrl_clk,life_clk,rst_n,
    input wire control_byte_valid,
    input wire [7:0] control_byte_data,
    output wire legacy_valid,
    output wire [7:0] legacy_type,legacy_len,
    output wire [255:0] legacy_payload,
    input wire legacy_ready,
    input wire notification_valid,
    input wire [7:0] notification_type,
    input wire [255:0] notification_payload,
    output wire notification_take,notification_done,
    input wire legacy_request_pulse,
    input wire [78:0] legacy_request_desc,
    output wire legacy_response_accepted,legacy_response_done,legacy_response_busy,
    output wire peer_ack_valid,
    output wire [7:0] peer_ack_type,
    output wire [255:0] peer_ack_payload,
    input wire peer_ack_ready,
    output wire app_event_valid,
    output wire [7:0] app_event_type,
    output wire [255:0] app_event_payload,
    input wire app_event_ready,
    input wire app_commit_valid,
    input wire [7:0] app_commit_type,
    input wire [255:0] app_commit_payload,
    output wire app_commit_ready,
    output wire control_tx_pin,
    output wire fault,
    output reg app_fault,
    output reg control_bridge_fault,
    output wire parser_error,
    output wire [2:0] parser_error_code,
    output wire [7:0] router_error,owner_error,tx_error,
    output wire quiet_ctrl,quiet_life,
 output wire [11:0] m_axi_awaddr,output wire m_axi_awvalid,input wire m_axi_awready,
 output wire [31:0] m_axi_wdata,output wire [3:0] m_axi_wstrb,output wire m_axi_wvalid,input wire m_axi_wready,
 input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
 output wire [11:0] m_axi_araddr,output wire m_axi_arvalid,input wire m_axi_arready,
 input wire [31:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rvalid,output wire m_axi_rready
);
    // Explicit internal declarations precede every use.
    wire chain_quiet;

    wire store_valid,chain_fault;
    wire [7:0] store_type;
    wire [255:0] store_payload;
    reg request_sent;
    reg [263:0] dispatched;
    reg app_pending;
    reg [263:0] app_token;
    wire request_ready,request_valid_dst;
    wire [263:0] request_data_dst;
    wire commit_ready_src,commit_valid_dst;
    wire [263:0] commit_data_dst;
    wire app_fault_ctrl;
    wire app_match,commit_matches_dispatch,dispatch_matches_offer;
    h1_control_equal_tree_v0_1 #(.WIDTH(264)) app_equal (
        .a({app_commit_type,app_commit_payload}),.b(app_token),.equal(app_match));
    h1_control_equal_tree_v0_1 #(.WIDTH(264)) commit_equal (
        .a(commit_data_dst),.b(dispatched),.equal(commit_matches_dispatch));
    h1_control_equal_tree_v0_1 #(.WIDTH(264)) offer_equal (
        .a(dispatched),.b({store_type,store_payload}),.equal(dispatch_matches_offer));
    wire ctrl_match=commit_matches_dispatch && dispatch_matches_offer;
    wire request_write=store_valid && !request_sent &&
        !control_bridge_fault && !app_fault_ctrl && !chain_fault;
    wire app_request_take=app_event_valid && app_event_ready;
    wire app_result_take=app_commit_valid && app_commit_ready;
    wire return_take=commit_valid_dst && request_sent && store_valid &&
        ctrl_match && !control_bridge_fault && !app_fault_ctrl && !chain_fault;
    assign app_event_valid=request_valid_dst && !app_pending && !app_fault;
    assign {app_event_type,app_event_payload}=request_data_dst;
    assign app_commit_ready=app_pending && app_match &&
        commit_ready_src && !app_fault;
    assign fault=chain_fault || control_bridge_fault || app_fault_ctrl;

    h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(264)) requests (
        .src_clk(ctrl_clk),.dst_clk(life_clk),.rst_n(rst_n),
        .src_valid(request_write),.src_data({store_type,store_payload}),
        .src_ready(request_ready),.dst_valid(request_valid_dst),
        .dst_data(request_data_dst),.dst_ready(app_request_take)
    );
    h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(264)) commits (
        .src_clk(life_clk),.dst_clk(ctrl_clk),.rst_n(rst_n),
        .src_valid(app_commit_valid && app_pending && app_match && !app_fault),
        .src_data({app_commit_type,app_commit_payload}),
        .src_ready(commit_ready_src),.dst_valid(commit_valid_dst),
        .dst_data(commit_data_dst),.dst_ready(return_take)
    );
    xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) app_fault_sync (
        .src_clk(life_clk),.src_in(app_fault),
        .dest_clk(ctrl_clk),.dest_out(app_fault_ctrl)
    );
    always @(posedge ctrl_clk or negedge rst_n) begin
        if(!rst_n) begin
            request_sent<=0;dispatched<=0;control_bridge_fault<=0;
        end else begin
            if(request_write && request_ready) begin
                request_sent<=1;
                dispatched<={store_type,store_payload};
            end
            if(commit_valid_dst && !control_bridge_fault) begin
                if(!request_sent || !store_valid || !ctrl_match)
                    control_bridge_fault<=1;
                else if(return_take) request_sent<=0;
            end
        end
    end
    always @(posedge life_clk or negedge rst_n) begin
        if(!rst_n) begin app_pending<=0;app_token<=0;app_fault<=0;end
        else begin
            if(app_request_take) begin
                app_pending<=1;
                app_token<={app_event_type,app_event_payload};
            end
            if(app_commit_valid && !app_fault) begin
                if(!app_pending || !app_match) app_fault<=1;
                else if(app_result_take) app_pending<=0;
            end
        end
    end
    h1_p1_control_chain_mmio_v0_1 #(
        .CLK_HZ(CTRL_CLK_HZ),.BAUD(CTRL_BAUD),.TX_TIMEOUT_CLKS(TX_TIMEOUT_CLKS),
        .RX_BYTE_TIMEOUT_CLKS(RX_BYTE_TIMEOUT_CLKS)
    ) control (
        .clk(ctrl_clk),.life_clk(life_clk),.rst_n(rst_n),.control_byte_valid(control_byte_valid),
        .control_byte_data(control_byte_data),.legacy_valid(legacy_valid),
        .legacy_type(legacy_type),.legacy_len(legacy_len),
        .legacy_payload(legacy_payload),.legacy_ready(legacy_ready),
        .store_valid(store_valid),.store_type(store_type),.store_payload(store_payload),
        .store_result_valid(return_take),.store_result_type(commit_data_dst[263:256]),
        .store_result_payload(commit_data_dst[255:0]),
        .peer_ack_valid(peer_ack_valid),.peer_ack_type(peer_ack_type),
        .peer_ack_payload(peer_ack_payload),.peer_ack_ready(peer_ack_ready),
        .notification_valid(notification_valid),.notification_type(notification_type),
        .notification_payload(notification_payload),.notification_take(notification_take),
        .notification_done(notification_done),.legacy_request_pulse(legacy_request_pulse),.legacy_request_desc(legacy_request_desc),
        .legacy_response_accepted(legacy_response_accepted),
        .legacy_response_done(legacy_response_done),.legacy_response_busy(legacy_response_busy),
        .control_tx_pin(control_tx_pin),.parser_error(parser_error),
        .parser_error_code(parser_error_code),.fault(chain_fault),
        .router_error(router_error),.owner_error(owner_error),.tx_error(tx_error),.quiet_ctrl(chain_quiet),
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

    assign quiet_ctrl=chain_quiet && !request_sent && !store_valid && !commit_valid_dst && !control_bridge_fault && !app_fault_ctrl;
    assign quiet_life=!app_pending && !request_valid_dst && !app_commit_valid && !app_fault;
endmodule
