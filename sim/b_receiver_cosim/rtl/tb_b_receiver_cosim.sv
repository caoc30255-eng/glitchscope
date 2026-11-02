`timescale 1ns/1ps
// Offline scoreboard only; no board/AXI/native transport or FPGA programming.
module tb_b_receiver_cosim;
  reg clk=0, rst_n=0, serial=1;
  reg [2:0] cfg_d=3;
  reg signed [3:0] cfg_s=-1;
  wire ce;
  wire [7:0] data;
  wire valid, fe, idle;
  rx_ce_gen_7020_v2_2 nco(.clk(clk),.rst_n(rst_n),.rx_ce(ce));
  uart_rx_b_7020_observe_v0_1 #(.INPUT_ALREADY_SYNCED(1)) dut(
    .clk(clk),.rst_n(rst_n),.rx_ce(ce),.uart_rx(serial),
    .cfg_d(cfg_d),.cfg_s(cfg_s),.rx_byte(data),.rx_valid(valid),
    .framing_error(fe),.rx_idle(idle));
  reg [31:0] vector[0:65535];
  reg [2047:0] case_path, vector_path;
  integer report_fd;
  integer fd, got, case_id, dd, ss, phase, length, i, cases, cycles, expected_acc;
  task reset_clock;
    begin #5 clk=1; #5 clk=0; end
  endtask
  initial begin
    report_fd=$fopen("scoreboard.log","w");
    if(report_fd==0) $fatal(1,"Cannot open scoreboard.log");
    cases=0; cycles=0;
    if (!$value$plusargs("CASES=%s",case_path)) case_path="cases.txt";
    fd=$fopen(case_path,"r");
    if (fd==0) begin $fdisplay(report_fd,"B_RX_RTL_FAIL cannot open case list"); $display("B_RX_RTL_FAIL cannot open case list"); $finish; end
    got=$fscanf(fd,"%d %d %d %d %d\n",case_id,dd,ss,phase,length);
    while(got==5) begin
      if(length<1 || length>65536) begin $fdisplay(report_fd,"B_RX_RTL_FAIL vector length"); $display("B_RX_RTL_FAIL vector length"); $finish; end
      $sformat(vector_path,"vectors/case_%05d.mem",case_id);
      $readmemh(vector_path,vector,0,length-1);
      rst_n=0;serial=1;cfg_d=dd;cfg_s=ss;
      reset_clock;reset_clock;
      // Deposit a possible steady-state NCO phase after reset. This is a
      // simulation initial condition, never a claim about measured phase.
      nco.acc=phase;nco.rx_ce=(phase<4);rst_n=1;
      for(i=0;i<length;i=i+1) begin
        serial=vector[i][0];
        #5 clk=1;
        #1;
        expected_acc=(phase+4*(i+1))%25;
        if({data,fe,valid} !== vector[i][10:1] || nco.acc !== expected_acc[4:0] || ce !== (expected_acc<4)) begin
          $fdisplay(report_fd,"B_RX_RTL_FAIL case=%0d cycle=%0d d=%0d s=%0d phase=%0d expected=%03x actual=%03x state=%0d n=%0d",case_id,i,dd,ss,phase,vector[i][10:1],{data,fe,valid},dut.state,dut.n); $display("B_RX_RTL_FAIL case=%0d cycle=%0d d=%0d s=%0d phase=%0d expected=%03x actual=%03x state=%0d n=%0d",case_id,i,dd,ss,phase,vector[i][10:1],{data,fe,valid},dut.state,dut.n);
          $finish;
        end
        cycles=cycles+1;
        #4 clk=0;
      end
      cases=cases+1;
      if(cases%25==0) begin $fdisplay(report_fd,"B_RX_RTL_PROGRESS cases=%0d cycles=%0d",cases,cycles); $display("B_RX_RTL_PROGRESS cases=%0d cycles=%0d",cases,cycles); end
      got=$fscanf(fd,"%d %d %d %d %d\n",case_id,dd,ss,phase,length);
    end
    $fclose(fd);
    $fdisplay(report_fd,"B_RX_RTL_COSIM_PASS cases=%0d cycles=%0d",cases,cycles); $display("B_RX_RTL_COSIM_PASS cases=%0d cycles=%0d",cases,cycles);
    $fclose(report_fd);
    $finish;
  end
endmodule
