`timescale 1ns / 1ps
// B1 isolated, synchronous command interface; NOT an AXI slave or frame parser.
// CLK assumption: 100 MHz; nominal UART 1 Mbps. All commands are in clk domain.
// Frontend and CE run continuously. Receivers are reset outside the RUN window.
module receiver_trial_7020_v2_2 #(
    parameter integer ID_WIDTH = 16,
    parameter integer IDLE_CLKS = 100,
    parameter integer MIN_WINDOW_CLKS = 1100
)(
    input wire clk, input wire rst_n, input wire ch0_async,
    input wire cmd_valid, input wire [2:0] cmd,
    input wire [ID_WIDTH-1:0] shadow_trial_id,
    input wire [2:0] shadow_d, input wire signed [3:0] shadow_s,
    input wire [31:0] shadow_window_clks,
    output reg rsp_valid, output reg [3:0] rsp_code,
    output reg configured, output reg [1:0] state,
    output reg [ID_WIDTH-1:0] active_trial_id,
    output reg [2:0] active_d, output reg signed [3:0] active_s,
    output reg [31:0] active_window_clks,
    output wire ready_to_start, output wire result_valid,
    output reg [1:0] result_reason,
    output reg [7:0] a_byte, output reg [7:0] b_byte,
    output reg a_fe, output reg b_fe,
    output reg [7:0] a_count, output reg [7:0] b_count,
    output reg a_count_overflow, output reg b_count_overflow,
    output reg [31:0] a_first_cycle, output reg [31:0] b_first_cycle,
    output reg [31:0] elapsed_clks,
    output wire rx_ce_o, output wire rx_sync_o,
    output wire a_event, output wire b_event,
    output wire [7:0] a_event_byte, output wire [7:0] b_event_byte,
    output wire a_event_fe, output wire b_event_fe
);
    localparam IDLE=2'd0, RUN=2'd1, HOLD=2'd2;
    localparam APPLY=3'd1, START=3'd2, ACK=3'd3, ABORT=3'd4;
    // Response: OK, illegal command/state, illegal d/s, window too short,
    // unconfigured, input not idle. No sticky protocol error clears results.
    localparam OK=4'd0, BAD_STATE=4'd1, BAD_CFG=4'd2,
               BAD_WINDOW=4'd3, NO_CFG=4'd4, NOT_IDLE=4'd5;
    wire legal_ds =
        ((shadow_d==1) && (shadow_s>=-4'sd2) && (shadow_s<=4'sd2)) ||
        ((shadow_d==2) && (shadow_s>=-4'sd2) && (shadow_s<=4'sd1)) ||
        ((shadow_d==3) && (shadow_s>=-4'sd2) && (shadow_s<=4'sd0)) ||
        ((shadow_d==4) && (shadow_s>=-4'sd2) && (shadow_s<=-4'sd1));

    uart_rx_frontend_7020_v2_2 frontend
        (.clk(clk), .rst_n(rst_n), .ref_rx_i(ch0_async), .ref_rx_sync(rx_sync_o));
    rx_ce_gen_7020_v2_2 ce (.clk(clk), .rst_n(rst_n), .rx_ce(rx_ce_o));
    wire rx_reset_n = rst_n && (state==RUN);
    uart_rx_a_7020_v2_2 #(.INPUT_ALREADY_SYNCED(1)) receiver_a
        (.clk(clk), .rst_n(rx_reset_n), .rx_ce(rx_ce_o), .uart_rx(rx_sync_o),
         .rx_byte(a_event_byte), .rx_valid(a_event), .framing_error(a_event_fe));
    uart_rx_b_7020_v2_2 #(.INPUT_ALREADY_SYNCED(1)) receiver_b
        (.clk(clk), .rst_n(rx_reset_n), .rx_ce(rx_ce_o), .uart_rx(rx_sync_o),
         .cfg_d(active_d), .cfg_s(active_s),
         .rx_byte(b_event_byte), .rx_valid(b_event), .framing_error(b_event_fe));

    reg [31:0] idle_count;
    // Extra initialization guard prevents reset-high synchronizers from being
    // mistaken for a physical idle line when CH0 is actually low at reset.
    reg [1:0] sync_warmup;
    always @(posedge clk) begin
        if (!rst_n) begin idle_count<=0; sync_warmup<=0; end
        else begin
            if (sync_warmup!=3) sync_warmup<=sync_warmup+1'b1;
            if (sync_warmup!=3 || !rx_sync_o) idle_count<=0;
            else if (idle_count<IDLE_CLKS) idle_count<=idle_count+1'b1;
        end
    end
    assign ready_to_start = configured && (state==IDLE) &&
                            (idle_count>=IDLE_CLKS) && rx_sync_o;
    assign result_valid = (state==HOLD);

    always @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE; configured<=0; active_trial_id<=0;
            active_d<=1; active_s<=0; active_window_clks<=0;
            rsp_valid<=0; rsp_code<=OK; result_reason<=0;
            a_byte<=0; b_byte<=0; a_fe<=0; b_fe<=0;
            a_count<=0; b_count<=0; a_count_overflow<=0; b_count_overflow<=0;
            a_first_cycle<=0; b_first_cycle<=0; elapsed_clks<=0;
        end else begin
            rsp_valid<=cmd_valid;
            if (cmd_valid) rsp_code<=BAD_STATE;

            // ABORT wins over an event and natural closure on the same edge.
            // Previously captured evidence is kept; coincident events omitted.
            if (state==RUN && !(cmd_valid && cmd==ABORT)) begin
                elapsed_clks<=elapsed_clks+1'b1;
                if (a_event) begin
                    if (a_count==0) begin
                        a_byte<=a_event_byte; a_fe<=a_event_fe;
                        a_first_cycle<=elapsed_clks+1'b1;
                    end
                    if (a_count!=8'hff) a_count<=a_count+1'b1;
                    else a_count_overflow<=1;
                end
                if (b_event) begin
                    if (b_count==0) begin
                        b_byte<=b_event_byte; b_fe<=b_event_fe;
                        b_first_cycle<=elapsed_clks+1'b1;
                    end
                    if (b_count!=8'hff) b_count<=b_count+1'b1;
                    else b_count_overflow<=1;
                end
                if (elapsed_clks==active_window_clks-1) begin
                    state<=HOLD; result_reason<=1;
                end
            end

            if (cmd_valid) begin
                case (cmd)
                    APPLY: if (state==IDLE) begin
                        if (!legal_ds) rsp_code<=BAD_CFG;
                        else if (shadow_window_clks<MIN_WINDOW_CLKS) rsp_code<=BAD_WINDOW;
                        else begin
                            active_trial_id<=shadow_trial_id;
                            active_d<=shadow_d; active_s<=shadow_s;
                            active_window_clks<=shadow_window_clks;
                            configured<=1; rsp_code<=OK;
                        end
                    end
                    START: if (state==IDLE) begin
                        if (!configured) rsp_code<=NO_CFG;
                        else if (!ready_to_start) rsp_code<=NOT_IDLE;
                        else begin
                            state<=RUN; rsp_code<=OK; result_reason<=0;
                            a_byte<=0; b_byte<=0; a_fe<=0; b_fe<=0;
                            a_count<=0; b_count<=0;
                            a_count_overflow<=0; b_count_overflow<=0;
                            a_first_cycle<=0; b_first_cycle<=0; elapsed_clks<=0;
                        end
                    end
                    ACK: if (state==HOLD) begin
                        state<=IDLE; configured<=0; rsp_code<=OK;
                        // Keep last data for diagnostics, but result_valid=0.
                        // Another APPLY is required before a new START.
                    end
                    ABORT: if (state==RUN) begin
                        state<=HOLD; result_reason<=2; rsp_code<=OK;
                    end
                    default: rsp_code<=BAD_STATE;
                endcase
            end
        end
    end
endmodule
