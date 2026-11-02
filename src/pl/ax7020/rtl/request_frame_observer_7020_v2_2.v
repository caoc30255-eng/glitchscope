`timescale 1ns / 1ps
// B2 OFFLINE PROPOSAL: observe the existing fixed 10-byte V1 request.
// One instance per receiver A/B. No TX, no image protocol, no payload repair.
// 16-bit trial and CRC widths describe the EXISTING V1 wire protocol only.
module request_frame_observer_7020_v2_2 (
    input wire clk, input wire rst_n,
    input wire arm, input wire abort_req, input wire ack,
    input wire [15:0] trusted_trial_id, input wire [15:0] trusted_source_crc,
    input wire [31:0] window_clks,
    input wire rx_valid, input wire [7:0] rx_byte, input wire rx_fe,
    output reg busy, output reg result_valid, output reg arm_rejected,
    output reg [15:0] expected_trial_id, output reg [15:0] expected_source_crc,
    output reg [15:0] received_trial_id,
    output reg [7:0] decoded_payload, output reg payload_seen,
    output reg [15:0] received_crc, output reg [15:0] calculated_crc,
    output reg complete_frame, output reg association_valid,
    output reg [7:0] flags,
    output reg [15:0] byte_event_count,
    output reg [31:0] elapsed_clks,
    output reg [15:0] ignored_after_result
);
    // flags: 0 timeout, 1 abort, 2 any FE, 3 header error,
    // 4 trial mismatch, 5 calculated vs received CRC mismatch,
    // 6 calculated vs trusted source CRC mismatch,
    // 7 received vs trusted source CRC mismatch.
    reg [3:0] index;
    reg [31:0] limit;
    reg [15:0] crc_work;
    reg [7:0] crc_hi;
    reg header_bad, header_fe, any_fe;
    function [15:0] crc_next;
        input [15:0] old_crc;
        input [7:0] data_byte;
        integer bit_no;
        reg [15:0] c;
        begin
            c=old_crc ^ {data_byte,8'h00};
            for(bit_no=0;bit_no<8;bit_no=bit_no+1)
                c=c[15] ? ((c<<1)^16'h1021) : (c<<1);
            crc_next=c;
        end
    endfunction
    wire final_byte = rx_valid && (index==9);
    always @(posedge clk) begin
        if(!rst_n) begin
            busy<=0;result_valid<=0;arm_rejected<=0;
            expected_trial_id<=0;expected_source_crc<=0;received_trial_id<=0;
            decoded_payload<=0;payload_seen<=0;received_crc<=0;calculated_crc<=0;
            complete_frame<=0;association_valid<=0;flags<=0;byte_event_count<=0;
            elapsed_clks<=0;ignored_after_result<=0;index<=0;limit<=0;
            crc_work<=16'hffff;crc_hi<=0;header_bad<=0;header_fe<=0;any_fe<=0;
        end else begin
            arm_rejected<=0;
            if(ack && result_valid) result_valid<=0;
            if(result_valid && rx_valid && ignored_after_result!=16'hffff)
                ignored_after_result<=ignored_after_result+1'b1;
            if(arm) begin
                // ACK+ARM is deliberately rejected: use separate transactions.
                if(busy || result_valid || window_clks==0) arm_rejected<=1;
                else begin
                    busy<=1;expected_trial_id<=trusted_trial_id;
                    expected_source_crc<=trusted_source_crc;limit<=window_clks;
                    received_trial_id<=0;decoded_payload<=0;payload_seen<=0;
                    received_crc<=0;calculated_crc<=0;complete_frame<=0;
                    association_valid<=0;flags<=0;byte_event_count<=0;
                    elapsed_clks<=0;ignored_after_result<=0;index<=0;
                    crc_work<=16'hffff;crc_hi<=0;header_bad<=0;header_fe<=0;any_fe<=0;
                end
            end
            if(busy) begin
                if(abort_req) begin
                    busy<=0;result_valid<=1;flags[1]<=1;
                    flags[2]<=any_fe;flags[3]<=header_bad;
                end else begin
                    elapsed_clks<=elapsed_clks+1'b1;
                    if(rx_valid) begin
                        if(byte_event_count!=16'hffff) byte_event_count<=byte_event_count+1'b1;
                        any_fe<=any_fe | rx_fe;
                        case(index)
                            0: if(rx_byte==8'ha5) begin index<=1;header_fe<=rx_fe;end
                            1: begin
                                if(rx_byte==8'h5a) begin
                                    index<=2;header_fe<=header_fe|rx_fe;
                                end else if(rx_byte==8'ha5) begin
                                    index<=1;header_fe<=rx_fe;
                                end else begin index<=0;header_fe<=0;end
                            end
                            2,3,4: begin
                                if((index==2 && rx_byte!=8'h01) ||
                                   (index==3 && rx_byte!=8'h20) ||
                                   (index==4 && rx_byte!=8'h03)) header_bad<=1;
                                header_fe<=header_fe|rx_fe;
                                crc_work<=crc_next(crc_work,rx_byte);index<=index+1'b1;
                            end
                            5: begin
                                received_trial_id[7:0]<=rx_byte;
                                header_fe<=header_fe|rx_fe;
                                crc_work<=crc_next(crc_work,rx_byte);index<=6;
                            end
                            6: begin
                                received_trial_id[15:8]<=rx_byte;
                                header_fe<=header_fe|rx_fe;
                                crc_work<=crc_next(crc_work,rx_byte);index<=7;
                            end
                            7: begin
                                decoded_payload<=rx_byte;payload_seen<=1;
                                crc_work<=crc_next(crc_work,rx_byte);index<=8;
                            end
                            8: begin crc_hi<=rx_byte;index<=9;end
                            9: begin
                                received_crc<={crc_hi,rx_byte};calculated_crc<=crc_work;
                                complete_frame<=1;busy<=0;result_valid<=1;
                                association_valid<=!header_bad && !header_fe &&
                                                   (received_trial_id==expected_trial_id);
                                flags<={({crc_hi,rx_byte}!=expected_source_crc),
                                        (crc_work!=expected_source_crc),
                                        (crc_work!={crc_hi,rx_byte}),
                                        (received_trial_id!=expected_trial_id),
                                        header_bad,(any_fe|rx_fe),2'b00};
                            end
                            default: index<=0;
                        endcase
                    end
                    // A final byte at the exact window boundary is accepted.
                    if(elapsed_clks==limit-1 && !final_byte) begin
                        busy<=0;result_valid<=1;flags[0]<=1;
                        flags[2]<=any_fe|(rx_valid && rx_fe);flags[3]<=header_bad;
                    end
                end
            end
        end
    end
endmodule
