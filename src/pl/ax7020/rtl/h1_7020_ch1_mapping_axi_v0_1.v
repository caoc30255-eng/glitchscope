`timescale 1ns/1ps
// Immutable owner mapping. No MMIO command can assert physical completion.
module h1_7020_ch1_mapping_axi_v0_1(
 input wire clk,rst_n,external_fault,runtime_busy,status_pending,
 input wire [31:0] evidence_epoch,
 input wire consume,
 input wire [31:0] consume_epoch,consume_record_id,
 input wire [255:0] consume_identity,
 input wire retired,
 input wire [31:0] retired_epoch,retired_record_id,
 input wire [255:0] retired_identity,
 output wire mapping_valid,
 output reg [31:0] mapping_epoch,mapping_peer_epoch,mapping_record_id,
 output reg [255:0] mapping_identity,
 output reg [15:0] mapping_inner_crc,
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
 localparam EMPTY=0,READY=1,ACTIVE=2;
 reg [1:0] state;
 reg [31:0] stage_epoch,stage_peer,stage_id,stage_crc;
 reg [255:0] stage_identity;
 reg [11:0] stage_mask;
 reg [31:0] last_generation,last_epoch,last_id,consume_count,retire_count;
 reg have_aw,have_w;
 reg [11:0] awaddr;
 reg [31:0] wdata;
 reg [3:0] wstrb;
 reg [31:0] read_value;
 reg [1:0] read_response;
 wire ready_ok=(stage_mask==12'hfff && stage_epoch!=0 && stage_epoch==evidence_epoch &&
  stage_peer!=0 && stage_id!=0 && (stage_epoch!=last_epoch || stage_id>last_id) && stage_crc[31:16]==0 &&
  stage_identity[255:219]==0 && stage_identity[218:187]!=0 && stage_identity[186:155]!=0 &&
  stage_identity[186:155]!=32'hffffffff && stage_identity[154:123]==stage_peer &&
  stage_identity[119:88]>last_generation && stage_identity[7:0]<=1)===1'b1;
 wire consume_ok=(state==READY && consume_epoch==mapping_epoch && consume_record_id==mapping_record_id &&
  consume_identity===mapping_identity)===1'b1;
 wire retire_ok=(state==ACTIVE && retired_epoch==mapping_epoch && retired_record_id==mapping_record_id &&
  retired_identity===mapping_identity)===1'b1;
 assign mapping_valid=state!=EMPTY && !fault_latched;
 assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !s_axi_rvalid;
 task fail;input [7:0] code;
 begin fault_latched<=1;first_fault<=code;end endtask
 always @* begin
  read_value=0;read_response=0;
  case(s_axi_araddr)
   12'h000:read_value=32'h48314d31; // H1M1
   12'h004:read_value={27'd0,status_pending,runtime_busy,fault_latched,state==ACTIVE,state==READY};
   12'h008:read_value=evidence_epoch;
   12'h00c:read_value={24'd0,first_fault};
   12'h010:read_value={20'd0,stage_mask};
   12'h014:read_value=consume_count;
   12'h018:read_value=retire_count;
   12'h100:read_value=mapping_epoch;
   12'h104:read_value=mapping_peer_epoch;
   12'h108:read_value=mapping_record_id;
   12'h10c:read_value={16'd0,mapping_inner_crc};
   default:if(s_axi_araddr>=12'h110 && s_axi_araddr<=12'h12c)
    read_value=mapping_identity[255-((s_axi_araddr-12'h110)>>2)*32 -:32];else read_response=2;
  endcase
  if(s_axi_araddr[1:0]!=0)read_response=2;
  if(read_response!=0)read_value=0;
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   state<=EMPTY;stage_epoch<=0;stage_peer<=0;stage_id<=0;stage_crc<=0;stage_identity<=0;stage_mask<=0;
   mapping_epoch<=0;mapping_peer_epoch<=0;mapping_record_id<=0;mapping_identity<=0;mapping_inner_crc<=0;
   last_generation<=0;last_epoch<=0;last_id<=0;consume_count<=0;retire_count<=0;
   fault_latched<=0;first_fault<=0;have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
   s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
  end else begin
   if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
   if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arvalid && s_axi_arready)begin s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_response;end
   if(!fault_latched)begin
    if(external_fault)fail(1);
    else if(state!=EMPTY && evidence_epoch!=mapping_epoch)fail(2);
    else if(consume && retired)fail(3);
    else if(consume)begin if(!consume_ok)fail(4);else begin state<=ACTIVE;consume_count<=consume_count+1'b1;end end
    else if(retired)begin if(!retire_ok)fail(5);else begin state<=EMPTY;stage_mask<=0;retire_count<=retire_count+1'b1;end end
   end
   if(have_aw && have_w && !s_axi_bvalid)begin
    have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
    if(wstrb==15 && awaddr[1:0]==0 && !fault_latched && !external_fault && !consume && !retired &&
     (state==EMPTY || evidence_epoch==mapping_epoch))begin
     if(awaddr==12'h060 && wdata==1)begin
      if(state==READY)s_axi_bresp<=0; // cached commit retry, no restaging
      else if(state==EMPTY && !runtime_busy && !status_pending && ready_ok)begin
       state<=READY;mapping_epoch<=stage_epoch;mapping_peer_epoch<=stage_peer;mapping_record_id<=stage_id;
       mapping_identity<=stage_identity;mapping_inner_crc<=stage_crc[15:0];stage_mask<=0;
       last_generation<=stage_identity[119:88];last_epoch<=stage_epoch;last_id<=stage_id;s_axi_bresp<=0;
      end
     end else if(awaddr==12'h064 && wdata==1 && state==READY && !runtime_busy && !status_pending)begin
      state<=EMPTY;stage_mask<=0;s_axi_bresp<=0; // consumes namespace; never undoes a live ARM
     end else if(state==EMPTY && !runtime_busy)begin
      case(awaddr)
       12'h030:begin stage_epoch<=wdata;stage_mask[0]<=1;s_axi_bresp<=0;end
       12'h034:begin stage_peer<=wdata;stage_mask[1]<=1;s_axi_bresp<=0;end
       12'h038:begin stage_id<=wdata;stage_mask[2]<=1;s_axi_bresp<=0;end
       12'h03c:begin stage_crc<=wdata;stage_mask[3]<=1;s_axi_bresp<=0;end
       default:if(awaddr>=12'h040 && awaddr<=12'h05c)begin
        stage_identity[255-((awaddr-12'h040)>>2)*32 -:32]<=wdata;
        stage_mask[4+((awaddr-12'h040)>>2)]<=1;s_axi_bresp<=0;
       end
      endcase
     end
    end
   end
  end
 end
endmodule
