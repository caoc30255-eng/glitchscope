`timescale 1ns/1ps
// Saved H1 RX tuple -> immutable local binding -> one physical_done pulse.
// saved_valid must be the actual exact persisted queue-pop handshake, not
// an MMIO boolean. Common clock/reset; no wire epoch is invented.
module h1_7020_ch1_completion_match_v0_4(
 input wire clk,rst_n,
 input wire [31:0] evidence_epoch,
 input wire bind,
 input wire [31:0] bind_epoch,bind_peer_epoch,bind_record_id,bind_ticket_floor,
 input wire [255:0] bind_identity,
 input wire [15:0] bind_inner_crc,
 input wire saved_valid,
 input wire [31:0] saved_epoch,saved_ticket,
 input wire [2:0] saved_reason,
 input wire [4:0] saved_length,
 input wire [143:0] saved_raw,
 input wire retired_valid,
 input wire [31:0] retired_epoch,retired_record_id,
 input wire [255:0] retired_identity,
 input wire external_fault,
 output reg physical_done,
 output reg [255:0] done_identity,
 output reg active,accepted_seen,done_seen,fault_latched,
 output reg [7:0] first_fault,
 output reg [31:0] matched_count,
 output reg [31:0] active_epoch,active_record_id,
 output reg [255:0] active_identity
);
 reg completed_valid;
 reg [15:0] expected_crc;
 reg [31:0] ticket_floor,last_ticket,last_session,last_seq;
 reg [143:0] last_raw;
 function [15:0] status_crc;
 input [143:0] raw;
 reg [15:0] c;reg [7:0] b;integer i,j;
 begin
  c=16'hffff;
  for(i=2;i<16;i=i+1)begin
   b=raw[143-i*8 -:8];c=c^{b,8'd0};
   for(j=0;j<8;j=j+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;
  end
  status_crc=c;
 end
 endfunction
 wire [7:0] state=saved_raw[119:112];
 wire format_ok=saved_reason==1 && saved_length==18 && saved_raw[143:128]==16'ha66a &&
  saved_raw[127:120]==1 && state>=8'h80 && state<=8'h83 && saved_raw[31:24]==0 &&
  saved_raw[23:16]<=1 && saved_raw[15:0]==status_crc(saved_raw);
 wire identity_ok=saved_raw[111:80]==active_identity[218:187] &&
  saved_raw[79:48]==active_identity[186:155] && saved_raw[47:32]==expected_crc;
 wire retired_session_ready=(!active && completed_valid && state==8'h80 &&
  saved_raw[111:80]==active_identity[218:187] && saved_raw[79:48]==0 && saved_raw[47:32]==0)===1'b1;
 wire binding_ok=bind_epoch!=0 && bind_epoch==evidence_epoch && bind_peer_epoch!=0 &&
  bind_record_id!=0 && bind_identity[255:219]==0 && bind_identity[218:187]!=0 &&
  bind_identity[186:155]!=0 && bind_identity[186:155]!=32'hffffffff &&
  bind_identity[154:123]==bind_peer_epoch && bind_identity[119:88]!=0 && bind_identity[7:0]<=1 &&
  (bind_identity[218:187]!=last_session || bind_identity[186:155]>last_seq);
 task fail;input [7:0] code;
 begin fault_latched<=1;first_fault<=code;end
 endtask
 always @(posedge clk)begin
  if(!rst_n)begin
   physical_done<=0;done_identity<=0;completed_valid<=0;active<=0;accepted_seen<=0;done_seen<=0;
   fault_latched<=0;first_fault<=0;matched_count<=0;active_epoch<=0;active_record_id<=0;
   active_identity<=0;expected_crc<=0;ticket_floor<=0;last_ticket<=0;last_raw<=0;
   last_session<=0;last_seq<=0;
  end else begin
   physical_done<=0;
   if(!fault_latched)begin
    // Invalid concurrent events veto publication in this same edge.
    if(external_fault)fail(1);
    else if(active && evidence_epoch!=active_epoch)fail(2);
    else if(bind)begin
     if(active || saved_valid || retired_valid || !binding_ok)fail(3);
     else begin
      active<=1;accepted_seen<=0;done_seen<=0;completed_valid<=0;active_epoch<=bind_epoch;
      active_record_id<=bind_record_id;active_identity<=bind_identity;expected_crc<=bind_inner_crc;
      ticket_floor<=bind_ticket_floor;last_ticket<=bind_ticket_floor;last_raw<=0;
      last_session<=bind_identity[218:187];last_seq<=bind_identity[186:155];
     end
    end else if(retired_valid)begin
     if(saved_valid || !active || !done_seen || retired_epoch!=active_epoch ||
      retired_record_id!=active_record_id || retired_identity!==active_identity)fail(4);
     else begin active<=0;accepted_seen<=0;done_seen<=0;completed_valid<=1;end
    end else if(saved_valid)begin
     // Before the first binding, HELLO READY is raw advisory only. Session
     // authorization/credit belongs to the software HELLO ledger, not this
     // matcher. It must never create a binding, completion or retired history.
     if(!active && !completed_valid && state==8'h80 && saved_raw[79:48]==0 &&
        saved_raw[47:32]==0 && saved_raw[111:80]!=0 && format_ok &&
        evidence_epoch!=0 && saved_epoch==evidence_epoch)begin
      if(saved_ticket==last_ticket && saved_ticket!=0 && saved_raw===last_raw)begin end
      else if(saved_ticket==0 || saved_ticket<=last_ticket)fail(6);
      else begin last_ticket<=saved_ticket;last_raw<=saved_raw;end
     end else if(saved_epoch!=active_epoch || evidence_epoch!=active_epoch || !format_ok || (!identity_ok && !retired_session_ready))fail(5);
     else if(!active)begin
      // Only exact previous retired generation advisory/replay is permissible.
      // READY credit0 conveys no capacity. Software separately requires credit1.
      if(!completed_valid || (state!=8'h80 && state!=8'h83))fail(5);
      else if(saved_ticket==last_ticket && saved_ticket>ticket_floor && saved_raw===last_raw)begin end
      else if(saved_ticket<=last_ticket)fail(6);
      else begin last_ticket<=saved_ticket;last_raw<=saved_raw;end
     end else if(saved_ticket==last_ticket && saved_ticket>ticket_floor && saved_raw===last_raw)begin
      // Exact held snapshot replay has no second semantic effect.
     end else if(saved_ticket<=last_ticket)fail(6);
     else if(state==8'h82 || (state==8'h83 && !accepted_seen) || (state==8'h81 && done_seen))fail(7);
     else begin
      last_ticket<=saved_ticket;last_raw<=saved_raw;
      if(state==8'h81)accepted_seen<=1;
      if(state==8'h83 && !done_seen)begin
       physical_done<=1;done_identity<=active_identity;done_seen<=1;matched_count<=matched_count+1'b1;
      end
     end
    end
   end
  end
 end
endmodule
