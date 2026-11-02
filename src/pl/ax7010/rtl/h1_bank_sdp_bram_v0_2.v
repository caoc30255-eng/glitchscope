`timescale 1ns/1ps
// The RAM write pins are driven exclusively by synchronous capture registers.
// One queued old-epoch write may drain on the first reset edge; no new write
// is captured in reset. Session validity revokes all old-epoch memory access.
module h1_bank_sdp_bram_v0_2(
 input wire clk,rst_n,write_en,input wire [9:0] write_addr,input wire [7:0] write_data,
 input wire read_en,input wire [9:0] read_addr,output reg [7:0] read_data
);
 (* ram_style="block" *) reg [7:0] bytes [0:1023];
 reg write_en_q;reg [9:0] write_addr_q;reg [7:0] write_data_q;
 always @(posedge clk) begin
  if(!rst_n) write_en_q<=0;
  else write_en_q<=write_en;
  if(write_en) begin write_addr_q<=write_addr;write_data_q<=write_data;end
  if(write_en_q) bytes[write_addr_q]<=write_data_q;
  if(read_en) read_data<=bytes[read_addr];
 end
endmodule
