`timescale 1ns/1ps
module tb_h3_uart_stop;
reg clk=0,rst_n=0,launch=0; always #10 clk=~clk;
reg [7:0] mem[0:277]; wire [9:0] addr; reg [7:0] ram;
always @(posedge clk) ram<=mem[addr];
wire raw_tx,masked_tx,busy,done,fault,mark;wire[15:0] completed;
h1_w19_frame_tx_v0_3 #(.CLK_HZ(50000000),.BAUD(1000000)) dut(
.clk(clk),.rst_n(rst_n),.launch(launch),.launch_authorized(1'b1),.current_valid(1'b1),
.current_started(1'b0),.current_done(1'b0),.frame_kind(8'd3),.frame_session(32'd1),.frame_seq(32'd1),.frame_len(16'd278),
.abort_request(1'b0),.rearm_request(1'b0),.rearm_authorized(1'b0),.rearm_session(32'd0),.rearm_seq(32'd0),
.read_addr(addr),.read_data(ram),.w19_tx(raw_tx),.mask_enable(1'b0),.mask_bit(3'd0),.mask_phase(16'd5),.mask_width(16'd1),
.masked_tx(masked_tx),.mask_mark(mark),.busy(busy),.physical_done(done),.completed_bytes(completed),.fault_latched(fault));
integer log_fd;
integer c,n,k,cellno,checked=0; reg expected;time begin_time,prev_time;
reg [1023:0] file_name;
initial begin
 log_fd=$fopen("scoreboard.log","w");
 if(!log_fd)$fatal(1,"LOG_OPEN_FAILED");
 for(c=0;c<5;c=c+1) begin
  case(c) 0:file_name="vector0.mem";1:file_name="vector1.mem";2:file_name="vector2.mem";3:file_name="vector3.mem";4:file_name="vector4.mem";endcase
  $readmemh(file_name,mem);
  rst_n=0;launch=0;repeat(5) @(negedge clk);rst_n=1;repeat(3) @(negedge clk);launch=1;@(negedge clk);launch=0;
  prev_time=0;
  for(n=0;n<278;n=n+1) begin
   @(negedge raw_tx);begin_time=$time;
   if(n>0 && begin_time-prev_time<10000) $fatal(1,"BYTE_OVERLAP c=%0d n=%0d",c,n);
   prev_time=begin_time;
   for(k=0;k<500;k=k+1) begin
    if(k>0) @(posedge clk);#1;
    cellno=k/50;
    if(cellno==0)expected=0;else if(cellno==9)expected=1;else expected=mem[n][cellno-1];
    if(raw_tx!==expected || masked_tx!==expected || mark!==0) $fatal(1,"UART_CYCLE_FAIL c=%0d n=%0d k=%0d raw=%b masked=%b expected=%b",c,n,k,raw_tx,masked_tx,expected);
    checked=checked+1;
   end
  end
  wait(done===1'b1);#1;if(completed!=278 || fault || busy) $fatal(1,"DONE_FAIL");
  $display("H3_UART_CASE_PASS case=%0d bytes=278 full_stop_clocks=50",c);
 $fdisplay(log_fd,"H3_UART_CASE_PASS case=%0d bytes=278 full_stop_clocks=50",c);
 end
 $display("H3_UART_STOPBIT_RTL_PASS cases=5 bytes=1390 checked_cycles=%0d",checked);$fdisplay(log_fd,"H3_UART_STOPBIT_RTL_PASS cases=5 bytes=1390 checked_cycles=%0d",checked);$fclose(log_fd);$finish;
end
initial begin #20000000;$fatal(1,"WATCHDOG");end
endmodule
