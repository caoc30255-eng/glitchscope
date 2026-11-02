`timescale 1ns/1ps
// Exact old FIFO-reset waveform vs candidate; extra READY latency is explicit.
module tb_reset_ready_registered_v0_12;
 reg life_clk=0,ctrl_clk=0,key_n=0,locked=0;
 always #10 life_clk=~life_clk;
 always #5 ctrl_clk=~ctrl_clk;
 wire old_reset,new_reset,old_ready,new_ready;
 wire async_release=key_n && locked;
 h1_board_reset_handoff_golden_v0_2 golden(
  .life_clk(life_clk),.ctrl_clk(ctrl_clk),.key_n(key_n),.clock_locked(locked),
  .core_reset_n(old_reset),.io_ready(old_ready));
 h1_board_reset_handoff_v0_2 candidate(
  .life_clk(life_clk),.ctrl_clk(ctrl_clk),.key_n(key_n),.clock_locked(locked),
  .core_reset_n(new_reset),.io_ready(new_ready));
 reg sampled_old_ready=0;
 integer comparisons=0,openings=0,losses=0;
 time golden_open=0;
 always @(posedge life_clk or negedge async_release)
  if(!async_release)sampled_old_ready<=0;else sampled_old_ready<=old_ready;
 always @(negedge life_clk)begin
  comparisons=comparisons+1;
  if(new_reset!==old_reset)$fatal(1,"original FIFO reset contract changed");
  if(new_ready!==sampled_old_ready)$fatal(1,"READY is not exactly the sampled golden predicate");
  if(new_ready && (!old_ready || !new_reset))$fatal(1,"candidate opened before golden FIFO recovery");
 end
 always @(posedge old_ready)golden_open=$time;
 always @(posedge new_ready)begin
  openings=openings+1;
  if(!old_ready || $time-golden_open!=20)$fatal(1,"not exactly one extra LIFE cycle before opening");
 end
 always @(negedge async_release)begin
  losses=losses+1;
  #1;if(new_ready!==0)$fatal(1,"KEY/LOCK loss failed immediate clamp");
 end
 task await_ready;integer n;begin
  n=0;
  while(new_ready!==1 && n<400)begin @(negedge life_clk);n=n+1;end
  if(new_ready!==1 || old_ready!==1 || new_reset!==1 || old_reset!==1)
   $fatal(1,"bounded reset recovery failed");
  #40;
 end endtask
 task check_closed;begin
  #1;if(new_ready!==0 || old_ready!==0)$fatal(1,"pins would reopen during reset/recovery");
 end endtask
 initial begin
  #103;key_n=1;
  repeat(8)@(negedge life_clk);
  if(new_ready || new_reset)$fatal(1,"opened before MMCM LOCK");
  #3;locked=1;await_ready();
  $display("RR1_PASS startup keeps exact FIFO reset waveform and opens exactly one LIFE edge later");
  @(negedge life_clk);#3;key_n=0;check_closed();#3;key_n=1;check_closed();
  // The pulse is shorter than one LIFE cycle: stale ready cannot reopen I/O.
  repeat(2)begin @(negedge life_clk);if(new_ready)$fatal(1,"short KEY pulse reused stale READY");end
  await_ready();
  $display("RR2_PASS sub-cycle KEY pulse immediately clamps, no stale READY reuse");
  @(negedge life_clk);#3;locked=0;check_closed();#3;locked=1;check_closed();
  await_ready();
  $display("RR3_PASS sub-cycle MMCM LOCK loss immediately clamps and recovers");
  @(negedge life_clk);#3;key_n=0;check_closed();#30;key_n=1;
  @(posedge old_reset);#53;key_n=0;check_closed();#17;key_n=1;
  await_ready();
  $display("RR4_PASS reset during RECOVER preserves coalesced original FIFO reset sequencing");
  @(negedge life_clk);#3;key_n=0;#4;key_n=1;#7;locked=0;#8;locked=1;
  #12;key_n=0;#5;key_n=1;await_ready();
  $display("RR5_PASS repeated losses during HOLD/recovery create no early opening");
  @(negedge life_clk);#3;locked=0;check_closed();#400;
  if(new_ready!==0)$fatal(1,"open with clock unlocked");
  locked=1;await_ready();
  if(openings!=6 || comparisons<400)$fatal(1,"insufficient reset contract coverage");
  $display("H1_RESET_READY_REGISTERED_V0_12_PASS openings=%0d comparisons=%0d losses=%0d",openings,comparisons,losses);
  $display("SCOPE_ACTUAL_OLD_NEW_RESET_CORE_WAVEFORM_AND_READY_LATENCY_NO_REAL_FIFO_NO_MMCM_NO_START_NO_SYNTH_NO_HARDWARE");
  $finish;
 end
 initial begin #100000;$fatal(1,"reset contract watchdog");end
endmodule
