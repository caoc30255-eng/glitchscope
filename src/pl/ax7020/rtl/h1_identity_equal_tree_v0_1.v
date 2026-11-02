`timescale 1ns/1ps
// Full 256-bit case equality. Combinational: no latency or truncation.
// Preserve small compare/reduction boundaries to avoid one long carry chain.
module h1_identity_equal_tree_v0_1(input wire [255:0] a,b,output wire equal);
 (* KEEP="TRUE" *) wire [85:0] triplet_equal;
 (* KEEP="TRUE" *) wire [14:0] group_equal;
 (* KEEP="TRUE" *) wire [2:0] upper_equal;
 genvar i;
 generate
  for(i=0;i<86;i=i+1)begin:leaf
   localparam integer LO=i*3;
   localparam integer HI=(LO+2>255)?255:LO+2;
   assign triplet_equal[i]=(a[HI:LO]===b[HI:LO]);
  end
  for(i=0;i<15;i=i+1)begin:groups
   localparam integer LO=i*6;
   localparam integer HI=(LO+5>85)?85:LO+5;
   assign group_equal[i]=&triplet_equal[HI:LO];
  end
  for(i=0;i<3;i=i+1)begin:upper
   localparam integer LO=i*6;
   localparam integer HI=(LO+5>14)?14:LO+5;
   assign upper_equal[i]=&group_equal[HI:LO];
  end
 endgenerate
 assign equal=&upper_equal;
endmodule
