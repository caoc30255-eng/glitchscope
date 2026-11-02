`timescale 1ns/1ps
// A latched, already validated payload interval. No per-byte schedule RAM.
module h1_multipoint_window_v0_1(
 input wire enabled,
 input wire [15:0] first_byte,
 input wire [8:0] count,
 input wire [9:0] byte_index,
 input wire point_mark,
 output wire mask_enable,first_mark
);
 wire [16:0] limit={1'b0,first_byte}+{8'd0,count};
 assign mask_enable=enabled && {6'd0,byte_index}>=first_byte && {7'd0,byte_index}<limit;
 // Preserve an emitted first mark even if an abort is sampled on that edge.
 assign first_mark=point_mark && {6'd0,byte_index}==first_byte;
endmodule
