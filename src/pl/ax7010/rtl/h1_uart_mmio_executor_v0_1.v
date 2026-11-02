`timescale 1ns/1ps
// LIFE-domain endpoint AFTER CRC-checked control parser and coherent CDC.
// Transport epoch is independent of authorized runtime epoch/session.
module h1_uart_mmio_executor_v0_1 #(parameter integer TIMEOUT_CLKS=1000000)(
 input wire clk,rst_n,external_fault,
 input wire request_valid,output wire request_ready,input wire [255:0] request_payload,
 output wire response_valid,input wire response_take,response_done,output reg [255:0] response_payload,
 output reg fault,output reg [7:0] fault_code,
 output reg [31:0] accepted_count,axi_read_count,axi_write_count,replay_count,
 output reg [11:0] m_axi_awaddr,output reg m_axi_awvalid,input wire m_axi_awready,
 output reg [31:0] m_axi_wdata,output wire [3:0] m_axi_wstrb,output reg m_axi_wvalid,input wire m_axi_wready,
 input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
 output reg [11:0] m_axi_araddr,output reg m_axi_arvalid,input wire m_axi_arready,
 input wire [31:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rvalid,output wire m_axi_rready
);
 localparam IDLE=0,READ_ADDRESS=1,READ_DATA=2,WRITE_CHANNELS=3,WRITE_REPLY=4,OFFER=5,PHYSICAL=6,LOCKED=7;
 reg [3:0] state;
 reg [255:0] held_request,last_request,last_response;
 reg [31:0] transport_epoch,last_id,wait_count;
 reg last_valid,replaying;
 reg [7:0] operation,word_index,requested_count;
 function [31:0] be32;input [255:0] p;input integer offset;
 begin be32={p[offset*8+:8],p[(offset+1)*8+:8],p[(offset+2)*8+:8],p[(offset+3)*8+:8]};end endfunction
 wire [31:0] req_epoch=be32(request_payload,0),req_id=be32(request_payload,4);
 wire [7:0] req_op=request_payload[64+:8],req_count=request_payload[72+:8];
 wire [15:0] req_addr={request_payload[80+:8],request_payload[88+:8]};
 wire fields_ok=req_epoch!=0 && req_id!=0 && req_addr[15:12]==0 && req_addr[1:0]==0 && request_payload[255:128]==0 &&
  ((req_op==0 && req_count==1 && request_payload[127:96]==0) ||
   (req_op==1 && req_count==1) ||
   (req_op==2 && req_count>=1 && req_count<=16 && request_payload[127:96]==0 &&
    req_addr>=16'h400 && ({1'b0,req_addr}+((req_count-1)*4))<=17'hc54));
 wire first_probe=req_op==0 && req_addr==0 && req_count==1 && req_id==1;
 assign request_ready=state==IDLE && !fault && !external_fault;
 assign response_valid=state==OFFER && !fault && !external_fault;
 assign m_axi_wstrb=4'hf;
 assign m_axi_rready=state==READ_DATA && !fault && !external_fault;
 assign m_axi_bready=state==WRITE_REPLY && !fault && !external_fault;
 always @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE;held_request<=0;last_request<=0;last_response<=0;response_payload<=0;
   transport_epoch<=0;last_id<=0;last_valid<=0;replaying<=0;wait_count<=0;
   operation<=0;word_index<=0;requested_count<=0;fault<=0;fault_code<=0;
   accepted_count<=0;axi_read_count<=0;axi_write_count<=0;replay_count<=0;
   m_axi_awaddr<=0;m_axi_awvalid<=0;m_axi_wdata<=0;m_axi_wvalid<=0;m_axi_araddr<=0;m_axi_arvalid<=0;
  end else if(!fault) begin
   if(external_fault) begin fault<=1;fault_code<=1;state<=LOCKED;end
   else if(response_done && state!=PHYSICAL) begin fault<=1;fault_code<=2;state<=LOCKED;end
   else if(state!=IDLE && wait_count>=TIMEOUT_CLKS-1) begin fault<=1;fault_code<=3;state<=LOCKED;end
   else begin
    if(state!=IDLE) wait_count<=wait_count+1'b1;
    case(state)
     IDLE:if(request_valid) begin
      if(!fields_ok) begin fault<=1;fault_code<=4;state<=LOCKED;end
      else if(last_valid && req_epoch==transport_epoch && req_id==last_id) begin
       if(request_payload!=last_request) begin fault<=1;fault_code<=5;state<=LOCKED;end
       else begin response_payload<=last_response;held_request<=last_request;replaying<=1;replay_count<=replay_count+1;wait_count<=0;state<=OFFER;end
      end else if((transport_epoch==0 && !first_probe) ||
       (transport_epoch!=0 && (req_epoch!=transport_epoch || !last_valid || last_id==32'hffffffff || req_id!=last_id+1'b1)))
       begin fault<=1;fault_code<=6;state<=LOCKED;end
      else begin
       transport_epoch<=req_epoch;held_request<=request_payload;operation<=req_op;requested_count<=req_count;word_index<=0;
       response_payload<=0;response_payload[95:0]<=request_payload[95:0];response_payload[112+:8]<=req_count;
       replaying<=0;accepted_count<=accepted_count+1;wait_count<=0;
       if(req_op==1) begin m_axi_awaddr<=req_addr[11:0];m_axi_awvalid<=1;m_axi_wdata<=be32(request_payload,12);m_axi_wvalid<=1;state<=WRITE_CHANNELS;end
       else begin m_axi_araddr<=req_addr[11:0];m_axi_arvalid<=1;state<=READ_ADDRESS;end
      end
     end
     READ_ADDRESS:if(m_axi_arvalid && m_axi_arready) begin m_axi_arvalid<=0;state<=READ_DATA;end
     READ_DATA:if(m_axi_rvalid && m_axi_rready) begin
      axi_read_count<=axi_read_count+1;
      if(m_axi_rresp!=0) begin response_payload[96+:8]<=1;response_payload[104+:8]<={6'd0,m_axi_rresp};response_payload[112+:8]<=0;response_payload[255:128]<=0;state<=OFFER;wait_count<=0;end
      else if(operation==0) begin
       response_payload[128+:8]<=m_axi_rdata[31:24];response_payload[136+:8]<=m_axi_rdata[23:16];
       response_payload[144+:8]<=m_axi_rdata[15:8];response_payload[152+:8]<=m_axi_rdata[7:0];state<=OFFER;wait_count<=0;
      end else begin
       response_payload[(16+word_index)*8+:8]<=m_axi_rdata[7:0];
       if(word_index+1==requested_count) begin state<=OFFER;wait_count<=0;end
       else begin word_index<=word_index+1;m_axi_araddr<=m_axi_araddr+4;m_axi_arvalid<=1;state<=READ_ADDRESS;end
      end
     end
     WRITE_CHANNELS:begin
      if(m_axi_awvalid && m_axi_awready) m_axi_awvalid<=0;
      if(m_axi_wvalid && m_axi_wready) m_axi_wvalid<=0;
      if((!m_axi_awvalid || m_axi_awready) && (!m_axi_wvalid || m_axi_wready)) state<=WRITE_REPLY;
     end
     WRITE_REPLY:if(m_axi_bvalid && m_axi_bready) begin
      axi_write_count<=axi_write_count+1;
      response_payload[96+:8]<=m_axi_bresp==0 ? 0 : 1;response_payload[104+:8]<={6'd0,m_axi_bresp};
      response_payload[112+:8]<=0;state<=OFFER;wait_count<=0;
     end
     OFFER:if(response_take) begin state<=PHYSICAL;wait_count<=0;end
     PHYSICAL:if(response_done) begin
      if(!replaying) begin last_request<=held_request;last_response<=response_payload;last_id<=be32(held_request,4);last_valid<=1;end
      state<=IDLE;wait_count<=0;
     end
     default:begin fault<=1;fault_code<=7;state<=LOCKED;end
    endcase
   end
  end
  // In a locked fault, pending AW/W/AR valid and their tuple are retained until
  // coordinated reset; never fabricate a response, cancel/restart a write.
 end
endmodule
