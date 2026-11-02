`timescale 1ns/1ps
// Protect the eight-bit HRP1 address port from aliases in its 4KiB BD window.
// AW precedes W at the downstream side; upstream W may be presented first.
module h1_7020_profile_window_guard_v0_1(
 input wire clk,rst_n,
 input wire [11:0] s_awaddr,input wire s_awvalid,output wire s_awready,
 input wire [31:0] s_wdata,input wire [3:0] s_wstrb,input wire s_wvalid,output wire s_wready,
 output wire [1:0] s_bresp,output wire s_bvalid,input wire s_bready,
 input wire [11:0] s_araddr,input wire s_arvalid,output wire s_arready,
 output wire [31:0] s_rdata,output wire [1:0] s_rresp,output wire s_rvalid,input wire s_rready,
 output wire [7:0] m_awaddr,output wire m_awvalid,input wire m_awready,
 output wire [31:0] m_wdata,output wire [3:0] m_wstrb,output wire m_wvalid,input wire m_wready,
 input wire [1:0] m_bresp,input wire m_bvalid,output wire m_bready,
 output wire [7:0] m_araddr,output wire m_arvalid,input wire m_arready,
 input wire [31:0] m_rdata,input wire [1:0] m_rresp,input wire m_rvalid,output wire m_rready
);
 reg have_aw,write_bad,wait_b,read_bad,read_pass;
 wire bad_aw=|s_awaddr[11:8];
 wire bad_ar=|s_araddr[11:8];
 assign m_awaddr=s_awaddr[7:0];
 assign m_awvalid=rst_n && s_awvalid && !have_aw && !wait_b && !bad_aw;
 assign s_awready=rst_n && !have_aw && !wait_b && (bad_aw || m_awready);
 assign m_wdata=s_wdata;assign m_wstrb=s_wstrb;
 assign m_wvalid=rst_n && s_wvalid && have_aw && !wait_b && !write_bad;
 assign s_wready=rst_n && have_aw && !wait_b && (write_bad || m_wready);
 assign s_bvalid=wait_b && (write_bad || m_bvalid);
 assign s_bresp=write_bad ? 2'b10 : m_bresp;
 assign m_bready=wait_b && !write_bad && s_bready;
 assign m_araddr=s_araddr[7:0];
 assign m_arvalid=rst_n && s_arvalid && !read_bad && !read_pass && !bad_ar;
 assign s_arready=rst_n && !read_bad && !read_pass && (bad_ar || m_arready);
 assign s_rvalid=read_bad || (read_pass && m_rvalid);
 assign s_rresp=read_bad ? 2'b10 : m_rresp;
 assign s_rdata=read_bad ? 32'd0 : m_rdata;
 assign m_rready=read_pass && s_rready;
 always @(posedge clk)begin
  if(!rst_n)begin have_aw<=0;write_bad<=0;wait_b<=0;read_bad<=0;read_pass<=0;end
  else begin
   if(s_awvalid && s_awready)begin have_aw<=1;write_bad<=bad_aw;end
   if(s_wvalid && s_wready)begin have_aw<=0;wait_b<=1;end
   if(s_bvalid && s_bready)begin wait_b<=0;write_bad<=0;end
   if(s_arvalid && s_arready)begin read_bad<=bad_ar;read_pass<=!bad_ar;end
   if(s_rvalid && s_rready)begin read_bad<=0;read_pass<=0;end
  end
 end
endmodule
