`timescale 1ns/1ps
// Real byte parser/router/commit owner/profile owner and physical ACK UART.
// Byte input is a fixture, not an RX-pin/CDC/full-board simulation.
module tb_multipoint_control_profile_v0_11;
 reg clk=0,rst_n=0,byte_valid=0;reg [7:0] byte_data=0;
 always #5 clk=~clk;
 wire packet_valid,parser_error,event_valid,event_ready,route_fault;
 wire [7:0] packet_type,packet_len,event_type;
 wire [255:0] packet_payload,event_payload;
 wire store_valid,store_result_valid,ack_valid,ack_take,ack_done,commit_fault,tx_fault,tx_pin;
 wire event_start,event_accepted,event_done,event_pin,event_error,arbiter_fault;
 wire [7:0] event_error_code,arbiter_fault_code;
 assign tx_fault=event_error || arbiter_fault;
 wire [7:0] store_type,result_type,ack_type;
 wire [255:0] store_payload,result_payload,ack_payload;
 wire owner_ready,owner_fault,prepared;wire [31:0] program_count;
 wire [8:0] count;wire enabled;
 localparam [255:0] ID=256'h0000000000000100070001010000000000000000182818270200000026594131;
 ctrl_packet_parser_runtime_v0_1 #(.MAX_PAYLOAD(32),.BYTE_TIMEOUT_CLKS(10000000)) parser(
  .clk(clk),.rst_n(rst_n),.byte_valid(byte_valid),.byte_data(byte_data),.packet_valid(packet_valid),
  .packet_type(packet_type),.packet_len(packet_len),.packet_payload(packet_payload),.parser_error(parser_error),
  .error_code(),.parser_idle());
 h1_p1_control_event_router_profile_v0_1 router(
  .clk(clk),.rst_n(rst_n),.packet_valid(packet_valid),.packet_type(packet_type),.packet_len(packet_len),
  .packet_payload(packet_payload),.event_valid(event_valid),.event_ready(event_ready),
  .event_type(event_type),.event_payload(event_payload),.legacy_valid(),.legacy_ready(1'b1),
  .legacy_type(),.legacy_len(),.legacy_payload(),.route_fault(route_fault),.route_error(),.first_type());
 h1_p1_event_commit_ack_profile_v0_1 commit_owner(
  .clk(clk),.rst_n(rst_n),.rx_valid(event_valid),.rx_type(event_type),.rx_payload(event_payload),
  .rx_ready(event_ready),.store_valid(store_valid),.store_type(store_type),.store_payload(store_payload),
  .store_result_valid(store_result_valid),.store_result_type(result_type),.store_result_payload(result_payload),
  .ack_valid(ack_valid),.ack_type(ack_type),.ack_payload(ack_payload),.ack_take(ack_take),.ack_done(ack_done),
  .fault(commit_fault),.fault_code());
 h1_item_profile_owner_v0_1 #(.CLK_HZ(50000000),.BAUD(1000000)) profile_owner(
  .clk(clk),.rst_n(rst_n),.external_fault(1'b0),.current_valid(1'b1),.current_started(1'b0),
  .new_commit(1'b0),.actual_start(1'b0),.actual_retired(1'b0),.current_kind(8'd3),.current_len(16'd278),
  .current_identity(ID),.event_valid(store_valid),.event_type(store_type),.event_payload(store_payload),
  .event_ready(owner_ready),.commit_valid(store_result_valid),.commit_type(result_type),
  .commit_payload(result_payload),.commit_ready(store_result_valid && store_valid && result_type==store_type && result_payload==store_payload),
  .prepared(prepared),.permitted(),.injection_enable(enabled),.injection_count(count),
  .injection_byte(),.injection_phase(),.injection_width(),.injection_bit(),.held_profile_payload(),
  .held_profile_type(),.program_count(program_count),.fault(owner_fault),.fault_code(),.first_bad_payload());
 h1_p1_event_uart_tx_mmio_v0_1 #(.CLK_HZ(100000000),.BAUD(230400),.IS_AX(1)) reply_uart(
  .clk(clk),.rst_n(rst_n),.start(event_start),.event_type(ack_type),.event_payload(ack_payload),
  .accepted(event_accepted),.done(event_done),.busy(),.tx_pin(event_pin),
  .error(event_error),.error_code(event_error_code));
 // Same arbiter as production: held valid becomes exactly one start pulse,
 // take is returned only on UART acceptance, completion follows physical done.
 h1_p1_control_tx_arbiter_v0_1 arbiter(
  .clk(clk),.rst_n(rst_n),.legacy_valid(1'b0),.legacy_start(),.legacy_accepted(1'b0),
  .legacy_done(1'b0),.legacy_pin(1'b1),.legacy_take(),.legacy_complete(),
  .event_valid(ack_valid),.event_start(event_start),.event_accepted(event_accepted),
  .event_done(event_done),.event_pin(event_pin),.event_take(ack_take),.event_complete(ack_done),
  .tx_pin(tx_pin),.busy(),.fault(arbiter_fault),.fault_code(arbiter_fault_code));
 reg [7:0] request[0:38],expected[0:38];reg [255:0] payload;
 integer i,replies=0;reg [15:0] crc;
 function [15:0] crc_next;input [15:0] c0;input [7:0] b;reg [15:0] c;integer j;begin
  c=c0^{b,8'd0};for(j=0;j<8;j=j+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_next=c;
 end endfunction
 task reset_all;begin rst_n=0;byte_valid=0;#1000;rst_n=1;#1000;end endtask
 task build_packet;input [7:0] typ;input integer n;begin
  payload=256'h0014000f00001400010000010007000101000000182818270200000026594131;
  payload[255:248]=(typ==8'h3c ? n-1 : 0);
  request[0]=8'ha5;request[1]=8'h5a;request[2]=1;request[3]=typ;request[4]=32;
  for(i=0;i<32;i=i+1)request[5+i]=payload[i*8+:8];
  crc=16'hffff;for(i=2;i<37;i=i+1)crc=crc_next(crc,request[i]);
  request[37]=crc[15:8];request[38]=crc[7:0];
  for(i=0;i<39;i=i+1)expected[i]=request[i];expected[3]=typ+8'h40;
  crc=16'hffff;for(i=2;i<37;i=i+1)crc=crc_next(crc,expected[i]);
  expected[37]=crc[15:8];expected[38]=crc[7:0];
 end endtask
 task send_packet;integer j;begin
  for(j=0;j<39;j=j+1)begin
   @(negedge clk);byte_valid=1;byte_data=request[j];@(negedge clk);byte_valid=0;
   repeat(10)@(negedge clk);
  end
 end endtask
 task receive_ack;integer j,k;reg [7:0] b;begin
  for(j=0;j<39;j=j+1)begin
   @(negedge tx_pin);#2170;if(tx_pin!==0)$fatal(1,"ACK start bit");
   for(k=0;k<8;k=k+1)begin #4340;b[k]=tx_pin;end
   #4340;if(tx_pin!==1 || b!==expected[j])$fatal(1,"ACK byte %0d mismatch",j);
  end
  replies=replies+1;
 end endtask
 initial begin
  reset_all();build_packet(8'h3c,4);request[38]=request[38]^1;
  send_packet();#10000;
  if(prepared || program_count || tx_pin!==1 || route_fault || commit_fault || owner_fault)
   $fatal(1,"bad CRC created a profile or response");
  $display("MP_CONTROL_PASS bad CRC creates no profile or ACK");
  build_packet(8'h3c,4);
  fork send_packet();receive_ack();join
  wait(ack_done);#1000;
  if(!prepared || !enabled || count!==4 || program_count!==1 || route_fault || commit_fault || owner_fault || tx_fault)
   $fatal(1,"TYPE3C full exact store/ACK failed prepared=%b enabled=%b count=%0d programs=%0d route=%b commit=%b owner=%b UART=%b UART_code=%0d arbiter=%b arbiter_code=%0d",prepared,enabled,count,program_count,route_fault,commit_fault,owner_fault,event_error,event_error_code,arbiter_fault,arbiter_fault_code);
  $display("MP_CONTROL_PASS actual parser/router/profile store yields exact physical 39B ACK7C");
  fork send_packet();receive_ack();join
  wait(ack_done);#1000;
  if(program_count!==1 || commit_fault || owner_fault)$fatal(1,"duplicate TYPE3C changed policy");
  $display("MP_CONTROL_PASS exact replay ACK without duplicate programming");
  build_packet(8'h3c,5);send_packet();#10000;
  if(!commit_fault || program_count!==1 || count!==4)$fatal(1,"changed count failed to fault");
  $display("MP_CONTROL_PASS changed count cannot replace held tuple");
  reset_all();build_packet(8'h3a,1);
  fork send_packet();receive_ack();join
  wait(ack_done);#1000;
  if(count!==1 || program_count!==1 || owner_fault || tx_fault)$fatal(1,"legacy TYPE3A regression");
  $display("MP_CONTROL_PASS legacy TYPE3A still returns exact ACK7A");
  reset_all();
  if(prepared || program_count || tx_pin!==1)$fatal(1,"reset did not clear policy/output");
  $display("H1_MULTIPOINT_CONTROL_PROFILE_V0_11_PASS replies=%0d",replies);
  $display("SCOPE_ACTUAL_BYTE_PARSER_ROUTER_COMMIT_PROFILE_ACK_UART_NO_RX_PIN_NO_CDC_NO_AXI_NO_START_NO_HARDWARE");
  $finish;
 end
 initial begin #12000000;$fatal(1,"control simulation watchdog");end
endmodule
