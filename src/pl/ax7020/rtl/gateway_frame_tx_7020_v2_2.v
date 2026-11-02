`timescale 1ns / 1ps
// B3 isolated V1 one-byte Gateway TX proposal. Input must be the selected
// receiver's observed byte. No correct source payload port exists by design.
// Physical pin/mux and image-frame protocol are outside this module.
module gateway_frame_tx_7020_v2_2 #(
    parameter integer CLKS_PER_BIT = 100
)(
    input wire clk,input wire rst_n,
    input wire launch,input wire clear_result,
    input wire association_valid,input wire decoded_valid,
    input wire decoded_fe,input wire multiple_events,
    input wire [7:0] decoded_byte,
    input wire [15:0] trusted_trial_id,input wire [15:0] trusted_source_crc,
    output reg tx,output reg busy,output reg result_valid,
    output reg result_success,output reg [2:0] drop_reason,
    output reg [7:0] forwarded_byte,output reg [15:0] forwarded_trial_id,
    output reg [15:0] forwarded_source_crc,
    output reg launch_rejected,output reg [3:0] bytes_sent
);
    // Drop reason: 0 none, 1 no association, 2 no decoded byte,
    // 3 FE, 4 multiple events. Priority is this order.
    reg [1:0] state;
    localparam IDLE=0,START=1,DATA=2,STOP=3;
    reg [15:0] tick_count;
    reg [3:0] byte_index;
    reg [2:0] bit_index;
    reg [7:0] frame_byte;
    always @* begin
        case(byte_index)
            0:frame_byte=8'ha5;
            1:frame_byte=8'h5a;
            2:frame_byte=8'h01;
            3:frame_byte=8'h20;
            4:frame_byte=8'h03;
            5:frame_byte=forwarded_trial_id[7:0];
            6:frame_byte=forwarded_trial_id[15:8];
            7:frame_byte=forwarded_byte;
            8:frame_byte=forwarded_source_crc[15:8];
            default:frame_byte=forwarded_source_crc[7:0];
        endcase
    end
    always @(posedge clk) begin
        if(!rst_n)begin
            tx<=1;busy<=0;result_valid<=0;result_success<=0;drop_reason<=0;
            forwarded_byte<=0;forwarded_trial_id<=0;forwarded_source_crc<=0;
            launch_rejected<=0;bytes_sent<=0;state<=IDLE;
            tick_count<=0;byte_index<=0;bit_index<=0;
        end else begin
            launch_rejected<=0;
            if(clear_result && result_valid)begin
                result_valid<=0;result_success<=0;drop_reason<=0;
            end
            if(launch)begin
                // A launch in the same cycle as clear is deliberately rejected.
                if(busy || result_valid)launch_rejected<=1;
                else begin
                    result_success<=0;drop_reason<=0;bytes_sent<=0;
                    forwarded_trial_id<=trusted_trial_id;
                    forwarded_source_crc<=trusted_source_crc;
                    forwarded_byte<=decoded_byte;
                    if(!association_valid)begin result_valid<=1;drop_reason<=1;end
                    else if(!decoded_valid)begin result_valid<=1;drop_reason<=2;end
                    else if(decoded_fe)begin result_valid<=1;drop_reason<=3;end
                    else if(multiple_events)begin result_valid<=1;drop_reason<=4;end
                    else begin
                        busy<=1;state<=START;tx<=0;
                        tick_count<=0;byte_index<=0;bit_index<=0;
                    end
                end
            end
            if(busy)begin
                if(tick_count==CLKS_PER_BIT-1)begin
                    tick_count<=0;
                    case(state)
                        START:begin state<=DATA;bit_index<=0;tx<=frame_byte[0];end
                        DATA:if(bit_index==7)begin state<=STOP;tx<=1;end
                             else begin bit_index<=bit_index+1'b1;tx<=frame_byte[bit_index+1'b1];end
                        STOP:begin
                            bytes_sent<=bytes_sent+1'b1;
                            if(byte_index==9)begin
                                busy<=0;state<=IDLE;tx<=1;
                                result_valid<=1;result_success<=1;
                            end else begin
                                byte_index<=byte_index+1'b1;
                                bit_index<=0;state<=START;tx<=0;
                            end
                        end
                        default:begin state<=IDLE;busy<=0;tx<=1;end
                    endcase
                end else tick_count<=tick_count+1'b1;
            end
        end
    end
endmodule
