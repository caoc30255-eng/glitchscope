`timescale 1ns/1ps
// Pure combinational == with the original four-state result preserved.
// Each three-bit equality has six inputs and fits one LUT6. Kept <=six-way
// reductions prevent a remaining wide carry-based reduction. For the actual
// widths <=264 the result is bounded to four LUT stages, with no registers.
module h1_control_equal_tree_v0_1 #(parameter integer WIDTH=264)(
 input wire [WIDTH-1:0] a,b,output wire equal
);
 localparam integer CHUNKS=(WIDTH+2)/3;
 localparam integer GROUPS=(CHUNKS+5)/6;
 localparam integer UPPER_GROUPS=(GROUPS+5)/6;
 (* KEEP="TRUE" *) wire [CHUNKS-1:0] chunk_equal;
 (* KEEP="TRUE" *) wire [GROUPS-1:0] group_equal;
 (* KEEP="TRUE" *) wire [UPPER_GROUPS-1:0] upper_equal;
 genvar i,g,u;
 generate for(i=0;i<CHUNKS;i=i+1)begin:chunk
  localparam integer N=(WIDTH-i*3<3)?WIDTH-i*3:3;
  assign chunk_equal[i]=(a[i*3+:N]==b[i*3+:N]);
 end
 for(g=0;g<GROUPS;g=g+1)begin:grouping
  localparam integer N=(CHUNKS-g*6<6)?CHUNKS-g*6:6;
  assign group_equal[g]=&chunk_equal[g*6+:N];
 end
 for(u=0;u<UPPER_GROUPS;u=u+1)begin:upper_grouping
  localparam integer N=(GROUPS-u*6<6)?GROUPS-u*6:6;
  assign upper_equal[u]=&group_equal[u*6+:N];
 end endgenerate
 assign equal=&upper_equal;
endmodule
