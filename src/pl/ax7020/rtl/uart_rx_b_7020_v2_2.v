`timescale 1ns / 1ps

// ============================================================
// RefDUT Receiver B
//
// UART:
//   1 Mbps nominal
//   8N1
//   LSB first
//
// clk:
//   100 MHz
//
// rx_ce:
//   average 16 MHz clock-enable
//
// ------------------------------------------------------------
// Start:
//
// first sampled LOW:
//     n = 0
//
// fixed start confirm:
//     m = 2
//
// fixed start center:
//     n = 8
//
// IMPORTANT:
//     start center is NOT shifted by s.
//
// ------------------------------------------------------------
// Data center:
//
// Dk:
//     c = 24 + 16*k
//
// Receiver B samples:
//
//     c+s-d
//     c+s
//     c+s+d
//
// and performs 3-point majority voting.
//
// ------------------------------------------------------------
// Stop:
//
// nominal center:
//     n = 152
//
// samples:
//
//     152+s-d
//     152+s
//     152+s+d
//
// ------------------------------------------------------------
// Legal configuration used by current experiment:
//
//     d = 1 ... 4
//     s = -2 ... +2
//
// m is fixed to 2.
//
// ------------------------------------------------------------
// Configuration behavior:
//
// cfg_d / cfg_s are latched when a new start candidate
// is detected.
//
// Therefore changing cfg_d/cfg_s in the middle of a frame
// does NOT alter the current frame.
//
// ------------------------------------------------------------
// Result timing:
//
// Result becomes pending after the last STOP sample.
//
// rx_valid is asserted on the NEXT 100 MHz clock.
//
// ------------------------------------------------------------
// V1.2 common-frontend compatibility:
//
// INPUT_ALREADY_SYNCED = 0
//
//     Legacy mode.
//     uart_rx passes through Receiver B internal 2FF
//     synchronizer.
//
// INPUT_ALREADY_SYNCED = 1
//
//     Final Top mode.
//     uart_rx already comes from common uart_rx_frontend.
//     Internal synchronizer is bypassed.
//
// Default remains 0 for all previous regression tests.
// ============================================================

module uart_rx_b_7020_v2_2
#(
    parameter INPUT_ALREADY_SYNCED = 0
)
(
    input  wire              clk,
    input  wire              rst_n,

    input  wire              rx_ce,

    input  wire              uart_rx,

    input  wire [2:0]        cfg_d,
    input  wire signed [3:0] cfg_s,

    output reg  [7:0]        rx_byte,
    output reg               rx_valid,
    output reg               framing_error
);


    // ========================================================
    // Legacy two-stage input synchronizer
    // ========================================================

    reg rx_sync1;
    reg rx_sync2;


    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            rx_sync1 <= 1'b1;
            rx_sync2 <= 1'b1;

        end

        else
        begin

            rx_sync1 <= uart_rx;
            rx_sync2 <= rx_sync1;

        end

    end


    // ========================================================
    // Effective receiver input
    // ========================================================

    wire rx_input_used;


    assign rx_input_used =
        INPUT_ALREADY_SYNCED
        ?
        uart_rx
        :
        rx_sync2;


    // ========================================================
    // FSM
    // ========================================================

    localparam ST_IDLE          = 3'd0;
    localparam ST_CONFIRM_START = 3'd1;
    localparam ST_CHECK_START   = 3'd2;
    localparam ST_DATA          = 3'd3;
    localparam ST_STOP          = 3'd4;
    localparam ST_WAIT_HIGH     = 3'd5;


    reg [2:0] state;


    // ========================================================
    // Oversample index
    // ========================================================

    reg [7:0] n;


    // ========================================================
    // Previous rx_ce sampled value
    // ========================================================

    reg prev_sample;


    // ========================================================
    // Start confirmation
    //
    // m = 2 fixed
    // ========================================================

    reg [2:0] low_count;


    // ========================================================
    // Working byte
    // ========================================================

    reg [7:0] byte_work;


    // ========================================================
    // Current data bit
    // ========================================================

    reg [2:0] bit_index;


    // ========================================================
    // Majority vote accumulator
    //
    // number of HIGH samples among current 3 samples
    //
    // range:
    //     0 ... 3
    // ========================================================

    reg [1:0] vote_ones;


    // ========================================================
    // Active configuration
    //
    // cfg_s externally:
    //
    //     -2,-1,0,+1,+2
    //
    // Internally convert to:
    //
    //     s_code:
    //
    //     -2 -> 0
    //     -1 -> 1
    //      0 -> 2
    //     +1 -> 3
    //     +2 -> 4
    //
    // Then:
    //
    // shifted_center
    //     = center + s_code - 2
    //
    // avoids unsigned/signed arithmetic ambiguity
    // in sampling-position calculations.
    // ========================================================

    reg [2:0] active_d;
    reg [2:0] active_s_code;


    // ========================================================
    // Pending result
    // ========================================================

    reg       result_pending;

    reg [7:0] pending_byte;

    reg       pending_framing_error;


    // ========================================================
    // Sampling-position combinational calculations
    // ========================================================

    wire [8:0] n_next_u;


    assign n_next_u =
        {1'b0, n}
        +
        9'd1;


    // --------------------------------------------------------
    // Data center:
    //
    // 24 + 16*bit_index
    // --------------------------------------------------------

    wire [8:0] data_center_u;


    assign data_center_u =
        9'd24
        +
        (
            {6'd0, bit_index}
            << 4
        );


    // --------------------------------------------------------
    // center+s
    // --------------------------------------------------------

    wire [8:0] data_shift_center_u;


    assign data_shift_center_u =
        data_center_u
        +
        {6'd0, active_s_code}
        -
        9'd2;


    // --------------------------------------------------------
    // Three data samples
    // --------------------------------------------------------

    wire [8:0] data_left_u;
    wire [8:0] data_mid_u;
    wire [8:0] data_right_u;


    assign data_left_u =
        data_shift_center_u
        -
        {6'd0, active_d};


    assign data_mid_u =
        data_shift_center_u;


    assign data_right_u =
        data_shift_center_u
        +
        {6'd0, active_d};


    // ========================================================
    // STOP sample positions
    // ========================================================

    wire [8:0] stop_shift_center_u;

    wire [8:0] stop_left_u;
    wire [8:0] stop_mid_u;
    wire [8:0] stop_right_u;


    assign stop_shift_center_u =
        9'd152
        +
        {6'd0, active_s_code}
        -
        9'd2;


    assign stop_left_u =
        stop_shift_center_u
        -
        {6'd0, active_d};


    assign stop_mid_u =
        stop_shift_center_u;


    assign stop_right_u =
        stop_shift_center_u
        +
        {6'd0, active_d};


    // ========================================================
    // Main state machine
    // ========================================================

    always @(posedge clk)
    begin

        if (!rst_n)
        begin

            state <= ST_IDLE;

            n <= 8'd0;

            prev_sample <= 1'b1;

            low_count <= 3'd0;

            byte_work <= 8'd0;

            bit_index <= 3'd0;

            vote_ones <= 2'd0;


            active_d <= 3'd1;

            active_s_code <= 3'd2;


            rx_byte <= 8'd0;

            rx_valid <= 1'b0;

            framing_error <= 1'b0;


            result_pending <= 1'b0;

            pending_byte <= 8'd0;

            pending_framing_error <= 1'b0;

        end

        else
        begin

            // =================================================
            // rx_valid is a one-system-clock pulse
            // =================================================

            rx_valid <= 1'b0;


            // =================================================
            // Submit result
            // =================================================

            if (result_pending)
            begin

                rx_byte <= pending_byte;

                framing_error <=
                    pending_framing_error;

                rx_valid <= 1'b1;

                result_pending <= 1'b0;

            end


            // =================================================
            // FSM only moves at rx_ce
            // =================================================

            if (rx_ce)
            begin

                // =============================================
                // WAIT_HIGH
                // =============================================

                if (state == ST_WAIT_HIGH)
                begin

                    if (rx_input_used == 1'b1)
                    begin

                        state <= ST_IDLE;

                        prev_sample <= 1'b1;

                        n <= 8'd0;

                    end

                end


                // =============================================
                // IDLE
                // =============================================

                else if (state == ST_IDLE)
                begin

                    // -----------------------------------------
                    // HIGH -> LOW:
                    //
                    // current sample = n=0
                    // -----------------------------------------

                    if (
                        (prev_sample == 1'b1)
                        &&
                        (rx_input_used == 1'b0)
                    )
                    begin

                        state <= ST_CONFIRM_START;

                        n <= 8'd0;

                        low_count <= 3'd1;

                        byte_work <= 8'd0;

                        bit_index <= 3'd0;

                        vote_ones <= 2'd0;


                        // =====================================
                        // Latch d
                        // =====================================

                        active_d <= cfg_d;


                        // =====================================
                        // Latch s
                        // =====================================

                        case (cfg_s)

                            -4'sd2:
                                active_s_code <= 3'd0;

                            -4'sd1:
                                active_s_code <= 3'd1;

                            4'sd0:
                                active_s_code <= 3'd2;

                            4'sd1:
                                active_s_code <= 3'd3;

                            4'sd2:
                                active_s_code <= 3'd4;

                            default:
                                active_s_code <= 3'd2;

                        endcase

                    end


                    prev_sample <=
                        rx_input_used;

                end


                // =============================================
                // Non-IDLE
                // =============================================

                else
                begin

                    n <= n + 1'b1;


                    // =========================================
                    // CONFIRM_START
                    //
                    // m=2
                    // =========================================

                    if (state == ST_CONFIRM_START)
                    begin

                        if (n_next_u < 9'd2)
                        begin

                            if (rx_input_used == 1'b0)
                            begin

                                low_count <=
                                    low_count + 1'b1;


                                if (
                                    (
                                        low_count
                                        + 1'b1
                                    )
                                    >= 3'd2
                                )
                                begin

                                    state <= ST_CHECK_START;

                                end

                            end

                            else
                            begin

                                state <= ST_IDLE;

                                prev_sample <= 1'b1;

                                n <= 8'd0;

                            end

                        end

                        else
                        begin

                            state <= ST_CHECK_START;

                        end

                    end


                    // =========================================
                    // CHECK_START
                    //
                    // fixed n=8
                    //
                    // s does NOT affect this.
                    // =========================================

                    else if (state == ST_CHECK_START)
                    begin

                        if (n_next_u == 9'd8)
                        begin

                            if (rx_input_used == 1'b0)
                            begin

                                state <= ST_DATA;

                                bit_index <= 3'd0;

                                vote_ones <= 2'd0;

                            end

                            else
                            begin

                                state <= ST_IDLE;

                                prev_sample <=
                                    rx_input_used;

                                n <= 8'd0;

                            end

                        end

                    end


                    // =========================================
                    // DATA
                    // =========================================

                    else if (state == ST_DATA)
                    begin

                        // -------------------------------------
                        // Sample #1:
                        // center+s-d
                        // -------------------------------------

                        if (n_next_u == data_left_u)
                        begin

                            if (rx_input_used)
                            begin

                                vote_ones <= 2'd1;

                            end

                            else
                            begin

                                vote_ones <= 2'd0;

                            end

                        end


                        // -------------------------------------
                        // Sample #2:
                        // center+s
                        // -------------------------------------

                        else if (n_next_u == data_mid_u)
                        begin

                            if (rx_input_used)
                            begin

                                vote_ones <=
                                    vote_ones + 1'b1;

                            end

                        end


                        // -------------------------------------
                        // Sample #3:
                        // center+s+d
                        //
                        // decide majority here.
                        // -------------------------------------

                        else if (n_next_u == data_right_u)
                        begin

                            if (
                                (
                                    vote_ones
                                    +
                                    (
                                        rx_input_used
                                        ?
                                        2'd1
                                        :
                                        2'd0
                                    )
                                )
                                >= 2
                            )
                            begin

                                byte_work[
                                    bit_index
                                ] <= 1'b1;

                            end

                            else
                            begin

                                byte_work[
                                    bit_index
                                ] <= 1'b0;

                            end


                            vote_ones <= 2'd0;


                            // =================================
                            // D7 completed
                            // =================================

                            if (bit_index == 3'd7)
                            begin

                                state <= ST_STOP;

                            end

                            else
                            begin

                                bit_index <=
                                    bit_index + 1'b1;

                            end

                        end

                    end


                    // =========================================
                    // STOP
                    // =========================================

                    else if (state == ST_STOP)
                    begin

                        // -------------------------------------
                        // Stop sample #1
                        // -------------------------------------

                        if (n_next_u == stop_left_u)
                        begin

                            if (rx_input_used)
                            begin

                                vote_ones <= 2'd1;

                            end

                            else
                            begin

                                vote_ones <= 2'd0;

                            end

                        end


                        // -------------------------------------
                        // Stop sample #2
                        // -------------------------------------

                        else if (n_next_u == stop_mid_u)
                        begin

                            if (rx_input_used)
                            begin

                                vote_ones <=
                                    vote_ones + 1'b1;

                            end

                        end


                        // -------------------------------------
                        // Stop sample #3
                        // -------------------------------------

                        else if (n_next_u == stop_right_u)
                        begin

                            pending_byte <=
                                byte_work;


                            // =================================
                            // Majority says STOP=1
                            // =================================

                            if (
                                (
                                    vote_ones
                                    +
                                    (
                                        rx_input_used
                                        ?
                                        2'd1
                                        :
                                        2'd0
                                    )
                                )
                                >= 2
                            )
                            begin

                                pending_framing_error <=
                                    1'b0;


                                result_pending <=
                                    1'b1;


                                state <= ST_IDLE;

                                prev_sample <= 1'b1;

                                n <= 8'd0;

                            end


                            // =================================
                            // Majority says STOP=0
                            // =================================

                            else
                            begin

                                pending_framing_error <=
                                    1'b1;


                                result_pending <=
                                    1'b1;


                                state <= ST_WAIT_HIGH;

                                n <= 8'd0;

                            end


                            vote_ones <=
                                2'd0;

                        end

                    end

                end

            end

        end

    end


endmodule