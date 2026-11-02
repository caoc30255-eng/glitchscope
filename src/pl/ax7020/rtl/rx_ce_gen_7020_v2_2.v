`timescale 1ns / 1ps

// ============================================================
// RefDUT 16x UART receive clock-enable generator
//
// Input:
//     clk = 100 MHz
//
// Output:
//     rx_ce average frequency = 16 MHz
//
// Algorithm:
//     acc += 4
//
//     if acc >= 25:
//         acc -= 25
//         rx_ce = 1
//
//     else:
//         rx_ce = 0
//
// Expected:
//
//     adjacent rx_ce intervals:
//         6 or 7 system clocks
//
//     every 16 rx_ce ticks:
//         exactly 100 system clocks
//         = 1000 ns
// ============================================================

module rx_ce_gen_7020_v2_2
(
    input  wire clk,
    input  wire rst_n,

    output reg  rx_ce
);


    // --------------------------------------------------------
    // acc range:
    //
    // 0 ~ 24
    //
    // 5 bits are sufficient.
    // --------------------------------------------------------

    reg [4:0] acc;


    // --------------------------------------------------------
    // Temporary sum:
    //
    // maximum:
    // 24 + 4 = 28
    //
    // 5 bits are sufficient.
    // --------------------------------------------------------

    wire [4:0] acc_plus_4;

    assign acc_plus_4 =
        acc + 5'd4;


    // ========================================================
    // NCO
    // ========================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            acc   <= 5'd0;
            rx_ce <= 1'b0;

        end

        else
        begin

            if (acc_plus_4 >= 5'd25)
            begin

                acc <=
                    acc_plus_4
                    - 5'd25;

                rx_ce <= 1'b1;

            end

            else
            begin

                acc <=
                    acc_plus_4;

                rx_ce <= 1'b0;

            end

        end

    end


endmodule