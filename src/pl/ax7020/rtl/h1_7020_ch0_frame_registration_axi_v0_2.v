`timescale 1ns/1ps
// Two owned 544-sample buffers. A/B decoded events and applied/idle indication
// must be wired to real receiver paths in integration; no byte is fabricated.
module h1_7020_ch0_frame_registration_axi_v0_2 #(parameter integer CLOCK_HZ=100000000)(
 input wire clk,rst_n,external_fault,a_path_ready,b_path_ready,
 input wire [31:0] evidence_epoch,
 input wire a_valid,b_valid,a_error,b_error,
 input wire [7:0] a_data,b_data,
 input wire [3:0] a_flags,b_flags,
 output wire registered_ready,
 output reg active,closed,fault_latched,
 output reg [7:0] first_fault,
 output reg [31:0] bound_epoch,bound_id,
 output reg [255:0] bound_identity,
 output reg [63:0] tick,start_tick,deadline_tick,
 input wire [14:0] s_axi_awaddr,
 input wire s_axi_awvalid,
 output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,
 input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid,
 output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,
 output reg s_axi_bvalid,
 input wire s_axi_bready,
 input wire [14:0] s_axi_araddr,
 input wire s_axi_arvalid,
 output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,
 output reg [1:0] s_axi_rresp,
 output reg s_axi_rvalid,
 input wire s_axi_rready
);
 (* ram_style="block" *) reg [79:0] a_ram[0:543],b_ram[0:543];
 reg [15:0] a_count,b_count,expected_count;
 reg [31:0] a_errors,b_errors,last_generation,last_id,last_epoch,release_count;
 reg [63:0] a_first_error,b_first_error,last_tick;
 reg rejected_valid,rejected_lane,rejected_has_byte;
 reg [7:0] rejected_data;
 reg [3:0] rejected_flags;
 reg [63:0] rejected_tick;
 reg [1:0] bound_kind;
 reg [31:0] stage_epoch,stage_id,stage_kind,stage_count,stage_delay,stage_duration;
 reg [255:0] stage_identity;
 reg [14:0] stage_mask;
 reg [31:0] stage_peer_epoch,bound_peer_epoch;
 reg [16:0] registration_mask;
 reg [24:0] archive_meta_mask;
 reg [2:0] a_read_mask[0:543],b_read_mask[0:543];
 reg [15:0] a_delivered,b_delivered;
 reg [31:0] proof_epoch,proof_id,proof_counts;
 reg [255:0] proof_identity;
 reg [10:0] proof_mask;
 reg have_aw,have_w;
 reg [14:0] awaddr;
 reg [31:0] wdata;
 reg [3:0] wstrb;
 reg [16:0] r_reg_credit;
 reg [24:0] r_meta_credit;
 reg r_sample,r_lane;
 reg [9:0] r_index;
 reg [1:0] r_part;
 reg [31:0] read_value;
 reg [1:0] read_resp;
 reg snap_valid;
 reg [31:0] snap_seq,snap_local_epoch,snap_peer_epoch,snap_record_id,snap_flags;
 reg [63:0] snap_tick;
 reg [7:0] snap_mask,r_snap_credit,proposed_snap_credit;
 wire current_window_open=active && !closed && !fault_latched && !external_fault &&
  evidence_epoch==bound_epoch && registered_ready && tick>=start_tick && tick<deadline_tick;
 wire snap_live=snap_valid && snap_flags[4] && current_window_open &&
  snap_local_epoch==evidence_epoch && snap_peer_epoch==bound_peer_epoch && snap_record_id==bound_id;

 reg [16:0] proposed_reg_credit;
 reg [24:0] proposed_meta_credit;
 reg proposed_sample,proposed_lane;
 reg [9:0] proposed_index;
 reg [1:0] proposed_part;
 integer i,index,part;
 wire [64:0] proposed_start={1'b0,tick}+{33'd0,stage_delay};
 wire [64:0] proposed_deadline=proposed_start+{33'd0,stage_duration};
 wire stage_ok=(stage_mask==15'h7fff && stage_epoch!=0 && stage_epoch==evidence_epoch && stage_id!=0 &&
  (stage_epoch!=last_epoch || stage_id>last_id) && stage_kind>=1 && stage_kind<=3 &&
  stage_count>=12 && stage_count<=534 && stage_delay>=4 && stage_duration!=0 && !proposed_deadline[64] &&
  stage_identity[255:219]==0 && stage_identity[218:187]!=0 && stage_identity[186:155]!=0 &&
  stage_peer_epoch!=0 && stage_identity[154:123]==stage_peer_epoch && stage_identity[122:120]==0 && stage_identity[119:88]>last_generation && stage_identity[7:0]<=1)===1'b1;
 wire proof_ok=(proof_mask==11'h7ff && proof_epoch==bound_epoch && proof_id==bound_id &&
  proof_counts=={a_count,b_count} && proof_identity===bound_identity)===1'b1;
 assign registered_ready=active && !closed && !fault_latched && !external_fault && a_path_ready && b_path_ready &&
  evidence_epoch==bound_epoch && registration_mask==17'h1ffff && a_count==0 && b_count==0 && a_errors==0 && b_errors==0;
 assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !s_axi_rvalid;
 task fail;input [7:0] code;
 begin fault_latched<=1;first_fault<=code;end endtask
 task reject_event;
 begin rejected_valid<=1;rejected_lane<=!a_valid && !a_error;
  rejected_has_byte<=a_valid || (!a_error && b_valid);
  rejected_data<=a_valid ? a_data : (!a_error && b_valid) ? b_data : 8'd0;
  rejected_flags<=a_valid || a_error ? a_flags : b_flags;rejected_tick<=tick;
 end endtask
 always @* begin
  read_value=0;read_resp=0;proposed_reg_credit=0;proposed_meta_credit=0;
  proposed_snap_credit=0;proposed_sample=0;proposed_lane=0;proposed_index=0;proposed_part=0;index=0;part=0;
  case(s_axi_araddr)
   15'h000:read_value=32'h48305232; // H0R2
   15'h004:read_value={27'd0,registered_ready,(!active && !fault_latched),fault_latched,closed,active};
   15'h008:begin read_value={16'd0,a_count};proposed_meta_credit=24'h400000;end
   15'h00c:begin read_value={16'd0,b_count};proposed_meta_credit=24'h800000;end
   15'h010:read_value={17'd0,stage_mask};
   15'h014:read_value=release_count;
   15'h018:read_value={15'd0,registration_mask};
   15'h01c:read_value={24'd0,first_fault};
   15'h020:read_value={7'd0,archive_meta_mask};
   15'h024:read_value={a_delivered,b_delivered};
   15'h100:begin read_value=bound_epoch;proposed_reg_credit=1;end
   15'h104:begin read_value=bound_id;proposed_reg_credit=2;end
   15'h108:begin read_value={30'd0,bound_kind};proposed_reg_credit=4;end
   15'h10c:begin read_value={16'd0,expected_count};proposed_reg_credit=8;end
   15'h130:begin read_value=start_tick[63:32];proposed_reg_credit=16'h1000;end
   15'h134:begin read_value=start_tick[31:0];proposed_reg_credit=16'h2000;end
   15'h138:begin read_value=deadline_tick[63:32];proposed_reg_credit=16'h4000;end
   15'h13c:begin read_value=deadline_tick[31:0];proposed_reg_credit=16'h8000;end
   15'h140:begin read_value=a_errors;proposed_meta_credit=24'h010000;end
   15'h144:begin read_value=b_errors;proposed_meta_credit=24'h020000;end
   15'h148:begin read_value=a_first_error[63:32];proposed_meta_credit=24'h040000;end
   15'h14c:begin read_value=a_first_error[31:0];proposed_meta_credit=24'h080000;end
   15'h150:begin read_value=b_first_error[63:32];proposed_meta_credit=24'h100000;end
   15'h154:begin read_value=b_first_error[31:0];proposed_meta_credit=24'h200000;end
   15'h170:begin read_value=bound_peer_epoch;proposed_reg_credit=17'h10000;end
   15'h180:begin read_value=snap_tick[63:32];proposed_snap_credit=1;end
   15'h184:begin read_value=snap_tick[31:0];proposed_snap_credit=2;end
   15'h188:begin read_value=snap_local_epoch;proposed_snap_credit=4;end
   15'h18c:begin read_value=snap_peer_epoch;proposed_snap_credit=8;end
   15'h190:begin read_value=snap_record_id;proposed_snap_credit=16;end
   15'h194:begin read_value=snap_seq;proposed_snap_credit=32;end
   15'h198:begin read_value=snap_flags;proposed_snap_credit=64;end
   15'h19c:begin read_value=CLOCK_HZ;proposed_snap_credit=128;end
   15'h1a0:read_value={30'd0,snap_live,snap_valid};
   15'h1a4:read_value={24'd0,snap_mask};
   15'h158:read_value={17'd0,rejected_valid,rejected_lane,rejected_has_byte,rejected_flags,rejected_data};
   15'h15c:read_value=rejected_tick[63:32];
   15'h160:read_value=rejected_tick[31:0];
   default:begin
    if(s_axi_araddr>=15'h110 && s_axi_araddr<=15'h12c)begin
     read_value=bound_identity[255-((s_axi_araddr-15'h110)>>2)*32 -:32];
     proposed_reg_credit=16'd1<<(4+((s_axi_araddr-15'h110)>>2));
    end else if(s_axi_araddr>=15'h400 && s_axi_araddr<15'h2600)begin
     index=(s_axi_araddr-15'h400)>>4;part=s_axi_araddr[3:2];
     if(index<a_count && part<3)begin
      proposed_sample=1;proposed_index=index;proposed_part=part;
      case(part)0:read_value=a_ram[index][79:48];1:read_value=a_ram[index][47:16];2:read_value={a_ram[index][15:0],16'd0};endcase
     end else read_resp=2;
    end else if(s_axi_araddr>=15'h2800 && s_axi_araddr<15'h4a00)begin
     index=(s_axi_araddr-15'h2800)>>4;part=s_axi_araddr[3:2];
     if(index<b_count && part<3)begin
      proposed_sample=1;proposed_lane=1;proposed_index=index;proposed_part=part;
      case(part)0:read_value=b_ram[index][79:48];1:read_value=b_ram[index][47:16];2:read_value={b_ram[index][15:0],16'd0};endcase
     end else read_resp=2;
    end else read_resp=2;
   end
  endcase
  if(proposed_reg_credit!=0)proposed_meta_credit=proposed_reg_credit[16] ? 25'h1000000 : {9'd0,proposed_reg_credit[15:0]};
  if(s_axi_araddr[1:0]!=0 || ((proposed_reg_credit!=0 || proposed_meta_credit!=0 || proposed_sample) && !active))read_resp=2;
  if(proposed_snap_credit!=0 && !snap_valid)read_resp=2;
  if(read_resp!=0)begin proposed_snap_credit=0;read_value=0;proposed_reg_credit=0;proposed_meta_credit=0;proposed_sample=0;end
 end
 // No reset on RAM data: metadata excludes all stale entries.
 always @(posedge clk)begin
  if(rst_n && active && !closed && !fault_latched && tick>=start_tick && tick<deadline_tick)begin
   if(a_valid && a_count<544)a_ram[a_count]<={4'd0,a_data,a_flags,tick};
   if(b_valid && b_count<544)b_ram[b_count]<={4'd0,b_data,b_flags,tick};
  end
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   snap_valid<=0;snap_seq<=0;snap_local_epoch<=0;snap_peer_epoch<=0;snap_record_id<=0;snap_flags<=0;snap_tick<=0;
   snap_mask<=0;r_snap_credit<=0;stage_peer_epoch<=0;bound_peer_epoch<=0;
   active<=0;closed<=0;fault_latched<=0;first_fault<=0;tick<=0;last_tick<=0;start_tick<=0;deadline_tick<=0;
   bound_epoch<=0;bound_id<=0;bound_identity<=0;bound_kind<=0;expected_count<=0;
   a_count<=0;b_count<=0;a_errors<=0;b_errors<=0;a_first_error<=0;b_first_error<=0;
   rejected_valid<=0;rejected_lane<=0;rejected_has_byte<=0;rejected_data<=0;rejected_flags<=0;rejected_tick<=0;
   last_generation<=0;last_id<=0;last_epoch<=0;release_count<=0;registration_mask<=0;archive_meta_mask<=0;
   a_delivered<=0;b_delivered<=0;stage_epoch<=0;stage_id<=0;stage_kind<=0;stage_count<=0;stage_delay<=0;stage_duration<=0;stage_identity<=0;stage_mask<=0;
   proof_epoch<=0;proof_id<=0;proof_counts<=0;proof_identity<=0;proof_mask<=0;
   have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
   r_reg_credit<=0;r_meta_credit<=0;r_sample<=0;r_lane<=0;r_index<=0;r_part<=0;
   for(i=0;i<544;i=i+1)begin a_read_mask[i]<=0;b_read_mask[i]<=0;end
  end else begin
   tick<=tick+1'b1;last_tick<=tick;
   if(!fault_latched)begin
    if(external_fault)fail(1);
    else if(active && evidence_epoch!=bound_epoch)fail(2);
    else if(active && closed && (a_valid || b_valid || a_error || b_error))begin reject_event;fail(5);end
    else if(active && !closed)begin
     if(tick>=deadline_tick)begin closed<=1;archive_meta_mask<=0;
      if(a_valid || b_valid || a_error || b_error)begin reject_event;fail(5);end
     end
     else if((a_valid || b_valid || a_error || b_error) && tick<start_tick)begin reject_event;fail(3);end
     else if((a_valid && a_count==544)||(b_valid && b_count==544))begin reject_event;fail(4);end
     else if((a_error && !a_valid)||(b_error && !b_valid))begin
      reject_event;fail(6);
      if(a_error)begin a_errors<=a_errors+1'b1;if(a_errors==0)a_first_error<=tick;end
      if(b_error)begin b_errors<=b_errors+1'b1;if(b_errors==0)b_first_error<=tick;end
     end
     else begin
      if(a_valid)a_count<=a_count+1'b1;
      if(b_valid)b_count<=b_count+1'b1;
      if(a_error || (a_valid && a_flags!=0))begin a_errors<=a_errors+1'b1;if(a_errors==0)a_first_error<=tick;end
      if(b_error || (b_valid && b_flags!=0))begin b_errors<=b_errors+1'b1;if(b_errors==0)b_first_error<=tick;end
     end
    end
   end
   if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
   if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready)begin
    s_axi_rvalid<=0;snap_mask<=snap_mask|r_snap_credit;
    if(active)registration_mask<=registration_mask|r_reg_credit;
    if(active && closed)begin
     archive_meta_mask<=archive_meta_mask|r_meta_credit;
     if(r_sample)begin
      if(!r_lane)begin
       if(!a_read_mask[r_index][r_part] && (a_read_mask[r_index]|(3'b001<<r_part))==7)a_delivered<=a_delivered+1'b1;
       a_read_mask[r_index][r_part]<=1;
      end else begin
       if(!b_read_mask[r_index][r_part] && (b_read_mask[r_index]|(3'b001<<r_part))==7)b_delivered<=b_delivered+1'b1;
       b_read_mask[r_index][r_part]<=1;
      end
     end
    end
   end
   if(s_axi_arvalid && s_axi_arready)begin
    s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_resp;r_reg_credit<=proposed_reg_credit;
    r_snap_credit<=proposed_snap_credit;r_meta_credit<=proposed_meta_credit;r_sample<=proposed_sample;r_lane<=proposed_lane;r_index<=proposed_index;r_part<=proposed_part;
   end
   if(have_aw && have_w && !s_axi_bvalid)begin
    have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
    if(wstrb==15 && awaddr==15'h07c && wdata==1 && active && !s_axi_rvalid && !s_axi_arvalid &&
     (!snap_valid || snap_mask==8'hff) && snap_seq!=32'hffffffff)begin
     snap_valid<=1;snap_seq<=snap_seq+1'b1;snap_tick<=tick;snap_local_epoch<=evidence_epoch;
     snap_peer_epoch<=bound_peer_epoch;snap_record_id<=bound_id;snap_mask<=0;
     snap_flags<={27'd0,current_window_open,registered_ready,
      (fault_latched || external_fault || evidence_epoch!=bound_epoch),closed,active};s_axi_bresp<=0;
    end else if(wstrb==15 && awaddr[1:0]==0 && !fault_latched && !external_fault)begin
     if(awaddr==15'h070 && wdata==1 && !active && stage_ok && a_path_ready && b_path_ready && !a_valid && !b_valid && !a_error && !b_error)begin
      active<=1;closed<=0;bound_peer_epoch<=stage_peer_epoch;bound_epoch<=stage_epoch;bound_id<=stage_id;bound_identity<=stage_identity;bound_kind<=stage_kind[1:0];expected_count<=stage_count[15:0];
      start_tick<=proposed_start[63:0];deadline_tick<=proposed_deadline[63:0];stage_mask<=0;proof_mask<=0;registration_mask<=0;archive_meta_mask<=0;
      a_count<=0;b_count<=0;a_errors<=0;b_errors<=0;a_first_error<=0;b_first_error<=0;a_delivered<=0;b_delivered<=0;
      for(i=0;i<544;i=i+1)begin a_read_mask[i]<=0;b_read_mask[i]<=0;end
      last_epoch<=stage_epoch;last_id<=stage_id;last_generation<=stage_identity[119:88];s_axi_bresp<=0;
     end else if(awaddr==15'h074 && wdata==1 && active && closed && evidence_epoch==bound_epoch && !a_valid && !b_valid && !a_error && !b_error && !s_axi_rvalid && !s_axi_arvalid && archive_meta_mask==25'h1ffffff && a_delivered==a_count && b_delivered==b_count && proof_ok)begin
      active<=0;closed<=0;proof_mask<=0;registration_mask<=0;release_count<=release_count+1'b1;s_axi_bresp<=0;
     end else if(active && closed)begin
      case(awaddr)
       15'h080:begin proof_epoch<=wdata;proof_mask[0]<=1;s_axi_bresp<=0;end
       15'h084:begin proof_id<=wdata;proof_mask[1]<=1;s_axi_bresp<=0;end
       15'h088:begin proof_counts<=wdata;proof_mask[2]<=1;s_axi_bresp<=0;end
       default:if(awaddr>=15'h090 && awaddr<=15'h0ac)begin proof_identity[255-((awaddr-15'h090)>>2)*32 -:32]<=wdata;proof_mask[3+((awaddr-15'h090)>>2)]<=1;s_axi_bresp<=0;end
      endcase
     end else if(!active)begin
      case(awaddr)
       15'h030:begin stage_epoch<=wdata;stage_mask[0]<=1;s_axi_bresp<=0;end
       15'h034:begin stage_id<=wdata;stage_mask[1]<=1;s_axi_bresp<=0;end
       15'h038:begin stage_kind<=wdata;stage_mask[2]<=1;s_axi_bresp<=0;end
       15'h03c:begin stage_count<=wdata;stage_mask[3]<=1;s_axi_bresp<=0;end
       15'h040:begin stage_delay<=wdata;stage_mask[4]<=1;s_axi_bresp<=0;end
       15'h044:begin stage_duration<=wdata;stage_mask[5]<=1;s_axi_bresp<=0;end
       15'h048:begin stage_peer_epoch<=wdata;stage_mask[14]<=1;s_axi_bresp<=0;end
       default:if(awaddr>=15'h050 && awaddr<=15'h06c)begin stage_identity[255-((awaddr-15'h050)>>2)*32 -:32]<=wdata;stage_mask[6+((awaddr-15'h050)>>2)]<=1;s_axi_bresp<=0;end
      endcase
     end
    end
   end
  end
 end
endmodule
