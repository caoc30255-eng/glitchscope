`timescale 1ns / 1ps
// Isolated semantic checker. result_ok is NOT H1 ACCEPTED or a W19 permit.
// Caller retains immutable raw bytes; configuration changes only on approved ACK.
module h1_inner_validator_v0_1 (
    input wire clk, rst_n,
    input wire frame_start,
    input wire [7:0] frame_kind,
    input wire [15:0] frame_len,
    input wire management_idle,
    input wire [7:0] expected_route,
    input wire byte_valid,
    input wire [7:0] byte_data,
    input wire frame_end,
    input wire result_ack,
    input wire commit_enable,
    output wire input_ready,
    output reg busy,
    output reg result_valid,
    output reg result_ok,
    output reg [7:0] result_code,
    output reg [7:0] result_kind,
    output reg [31:0] result_run,
    output reg [7:0] result_image,
    output reg [15:0] result_trial, result_item, result_payload_len,
    output reg [7:0] result_attempt, result_route,
    output reg commit_done,
    output reg protocol_fault,
    output reg cfg_valid,
    output reg [31:0] cfg_run,
    output reg [7:0] cfg_image,
    output reg [15:0] cfg_width, cfg_height, cfg_items, cfg_chunk,
    output reg [31:0] cfg_total,
    output reg [255:0] cfg_sha
);
    // Local diagnostics only; these are not new wire-protocol status codes.
    localparam [7:0] OK=0, FORMAT=1, LENGTH=2, FRAME_CRC=3,
        NO_CONFIG=4, IDENTITY=5, ITEM_LENGTH=6, SOURCE_TABLE=7,
        PAYLOAD_CRC=8, MANAGEMENT_BUSY=9, CLEANUP_COMMAND=10,
        ROUTE=11, ITEM_INDEX=12, ATTEMPT=13, LOCAL_INTERFACE=14;
    reg [7:0] kind, route_expected;
    reg [15:0] declared_len, count;
    reg idle_snapshot, overlength;
    reg [15:0] crc_frame, crc_payload, wire_crc;
    reg [7:0] sof0, sof1, ver, image, pix, channels;
    reg [31:0] run_id, total_bytes;
    reg [15:0] width, height, items, chunk;
    reg [255:0] sha;
    reg [15:0] trial_id, item_index, item_total, source_crc, payload_len, command;
    reg [7:0] attempt, route;
    reg [15:0] staged_crc [0:63];
    reg [15:0] cfg_crc [0:63];
    reg [7:0] check_code;
    integer i;

    assign input_ready = busy && !result_valid;
    function [15:0] crc_next;
        input [15:0] previous;
        input [7:0] data;
        reg [15:0] value;
        integer bit_no;
        begin
            value = previous ^ {data,8'd0};
            for (bit_no=0; bit_no<8; bit_no=bit_no+1)
                if (value[15]) value = (value << 1) ^ 16'h1021;
                else value = value << 1;
            crc_next = value;
        end
    endfunction

    // Explicit widths avoid 16-bit arithmetic truncation and division hardware.
    wire [31:0] dimensions = {16'd0,width} * {16'd0,height};
    wire [31:0] upper_bytes = {16'd0,items} * {16'd0,chunk};
    wire [31:0] lower_bytes = ({16'd0,items}-32'd1) * {16'd0,chunk};
    wire [31:0] final_item_len = cfg_total - (({16'd0,cfg_items}-32'd1) * {16'd0,cfg_chunk});
    wire [31:0] expected_item_len =
        (item_index == cfg_items-16'd1) ? final_item_len : {16'd0,cfg_chunk};

    always @* begin
        check_code = OK;
        if (overlength || declared_len<12 || declared_len>534 || count!=declared_len)
            check_code = LENGTH;
        else if (ver!=8'h02 || sof0!=8'h55 ||
            !((kind==2 && sof1==8'hcc) || (kind==3 && sof1==8'haa) || (kind==4 && sof1==8'hee)))
            check_code = FORMAT;
        else if (crc_frame!=wire_crc)
            check_code = FRAME_CRC;
        else if (kind==2) begin
            if (!idle_snapshot) check_code = MANAGEMENT_BUSY;
            else if (pix!=1 || channels!=0) check_code = FORMAT;
            else if (items<1 || items>64 || chunk<1 || chunk>512 || width==0 || height==0 ||
                declared_len!=(16'd56+(items<<1)) || total_bytes!=dimensions ||
                total_bytes<=lower_bytes || total_bytes>upper_bytes)
                check_code = LENGTH;
        end else if (kind==3) begin
            if (!cfg_valid) check_code = NO_CONFIG;
            else if (run_id!=cfg_run || image!=cfg_image || item_total!=cfg_items)
                check_code = IDENTITY;
            else if (item_index>=item_total || item_index>=64)
                check_code = ITEM_INDEX;
            else if (attempt>3) check_code = ATTEMPT;
            else if (route>1 || route_expected>1 || route!=route_expected) check_code = ROUTE;
            else if (payload_len<1 || payload_len>512 || declared_len!=(16'd22+payload_len) ||
                {16'd0,payload_len}!=expected_item_len) check_code = ITEM_LENGTH;
            else if (source_crc!=cfg_crc[item_index[5:0]]) check_code = SOURCE_TABLE;
            else if (crc_payload!=source_crc) check_code = PAYLOAD_CRC;
        end else if (kind==4) begin
            if (declared_len!=12) check_code = LENGTH;
            else if (!idle_snapshot) check_code = MANAGEMENT_BUSY;
            else if (!cfg_valid) check_code = NO_CONFIG;
            else if (run_id!=cfg_run || image!=cfg_image) check_code = IDENTITY;
            else if (command!=1) check_code = CLEANUP_COMMAND;
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            busy<=0; result_valid<=0; result_ok<=0; result_code<=0;
            commit_done<=0; protocol_fault<=0; cfg_valid<=0;
            cfg_run<=0; cfg_image<=0; cfg_width<=0; cfg_height<=0;
            cfg_items<=0; cfg_chunk<=0; cfg_total<=0; cfg_sha<=0;
            result_kind<=0; result_run<=0; result_image<=0;
            result_trial<=0; result_item<=0; result_payload_len<=0;
            result_attempt<=0; result_route<=0;
            kind<=0; declared_len<=0; count<=0; idle_snapshot<=0;
            route_expected<=0; overlength<=0;
            crc_frame<=16'hffff; crc_payload<=16'hffff; wire_crc<=0;
            sof0<=0; sof1<=0; ver<=0; run_id<=0; image<=0;
            pix<=0; channels<=0; width<=0; height<=0; total_bytes<=0;
            items<=0; chunk<=0; sha<=0;
            trial_id<=0; item_index<=0; item_total<=0; source_crc<=0;
            payload_len<=0; attempt<=0; route<=0; command<=0;
            for (i=0; i<64; i=i+1) begin staged_crc[i]<=0; cfg_crc[i]<=0; end
        end else begin
            commit_done<=0;
            // Caller must separate start, bytes, end, and ACK clock cycles.
            if ((frame_start && (busy || result_valid || byte_valid || frame_end || result_ack)) ||
                (byte_valid && (!input_ready || frame_end)) ||
                (frame_end && (!busy || byte_valid)) || (result_ack && !result_valid) ||
                (commit_enable && !result_ack) ||
                (result_ack && commit_enable && result_ok && kind!=3 && !management_idle)) protocol_fault<=1;

            if (result_valid) begin
                if (result_ack) begin
                    // Never commit after a local interface fault or bad result.
                    if (commit_enable && result_ok && !protocol_fault && !frame_start && !byte_valid && !frame_end &&
                        (kind==3 || management_idle)) begin
                        commit_done<=1;
                        if (kind==2) begin
                            cfg_valid<=1; cfg_run<=run_id; cfg_image<=image;
                            cfg_width<=width; cfg_height<=height; cfg_total<=total_bytes;
                            cfg_items<=items; cfg_chunk<=chunk; cfg_sha<=sha;
                            for (i=0; i<64; i=i+1)
                                if (i<items) cfg_crc[i]<=staged_crc[i];
                                else cfg_crc[i]<=0;
                        end else if (kind==4) begin
                            cfg_valid<=0;
                        end
                    end
                    result_valid<=0;
                end
            end else if (frame_start && !busy) begin
                busy<=1; kind<=frame_kind; declared_len<=frame_len;
                idle_snapshot<=management_idle; route_expected<=expected_route;
                count<=0; overlength<=0; crc_frame<=16'hffff; crc_payload<=16'hffff; wire_crc<=0;
                sof0<=0; sof1<=0; ver<=0; run_id<=0; image<=0;
                pix<=0; channels<=0; width<=0; height<=0; total_bytes<=0;
                items<=0; chunk<=0; sha<=0;
                trial_id<=0; item_index<=0; item_total<=0; source_crc<=0;
                payload_len<=0; attempt<=0; route<=0; command<=0;
            end else if (busy) begin
                if (byte_valid) begin
                    if (count!=16'hffff) count<=count+1'b1;
                    else overlength<=1;
                    if (count>=declared_len || count>=534) overlength<=1;
                    if (count>=2 && declared_len>=2 && count<declared_len-2)
                        crc_frame<=crc_next(crc_frame,byte_data);
                    if (declared_len>=2 && count==declared_len-2) wire_crc[15:8]<=byte_data;
                    if (declared_len>=1 && count==declared_len-1) wire_crc[7:0]<=byte_data;
                    case (count)
                        0: sof0<=byte_data;
                        1: sof1<=byte_data;
                        2: ver<=byte_data;
                        3,4,5,6: run_id<={run_id[23:0],byte_data};
                        7: image<=byte_data;
                        default: ;
                    endcase
                    if (kind==2) begin
                        case (count)
                            8: pix<=byte_data;
                            9: channels<=byte_data;
                            10,11: width<={width[7:0],byte_data};
                            12,13: height<={height[7:0],byte_data};
                            14,15,16,17: total_bytes<={total_bytes[23:0],byte_data};
                            18,19: items<={items[7:0],byte_data};
                            20,21: chunk<={chunk[7:0],byte_data};
                            default: ;
                        endcase
                        if (count>=22 && count<=53) sha<={sha[247:0],byte_data};
                        if (count>=54 && count<182 && count<declared_len-2) begin
                            if (!count[0]) staged_crc[(count-54)>>1][15:8]<=byte_data;
                            else staged_crc[(count-54)>>1][7:0]<=byte_data;
                        end
                    end else if (kind==3) begin
                        case (count)
                            8,9: trial_id<={trial_id[7:0],byte_data};
                            10,11: item_index<={item_index[7:0],byte_data};
                            12,13: item_total<={item_total[7:0],byte_data};
                            14: attempt<=byte_data;
                            15: route<=byte_data;
                            16,17: source_crc<={source_crc[7:0],byte_data};
                            18,19: payload_len<={payload_len[7:0],byte_data};
                            default: ;
                        endcase
                        if (count>=20 && declared_len>=2 && count<declared_len-2)
                            crc_payload<=crc_next(crc_payload,byte_data);
                    end else if (kind==4 && (count==8 || count==9))
                        command<={command[7:0],byte_data};
                end
                if (frame_end) begin
                    busy<=0; result_valid<=1;
                    result_code <= (protocol_fault || byte_valid) ? LOCAL_INTERFACE : check_code;
                    result_ok <= !protocol_fault && !byte_valid && check_code==OK;
                    result_kind<=kind; result_run<=run_id; result_image<=image;
                    result_trial<=trial_id; result_item<=item_index; result_payload_len<=payload_len;
                    result_attempt<=attempt; result_route<=route;
                end
            end
        end
    end
endmodule
