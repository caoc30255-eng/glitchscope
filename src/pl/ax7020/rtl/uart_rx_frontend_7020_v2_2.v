`timescale 1ns / 1ps

// ============================================================
// Common UART RX Synchronizer Frontend
//
// Final hardware:
//
// UART_STIM_OUT pin
//       |
//       | external physical wire
//       v
// REF_RX_IN pin
//       |
//       v
// uart_rx_frontend
//       |
//       | ref_rx_sync
//       +------ Receiver A
//       |
//       +------ Receiver B
//
// A/B observe the SAME synchronized digital signal.
//
// IMPORTANT:
//
// - Two-stage synchronizer is shared.
// - Trial CLEANUP / ABORT does NOT reset this block.
// - Only global rst_n resets this block.
// ============================================================

module uart_rx_frontend_7020_v2_2
(
    input  wire clk,
    input  wire rst_n,

    input  wire ref_rx_i,

    output wire ref_rx_sync
);


    (* ASYNC_REG = "TRUE" *)
    reg rx_sync_ff1;

    (* ASYNC_REG = "TRUE" *)
    reg rx_sync_ff2;


    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            // UART idle = HIGH
            rx_sync_ff1 <= 1'b1;
            rx_sync_ff2 <= 1'b1;

        end

        else
        begin

            rx_sync_ff1 <= ref_rx_i;
            rx_sync_ff2 <= rx_sync_ff1;

        end

    end


    assign ref_rx_sync =
        rx_sync_ff2;


endmodule