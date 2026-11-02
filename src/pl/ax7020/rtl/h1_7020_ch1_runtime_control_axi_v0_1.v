`timescale 1ns/1ps
// Software runtime commands; physical completion is never synthesized by MMIO.
module h1_7020_ch1_runtime_control_axi_v0_1(
 input wire clk,rst_n,
 input wire [63:0] tick,
 input wire core_active,core_record_valid,core_retire_ready,aux_pending,external_fault,
 input wire actual_retired_valid,
 input wire [31:0] actual_retired_epoch,actual_retired_id,actual_retire_count,
 input wire [255:0] actual_retired_identity,
 output reg [31:0] evidence_epoch,
 output reg arm,
 output reg [1:0] arm_kind,
 output reg [31:0] arm_record_id,
 output reg [255:0] arm_identity,
 output reg [63:0] start_tick,deadline_tick,
 output wire release_request,
 output reg abort_event,
 output reg fault_latched,
 output reg [7:0] first_fault,
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
 reg live_binding,arm_pending,release_pending;
 reg [4:0] arm_wait;
 reg [31:0] staged_epoch,staged_kind,staged_id,staged_delay,staged_window,last_generation,last_record_id;
 reg [255:0] staged_identity;
 reg [11:0] arm_mask;
 reg [31:0] release_epoch,release_id;
 reg [255:0] release_identity;
 reg [9:0] release_mask;
 reg [63:0] last_tick,snapshot_tick;
 reg [31:0] snapshot_epoch,snapshot_seq;
 reg snapshot_valid;
 reg [3:0] snapshot_mask,r_credit;
 reg have_aw,have_w;
 reg [11:0] awaddr;
 reg [31:0] wdata;
 reg [3:0] wstrb;
 reg [31:0] read_value;
 reg [1:0] read_response;
 reg [3:0] read_credit;
 wire busy=live_binding || arm_pending || core_active;
 wire [64:0] proposed_start={1'b0,tick}+{33'd0,staged_delay};
 wire [64:0] proposed_deadline=proposed_start+{33'd0,staged_window};
 wire arm_ok=(arm_mask==12'hfff && evidence_epoch!=0 && staged_kind>=1 && staged_kind<=3 &&
  staged_id!=0 && staged_id>last_record_id && staged_delay>=4 && staged_window!=0 && !proposed_deadline[64] &&
  staged_identity[255:219]==0 && staged_identity[218:187]!=0 && staged_identity[186:155]!=0 &&
  staged_identity[119:88]!=0 && staged_identity[119:88]>last_generation && staged_identity[7:0]<=1)===1'b1;
 wire release_match=(release_mask==10'h3ff && release_epoch==evidence_epoch && release_id==arm_record_id &&
  release_identity===arm_identity)===1'b1;
 wire retirement_match=(live_binding && release_pending && actual_retired_epoch==evidence_epoch &&
  actual_retired_id==arm_record_id && actual_retired_identity===arm_identity)===1'b1;
 assign release_request=rst_n && release_pending && !fault_latched && !external_fault && !aux_pending;
 assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !s_axi_rvalid;
 wire write_exec=have_aw && have_w && !s_axi_bvalid;
 task fault;
 input [7:0] code;
 begin fault_latched<=1;first_fault<=code;end
 endtask
 always @* begin
  read_value=0;read_response=0;read_credit=0;
  case(s_axi_araddr)
   12'h000:read_value=32'h48315231; // H1R1
   12'h004:read_value={23'd0,aux_pending,core_retire_ready,core_record_valid,arm_pending,snapshot_valid,fault_latched,release_pending,busy,(evidence_epoch!=0)};
   12'h008:read_value=evidence_epoch;
   12'h00c:read_value={24'd0,first_fault};
   12'h014:begin read_value=snapshot_tick[63:32];read_credit=1;end
   12'h018:begin read_value=snapshot_tick[31:0];read_credit=2;end
   12'h01c:begin read_value=snapshot_epoch;read_credit=4;end
   12'h020:begin read_value=snapshot_seq;read_credit=8;end
   12'h024:read_value=actual_retire_count;
   12'h028:read_value={28'd0,snapshot_mask};
   12'h100:read_value=arm_record_id;
   12'h104:read_value={30'd0,arm_kind};
   12'h108:read_value=start_tick[63:32];
   12'h10c:read_value=start_tick[31:0];
   12'h110:read_value=deadline_tick[63:32];
   12'h114:read_value=deadline_tick[31:0];
   default:begin
    if(s_axi_araddr>=12'h120 && s_axi_araddr<=12'h13c)
     read_value=arm_identity[255-((s_axi_araddr-12'h120)>>2)*32 -:32];
    else read_response=2;
   end
  endcase
  if(read_credit!=0 && !snapshot_valid)read_response=2;
  if(s_axi_araddr[1:0]!=0)read_response=2;
  if(read_response!=0)begin read_value=0;read_credit=0;end
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   evidence_epoch<=0;arm<=0;arm_kind<=0;arm_record_id<=0;arm_identity<=0;start_tick<=0;deadline_tick<=0;
   abort_event<=0;fault_latched<=0;first_fault<=0;live_binding<=0;arm_pending<=0;release_pending<=0;arm_wait<=0;
   staged_epoch<=0;staged_kind<=0;staged_id<=0;staged_delay<=0;staged_window<=0;staged_identity<=0;arm_mask<=0;last_generation<=0;last_record_id<=0;
   release_epoch<=0;release_id<=0;release_identity<=0;release_mask<=0;
   last_tick<=0;snapshot_tick<=0;snapshot_epoch<=0;snapshot_seq<=0;snapshot_valid<=0;snapshot_mask<=0;r_credit<=0;
   have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
  end else begin
   arm<=0;abort_event<=0;last_tick<=tick;
   if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
   if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready)begin s_axi_rvalid<=0;snapshot_mask<=snapshot_mask|r_credit;end
   if(s_axi_arvalid && s_axi_arready)begin s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_response;r_credit<=read_credit;end
   if(!fault_latched)begin
    if(external_fault)fault(1);
    else if(tick<last_tick)fault(2);
    else if(actual_retired_valid && !retirement_match)fault(3);
    else if(actual_retired_valid)begin live_binding<=0;release_pending<=0;release_mask<=0;end
    else if(arm_pending)begin
     if(core_active)arm_pending<=0;
     else if(arm_wait==15)fault(4);
     else arm_wait<=arm_wait+1'b1;
    end
   end
   if(write_exec)begin
    have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
    // Same-edge retirement, reversed tick and external fault veto every command.
    if(wstrb==15 && awaddr[1:0]==0 && !fault_latched && !external_fault && tick>=last_tick && !actual_retired_valid)begin
     case(awaddr)
      12'h010:if(wdata==1 && evidence_epoch!=0 && !s_axi_rvalid && !s_axi_arvalid &&
       (!snapshot_valid || snapshot_mask==15))begin
       if(snapshot_seq==32'hffffffff)fault(5);
       else begin snapshot_tick<=tick;snapshot_epoch<=evidence_epoch;snapshot_seq<=snapshot_seq+1'b1;
        snapshot_valid<=1;snapshot_mask<=0;s_axi_bresp<=0;end
      end
      12'h030:if(!busy)begin staged_epoch<=wdata;s_axi_bresp<=0;end
      12'h034:if(wdata==1 && !busy && !aux_pending && staged_epoch!=0 && staged_epoch>evidence_epoch &&
       !s_axi_rvalid && !s_axi_arvalid && (!snapshot_valid || snapshot_mask==15))begin
       evidence_epoch<=staged_epoch;snapshot_valid<=0;snapshot_mask<=0;arm_mask<=0;release_mask<=0;last_record_id<=0;s_axi_bresp<=0;
      end
      12'h040:if(!busy)begin staged_kind<=wdata;arm_mask[0]<=1;s_axi_bresp<=0;end
      12'h044:if(!busy)begin staged_id<=wdata;arm_mask[1]<=1;s_axi_bresp<=0;end
      12'h048:if(!busy)begin staged_delay<=wdata;arm_mask[2]<=1;s_axi_bresp<=0;end
      12'h04c:if(!busy)begin staged_window<=wdata;arm_mask[3]<=1;s_axi_bresp<=0;end
      12'h070:if(wdata==1 && !busy && !aux_pending && arm_ok)begin
       arm<=1;arm_kind<=staged_kind[1:0];arm_record_id<=staged_id;arm_identity<=staged_identity;
       start_tick<=proposed_start[63:0];deadline_tick<=proposed_deadline[63:0];last_generation<=staged_identity[119:88];last_record_id<=staged_id;
       live_binding<=1;arm_pending<=1;arm_wait<=0;release_pending<=0;release_mask<=0;arm_mask<=0;s_axi_bresp<=0;
      end
      12'h080:if(live_binding && !release_pending)begin release_epoch<=wdata;release_mask[0]<=1;s_axi_bresp<=0;end
      12'h084:if(live_binding && !release_pending)begin release_id<=wdata;release_mask[1]<=1;s_axi_bresp<=0;end
      12'h0a8:if(wdata==1 && live_binding && !arm_pending)begin
       if(!release_match)fault(6);
       else if(release_pending) s_axi_bresp<=0; // matching held command is idempotent
       else if(core_record_valid && core_retire_ready && !aux_pending)begin release_pending<=1;s_axi_bresp<=0;end
      end
      12'h0b0:if(wdata==1 && live_binding && !arm_pending && core_active && !release_pending)begin abort_event<=1;s_axi_bresp<=0;end
      default:begin
       if(awaddr>=12'h050 && awaddr<=12'h06c && !busy)begin
        staged_identity[255-((awaddr-12'h050)>>2)*32 -:32]<=wdata;arm_mask[4+((awaddr-12'h050)>>2)]<=1;s_axi_bresp<=0;
       end else if(awaddr>=12'h088 && awaddr<=12'h0a4 && live_binding && !release_pending)begin
        release_identity[255-((awaddr-12'h088)>>2)*32 -:32]<=wdata;release_mask[2+((awaddr-12'h088)>>2)]<=1;s_axi_bresp<=0;
       end
      end
     endcase
    end
   end
  end
 end
endmodule
