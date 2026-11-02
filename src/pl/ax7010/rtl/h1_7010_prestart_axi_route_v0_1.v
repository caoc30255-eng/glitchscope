`timescale 1ns/1ps
// LIFE-clock 4KiB logical UART MMIO aperture. Preserve H5E1 offsets <D00.
module h1_7010_prestart_axi_route_v0_1(
 input wire clk,rst_n,
 input wire [11:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
 input wire [11:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
 output wire [11:0] legacy_awaddr,output wire legacy_awvalid,input wire legacy_awready,
 output wire [31:0] legacy_wdata,output wire [3:0] legacy_wstrb,output wire legacy_wvalid,input wire legacy_wready,
 input wire [1:0] legacy_bresp,input wire legacy_bvalid,output wire legacy_bready,
 output wire [11:0] legacy_araddr,output wire legacy_arvalid,input wire legacy_arready,
 input wire [31:0] legacy_rdata,input wire [1:0] legacy_rresp,input wire legacy_rvalid,output wire legacy_rready,
 output wire [11:0] observer_awaddr,output wire observer_awvalid,input wire observer_awready,
 output wire [31:0] observer_wdata,output wire [3:0] observer_wstrb,output wire observer_wvalid,input wire observer_wready,
 input wire [1:0] observer_bresp,input wire observer_bvalid,output wire observer_bready,
 output wire [11:0] observer_araddr,output wire observer_arvalid,input wire observer_arready,
 input wire [31:0] observer_rdata,input wire [1:0] observer_rresp,input wire observer_rvalid,output wire observer_rready
);
 reg aw_held,w_held,w_active,aw_sent,w_sent,w_select;
 reg [11:0] awaddr,araddr;
 reg [31:0] wdata;
 reg [3:0] wstrb;
 reg r_active,ar_sent,r_select;
 wire write_ready=w_select ? observer_awready : legacy_awready;
 wire data_ready=w_select ? observer_wready : legacy_wready;
 wire b_valid=w_select ? observer_bvalid : legacy_bvalid;
 wire [1:0] b_resp=w_select ? observer_bresp : legacy_bresp;
 wire ar_ready=r_select ? observer_arready : legacy_arready;
 wire r_valid=r_select ? observer_rvalid : legacy_rvalid;
 wire [31:0] r_data=r_select ? observer_rdata : legacy_rdata;
 wire [1:0] r_resp=r_select ? observer_rresp : legacy_rresp;
 assign s_axi_awready=rst_n && !aw_held && !w_active && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !w_held && !w_active && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !r_active && !s_axi_rvalid;
 assign legacy_awaddr=awaddr;assign legacy_awvalid=w_active && !w_select && !aw_sent;
 assign legacy_wdata=wdata;assign legacy_wstrb=wstrb;assign legacy_wvalid=w_active && !w_select && !w_sent;
 assign legacy_bready=w_active && !w_select && aw_sent && w_sent && !s_axi_bvalid;
 assign legacy_araddr=araddr;assign legacy_arvalid=r_active && !r_select && !ar_sent;
 assign legacy_rready=r_active && !r_select && ar_sent && !s_axi_rvalid;
 assign observer_awaddr=awaddr-12'hd00;assign observer_awvalid=w_active && w_select && !aw_sent;
 assign observer_wdata=wdata;assign observer_wstrb=wstrb;assign observer_wvalid=w_active && w_select && !w_sent;
 assign observer_bready=w_active && w_select && aw_sent && w_sent && !s_axi_bvalid;
 assign observer_araddr=araddr-12'hd00;assign observer_arvalid=r_active && r_select && !ar_sent;
 assign observer_rready=r_active && r_select && ar_sent && !s_axi_rvalid;
 always @(posedge clk)begin
  if(!rst_n)begin
   aw_held<=0;w_held<=0;w_active<=0;aw_sent<=0;w_sent<=0;w_select<=0;
   awaddr<=0;araddr<=0;wdata<=0;wstrb<=0;r_active<=0;ar_sent<=0;r_select<=0;
   s_axi_bresp<=0;s_axi_bvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;s_axi_rvalid<=0;
  end else begin
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_awvalid && s_axi_awready)begin aw_held<=1;awaddr<=s_axi_awaddr;end
   if(s_axi_wvalid && s_axi_wready)begin w_held<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
   if(aw_held && w_held && !w_active && !s_axi_bvalid)begin
    aw_held<=0;w_held<=0;w_active<=1;aw_sent<=0;w_sent<=0;w_select<=awaddr>=12'hd00;
   end
   if(w_active)begin
    if(!aw_sent && write_ready)aw_sent<=1;
    if(!w_sent && data_ready)w_sent<=1;
    if(aw_sent && w_sent && b_valid && !s_axi_bvalid)begin s_axi_bresp<=b_resp;s_axi_bvalid<=1;w_active<=0;end
   end
   if(s_axi_arvalid && s_axi_arready)begin
    r_active<=1;ar_sent<=0;araddr<=s_axi_araddr;r_select<=s_axi_araddr>=12'hd00;
   end
   if(r_active)begin
    if(!ar_sent && ar_ready)ar_sent<=1;
    if(ar_sent && r_valid && !s_axi_rvalid)begin s_axi_rdata<=r_data;s_axi_rresp<=r_resp;s_axi_rvalid<=1;r_active<=0;end
   end
  end
 end
endmodule
