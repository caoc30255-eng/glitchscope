module accumulator(input logic clk,rst,in_valid,out_ready,
 input logic [7:0] din,output logic in_ready,valid,output logic [7:0] data);
 logic [7:0] acc=0;
 assign in_ready=~valid|out_ready;
 always_ff @(posedge clk) begin
  if(rst)begin acc<=0;valid<=0;data<=0;end
  else if(in_ready)begin
   valid<=in_valid;
   if(in_valid)begin acc<=acc+din;data<=acc+din;end
  end
`ifdef INJECT_STALL_BUG
  if(!rst && valid && !out_ready)data<=data+1;
`endif
 end
endmodule
