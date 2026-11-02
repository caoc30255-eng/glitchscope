`timescale 1ns / 1ps

module ctrl_uart_rx #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD   = 1_000_000
)(
    input  wire       clk,
    input  wire       rst_n,

    input  wire       uart_rx,

    output reg  [7:0] rx_data,
    output reg        rx_valid,
    output reg        framing_error,
    output reg        rx_busy
);


// ============================================================
// UART timing
// ============================================================

localparam integer CLKS_PER_BIT  = CLK_HZ / BAUD;
localparam integer HALF_BIT_CLKS = CLKS_PER_BIT / 2;


// ============================================================
// RX state definitions
// ============================================================

localparam [1:0]
    S_IDLE  = 2'd0,
    S_START = 2'd1,
    S_DATA  = 2'd2,
    S_STOP  = 2'd3;


// ============================================================
// State machine state
//
// mark_debug:
// Observe state transition with ILA
// ============================================================

(* mark_debug = "true" *)
reg [1:0] state;


// ============================================================
// Raw UART input debug signal
//
// This is a copy of the physical UART RX input.
// It allows ILA to observe the waveform arriving at F17.
// ============================================================

(* mark_debug = "true" *)
wire uart_rx_dbg;

assign uart_rx_dbg = uart_rx;


// ============================================================
// UART input synchronizer
// ============================================================

(* ASYNC_REG = "TRUE" *)
reg rx_ff1;

(* ASYNC_REG = "TRUE", mark_debug = "true" *)
reg rx_ff2;

reg rx_prev;


always @(posedge clk) begin

    if (!rst_n) begin

        rx_ff1  <= 1'b1;
        rx_ff2  <= 1'b1;
        rx_prev <= 1'b1;

    end
    else begin

        rx_ff1  <= uart_rx;
        rx_ff2  <= rx_ff1;
        rx_prev <= rx_ff2;

    end

end


// ============================================================
// Start-bit falling-edge detection
// ============================================================

wire start_fall;

assign start_fall =
    rx_prev
    &
    ~rx_ff2;


// ============================================================
// RX state-machine registers
// ============================================================

(* mark_debug = "true" *)
reg [15:0] clk_cnt;

(* mark_debug = "true" *)
reg [2:0] bit_idx;

reg [7:0] shift_reg;


// ============================================================
// Debug mirrors
//
// These mirror the one-clock output pulses so Vivado keeps
// convenient ILA probe names.
// ============================================================

(* mark_debug = "true" *)
wire rx_valid_dbg;

(* mark_debug = "true" *)
wire framing_error_dbg;


assign rx_valid_dbg =
    rx_valid;

assign framing_error_dbg =
    framing_error;


// ============================================================
// RX state machine
// ============================================================

always @(posedge clk) begin

    if (!rst_n) begin

        state         <= S_IDLE;

        clk_cnt       <= 16'd0;
        bit_idx       <= 3'd0;
        shift_reg     <= 8'd0;

        rx_data       <= 8'd0;
        rx_valid      <= 1'b0;
        framing_error <= 1'b0;
        rx_busy       <= 1'b0;

    end
    else begin

        // ----------------------------------------------------
        // One-clock event outputs
        // ----------------------------------------------------

        rx_valid      <= 1'b0;
        framing_error <= 1'b0;


        case (state)


            // =================================================
            // IDLE
            //
            // Wait for HIGH -> LOW transition.
            // =================================================

            S_IDLE: begin

                clk_cnt <= 16'd0;
                bit_idx <= 3'd0;
                rx_busy <= 1'b0;

                if (start_fall) begin

                    clk_cnt <= 16'd0;
                    rx_busy <= 1'b1;

                    state <= S_START;

                end

            end


            // =================================================
            // START BIT
            //
            // Sample approximately at the center of the start
            // bit.
            //
            // LOW  -> valid start bit
            // HIGH -> false start
            // =================================================

            S_START: begin

                rx_busy <= 1'b1;

                if (
                    clk_cnt ==
                    HALF_BIT_CLKS - 1
                ) begin

                    clk_cnt <= 16'd0;

                    if (rx_ff2 == 1'b0) begin

                        bit_idx <= 3'd0;
                        state   <= S_DATA;

                    end
                    else begin

                        // False start
                        rx_busy <= 1'b0;
                        state   <= S_IDLE;

                    end

                end
                else begin

                    clk_cnt <=
                        clk_cnt + 1'b1;

                end

            end


            // =================================================
            // DATA BITS
            //
            // UART is LSB first:
            //
            // D0, D1, ... D7
            // =================================================

            S_DATA: begin

                rx_busy <= 1'b1;

                if (
                    clk_cnt ==
                    CLKS_PER_BIT - 1
                ) begin

                    clk_cnt <= 16'd0;

                    shift_reg[bit_idx] <=
                        rx_ff2;

                    if (bit_idx == 3'd7) begin

                        state <= S_STOP;

                    end
                    else begin

                        bit_idx <=
                            bit_idx + 1'b1;

                    end

                end
                else begin

                    clk_cnt <=
                        clk_cnt + 1'b1;

                end

            end


            // =================================================
            // STOP BIT
            //
            // Sample stop bit.
            //
            // HIGH -> valid UART frame
            // LOW  -> framing error
            // =================================================

            S_STOP: begin

                rx_busy <= 1'b1;

                if (
                    clk_cnt ==
                    CLKS_PER_BIT - 1
                ) begin

                    clk_cnt <= 16'd0;

                    if (rx_ff2 == 1'b1) begin

                        rx_data <=
                            shift_reg;

                        rx_valid <=
                            1'b1;

                    end
                    else begin

                        rx_data <=
                            shift_reg;

                        framing_error <=
                            1'b1;

                    end

                    rx_busy <=
                        1'b0;

                    state <=
                        S_IDLE;

                end
                else begin

                    clk_cnt <=
                        clk_cnt + 1'b1;

                end

            end


            // =================================================
            // DEFAULT
            // =================================================

            default: begin

                state <=
                    S_IDLE;

                clk_cnt <=
                    16'd0;

                bit_idx <=
                    3'd0;

                rx_busy <=
                    1'b0;

                rx_valid <=
                    1'b0;

                framing_error <=
                    1'b0;

            end


        endcase

    end

end


endmodule