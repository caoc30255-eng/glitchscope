`timescale 1ns / 1ps

// ============================================================
// RefDUT Receiver A
//
// UART:
//   1 Mbps nominal
//   8N1
//   LSB first
//
// Clock:
//   100 MHz
//
// rx_ce:
//   16x clock enable
//   generated externally
//
// Start timing:
//
//   first sampled LOW = n = 0
//
//   start confirm:
//       m = 2
//
//   start center:
//       n = 8
//
// Data centers:
//
//   D0 = 24
//   D1 = 40
//   D2 = 56
//   D3 = 72
//   D4 = 88
//   D5 = 104
//   D6 = 120
//   D7 = 136
//
// Stop center:
//
//   n = 152
//
// Receiver A:
//
//   single-point sampling.
//
// IMPORTANT:
//
//   rx_valid is generated on the NEXT 100 MHz clock
//   after the stop-bit sample.
//
// ------------------------------------------------------------
// V1.2 common-frontend compatibility:
//
// INPUT_ALREADY_SYNCED = 0
//     Legacy mode.
//     uart_rx is asynchronous/raw.
//     Use Receiver A internal two-stage synchronizer.
//
// INPUT_ALREADY_SYNCED = 1
//     Final Top mode.
//     uart_rx already comes from shared uart_rx_frontend.
//     Internal synchronizer is bypassed.
//
// The default remains 0 so all previous testbenches continue
// to use exactly the legacy input path.
// ============================================================

module uart_rx_a_7020_observe_v0_1
#(
    parameter INPUT_ALREADY_SYNCED = 0
)
(
    input  wire       clk,
    input  wire       rst_n,

    input  wire       rx_ce,

    input  wire       uart_rx,

    output reg [7:0]  rx_byte,
    output reg        rx_valid,
    output reg        framing_error,
    output wire rx_idle
);


    // ========================================================
    // Legacy internal input synchronizer
    //
    // Still physically exists for backward-compatible tests.
    //
    // In final Top:
    //
    // INPUT_ALREADY_SYNCED = 1
    //
    // and rx_input_used directly uses uart_rx, which is already
    // the output of the shared two-stage frontend.
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
    // FSM encoding
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
    //
    // Need to reach at least 152.
    //
    // 8 bits is enough.
    // ========================================================

    reg [7:0] n;


    // ========================================================
    // Previous sampled RX level
    //
    // Only meaningful at rx_ce sample instants.
    // ========================================================

    reg prev_sample;


    // ========================================================
    // Start confirmation
    //
    // m = 2 fixed.
    // ========================================================

    reg [2:0] low_count;


    // ========================================================
    // Temporary receive byte
    // ========================================================

    reg [7:0] byte_work;


    // ========================================================
    // Pending-result mechanism
    //
    // Stop is sampled during an rx_ce event.
    //
    // But specification requires:
    //
    // result submitted on NEXT 100 MHz clock.
    //
    // Therefore:
    //
    // stop sample
    //      ↓
    // result_pending = 1
    //      ↓
    // next clk
    //      ↓
    // rx_valid = 1
    // ========================================================

    reg       result_pending;
    reg [7:0] pending_byte;
    reg       pending_framing_error;


    // ========================================================
    // Main receiver logic
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
            // rx_valid is normally LOW
            // =================================================

            rx_valid <= 1'b0;


            // =================================================
            // Submit pending result
            //
            // This happens one 100 MHz clock after the
            // stop-bit sampling event.
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
            // Receiver state machine only advances on rx_ce
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
                    // Detect sampled HIGH -> LOW transition.
                    //
                    // Current LOW sample becomes n = 0.
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

                    end


                    prev_sample <= rx_input_used;

                end


                // =============================================
                // Non-IDLE states:
                //
                // current processing corresponds to n+1
                // =============================================

                else
                begin

                    n <= n + 1'b1;


                    // =========================================
                    // CONFIRM_START
                    //
                    // m = 2
                    //
                    // n=0 already counted.
                    //
                    // At n=1:
                    // RX must still be LOW.
                    // =========================================

                    if (state == ST_CONFIRM_START)
                    begin

                        if ((n + 1'b1) < 8'd2)
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

                                // Fake start ended too early.

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
                    // n = 8 must still be LOW.
                    // =========================================

                    else if (state == ST_CHECK_START)
                    begin

                        if (
                            (n + 1'b1)
                            == 8'd8
                        )
                        begin

                            if (rx_input_used == 1'b0)
                            begin

                                state <= ST_DATA;

                            end

                            else
                            begin

                                state <= ST_IDLE;

                                prev_sample <= rx_input_used;

                                n <= 8'd0;

                            end

                        end

                    end


                    // =========================================
                    // DATA
                    //
                    // Receiver A:
                    // single-point sample.
                    // =========================================

                    else if (state == ST_DATA)
                    begin

                        case (n + 1'b1)

                            8'd24:
                            begin

                                byte_work[0] <=
                                    rx_input_used;

                            end


                            8'd40:
                            begin

                                byte_work[1] <=
                                    rx_input_used;

                            end


                            8'd56:
                            begin

                                byte_work[2] <=
                                    rx_input_used;

                            end


                            8'd72:
                            begin

                                byte_work[3] <=
                                    rx_input_used;

                            end


                            8'd88:
                            begin

                                byte_work[4] <=
                                    rx_input_used;

                            end


                            8'd104:
                            begin

                                byte_work[5] <=
                                    rx_input_used;

                            end


                            8'd120:
                            begin

                                byte_work[6] <=
                                    rx_input_used;

                            end


                            8'd136:
                            begin

                                byte_work[7] <=
                                    rx_input_used;

                                // D7 completed.
                                // Enter STOP.

                                state <= ST_STOP;

                            end


                            default:
                            begin
                            end

                        endcase

                    end


                    // =========================================
                    // STOP
                    //
                    // n = 152
                    // =========================================

                    else if (state == ST_STOP)
                    begin

                        if (
                            (n + 1'b1)
                            == 8'd152
                        )
                        begin

                            // ---------------------------------
                            // Capture result into pending regs.
                            //
                            // rx_valid is NOT asserted here.
                            //
                            // It will be asserted next 100 MHz
                            // system clock.
                            // ---------------------------------

                            pending_byte <=
                                byte_work;


                            pending_framing_error <=
                                (
                                    rx_input_used
                                    == 1'b0
                                );


                            result_pending <=
                                1'b1;


                            // ---------------------------------
                            // Valid stop bit
                            // ---------------------------------

                            if (rx_input_used == 1'b1)
                            begin

                                state <= ST_IDLE;

                                prev_sample <= 1'b1;

                                n <= 8'd0;

                            end


                            // ---------------------------------
                            // Framing error
                            // ---------------------------------

                            else
                            begin

                                state <= ST_WAIT_HIGH;

                                n <= 8'd0;

                            end

                        end

                    end

                end

            end

        end

    end


    assign rx_idle=(state==ST_IDLE) && !result_pending && !rx_valid;
endmodule