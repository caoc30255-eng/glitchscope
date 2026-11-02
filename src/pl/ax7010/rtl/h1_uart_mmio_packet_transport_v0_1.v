`timescale 1ns/1ps
// Actual UART RX/parser, coherent CDC, LIFE executor and shared physical TX.
// Common reset of all three FIFOs and sender/endpoint is mandatory.
module h1_uart_mmio_packet_transport_v0_1 #(
 parameter integer CTRL_CLK_HZ=100000000,BAUD=230400,EXEC_TIMEOUT_CLKS=1000000,TX_TIMEOUT_CLKS=2000000
)(
 input wire ctrl_clk,life_clk,rst_n,external_fault,
 input wire packet_valid,input wire [7:0] packet_type,packet_len,input wire [255:0] packet_payload,
 output wire ctrl_tx_pin,
 output reg legacy_packet_valid,input wire legacy_packet_ready,
 output reg [7:0] legacy_packet_type,legacy_packet_len,output reg [255:0] legacy_packet_payload,
 input wire legacy_response_pulse,input wire [78:0] legacy_response_desc,
 output wire legacy_response_accepted,legacy_response_done,legacy_response_busy,
 input wire auxiliary_valid,input wire [7:0] auxiliary_type,input wire [255:0] auxiliary_payload,
 output wire auxiliary_take,auxiliary_done,
 output reg control_fault,output reg [7:0] control_fault_code,
 output wire executor_fault,output wire [7:0] executor_fault_code,
 output wire [31:0] accepted_count,axi_read_count,axi_write_count,replay_count,
 output wire [11:0] m_axi_awaddr,output wire m_axi_awvalid,input wire m_axi_awready,
 output wire [31:0] m_axi_wdata,output wire [3:0] m_axi_wstrb,output wire m_axi_wvalid,input wire m_axi_wready,
 input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
 output wire [11:0] m_axi_araddr,output wire m_axi_arvalid,input wire m_axi_arready,
 input wire [31:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rvalid,output wire m_axi_rready
);
 reg request_hold_valid;reg [255:0] request_hold;
 wire request_src_ready,request_dst_valid,request_dst_ready;wire [255:0] request_dst_data;
 h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(256)) requests(.src_clk(ctrl_clk),.dst_clk(life_clk),.rst_n(rst_n),
 .src_valid(request_hold_valid && !control_fault),.src_data(request_hold),.src_ready(request_src_ready),.dst_valid(request_dst_valid),.dst_data(request_dst_data),.dst_ready(request_dst_ready));
 wire control_fault_life,executor_fault_ctrl;
 xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) fault_to_life(.src_clk(ctrl_clk),.src_in(control_fault),.dest_clk(life_clk),.dest_out(control_fault_life));
 xpm_cdc_single #(.DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) fault_to_ctrl(.src_clk(life_clk),.src_in(executor_fault),.dest_clk(ctrl_clk),.dest_out(executor_fault_ctrl));
 wire response_valid,response_take,response_done;wire [255:0] response_payload;
 reg response_submitted;wire response_src_ready,response_dst_valid,response_dst_ready;wire [255:0] response_dst_data;
 h1_p1_event_cdc_xpm_v0_2 #(.WIDTH(256)) responses(.src_clk(life_clk),.dst_clk(ctrl_clk),.rst_n(rst_n),
 .src_valid(response_valid && !response_submitted),.src_data(response_payload),.src_ready(response_src_ready),.dst_valid(response_dst_valid),.dst_data(response_dst_data),.dst_ready(response_dst_ready));
 reg feedback_valid;reg [263:0] feedback_data;wire feedback_src_ready,feedback_dst_valid;wire [263:0] feedback_dst_data;
 h1_p1_event_cdc_xpm_v0_2 feedback(.src_clk(ctrl_clk),.dst_clk(life_clk),.rst_n(rst_n),
 .src_valid(feedback_valid && !control_fault),.src_data(feedback_data),.src_ready(feedback_src_ready),.dst_valid(feedback_dst_valid),.dst_data(feedback_dst_data),.dst_ready(1'b1));
 wire feedback_matches=feedback_dst_data[255:0]==response_payload;
 assign response_take=feedback_dst_valid && feedback_matches && feedback_dst_data[263:256]==1;
 assign response_done=feedback_dst_valid && feedback_matches && feedback_dst_data[263:256]==2;
 reg feedback_fault;
 always @(posedge life_clk) begin
  if(!rst_n) begin response_submitted<=0;feedback_fault<=0;end
  else begin
   if(response_valid && !response_submitted && response_src_ready) response_submitted<=1;
   if(response_done) response_submitted<=0;
   if(feedback_dst_valid && (!feedback_matches || (feedback_dst_data[263:256]!=1 && feedback_dst_data[263:256]!=2))) feedback_fault<=1;
  end
 end
 h1_uart_mmio_executor_v0_1 #(.TIMEOUT_CLKS(EXEC_TIMEOUT_CLKS)) executor(
 .clk(life_clk),.rst_n(rst_n),.external_fault(external_fault || control_fault_life || feedback_fault),
 .request_valid(request_dst_valid),.request_ready(request_dst_ready),.request_payload(request_dst_data),
 .response_valid(response_valid),.response_take(response_take),.response_done(response_done),.response_payload(response_payload),
 .fault(executor_fault),.fault_code(executor_fault_code),.accepted_count(accepted_count),.axi_read_count(axi_read_count),.axi_write_count(axi_write_count),.replay_count(replay_count),
 .m_axi_awaddr(m_axi_awaddr),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),.m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
 .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.m_axi_araddr(m_axi_araddr),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),.m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready));
 reg [1:0] tx_owner;reg offered;reg [7:0] offered_type;reg [255:0] offered_payload;
 wire sender_take,sender_done,sender_fault;wire [7:0] sender_fault_code;wire old_error;wire [2:0] old_error_code;
 assign auxiliary_take=sender_take && tx_owner==1;
 assign auxiliary_done=sender_done && tx_owner==1;
 assign response_dst_ready=sender_take && tx_owner==2;
 h1_p1_control_tx_bridge_mmio_v0_1 #(.CLK_HZ(CTRL_CLK_HZ),.BAUD(BAUD),.TX_TIMEOUT_CLKS(TX_TIMEOUT_CLKS)) shared_tx(
 .clk(ctrl_clk),.rst_n(rst_n),.legacy_request_pulse(legacy_response_pulse),.legacy_request_desc(legacy_response_desc),
 .legacy_response_accepted(legacy_response_accepted),.legacy_response_done(legacy_response_done),.legacy_response_busy_to_controller(legacy_response_busy),.legacy_response_error(old_error),.legacy_response_error_code(old_error_code),
 .event_request_valid(offered && !control_fault),.event_type(offered_type),.event_payload(offered_payload),.event_request_take(sender_take),.event_frame_done(sender_done),.uart_tx(ctrl_tx_pin),.fault(sender_fault),.fault_code(sender_fault_code));
 always @(posedge ctrl_clk) begin
  if(!rst_n) begin
   request_hold_valid<=0;request_hold<=0;legacy_packet_valid<=0;legacy_packet_type<=0;legacy_packet_len<=0;legacy_packet_payload<=0;
   control_fault<=0;control_fault_code<=0;feedback_valid<=0;feedback_data<=0;tx_owner<=0;offered<=0;offered_type<=0;offered_payload<=0;
  end else begin
   if(request_hold_valid && request_src_ready && !control_fault) request_hold_valid<=0;
   if(legacy_packet_valid && legacy_packet_ready) legacy_packet_valid<=0;
   if(feedback_valid && feedback_src_ready && !control_fault) feedback_valid<=0;
   if(!control_fault) begin
    // Bad outer CRC is discarded by parser. Never create a bus request for it.
    if(executor_fault_ctrl || sender_fault) begin control_fault<=1;control_fault_code<=1;end
    if(packet_valid) begin
     if(packet_type==8'h3b) begin
      if(packet_len!=32) begin control_fault<=1;control_fault_code<=2;end
      else if(request_hold_valid && !request_src_ready) begin
       if(request_hold!=packet_payload) begin control_fault<=1;control_fault_code<=3;end
      end else begin request_hold_valid<=1;request_hold<=packet_payload;end
     end else if(packet_type==8'h7b) begin control_fault<=1;control_fault_code<=4;end
     else if(legacy_packet_valid && !legacy_packet_ready) begin
      if(legacy_packet_type!=packet_type || legacy_packet_len!=packet_len || legacy_packet_payload!=packet_payload) begin control_fault<=1;control_fault_code<=5;end
     end else begin legacy_packet_valid<=1;legacy_packet_type<=packet_type;legacy_packet_len<=packet_len;legacy_packet_payload<=packet_payload;end
    end
    if(tx_owner==0) begin
     if(auxiliary_valid) begin tx_owner<=1;offered<=1;offered_type<=auxiliary_type;offered_payload<=auxiliary_payload;end
     else if(response_dst_valid) begin tx_owner<=2;offered<=1;offered_type<=8'h7b;offered_payload<=response_dst_data;end
    end
    if(sender_take) begin
     offered<=0;
     if(tx_owner==2) begin
      if(feedback_valid && !feedback_src_ready) begin control_fault<=1;control_fault_code<=6;end
      else begin feedback_valid<=1;feedback_data<={8'd1,offered_payload};end
     end
    end
    if(sender_done) begin
     tx_owner<=0;
     if(tx_owner==2) begin
      if(feedback_valid && !feedback_src_ready) begin control_fault<=1;control_fault_code<=6;end
      else begin feedback_valid<=1;feedback_data<={8'd2,offered_payload};end
     end
    end
   end
  end
 end
endmodule
