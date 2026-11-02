`timescale 1ns/1ps
// Exact routed functional netlist, 8 pins only. No SDF/private probes/force.
module tb_mp_net_v0_12;
 localparam integer BIT_NS=4340;
 reg pl_clk_50m=0,key_n=0,h1_rx_pin=1,ctrl_rx_pin=1;
 always #10 pl_clk_50m=~pl_clk_50m;
 wire h1_tx_pin,ctrl_tx_pin,w19_tx,fault_mark;
 h1_ax7010_uart_cdc_sync_board_top_v0_7 dut(
  .pl_clk_50m(pl_clk_50m),.key_n(key_n),.h1_rx_pin(h1_rx_pin),.ctrl_rx_pin(ctrl_rx_pin),
  .h1_tx_pin(h1_tx_pin),.ctrl_tx_pin(ctrl_tx_pin),.w19_tx(w19_tx),.fault_mark(fault_mark));
 reg [7:0] requests[0:311],replies[0:311],expected[0:38];
 integer byte_index=0,frames=0,reset_epoch=0,i;
 reg response_active=0,watch_idle=0;
 always @(posedge pl_clk_50m)if(watch_idle)begin
  if(w19_tx!==1 || h1_tx_pin!==1 || fault_mark!==0)
   $fatal(1,"H1/W19/mark changed without upload or START");
 end
 always @(negedge ctrl_tx_pin)begin:decode
  integer b,epoch;reg [7:0] value;
  epoch=reset_epoch;response_active=1;
  #(BIT_NS/2);if(epoch!=reset_epoch)disable decode;
  if(ctrl_tx_pin!==0)$fatal(1,"false control start");
  for(b=0;b<8;b=b+1)begin
   #BIT_NS;if(epoch!=reset_epoch)disable decode;value[b]=ctrl_tx_pin;
  end
  #BIT_NS;if(epoch!=reset_epoch)disable decode;
  if(ctrl_tx_pin!==1 || value!==expected[byte_index])
   $fatal(1,"routed reply byte %0d got %02x expected %02x",byte_index,value,expected[byte_index]);
  byte_index=byte_index+1;response_active=0;
  if(byte_index==39)begin byte_index=0;frames=frames+1;end
 end
 task send_byte;input [7:0] value;integer b;begin
  ctrl_rx_pin=0;#BIT_NS;
  for(b=0;b<8;b=b+1)begin ctrl_rx_pin=value[b];#BIT_NS;end
  ctrl_rx_pin=1;#BIT_NS;
 end endtask
 task send;input integer index;input bad_crc;integer n;reg [7:0] value;begin
  for(n=0;n<39;n=n+1)expected[n]=replies[index*39+n];
  for(n=0;n<39;n=n+1)begin
   value=requests[index*39+n];if(bad_crc && n==38)value=value^1;
   send_byte(value);
  end
 end endtask
 task wait_frames;input integer target;integer limit;begin
  limit=0;
  while(frames<target && limit<500)begin #100000;limit=limit+1;end
  if(frames!=target || byte_index!=0)$fatal(1,"missing/extra routed reply target=%0d actual=%0d",target,frames);
  #(BIT_NS*2);
 end endtask
 initial begin
  $readmemh("vectors/net_requests.mem",requests);
  $readmemh("vectors/net_replies.mem",replies);
  for(i=0;i<312;i=i+1)if((^{requests[i],replies[i]})===1'bx)$fatal(1,"missing netlist golden input");
  #1000;key_n=1;#200000;watch_idle=1;
  send(0,1);#4000000;
  if(frames || byte_index || response_active)$fatal(1,"bad CRC produced a physical reply");
  $display("MN1_PASS routed bad CRC silent, H1/W19/mark remain idle");
  for(i=0;i<4;i=i+1)begin send(i,0);wait_frames(i+1);end
  $display("MN2_PASS routed H5E1/MPG1 exact replies, unauthorized count read and capability write denied");
  send(4,0);wait(response_active);#(BIT_NS*2);
  reset_epoch=reset_epoch+1;key_n=0;ctrl_rx_pin=1;byte_index=0;response_active=0;
  #10;if(ctrl_tx_pin!==1 || h1_tx_pin!==1 || w19_tx!==1 || fault_mark!==0)
   $fatal(1,"KEY did not immediately clamp all routed output pins");
  #100000;key_n=1;#200000;
  if(frames!=4)$fatal(1,"aborted old frame became complete");
  for(i=5;i<8;i=i+1)begin send(i,0);wait_frames(i);end
  #1000000;
  if(frames!=7 || byte_index || response_active)$fatal(1,"extra or stale reply after reset");
  $display("MN3_PASS routed KEY abort clamps pins; fresh namespace returns identity/MPG1, stats still unauthorized");
  $display("H1_MULTIPOINT_ROUTED_CONTROL_V0_12_PASS replies=%0d",frames);
  $display("SCOPE_EXACT_ROUTED_FUNCTIONAL_NETLIST_8_PINS_230400_MMCM_CDC_AXI_NO_SDF_NO_UPLOAD_NO_START_NO_MCU_NO_HARDWARE");
  $finish;
 end
 initial begin #80000000;$fatal(1,"routed netlist smoke watchdog");end
endmodule
