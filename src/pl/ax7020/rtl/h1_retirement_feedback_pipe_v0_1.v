`timescale 1ns/1ps
// Capture only an actual core retirement handshake and its full tuple.
// Consumer receives that immutable fact on the next clock; never generates
// a retirement request, completion or saved-data assertion.
module h1_retirement_feedback_pipe_v0_1(
 input wire clk,rst_n,actual_take,
 input wire [31:0] actual_epoch,actual_id,
 input wire [255:0] actual_identity,
 output reg fact_valid,
 output reg [31:0] fact_epoch,fact_id,
 output reg [255:0] fact_identity
);
 always @(posedge clk)begin
  if(!rst_n)begin fact_valid<=0;fact_epoch<=0;fact_id<=0;fact_identity<=0;end
  else begin
   fact_valid<=actual_take;
   if(actual_take)begin fact_epoch<=actual_epoch;fact_id<=actual_id;fact_identity<=actual_identity;end
  end
 end
endmodule
