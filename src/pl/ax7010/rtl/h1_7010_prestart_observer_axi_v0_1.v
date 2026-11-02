`timescale 1ns/1ps
// Same LIFE clock as W19 core. Snapshots observe, never authorize or START.
module h1_7010_prestart_observer_axi_v0_1(
 input wire clk,rst_n,authorized,source_fault,source_idle,current_valid,current_started,slot_busy,
 input wire [31:0] runtime_epoch,runtime_session,next_start_generation,
 input wire [255:0] prestart_full_identity,
 input wire [7:0] current_kind,
 input wire [15:0] current_len,
 input wire [8:0] mp_expected,mp_emitted,
 input wire [255:0] mp_identity,
 input wire mp_done,
 input wire [11:0] s_axi_awaddr,
 input wire s_axi_awvalid,
 output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,
 input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid,
 output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,
 output reg s_axi_bvalid,
 input wire s_axi_bready,
 input wire [11:0] s_axi_araddr,
 input wire s_axi_arvalid,
 output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,
 output reg [1:0] s_axi_rresp,
 output reg s_axi_rvalid,
 input wire s_axi_rready
);
 reg snapshot_valid,snapshot_current;
 reg [31:0] snapshot_seq,snapshot_epoch,snapshot_session,snapshot_generation;
 reg [23:0] snapshot_kind_len;
 reg [255:0] snapshot_identity;
 reg [11:0] delivered_mask,read_credit;
 reg have_aw,have_w;
 reg [11:0] awaddr;
 reg [31:0] wdata;
 reg [3:0] wstrb;
 reg [31:0] read_value;
 reg [1:0] read_resp;
 reg [11:0] proposed_credit;
 wire clean_source=(authorized && !source_fault && source_idle &&
  runtime_epoch!=0 && runtime_session!=0 && next_start_generation!=0)===1'b1;
 wire identity_ok=(prestart_full_identity[255:219]==0 &&
  prestart_full_identity[218:187]==runtime_session && prestart_full_identity[186:155]!=0 &&
  prestart_full_identity[154:123]==runtime_epoch && prestart_full_identity[122:120]==0 &&
  prestart_full_identity[119:88]==next_start_generation && prestart_full_identity[7:0]<=1 &&
  current_kind>=2 && current_kind<=4 && current_len>=12 && current_len<=534)===1'b1;
 wire snapshot_live=snapshot_valid && clean_source && snapshot_epoch==runtime_epoch &&
  snapshot_session==runtime_session && snapshot_generation==next_start_generation &&
  (snapshot_current ? (slot_busy && current_valid && !current_started && identity_ok && snapshot_identity===prestart_full_identity &&
   snapshot_kind_len=={current_len,current_kind}) : !slot_busy);
 assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !s_axi_rvalid;
 always @* begin
  read_value=0;read_resp=0;proposed_credit=0;
  case(s_axi_araddr)
   12'h000:read_value=32'h48505131; // HPQ1
   12'h004:read_value={24'd0,slot_busy,snapshot_current,snapshot_live,source_fault,current_started,current_valid,snapshot_valid,authorized};
   12'h020:read_value=32'h4d504731; // MPG1 capability, new candidate only
   12'h024:begin read_value={14'd0,mp_emitted,mp_expected};if(!authorized)read_resp=2;end
   12'h028:begin read_value={30'd0,source_fault,mp_done};if(!authorized)read_resp=2;end
   12'h030,12'h034,12'h038,12'h03c,12'h040,12'h044,12'h048,12'h04c:begin
    read_value=mp_identity[255-((s_axi_araddr-12'h030)>>2)*32 -:32];if(!authorized)read_resp=2;
   end
   12'h008:read_value=snapshot_seq;
   12'h00c:read_value={20'd0,delivered_mask};
   12'h100:begin read_value=snapshot_epoch;proposed_credit=1;end
   12'h104:begin read_value=snapshot_generation;proposed_credit=2;end
   12'h108:begin read_value={8'd0,snapshot_kind_len};proposed_credit=4;end
   12'h10c:begin read_value=snapshot_session;proposed_credit=8;end
   default:if(s_axi_araddr>=12'h110 && s_axi_araddr<=12'h12c)begin
    read_value=snapshot_identity[255-((s_axi_araddr-12'h110)>>2)*32 -:32];
    proposed_credit=12'd1<<(4+((s_axi_araddr-12'h110)>>2));
   end else read_resp=2;
  endcase
  if(s_axi_araddr[1:0]!=0 || (proposed_credit!=0 && !snapshot_valid))read_resp=2;
  if(read_resp!=0)begin read_value=0;proposed_credit=0;end
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   snapshot_valid<=0;snapshot_current<=0;snapshot_seq<=0;snapshot_epoch<=0;snapshot_session<=0;
   snapshot_generation<=0;snapshot_kind_len<=0;snapshot_identity<=0;delivered_mask<=0;read_credit<=0;
   have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
   s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
  end else begin
   if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
   if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready)begin s_axi_rvalid<=0;delivered_mask<=delivered_mask|read_credit;end
   if(s_axi_arvalid && s_axi_arready)begin
    s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_resp;read_credit<=proposed_credit;
   end
   if(have_aw && have_w && !s_axi_bvalid)begin
    have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
    if(wstrb==15 && wdata==1 && (awaddr==12'h010 || awaddr==12'h014) && clean_source &&
     !s_axi_rvalid && !s_axi_arvalid && (!snapshot_valid || delivered_mask==12'hfff) && snapshot_seq!=32'hffffffff &&
     (awaddr==12'h010 ? (slot_busy && current_valid && !current_started && identity_ok) : !slot_busy))begin
     snapshot_valid<=1;snapshot_current<=awaddr==12'h010;snapshot_seq<=snapshot_seq+1'b1;
     snapshot_epoch<=runtime_epoch;snapshot_session<=runtime_session;snapshot_generation<=next_start_generation;
     snapshot_kind_len<=awaddr==12'h010 ? {current_len,current_kind} : 24'd0;
     snapshot_identity<=awaddr==12'h010 ? prestart_full_identity : 256'd0;
     delivered_mask<=0;s_axi_bresp<=0;
    end
   end
  end
 end
endmodule
