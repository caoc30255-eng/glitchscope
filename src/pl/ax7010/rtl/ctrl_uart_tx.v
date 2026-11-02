`timescale 1ns / 1ps

module ctrl_uart_tx #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD   = 1_000_000
)(
    input  wire       clk,
    input  wire       rst_n,

    input  wire [7:0] tx_data,
    input  wire       tx_start,

    output reg        uart_tx,
    output reg        tx_busy,
    output reg        tx_done
);

    localparam integer CLKS_PER_BIT = CLK_HZ / BAUD;

    localparam [1:0]
        S_IDLE  = 2'd0,
        S_START = 2'd1,
        S_DATA  = 2'd2,
        S_STOP  = 2'd3;

    reg [1:0] state;

    reg [15:0] clk_cnt;
    reg [2:0]  bit_idx;
    reg [7:0]  data_latched;

    always @(posedge clk) begin
        if (!rst_n) begin
            state        <= S_IDLE;
            clk_cnt      <= 16'd0;
            bit_idx      <= 3'd0;
            data_latched <= 8'd0;

            uart_tx      <= 1'b1;
            tx_busy      <= 1'b0;
            tx_done      <= 1'b0;
        end
        else begin
            tx_done <= 1'b0;

            case (state)

                S_IDLE: begin
                    uart_tx <= 1'b1;
                    tx_busy <= 1'b0;
                    clk_cnt <= 16'd0;
                    bit_idx <= 3'd0;

                    if (tx_start) begin
                        data_latched <= tx_data;
                        tx_busy      <= 1'b1;
                        uart_tx      <= 1'b0;
                        state        <= S_START;
                    end
                end

                S_START: begin
                    uart_tx <= 1'b0;

                    if (clk_cnt == CLKS_PER_BIT - 1) begin
                        clk_cnt <= 16'd0;
                        bit_idx <= 3'd0;
                        uart_tx <= data_latched[0];
                        state   <= S_DATA;
                    end
                    else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

             S_DATA: begin
    if (clk_cnt == CLKS_PER_BIT - 1) begin
        clk_cnt <= 16'd0;

        if (bit_idx == 3'd7) begin
            // D7 完整保持 100 clocks 后立即进入 STOP
            uart_tx <= 1'b1;
            state   <= S_STOP;
        end
        else begin
            // 当前数据位完整保持 100 clocks 后，
            // 在这个边沿立即切换到下一数据位
            bit_idx <= bit_idx + 1'b1;
            uart_tx <= data_latched[bit_idx + 1'b1];
        end
    end
    else begin
        clk_cnt <= clk_cnt + 1'b1;
    end
end

                S_STOP: begin
                    uart_tx <= 1'b1;

                    if (clk_cnt == CLKS_PER_BIT - 1) begin
                        clk_cnt <= 16'd0;
                        tx_busy <= 1'b0;
                        tx_done <= 1'b1;
                        state   <= S_IDLE;
                    end
                    else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

                default: begin
                    state   <= S_IDLE;
                    uart_tx <= 1'b1;
                    tx_busy <= 1'b0;
                    tx_done <= 1'b0;
                end

            endcase
        end
    end

endmodule