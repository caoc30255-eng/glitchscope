`timescale 1ns/1ps
// Actual profile owner + latched guard + shared range gate + real W19 UART.
// Independent center-sampling decoders verify all 278 RAW and masked bytes.
module tb_multipoint_owner_sender_v0_11;
 reg clk=0,rst_n=0,event_valid=0,launch=0,frame_abort=0,skip_last=0;
 always #10 clk=~clk;
 reg [7:0] event_type=8'h3a;
 reg [255:0] payload=0;
 wire prepared,permitted,owner_fault,commit_valid,injection_enable;
 wire [7:0] commit_type,owner_code;
 wire [255:0] commit_payload;
 wire [15:0] target_byte,phase,width;
 wire [8:0] count,saved_count,emitted;
 wire [2:0] bit_number,saved_bit;
 wire [15:0] saved_byte,saved_phase,saved_width;
 wire [31:0] programs,marks;
 localparam [255:0] ID=256'h0000000000000100070001010000000000000000182818270200000026594131;
 localparam [255:0] GUARD_ID={37'd0,32'h31415926,32'd2,32'h27182818,3'd0,32'd1,32'h01010007,8'd1,16'd7,16'd1,8'd0,8'd0};
 wire launch_accept,start_take,sender_done,raw_tx,masked_tx,active,point_mark,first_mark;
 wire busy,sender_fault,guard_fault,guard_active,saved_enable,configuration_ok;
 wire [9:0] read_addr,byte_index;
 wire [2:0] bit_index;
 wire [31:0] bit_clock,starts,dones;
 wire data_active,mask_enable;
 wire [15:0] completed;
 reg [7:0] data[0:277];
 integer expected_first=20,expected_count=0,inverted_cycles=0,point_pulses=0,first_pulses=0;
 integer raw_bytes=0,masked_bytes=0,i;
 h1_item_profile_owner_v0_1 owner(
  .clk(clk),.rst_n(rst_n),.external_fault(1'b0),.current_valid(1'b1),.current_started(1'b0),
  .new_commit(1'b0),.actual_start(launch_accept),.actual_retired(1'b0),
  .current_kind(8'd3),.current_len(16'd278),.current_identity(ID),
  .event_valid(event_valid),.event_type(event_type),.event_payload(payload),.event_ready(),
  .commit_valid(commit_valid),.commit_type(commit_type),.commit_payload(commit_payload),.commit_ready(1'b1),
  .prepared(prepared),.permitted(permitted),.injection_enable(injection_enable),.injection_count(count),
  .injection_byte(target_byte),.injection_phase(phase),.injection_width(width),.injection_bit(bit_number),
  .held_profile_payload(),.held_profile_type(),.program_count(programs),.fault(owner_fault),
  .fault_code(owner_code),.first_bad_payload());
 h1_multipoint_window_v0_1 window_gate(
  .enabled(guard_active && saved_enable && !guard_fault),.first_byte(saved_byte),.count(saved_count),
  .byte_index(byte_index),.point_mark(point_mark),.mask_enable(mask_enable),.first_mark(first_mark));
 h1_w19_frame_tx_v0_3 sender(
  .clk(clk),.rst_n(rst_n),.launch(launch),.launch_authorized(permitted),.current_valid(1'b1),
  .current_started(1'b0),.current_done(1'b0),.frame_kind(8'd3),.frame_session(32'h31415926),
  .frame_seq(32'd2),.frame_len(16'd278),.abort_request(frame_abort || guard_fault),
  .rearm_request(1'b0),.rearm_authorized(1'b0),.rearm_session(32'd0),.rearm_seq(32'd0),
  .read_addr(read_addr),.read_data(data[read_addr]),.w19_tx(raw_tx),.physical_start_take(start_take),
  .launch_accept(launch_accept),.data_bit_active(data_active),
  .mask_enable(mask_enable && !(skip_last && byte_index==expected_first+expected_count-1)),
  .mask_bit(saved_bit),.mask_phase(saved_phase),.mask_width(saved_width),
  .masked_tx(masked_tx),.mask_active(active),.mask_mark(point_mark),.frame_byte_index(byte_index),
  .data_bit_index(bit_index),.data_bit_clock(bit_clock),.busy(busy),.physical_done(sender_done),
  .completed_bytes(completed),.fault_latched(sender_fault),.start_count(starts),.done_count(dones));
 h1_payload_fault_overlay_v0_1 guard(
  .clk(clk),.rst_n(rst_n),.configure_take(launch_accept),.physical_start_take(start_take),
  .physical_done(sender_done),.frame_abort(frame_abort || sender_fault),
  .frame_kind(8'd3),.frame_len(16'd278),.frame_session(32'h31415926),.frame_seq(32'd2),
  .frame_identity(GUARD_ID),.fault_enable(injection_enable),.target_count(count),
  .target_byte(target_byte),.phase_clks(phase),.width_clks(width),.target_bit(bit_number),
  .raw_tx(raw_tx),.data_bit_active(data_active),.observed_fault_mark(point_mark),
  .byte_index(byte_index),.bit_index(bit_index),.bit_clock(bit_clock),.configuration_ok(configuration_ok),
  .w19_tx(),.fault_active(),.fault_mark(),.frame_active(guard_active),.configuration_pending(),.policy_ignored(),
  .mark_identity(),.snapshot_identity(),.saved_target_byte(saved_byte),.saved_phase(saved_phase),
  .saved_width(saved_width),.saved_target_bit(saved_bit),.saved_enable(saved_enable),
  .saved_count(saved_count),.frame_point_count(emitted),.mark_count(marks),.interface_fault(guard_fault));
 always @(posedge clk)begin
  if(!rst_n)begin inverted_cycles<=0;point_pulses<=0;first_pulses<=0;end
  else begin
   if(active)begin
    inverted_cycles<=inverted_cycles+1;
    if(byte_index<expected_first || byte_index>=expected_first+expected_count || bit_index!=0 ||
       bit_clock<15 || bit_clock>=35 || !data_active)$fatal(1,"unexpected physical inversion coordinate");
   end
   if(point_mark)point_pulses<=point_pulses+1;
   if(first_mark)begin
    first_pulses<=first_pulses+1;
    if(byte_index!=expected_first)$fatal(1,"CH2 must mark first point only");
   end
   if(masked_tx!==(raw_tx ^ active))$fatal(1,"registered physical pin XOR mismatch");
  end
 end
 task reset_all;begin
  rst_n=0;event_valid=0;launch=0;frame_abort=0;skip_last=0;#1000;rst_n=1;#1000;
 end endtask
 task make_profile;input [7:0] typ;input integer first,n,enabled;begin
  event_type=typ;
  // Replace all coordinate bytes explicitly; use the legacy reviewed context.
  payload=256'h0014000f00001400010000010007000101000000182818270200000026594131;
  payload[191:184]=enabled;
  payload[199:192]=(first>>8)&255;payload[207:200]=first&255;
  payload[215:208]=0;payload[223:216]=0;payload[231:224]=15;
  payload[239:232]=0;payload[247:240]=20;
  payload[255:248]=(typ==8'h3c ? n-1 : 0);
  if(!enabled)payload[255:192]=0;
 end endtask
 task deliver_profile;begin
  @(negedge clk);event_valid=1;@(posedge clk);#1;
  @(negedge clk);event_valid=0;#100;
 end endtask
 task receive_raw;integer j,k;reg [7:0] value;begin
  raw_bytes=0;
  for(j=0;j<278;j=j+1)begin
   @(negedge raw_tx);#500;if(raw_tx!==0)$fatal(1,"RAW start cell");
   for(k=0;k<8;k=k+1)begin #1000;value[k]=raw_tx;end
   #1000;if(raw_tx!==1)$fatal(1,"RAW stop cell");
   if(value!==data[j])$fatal(1,"RAW frame changed byte %0d",j);
   raw_bytes=raw_bytes+1;
  end
 end endtask
 task receive_masked;integer j,k;reg [7:0] value,expected;begin
  masked_bytes=0;
  for(j=0;j<278;j=j+1)begin
   @(negedge masked_tx);#500;if(masked_tx!==0)$fatal(1,"masked start cell");
   for(k=0;k<8;k=k+1)begin #1000;value[k]=masked_tx;end
   #1000;if(masked_tx!==1)$fatal(1,"masked stop cell");
   expected=data[j];
   if(j>=expected_first && j<expected_first+expected_count)expected=expected^8'h01;
   if(value!==expected)$fatal(1,"masked byte %0d got %02x expected %02x",j,value,expected);
   masked_bytes=masked_bytes+1;
  end
 end endtask
 task run_case;input [7:0] typ;input integer first,n,enabled;begin
  reset_all();expected_first=first;expected_count=enabled ? n : 0;
  make_profile(typ,first,n,enabled);deliver_profile();
  if(!prepared || !permitted || owner_fault || count!==n || commit_type!==typ || programs!==1)
   $fatal(1,"owner did not freeze exact type/range");
  deliver_profile();
  if(programs!==1 || owner_fault)$fatal(1,"identical replay changed owner count");
  fork
   receive_raw();
   receive_masked();
   begin @(negedge clk);launch=1;@(negedge clk);launch=0;wait(sender_done);end
  join
  #1000;
  if(owner_fault || sender_fault || guard_fault || completed!==278 || starts!==1 || dones!==1 ||
     raw_bytes!=278 || masked_bytes!=278 || emitted!==expected_count ||
     point_pulses!=expected_count || marks!==expected_count || inverted_cycles!=expected_count*20 ||
     first_pulses!=(expected_count!=0 ? 1 : 0))$fatal(1,"range physical count/frame completion mismatch");
  $display("MP_PASS type=%02x first=%0d points=%0d 278 RAW/masked UART bytes verified, CH2_first=%0d",typ,first,expected_count,first_pulses);
 end endtask
 initial begin
  for(i=0;i<278;i=i+1)data[i]=(i-20)&255;
  run_case(8'h3a,20,1,0);
  run_case(8'h3a,20,1,1);
  run_case(8'h3c,20,4,1);
  run_case(8'h3c,20,256,1);
  run_case(8'h3c,275,1,1);
  reset_all();make_profile(8'h3a,20,1,1);payload[255:248]=1;deliver_profile();
  if(!owner_fault || prepared || permitted)$fatal(1,"legacy reserved byte accepted");
  $display("MP_NEG_PASS legacy TYPE3A reserved byte still rejected");
  reset_all();make_profile(8'h3c,275,2,1);deliver_profile();
  if(!owner_fault || prepared)$fatal(1,"range touching CRC accepted");
  $display("MP_NEG_PASS range cannot touch CRC");
  reset_all();make_profile(8'h3c,19,4,1);deliver_profile();
  if(!owner_fault || prepared)$fatal(1,"range touching header accepted");
  reset_all();make_profile(8'h3c,20,4,1);deliver_profile();
  make_profile(8'h3c,20,5,1);deliver_profile();
  if(!owner_fault || permitted)$fatal(1,"changed held count accepted");
  $display("MP_NEG_PASS header and changed held policy rejected");
  reset_all();make_profile(8'h3c,20,4,1);deliver_profile();
  make_profile(8'h3a,20,1,1);deliver_profile();
  if(!owner_fault)$fatal(1,"cross-type replacement accepted");
  reset_all();expected_first=20;expected_count=4;
  make_profile(8'h3c,20,4,1);deliver_profile();skip_last=1;
  @(negedge clk);launch=1;@(negedge clk);launch=0;wait(sender_done);#1000;
  if(!guard_fault || emitted!==3)$fatal(1,"missing physical point did not fault at completion");
  $display("MP_NEG_PASS missing physical point faults before accepted completion");
  reset_all();make_profile(8'h3c,20,4,1);deliver_profile();
  @(negedge clk);launch=1;@(negedge clk);launch=0;
  wait(point_mark);@(negedge clk);frame_abort=1;#500;
  if(!sender_fault || dones!=0 || sender_done || raw_tx!==1 || masked_tx!==1 || first_mark)
   $fatal(1,"abort fabricated completion or left a pin asserted");
  rst_n=0;#1000;
  if(emitted!==0 || point_mark || first_mark)$fatal(1,"reset leaked point evidence");
  $display("MP_NEG_PASS active abort and reset retain no fabricated completion");
  $display("H1_MULTIPOINT_OWNER_SENDER_V0_11_PASS");
  $display("SCOPE_ACTUAL_OWNER_GUARD_RANGE_UART_1MBPS_NO_FULL_CONTROL_CDC_AXI_NO_SDF_NO_MCU_NO_HARDWARE");
  $finish;
 end
 initial begin #30000000;$fatal(1,"simulation watchdog");end
endmodule
