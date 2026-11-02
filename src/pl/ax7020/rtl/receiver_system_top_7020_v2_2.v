`timescale 1ns / 1ps
// Integrated DIGITAL V1 trial prototype: two local AXI-Lite banks, no PS/BD,
// pin assignment or image FIFO. Metadata commands and RX commands are distinct.
// Host order: RX APPLY/readback, META COMMIT/readback, META ARM, META START,
// RX START, then command AX7010 to transmit. Both AXI ports use this clock.
module receiver_system_top_7020_v2_2 (
    input wire clk,input wire rst_n,input wire ch0_async,
    input wire [7:0] rx_awaddr,input wire rx_awvalid,output wire rx_awready,
    input wire [31:0] rx_wdata,input wire [3:0] rx_wstrb,
    input wire rx_wvalid,output wire rx_wready,
    output wire [1:0] rx_bresp,output wire rx_bvalid,input wire rx_bready,
    input wire [7:0] rx_araddr,input wire rx_arvalid,output wire rx_arready,
    output wire [31:0] rx_rdata,output wire [1:0] rx_rresp,
    output wire rx_rvalid,input wire rx_rready,
    input wire [7:0] meta_awaddr,input wire meta_awvalid,output wire meta_awready,
    input wire [31:0] meta_wdata,input wire [3:0] meta_wstrb,
    input wire meta_wvalid,output wire meta_wready,
    output wire [1:0] meta_bresp,output wire meta_bvalid,input wire meta_bready,
    input wire [7:0] meta_araddr,input wire meta_arvalid,output wire meta_arready,
    output wire [31:0] meta_rdata,output wire [1:0] meta_rresp,
    output wire meta_rvalid,input wire meta_rready,
    output wire gateway_tx,output wire gateway_busy,output wire gateway_result_valid,
    output wire gateway_success,output wire [2:0] gateway_drop_reason,
    output wire [7:0] gateway_forwarded_byte,
    output wire a_frame_result,output wire b_frame_result,
    output wire [7:0] a_frame_payload,output wire [7:0] b_frame_payload,
    output wire [7:0] a_frame_flags,output wire [7:0] b_frame_flags,
    output wire [3:0] metadata_state
);
    wire [31:0] rx_window;
    wire a_event,b_event,a_fe,b_fe;
    wire [7:0] a_byte,b_byte;
    receiver_axi_lite_7020_v2_2 rx_bank(
        .s_axi_aclk(clk),.s_axi_aresetn(rst_n),.ch0_async(ch0_async),
        .s_axi_awaddr(rx_awaddr),.s_axi_awvalid(rx_awvalid),.s_axi_awready(rx_awready),
        .s_axi_wdata(rx_wdata),.s_axi_wstrb(rx_wstrb),
        .s_axi_wvalid(rx_wvalid),.s_axi_wready(rx_wready),
        .s_axi_bresp(rx_bresp),.s_axi_bvalid(rx_bvalid),.s_axi_bready(rx_bready),
        .s_axi_araddr(rx_araddr),.s_axi_arvalid(rx_arvalid),.s_axi_arready(rx_arready),
        .s_axi_rdata(rx_rdata),.s_axi_rresp(rx_rresp),
        .s_axi_rvalid(rx_rvalid),.s_axi_rready(rx_rready),
        .active_window_o(rx_window),.a_event_o(a_event),.b_event_o(b_event),
        .a_event_byte_o(a_byte),.b_event_byte_o(b_byte),
        .a_event_fe_o(a_fe),.b_event_fe_o(b_fe));

    wire meta_arm,meta_start,meta_ack;
    wire [31:0] active_run,active_trial;
    wire [7:0] active_image,active_attempt,active_route,active_profile;
    wire [15:0] active_index,active_total,active_len,active_crc;
    reg observed_pulse,forwarded_pulse,dropped_pulse;
    trusted_item_axilite_7020_v2_2 metadata_bank(
        .s_axi_aclk(clk),.s_axi_aresetn(rst_n),
        .s_axi_awaddr(meta_awaddr),.s_axi_awvalid(meta_awvalid),.s_axi_awready(meta_awready),
        .s_axi_wdata(meta_wdata),.s_axi_wstrb(meta_wstrb),
        .s_axi_wvalid(meta_wvalid),.s_axi_wready(meta_wready),
        .s_axi_bresp(meta_bresp),.s_axi_bvalid(meta_bvalid),.s_axi_bready(meta_bready),
        .s_axi_araddr(meta_araddr),.s_axi_arvalid(meta_arvalid),.s_axi_arready(meta_arready),
        .s_axi_rdata(meta_rdata),.s_axi_rresp(meta_rresp),
        .s_axi_rvalid(meta_rvalid),.s_axi_rready(meta_rready),
        .observed_event(observed_pulse),.forwarded_event(forwarded_pulse),
        .dropped_event(dropped_pulse),.report_event(1'b0),
        .host_timeout_event(1'b0),.arm_pulse(meta_arm),
        .start_pulse(meta_start),.ack_pulse(meta_ack),
        .meta_state(metadata_state),.meta_result_valid(),
        .active_run_id(active_run),.active_trial_id(active_trial),
        .active_image_id(active_image),.active_attempt_id(active_attempt),
        .active_route_mode(active_route),.active_rx_profile(active_profile),
        .active_item_index(active_index),.active_item_total(active_total),
        .active_payload_len(active_len),.active_source_crc(active_crc));

    wire a_assoc,b_assoc,a_seen,b_seen,a_complete,b_complete;
    request_frame_observer_7020_v2_2 observer_a(
        .clk(clk),.rst_n(rst_n),.arm(meta_arm),.abort_req(1'b0),.ack(meta_ack),
        .trusted_trial_id(active_trial[15:0]),.trusted_source_crc(active_crc),
        .window_clks(rx_window),.rx_valid(a_event),.rx_byte(a_byte),.rx_fe(a_fe),
        .result_valid(a_frame_result),.association_valid(a_assoc),
        .decoded_payload(a_frame_payload),.payload_seen(a_seen),
        .complete_frame(a_complete),.flags(a_frame_flags),
        .busy(),.arm_rejected(),.expected_trial_id(),.expected_source_crc(),
        .received_trial_id(),.received_crc(),.calculated_crc(),
        .byte_event_count(),.elapsed_clks(),.ignored_after_result());
    request_frame_observer_7020_v2_2 observer_b(
        .clk(clk),.rst_n(rst_n),.arm(meta_arm),.abort_req(1'b0),.ack(meta_ack),
        .trusted_trial_id(active_trial[15:0]),.trusted_source_crc(active_crc),
        .window_clks(rx_window),.rx_valid(b_event),.rx_byte(b_byte),.rx_fe(b_fe),
        .result_valid(b_frame_result),.association_valid(b_assoc),
        .decoded_payload(b_frame_payload),.payload_seen(b_seen),
        .complete_frame(b_complete),.flags(b_frame_flags),
        .busy(),.arm_rejected(),.expected_trial_id(),.expected_source_crc(),
        .received_trial_id(),.received_crc(),.calculated_crc(),
        .byte_event_count(),.elapsed_clks(),.ignored_after_result());

    reg gateway_launch;
    reg frame_handled,gateway_handled;
    wire choose_b=active_profile[0];
    wire selected_assoc=choose_b ? b_assoc : a_assoc;
    wire selected_seen=choose_b ? b_seen : a_seen;
    wire selected_fe=choose_b ? b_frame_flags[2] : a_frame_flags[2];
    wire [7:0] selected_byte=choose_b ? b_frame_payload : a_frame_payload;
    wire [3:0] tx_bytes;
    gateway_frame_tx_7020_v2_2 gateway(
        .clk(clk),.rst_n(rst_n),.launch(gateway_launch),.clear_result(meta_ack),
        .association_valid(selected_assoc && active_trial[31:16]==0 &&
                           active_len==1),
        .decoded_valid(selected_seen),.decoded_fe(selected_fe),
        .multiple_events(1'b0),.decoded_byte(selected_byte),
        .trusted_trial_id(active_trial[15:0]),.trusted_source_crc(active_crc),
        .tx(gateway_tx),.busy(gateway_busy),.result_valid(gateway_result_valid),
        .result_success(gateway_success),.drop_reason(gateway_drop_reason),
        .forwarded_byte(gateway_forwarded_byte),.forwarded_trial_id(),
        .forwarded_source_crc(),.launch_rejected(),.bytes_sent(tx_bytes));

    always @(posedge clk)begin
        if(!rst_n)begin
            observed_pulse<=0;forwarded_pulse<=0;dropped_pulse<=0;
            gateway_launch<=0;frame_handled<=0;gateway_handled<=0;
        end else begin
            observed_pulse<=0;forwarded_pulse<=0;dropped_pulse<=0;
            gateway_launch<=0;
            if(meta_ack)begin frame_handled<=0;gateway_handled<=0;end
            if(metadata_state==4'd3 && a_frame_result && b_frame_result &&
               !frame_handled)begin
                frame_handled<=1;observed_pulse<=1;
                if(active_route==1)gateway_launch<=1;
            end
            if(gateway_result_valid && frame_handled && !gateway_handled)begin
                gateway_handled<=1;
                if(gateway_success)forwarded_pulse<=1;
                else dropped_pulse<=1;
            end
        end
    end
endmodule
