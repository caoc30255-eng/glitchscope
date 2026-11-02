`timescale 1ns/1ps
// HRP1: actual applied B d/s, full R delivery and real dual-RX idle qualification.
// Only global reset clears RX/profile/orphan state. No UART data source inputs
// from software, no endpoint reset/APPLY while a capture or UART byte is held.
module h1_7020_ch0_rx_profile_axi_v0_1 #(
 parameter integer IDLE_CLKS=10000
)(
 input wire clk,rst_n,external_fault,rx_sync,a_idle,b_idle,
 input wire capture_active,capture_closed,
 input wire [63:0] tick,
 input wire a_event,b_event,a_fe,b_fe,
 input wire [7:0] a_byte,b_byte,
 output reg [2:0] active_d,
 output reg signed [3:0] active_s,
 output wire paths_ready,
 output reg profile_fault,
 input wire [7:0] p_axi_awaddr,
 input wire p_axi_awvalid,output wire p_axi_awready,
 input wire [31:0] p_axi_wdata,input wire [3:0] p_axi_wstrb,
 input wire p_axi_wvalid,output wire p_axi_wready,
 output reg [1:0] p_axi_bresp,output reg p_axi_bvalid,input wire p_axi_bready,
 input wire [7:0] p_axi_araddr,input wire p_axi_arvalid,output wire p_axi_arready,
 output reg [31:0] p_axi_rdata,output reg [1:0] p_axi_rresp,
 output reg p_axi_rvalid,input wire p_axi_rready
);
 reg configured;
 reg [31:0] applied_seq,idle_count,stage_d,stage_s;
 reg [1:0] stage_mask;
 reg [2:0] delivered_mask,r_credit,proposed_credit;
 reg [31:0] a_orphans,b_orphans;
 reg [11:0] a_first,b_first;
 reg [63:0] a_first_tick,b_first_tick;
 reg [1:0] warmup;
 reg [7:0] first_fault;
 reg have_aw,have_w;
 reg [7:0] awaddr;
 reg [31:0] wdata,read_value;
 reg [3:0] wstrb;
 reg [1:0] read_resp;
 wire real_idle=warmup==3 && rx_sync && a_idle && b_idle && !a_event && !b_event;
 wire cfg_legal=(stage_mask==3 && stage_d>=1 && stage_d<=4 &&
  $signed(stage_s)>=-2 && $signed(stage_s)<=2 &&
  ((stage_d==1) || (stage_d==2 && $signed(stage_s)<=1) ||
   (stage_d==3 && $signed(stage_s)<=0) || (stage_d==4 && $signed(stage_s)<=-1)))===1'b1;
 assign paths_ready=configured && delivered_mask==7 && real_idle &&
  idle_count>=IDLE_CLKS && !profile_fault && !external_fault;
 assign p_axi_awready=rst_n && !have_aw && !p_axi_bvalid;
 assign p_axi_wready=rst_n && !have_w && !p_axi_bvalid;
 assign p_axi_arready=rst_n && !p_axi_rvalid;
 always @* begin
  read_value=0;read_resp=0;proposed_credit=0;
  case(p_axi_araddr)
   8'h00:read_value=32'h48525031;
   8'h04:read_value={26'd0,capture_closed,capture_active,profile_fault,real_idle,paths_ready,configured};
   8'h08:begin read_value=applied_seq;proposed_credit=4;end
   8'h0c:read_value=idle_count;
   8'h10:begin read_value={29'd0,active_d};proposed_credit=1;end
   8'h14:begin read_value={{28{active_s[3]}},active_s};proposed_credit=2;end
   8'h18:read_value=a_orphans;
   8'h1c:read_value=b_orphans;
   8'h20:read_value={20'd0,a_first};
   8'h24:read_value=a_first_tick[63:32];
   8'h28:read_value=a_first_tick[31:0];
   8'h2c:read_value={20'd0,b_first};
   8'h30:read_value=stage_d;
   8'h34:read_value=stage_s;
   8'h3c:read_value={30'd0,stage_mask};
   8'h40:read_value=b_first_tick[63:32];
   8'h44:read_value=b_first_tick[31:0];
   8'h48:read_value={24'd0,first_fault};
   8'h4c:read_value={29'd0,delivered_mask};
   default:read_resp=2;
  endcase
  if(p_axi_araddr[1:0]!=0 || (proposed_credit!=0 && !configured))read_resp=2;
  if(read_resp!=0)begin read_value=0;proposed_credit=0;end
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   active_d<=1;active_s<=0;configured<=0;applied_seq<=0;idle_count<=0;warmup<=0;
   stage_d<=0;stage_s<=0;stage_mask<=0;delivered_mask<=0;r_credit<=0;
   profile_fault<=0;first_fault<=0;a_orphans<=0;b_orphans<=0;
   a_first<=0;b_first<=0;a_first_tick<=0;b_first_tick<=0;
   have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
   p_axi_bresp<=0;p_axi_bvalid<=0;p_axi_rdata<=0;p_axi_rresp<=0;p_axi_rvalid<=0;
  end else begin
   if(warmup!=3)warmup<=warmup+1'b1;
   if(!real_idle)idle_count<=0;
   else if(idle_count<IDLE_CLKS)idle_count<=idle_count+1'b1;
   // An in-progress byte at closure cannot be removed by an early saved release.
   if(!profile_fault && (external_fault || (capture_active && capture_closed && (!a_idle || !b_idle))))begin
    profile_fault<=1;first_fault<=external_fault ? 1 : 2;
   end
   // Real late/unbound events retained per lane; never reset RX to hide them.
   if(!capture_active || capture_closed)begin
    if(a_event)begin
     if(a_orphans==0)begin a_first<={2'd0,a_fe,1'd0,a_byte};a_first_tick<=tick;end
     if(a_orphans!=32'hffffffff)a_orphans<=a_orphans+1'b1;
     if(!profile_fault)begin profile_fault<=1;first_fault<=3;end
    end
    if(b_event)begin
     if(b_orphans==0)begin b_first<={2'd0,b_fe,1'd0,b_byte};b_first_tick<=tick;end
     if(b_orphans!=32'hffffffff)b_orphans<=b_orphans+1'b1;
     if(!profile_fault)begin profile_fault<=1;first_fault<=3;end
    end
   end
   if(p_axi_awvalid && p_axi_awready)begin have_aw<=1;awaddr<=p_axi_awaddr;end
   if(p_axi_wvalid && p_axi_wready)begin have_w<=1;wdata<=p_axi_wdata;wstrb<=p_axi_wstrb;end
   if(p_axi_bvalid && p_axi_bready)p_axi_bvalid<=0;
   if(p_axi_rvalid && p_axi_rready)begin p_axi_rvalid<=0;delivered_mask<=delivered_mask|r_credit;end
   if(p_axi_arvalid && p_axi_arready)begin
    p_axi_rvalid<=1;p_axi_rdata<=read_value;p_axi_rresp<=read_resp;r_credit<=proposed_credit;
   end
   if(have_aw && have_w && !p_axi_bvalid)begin
    have_aw<=0;have_w<=0;p_axi_bvalid<=1;p_axi_bresp<=2;
    if(wstrb==15 && awaddr[1:0]==0 && !capture_active && !profile_fault && !external_fault && real_idle && idle_count>=IDLE_CLKS)begin
     case(awaddr)
      8'h30:begin stage_d<=wdata;stage_mask[0]<=1;p_axi_bresp<=0;end
      8'h34:begin stage_s<=wdata;stage_mask[1]<=1;p_axi_bresp<=0;end
      8'h38:if(wdata==1 && cfg_legal && (!configured || delivered_mask==7) && !p_axi_rvalid && !p_axi_arvalid && applied_seq!=32'hffffffff)begin
       active_d<=stage_d[2:0];active_s<=stage_s[3:0];configured<=1;
       applied_seq<=applied_seq+1'b1;stage_mask<=0;delivered_mask<=0;p_axi_bresp<=0;
      end
     endcase
    end
   end
  end
 end
endmodule
