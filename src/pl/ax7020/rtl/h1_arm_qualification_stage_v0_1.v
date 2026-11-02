`timescale 1ns/1ps
// Request reserves a mapping at the qualification edge. Actual consumers
// publish one clock later, after full mapping check and live veto checks.
module h1_arm_qualification_stage_v0_1(
 input wire clk,rst_n,request,qualify_now,late_bad,
 output reg publish_arm,qualified,fault_latched
);
 always @(posedge clk)begin
  if(!rst_n)begin publish_arm<=0;qualified<=0;fault_latched<=0;end
  else begin
   publish_arm<=request;
   if(request)begin qualified<=(qualify_now===1'b1);if(qualify_now!==1'b1)fault_latched<=1;end
   if(late_bad)fault_latched<=1;
  end
 end
endmodule
