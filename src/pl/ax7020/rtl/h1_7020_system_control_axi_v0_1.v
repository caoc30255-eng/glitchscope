`timescale 1ns/1ps
// Capacity permission only; never synthesizes physical completion or saved data.
module h1_7020_system_control_axi_v0_1(
 input wire clk,rst_n,ch0_active,ch0_closed,record_active,record_valid,matcher_done,
 input wire fault_summary,retired_take,
 input wire [31:0] epoch,ch0_id,retire_count,
 input wire [7:0] ch0_fault_code,
 output wire capacity,stop,
 input wire [11:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
 input wire [11:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready
);
 reg have_aw,have_w,permission,stopped;
 reg [11:0] awaddr;
 reg [31:0] wdata,grant_count;
 reg [3:0] wstrb;
 wire execute=have_aw && have_w && !s_axi_bvalid;
 wire stop_command=execute && awaddr==12'h024 && wstrb==15 && wdata==1;
 assign stop=stopped || stop_command;
 assign capacity=permission && !stop && !fault_summary && !ch0_active;
 assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
 assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
 assign s_axi_arready=rst_n && !s_axi_rvalid;
 always @(posedge clk)begin
  if(!rst_n)begin
   have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
   permission<=0;stopped<=0;grant_count<=0;s_axi_bvalid<=0;s_axi_bresp<=0;
   s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
  end else begin
   if(fault_summary)begin stopped<=1;permission<=0;end
   if(retired_take)permission<=0;
   if(s_axi_awvalid && s_axi_awready)begin awaddr<=s_axi_awaddr;have_aw<=1;end
   if(s_axi_wvalid && s_axi_wready)begin wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;have_w<=1;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(execute)begin
    have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
    if(wstrb==15 && awaddr==12'h020 && wdata==0)begin permission<=0;s_axi_bresp<=0;end
    else if(wstrb==15 && awaddr==12'h020 && wdata==1 && !stopped && !fault_summary && !retired_take &&
      !ch0_active && record_active && record_valid && matcher_done && epoch!=0 && grant_count!=32'hffffffff)begin
     permission<=1;grant_count<=grant_count+1'b1;s_axi_bresp<=0;
    end else if(stop_command)begin stopped<=1;permission<=0;s_axi_bresp<=0;end
   end
   if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arvalid && s_axi_arready)begin
    s_axi_rvalid<=1;s_axi_rdata<=0;s_axi_rresp<=0;
    case(s_axi_araddr)
     12'h000:s_axi_rdata<=32'h48375331; // H7S1 candidate system gate
     12'h004:s_axi_rdata<={24'd0,fault_summary,matcher_done,record_valid,record_active,ch0_closed,ch0_active,stop,capacity};
     12'h008:s_axi_rdata<=100000000; // compiled declaration only
     12'h00c:s_axi_rdata<=epoch;
     12'h010:s_axi_rdata<=ch0_id;
     12'h014:s_axi_rdata<={24'd0,ch0_fault_code};
     12'h018:s_axi_rdata<=retire_count;
     12'h01c:s_axi_rdata<=grant_count;
     12'h020:s_axi_rdata<={31'd0,permission};
     default:s_axi_rresp<=2;
    endcase
   end
  end
 end
endmodule
