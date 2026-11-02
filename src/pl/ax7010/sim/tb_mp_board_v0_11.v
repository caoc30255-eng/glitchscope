`timescale 1ns/1ps
// New candidate full RTL: eight external pins, actual MMCM/CDC/AXI; no private force/deposit.
module tb_mp_board_v0_11;
 localparam integer CTRL_BIT_NS=4340;
 reg pl_clk_50m=0,key_n=0,h1_rx_pin=1,ctrl_rx_pin=1;
 always #10 pl_clk_50m=~pl_clk_50m;
 wire h1_tx_pin,ctrl_tx_pin,w19_tx,fault_mark;
 h1_ax7010_uart_cdc_sync_board_top_v0_7 dut(.pl_clk_50m(pl_clk_50m),.key_n(key_n),
  .h1_rx_pin(h1_rx_pin),.ctrl_rx_pin(ctrl_rx_pin),.h1_tx_pin(h1_tx_pin),
  .ctrl_tx_pin(ctrl_tx_pin),.w19_tx(w19_tx),.fault_mark(fault_mark));
 reg [7:0] request1[0:38],request2[0:38],reply1[0:38],reply2[0:38],expected[0:38];
 reg [7:0] ext_request[0:1013],ext_reply[0:1013];
 reg [7:0] reset_request[0:116],reset_reply[0:116];
 reg [7:0] mp_request[0:623],mp_reply[0:623];
 integer operation;
 integer i,byte_index=0,reply_frames=0,reset_epoch=0,case_id=0;
 reg response_active=0,monitor_quiet=0;
 always @(posedge pl_clk_50m) if(monitor_quiet)begin
  if(w19_tx!==1'b1 || fault_mark!==1'b0 || h1_tx_pin!==1'b1)
   $fatal(1,"unexpected H1/W19/mark effect without ARM or START case=%0d",case_id);
 end
 always @(negedge ctrl_tx_pin) begin:decode_byte
  integer bit_no,byte_epoch;reg [7:0] value;
  byte_epoch=reset_epoch;response_active=1;value=0;
  #(CTRL_BIT_NS/2);
  if(byte_epoch!=reset_epoch)disable decode_byte;
  if(ctrl_tx_pin!==0)$fatal(1,"false control start");
  for(bit_no=0;bit_no<8;bit_no=bit_no+1)begin
   #CTRL_BIT_NS;if(byte_epoch!=reset_epoch)disable decode_byte;
   value[bit_no]=ctrl_tx_pin;
  end
  #CTRL_BIT_NS;if(byte_epoch!=reset_epoch)disable decode_byte;
  if(ctrl_tx_pin!==1)$fatal(1,"control final stop error");
  if(value!==expected[byte_index])$fatal(1,"routed control byte=%0d got=%02x expected=%02x case=%0d",byte_index,value,expected[byte_index],case_id);
  byte_index=byte_index+1;response_active=0;
  if(byte_index==39)begin byte_index=0;reply_frames=reply_frames+1;end
 end
 task send_byte;input [7:0] value;integer b;
 begin ctrl_rx_pin=0;#CTRL_BIT_NS;
  for(b=0;b<8;b=b+1)begin ctrl_rx_pin=value[b];#CTRL_BIT_NS;end
  ctrl_rx_pin=1;#CTRL_BIT_NS;
 end endtask
 task select_reply;input second;integer n;
 begin for(n=0;n<39;n=n+1)expected[n]=second?reply2[n]:reply1[n];end endtask
 task send_probe;input second,bad_crc;integer n;reg [7:0] value;
 begin for(n=0;n<39;n=n+1)begin
  value=second?request2[n]:request1[n];if(bad_crc && n==38)value=value^8'h01;send_byte(value);
 end end endtask
 task send_probe_with_host_gap;integer n;
 begin
  for(n=0;n<39;n=n+1)begin
   if(n==21)begin
    #25000000;
    if(reply_frames!=0 || byte_index!=0 || response_active)
     $fatal(1,"partial serial command created reply before CRC completion");
   end
   send_byte(request1[n]);
  end
 end endtask
 task wait_reply;input integer target;integer limit;
 begin limit=0;while(reply_frames<target && limit<500)begin #100000;limit=limit+1;end
  if(reply_frames!=target || byte_index!=0)$fatal(1,"routed reply accounting case=%0d got=%0d expected=%0d",case_id,reply_frames,target);
  #(CTRL_BIT_NS*2);
 end endtask
 task send_extended;input integer index;integer n;begin
  for(n=0;n<39;n=n+1)expected[n]=ext_reply[index*39+n];
  for(n=0;n<39;n=n+1)send_byte(ext_request[index*39+n]);
  wait_reply(4+index);
 end endtask
 task send_after_reset;input integer index;integer n;begin
  for(n=0;n<39;n=n+1)expected[n]=reset_reply[index*39+n];
  for(n=0;n<39;n=n+1)send_byte(reset_request[index*39+n]);
  wait_reply(42+index);
 end endtask
 task send_mp;input integer index,target;integer n;begin
  for(n=0;n<39;n=n+1)expected[n]=mp_reply[index*39+n];
  for(n=0;n<39;n=n+1)send_byte(mp_request[index*39+n]);
  wait_reply(target);
 end endtask
 initial begin #(64'd300000000);$fatal(1,"board prestart pin watchdog (300ms)");end
 initial begin
  $readmemh("vectors/mp_requests.mem",mp_request);
  $readmemh("vectors/mp_replies.mem",mp_reply);
  $readmemh("vectors/reset_requests.mem",reset_request);
  $readmemh("vectors/reset_replies.mem",reset_reply);
  $readmemh("vectors/prestart_requests.mem",ext_request);
  $readmemh("vectors/prestart_replies.mem",ext_reply);
  $readmemh("vectors/probe_request_epoch1.mem",request1,0,38);
  $readmemh("vectors/probe_request_epoch2.mem",request2,0,38);
  $readmemh("vectors/probe_reply_epoch1.mem",reply1,0,38);
  $readmemh("vectors/probe_reply_epoch2.mem",reply2,0,38);
  for(i=0;i<39;i=i+1)if((^{request1[i],request2[i],reply1[i],reply2[i]})===1'bx)$fatal(1,"missing independent pin golden");
  for(i=0;i<1014;i=i+1)if((^{ext_request[i],ext_reply[i]})===1'bx)$fatal(1,"missing extended control golden");
  for(i=0;i<117;i=i+1)if((^{reset_request[i],reset_reply[i]})===1'bx)$fatal(1,"missing reset golden");
  #1000;key_n=1;#200000;monitor_quiet=1;select_reply(0);
  case_id=1;send_probe(0,1);#4000000;
  if(reply_frames!=0 || response_active || byte_index!=0)$fatal(1,"bad CRC generated physical reply");
  $display("N1_PASS actual production-rate control bad CRC silent before admission");
  case_id=2;send_probe_with_host_gap;wait_reply(1);
  $display("P1_PASS actual 230400 UART command with25ms idle before byte22 reaches MMCM/CDC/AXI and exact CRC-valid 39B reply; no reply from partial prefix");
  $display("N2_PASS production eight-pin MMCM/CDC/MMIO/actual UART returns exact 39B H5E1 identity");
  case_id=3;send_probe(0,0);wait_reply(2);
  $display("N3_PASS exact request replay returns identical physical reply without unauthorized H1/W19 effect");
  case_id=4;send_probe(0,0);wait(response_active);#(CTRL_BIT_NS*2);
  // Decoder cancels only the explicitly aborted epoch, never forgives a live mismatch.
  reset_epoch=reset_epoch+1;key_n=0;ctrl_rx_pin=1;byte_index=0;response_active=0;
  #10;if(ctrl_tx_pin!==1 || h1_tx_pin!==1 || w19_tx!==1 || fault_mark!==0)$fatal(1,"key reset failed to clamp actual pins");
  #100000;key_n=1;#200000;
  if(reply_frames!=2 || byte_index!=0)$fatal(1,"old partial reply became a completed fresh frame");
  $display("N4_PASS key reset aborts actual partial reply and clamps pins, no fabricated completed old frame");
  case_id=5;select_reply(1);send_probe(1,0);wait_reply(3);#4000000;
  if(reply_frames!=3 || byte_index!=0 || response_active)$fatal(1,"ghost reply after fresh epoch");
  $display("N5_PASS fresh transport epoch returns one exact routed identity reply after reset");
  for(operation=0;operation<26;operation=operation+1)begin
   case_id=100+operation;send_extended(operation);
   if(operation==1)$display("S1_PASS actual 230400 control UART returns HPQ1 ID and denies unauthorized basis");
   if(operation==9)$display("S2_PASS actual shared namespace authorization and H5E1 capacity status221; no START");
  end
  $display("S3_PASS full 12-word real prestart basis delivered, generation1 and zero current identity");
  $display("S4_PASS same eight physical pins and MMCM, no H1/W19/mark publication from read-only observer");
  for(operation=0;operation<11;operation=operation+1)begin
   case_id=300+operation;send_mp(operation,30+operation);
  end
  $display("MP_BOARD_PASS physical 230400 UART through MMCM/CDC/AXI returns MPG1, zero fresh counts/status/identity, no START");
  reset_epoch=reset_epoch+1;key_n=0;ctrl_rx_pin=1;byte_index=0;response_active=0;
  #10;if(ctrl_tx_pin!==1 || h1_tx_pin!==1 || w19_tx!==1 || fault_mark!==0)$fatal(1,"new observer reset failed pin clamp");
  #100000;key_n=1;#200000;
  case_id=200;select_reply(0);send_probe(0,0);wait_reply(41);
  for(operation=0;operation<3;operation=operation+1)begin
   case_id=201+operation;send_after_reset(operation);
  end
  $display("S5_PASS common physical KEY reset clears real HPQ1 snapshot and H5E1 namespace; fresh UART probe only");
  for(operation=11;operation<16;operation=operation+1)begin
   case_id=400+operation;send_mp(operation,34+operation);
  end
  $display("MP_BOARD_PASS KEY reset clears namespace; MPG1 visible, unauthorized stats/identity and capability writes return exact SLVERR");
  $display("H1_MULTIPOINT_BOARD_CONTROL_V0_11_PASS replies=%0d",reply_frames);
  $display("SCOPE_FULL_CANDIDATE_RTL_EIGHT_PINS_MMCM_CDC_AXI_230400_25MS_GAP_NEW_CSR_CONTROL_ONLY_NO_H1_UPLOAD_NO_START_NO_REAL_MCU_NO_SYNTH_NO_HARDWARE");$finish;
 end
endmodule
