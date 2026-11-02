`timescale 1ns / 1ps
// Invert one bounded interval of one payload DATA bit. No header/CRC repair.
module h1_payload_fault_overlay_v0_1 #(
    parameter integer CLK_HZ=50000000, BAUD=1000000
)(
    input wire clk,rst_n,
    input wire configure_take,physical_start_take,physical_done,frame_abort,
    input wire [7:0] frame_kind,
    input wire [15:0] frame_len,
    input wire [31:0] frame_session,frame_seq,
    input wire [255:0] frame_identity,
    input wire fault_enable,
    input wire [8:0] target_count,
    input wire [15:0] target_byte,phase_clks,width_clks,
    input wire [2:0] target_bit,
    input wire raw_tx,data_bit_active,
    input wire observed_fault_mark,
    input wire [9:0] byte_index,
    input wire [2:0] bit_index,
    input wire [31:0] bit_clock,
    output wire configuration_ok,w19_tx,fault_active,fault_mark,
    output reg frame_active,configuration_pending,policy_ignored,
    output wire [255:0] mark_identity,
    output reg [255:0] snapshot_identity,
    output reg [15:0] saved_target_byte,saved_phase,saved_width,
    output reg [2:0] saved_target_bit,
    output reg saved_enable,
    output reg [8:0] saved_count,frame_point_count,
    output reg [31:0] mark_count,
    output reg interface_fault
);
    localparam integer PERIOD=CLK_HZ/BAUD;
    reg [255:0] last_mark_identity;
    wire [16:0] requested_end={1'b0,phase_clks}+{1'b0,width_clks};
    wire [16:0] saved_end={1'b0,saved_phase}+{1'b0,saved_width};
    wire descriptor_known=(^frame_identity)!==1'bx && (^frame_len)!==1'bx;
    wire identity_ok=descriptor_known && frame_identity[255:219]==0 && frame_identity[119:88]!=0 &&
        frame_identity[218:187]===frame_session && frame_identity[186:155]===frame_seq && frame_seq!=0 && frame_len>=1 && frame_len<=534;
    wire [16:0] requested_limit={1'b0,target_byte}+{8'd0,target_count};
    wire coordinates_known=(^{target_byte,target_bit,phase_clks,width_clks,target_count})!==1'bx;
    wire coordinates_ok=coordinates_known && frame_len>=22 && target_byte>=20 && target_count>=1 && target_count<=256 && requested_limit<=({1'b0,frame_len}-17'd2) &&
        width_clks!=0 && requested_end<=PERIOD;
    assign configuration_ok=identity_ok &&
        ((frame_kind===8'd2 || frame_kind===8'd4) ||
         (frame_kind===8'd3 && (fault_enable===1'b0 || (fault_enable===1'b1 && coordinates_ok))));
    assign fault_active=frame_active && saved_enable && !interface_fault && data_bit_active &&
        {6'd0,byte_index}>=saved_target_byte && {7'd0,byte_index}<({1'b0,saved_target_byte}+{8'd0,saved_count}) && bit_index==saved_target_bit && bit_clock>=saved_phase && bit_clock<saved_end;
    assign fault_mark=fault_active && bit_clock==saved_phase;
    assign mark_identity=observed_fault_mark ? snapshot_identity : last_mark_identity;
    assign w19_tx=raw_tx ^ fault_active;
    always @(posedge clk) begin
        if(!rst_n) begin
            frame_active<=0;configuration_pending<=0;policy_ignored<=0;snapshot_identity<=0;last_mark_identity<=0;
            saved_target_byte<=0;saved_target_bit<=0;saved_phase<=0;saved_width<=0;saved_enable<=0;
            mark_count<=0;interface_fault<=0;saved_count<=1;frame_point_count<=0;
        end else begin
            if(configure_take) begin
                if(!configuration_ok || frame_active || configuration_pending) interface_fault<=1;
                else begin
                    configuration_pending<=1;snapshot_identity<=frame_identity;
                    saved_target_byte<=target_byte;saved_target_bit<=target_bit;saved_phase<=phase_clks;saved_width<=width_clks;
                    saved_enable<=fault_enable===1'b1 && frame_kind==3;saved_count<=target_count;frame_point_count<=0;
                    policy_ignored<=fault_enable===1'b1 && frame_kind!=3;
                end
            end
            if(physical_start_take) begin
                if(!configuration_pending || frame_active) interface_fault<=1;
                else begin frame_active<=1;configuration_pending<=0;end
            end
            if(physical_done || frame_abort) begin frame_active<=0;configuration_pending<=0;end
            // Abort is sampled on this edge; a window already emitted keeps its mark evidence.
            if(physical_done && !frame_abort && frame_active && saved_enable && frame_point_count!=saved_count) interface_fault<=1;
            if(observed_fault_mark) begin
                if(!frame_active || !saved_enable || frame_point_count>=saved_count) interface_fault<=1;
                else frame_point_count<=frame_point_count+1'b1;
                last_mark_identity<=snapshot_identity;
                if(mark_count!=32'hffffffff) mark_count<=mark_count+1'b1;
            end
        end
    end
    initial begin
        if(BAUD<=0 || CLK_HZ%BAUD!=0 || PERIOD<2 || PERIOD>65535) $fatal(1,"Invalid payload fault clock profile");
    end
endmodule
