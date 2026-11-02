`timescale 1ns / 1ps
// H1 v0.1 isolated candidate capture, AX 50 MHz clock domain.
// Software-only H1 draft: 02_H1_图片上行链路契约草案_v0_1.md
//
// This module does NOT issue ACCEPTED, validate all v0.6.11 semantics, dedup
// retransmissions, or start W19. A parent must keep credit=0 while candidate
// is held and must not wire this directly to a production board bitstream.
module h1_ax_frame_capture_runtime_v0_1 #(
    parameter integer TIMEOUT_CLKS = 500000
)(
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  rx_data,
    input  wire        rx_valid,
    input  wire        rx_fe,
    input  wire        candidate_release,
    input  wire [9:0]  read_addr,
    output reg  [7:0]  read_data,
    output reg         candidate_valid,
    output reg  [7:0]  candidate_kind,
    output reg  [31:0] candidate_session,
    output reg  [31:0] candidate_seq,
    output reg  [15:0] candidate_len,
    output reg  [15:0] candidate_inner_crc,
    output reg         error_valid,
    output reg  [7:0]  error_code,
    output reg  [7:0]  first_error_code,
    output reg  [31:0] error_count,
    output reg         fault_latched,
    output wire capture_idle
);
    localparam [2:0] S_SYNC0=3'd0, S_SYNC1=3'd1, S_HEADER=3'd2,
                     S_INNER=3'd3, S_CRC_H=3'd4, S_CRC_L=3'd5,
                     S_HOLD=3'd6;
    localparam [7:0] E_NONE=8'd0, E_UART_FE=8'd1, E_TIMEOUT=8'd2,
                     E_LENGTH=8'd3, E_HEADER=8'd4, E_OUTER_CRC=8'd5,
                     E_INNER_CRC=8'd6, E_INNER_SHAPE=8'd7,
                     E_EXTRA_WHILE_HELD=8'd8;
    localparam [7:0] K_HELLO=8'h01, K_CONFIG=8'h02,
                     K_ITEM=8'h03, K_CLEANUP=8'h04;

    reg [2:0] state;
    reg [3:0] header_index;
    reg [9:0] inner_index;
    reg [7:0] version_reg, kind_reg, len_hi;
    reg [31:0] session_reg, seq_reg;
    reg [15:0] inner_len;
    reg [7:0] outer_crc_hi, inner_sof0, inner_sof1, inner_ver;
    reg [15:0] outer_crc, inner_body_crc, inner_total_crc;
    reg [7:0] inner_crc_hi, inner_crc_lo;
    reg [15:0] inner_word_18_19;
    reg [31:0] timeout_count;
    reg [7:0] inner_mem [0:533];

    function [15:0] crc_next;
        input [15:0] old_crc;
        input [7:0] value;
        reg [15:0] work;
        integer bit_no;
        begin
            work = old_crc ^ {value,8'h00};
            for (bit_no=0; bit_no<8; bit_no=bit_no+1) begin
                if (work[15]) work = (work << 1) ^ 16'h1021;
                else work = work << 1;
            end
            crc_next = work;
        end
    endfunction

    wire [15:0] assembled_len = {len_hi,rx_data};
    wire header_kind_ok = kind_reg==K_HELLO || kind_reg==K_CONFIG ||
                          kind_reg==K_ITEM || kind_reg==K_CLEANUP;
    wire header_length_ok =
        (kind_reg==K_HELLO && assembled_len==0 && seq_reg==0) ||
        (kind_reg==K_CONFIG && seq_reg!=0 && assembled_len>=58 &&
         assembled_len<=184 && !assembled_len[0]) ||
        (kind_reg==K_ITEM && seq_reg!=0 && assembled_len>=23 &&
         assembled_len<=534) ||
        (kind_reg==K_CLEANUP && seq_reg!=0 && assembled_len==12);
    wire inner_sof_ok =
        (kind_reg==K_CONFIG && inner_sof0==8'h55 && inner_sof1==8'hcc) ||
        (kind_reg==K_ITEM && inner_sof0==8'h55 && inner_sof1==8'haa) ||
        (kind_reg==K_CLEANUP && inner_sof0==8'h55 && inner_sof1==8'hee);
    wire config_shape_ok = inner_word_18_19>=1 && inner_word_18_19<=64 &&
                           inner_len==(16'd56+(inner_word_18_19 << 1));
    wire item_shape_ok = inner_word_18_19>=1 && inner_word_18_19<=512 &&
                         inner_len==(16'd22+inner_word_18_19);
    wire inner_shape_ok =
        (kind_reg==K_HELLO && inner_len==0) ||
        (kind_reg==K_CONFIG && inner_sof_ok && inner_ver==8'h02 && config_shape_ok) ||
        (kind_reg==K_ITEM && inner_sof_ok && inner_ver==8'h02 && item_shape_ok) ||
        (kind_reg==K_CLEANUP && inner_sof_ok && inner_ver==8'h02 && inner_len==12);

    // Synchronous read allows the 534-byte staging array to be inferred as RAM.
    always @(posedge clk) begin
        if (!rst_n) read_data <= 0;
        else if (candidate_valid && read_addr<10'd534)
            read_data <= inner_mem[read_addr];
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= S_SYNC0;
            header_index <= 0;
            inner_index <= 0;
            version_reg <= 0;
            kind_reg <= 0;
            len_hi <= 0;
            session_reg <= 0;
            seq_reg <= 0;
            inner_len <= 0;
            outer_crc_hi <= 0;
            inner_sof0 <= 0;
            inner_sof1 <= 0;
            inner_ver <= 0;
            outer_crc <= 16'hffff;
            inner_body_crc <= 16'hffff;
            inner_total_crc <= 16'hffff;
            inner_crc_hi <= 0;
            inner_crc_lo <= 0;
            inner_word_18_19 <= 0;
            timeout_count <= 0;
            candidate_valid <= 0;
            candidate_kind <= 0;
            candidate_session <= 0;
            candidate_seq <= 0;
            candidate_len <= 0;
            candidate_inner_crc <= 0;
            error_valid <= 0;
            error_code <= E_NONE;
            first_error_code <= E_NONE;
            error_count <= 0;
            fault_latched <= 0;
        end else begin
            error_valid <= 0;
            if (state==S_SYNC0 || state==S_HOLD || rx_valid || rx_fe)
                timeout_count <= 0;
            else if (timeout_count<TIMEOUT_CLKS)
                timeout_count <= timeout_count+1'b1;

            // A framing error invalidates any partial frame. While a finished
            // candidate is held it also latches a fault, preserving evidence.
            if (rx_fe) begin
                error_valid <= 1;
                error_code <= E_UART_FE;
                if (first_error_code==E_NONE) first_error_code <= E_UART_FE;
                if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                if (state==S_HOLD) fault_latched <= 1;
                else state <= S_SYNC0;
            end else if (rx_valid) begin
                case (state)
                    S_SYNC0: if (rx_data==8'ha6) state <= S_SYNC1;
                    S_SYNC1: begin
                        if (rx_data==8'h69) begin
                            state <= S_HEADER;
                            header_index <= 0;
                            inner_index <= 0;
                            outer_crc <= 16'hffff;
                            inner_body_crc <= 16'hffff;
                            inner_total_crc <= 16'hffff;
                            session_reg <= 0;
                            seq_reg <= 0;
                            inner_word_18_19 <= 0;
                        end else if (rx_data!=8'ha6) state <= S_SYNC0;
                    end
                    S_HEADER: begin
                        outer_crc <= crc_next(outer_crc,rx_data);
                        case (header_index)
                            4'd0: version_reg <= rx_data;
                            4'd1: kind_reg <= rx_data;
                            4'd2,4'd3,4'd4,4'd5:
                                session_reg <= {session_reg[23:0],rx_data};
                            4'd6,4'd7,4'd8,4'd9:
                                seq_reg <= {seq_reg[23:0],rx_data};
                            4'd10: len_hi <= rx_data;
                            4'd11: begin
                                inner_len <= assembled_len;
                                if (version_reg!=8'h01 || !header_kind_ok) begin
                                    state <= S_SYNC0;
                                    error_valid <= 1;
                                    error_code <= E_HEADER;
                                    if (first_error_code==E_NONE) first_error_code <= E_HEADER;
                                    if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                                end else if (!header_length_ok) begin
                                    state <= S_SYNC0;
                                    error_valid <= 1;
                                    error_code <= E_LENGTH;
                                    if (first_error_code==E_NONE) first_error_code <= E_LENGTH;
                                    if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                                end else if (assembled_len==0) state <= S_CRC_H;
                                else state <= S_INNER;
                            end
                            default: ;
                        endcase
                        if (header_index!=4'd11) header_index <= header_index+1'b1;
                    end
                    S_INNER: begin
                        inner_mem[inner_index] <= rx_data;
                        outer_crc <= crc_next(outer_crc,rx_data);
                        inner_total_crc <= crc_next(inner_total_crc,rx_data);
                        if (inner_index>=10'd2 && inner_index<inner_len-2)
                            inner_body_crc <= crc_next(inner_body_crc,rx_data);
                        if (inner_index==0) inner_sof0 <= rx_data;
                        if (inner_index==1) inner_sof1 <= rx_data;
                        if (inner_index==2) inner_ver <= rx_data;
                        if (inner_index==18) inner_word_18_19[15:8] <= rx_data;
                        if (inner_index==19) inner_word_18_19[7:0] <= rx_data;
                        if (inner_index==inner_len-2) inner_crc_hi <= rx_data;
                        if (inner_index==inner_len-1) begin
                            inner_crc_lo <= rx_data;
                            state <= S_CRC_H;
                        end else inner_index <= inner_index+1'b1;
                    end
                    S_CRC_H: begin
                        outer_crc_hi <= rx_data;
                        state <= S_CRC_L;
                    end
                    S_CRC_L: begin
                        if (outer_crc!={outer_crc_hi,rx_data}) begin
                            error_valid <= 1;
                            error_code <= E_OUTER_CRC;
                            if (first_error_code==E_NONE) first_error_code <= E_OUTER_CRC;
                            if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                            state <= S_SYNC0;
                        end else if (kind_reg!=K_HELLO &&
                                     inner_body_crc!={inner_crc_hi,inner_crc_lo}) begin
                            error_valid <= 1;
                            error_code <= E_INNER_CRC;
                            if (first_error_code==E_NONE) first_error_code <= E_INNER_CRC;
                            if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                            state <= S_SYNC0;
                        end else if (!inner_shape_ok) begin
                            error_valid <= 1;
                            error_code <= E_INNER_SHAPE;
                            if (first_error_code==E_NONE) first_error_code <= E_INNER_SHAPE;
                            if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                            state <= S_SYNC0;
                        end else begin
                            candidate_kind <= kind_reg;
                            candidate_session <= session_reg;
                            candidate_seq <= seq_reg;
                            candidate_len <= inner_len;
                            candidate_inner_crc <= kind_reg==K_HELLO ? 16'd0 : inner_total_crc;
                            candidate_valid <= 1;
                            state <= S_HOLD;
                        end
                    end
                    S_HOLD: begin
                        error_valid <= 1;
                        error_code <= E_EXTRA_WHILE_HELD;
                        if (first_error_code==E_NONE)
                            first_error_code <= E_EXTRA_WHILE_HELD;
                        if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                        fault_latched <= 1;
                    end
                    default: state <= S_SYNC0;
                endcase
            end else if (state!=S_SYNC0 && state!=S_HOLD &&
                         timeout_count>=TIMEOUT_CLKS-1) begin
                error_valid <= 1;
                error_code <= E_TIMEOUT;
                if (first_error_code==E_NONE) first_error_code <= E_TIMEOUT;
                if (error_count!=32'hffffffff) error_count <= error_count+1'b1;
                state <= S_SYNC0;
            end else if (state==S_HOLD && candidate_release && !fault_latched) begin
                candidate_valid <= 0;
                state <= S_SYNC0;
            end
        end
    end
    assign capture_idle=state==S_SYNC0 && !candidate_valid && !fault_latched;
endmodule
