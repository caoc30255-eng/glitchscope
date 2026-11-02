`timescale 1ns / 1ps

// ============================================================================
// AXI4-Lite wrapper for STM32 DUT response receiver V1
//
// Register map:
//
// 0x00 COMMAND      WO
//      bit0: clear response mailbox and latched error
//      bit1: clear response/error counters
//
// 0x04 STATUS       RO
//      bit0: response_valid
//      bit1: response_overrun
//      bit2: error_latched
//      bit3: receiver busy
//      bits7:4: last_error_code
//      bits15:8: STM32 response status
//
// 0x08 TRIAL_ID     RO
//      bits15:0: response trial ID
//
// 0x0C RESPONSE     RO
//      bits7:0: received length
//      bits15:8: received payload
//      bits23:16: STM32 UART flags
//      bits31:24: STM32 response status
//
// 0x10 COUNTS       RO
//      bits15:0: accepted response count
//      bits31:16: receiver/protocol error count
//
// 0x14 LIVE         RO
//      bit0: raw DUT response input level
// ============================================================================

module dut_response_axi_lite_v1 #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 6,
    parameter integer CLK_HZ = 100_000_000,
    parameter integer BAUD = 1_000_000,
    parameter integer BYTE_TIMEOUT_CLKS = 1_000_000
)(
    input  wire                              s_axi_aclk,
    input  wire                              s_axi_aresetn,

    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_awaddr,
    input  wire                              s_axi_awvalid,
    output wire                              s_axi_awready,

    input  wire [C_S_AXI_DATA_WIDTH-1:0]     s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  wire                              s_axi_wvalid,
    output wire                              s_axi_wready,

    output reg  [1:0]                        s_axi_bresp,
    output reg                               s_axi_bvalid,
    input  wire                              s_axi_bready,

    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_araddr,
    input  wire                              s_axi_arvalid,
    output wire                              s_axi_arready,

    output reg  [C_S_AXI_DATA_WIDTH-1:0]     s_axi_rdata,
    output reg  [1:0]                        s_axi_rresp,
    output reg                               s_axi_rvalid,
    input  wire                              s_axi_rready,

    input  wire                              dut_response_i
);

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_COMMAND  = 6'h00,
        ADDR_STATUS   = 6'h04,
        ADDR_TRIAL_ID = 6'h08,
        ADDR_RESPONSE = 6'h0C,
        ADDR_COUNTS   = 6'h10,
        ADDR_LIVE     = 6'h14;

    localparam [1:0]
        AXI_OKAY   = 2'b00,
        AXI_SLVERR = 2'b10;

    reg aw_hold_valid;
    reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_hold;
    reg w_hold_valid;
    reg [C_S_AXI_DATA_WIDTH-1:0] wdata_hold;
    reg [(C_S_AXI_DATA_WIDTH/8)-1:0] wstrb_hold;

    reg receiver_clear_pulse;
    reg counters_clear_pulse;

    wire receiver_response_valid;
    wire [15:0] receiver_trial_id;
    wire [7:0] receiver_rx_len;
    wire [7:0] receiver_rx_payload;
    wire [7:0] receiver_uart_flags;
    wire [7:0] receiver_status;
    wire receiver_overrun;
    wire receiver_error_pulse;
    wire [3:0] receiver_error_code;
    wire receiver_busy;

    reg response_valid_delayed;
    reg error_latched;
    reg [3:0] last_error_code;
    reg [15:0] response_count;
    reg [15:0] error_count;

    // The original LIVE register sampled the asynchronous pin directly.
    // Keep the mailbox receiver unchanged; synchronize the diagnostic LIVE bit.
    (* ASYNC_REG = "TRUE" *) reg live_sync1;
    (* ASYNC_REG = "TRUE" *) reg live_sync2;
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            live_sync1 <= 1'b1;
            live_sync2 <= 1'b1;
        end else begin
            live_sync1 <= dut_response_i;
            live_sync2 <= live_sync1;
        end
    end

    assign s_axi_awready =
        !aw_hold_valid && !s_axi_bvalid;

    assign s_axi_wready =
        !w_hold_valid && !s_axi_bvalid;

    assign s_axi_arready =
        !s_axi_rvalid;

    dut_response_receiver_v1 #(
        .CLK_HZ            (CLK_HZ),
        .BAUD              (BAUD),
        .BYTE_TIMEOUT_CLKS (BYTE_TIMEOUT_CLKS)
    ) u_dut_response_receiver (
        .clk                 (s_axi_aclk),
        .rst_n               (s_axi_aresetn),
        .uart_rx             (dut_response_i),
        .clear               (receiver_clear_pulse),
        .response_valid      (receiver_response_valid),
        .response_trial_id   (receiver_trial_id),
        .response_rx_len     (receiver_rx_len),
        .response_rx_payload (receiver_rx_payload),
        .response_uart_flags (receiver_uart_flags),
        .response_status     (receiver_status),
        .response_overrun    (receiver_overrun),
        .error_pulse         (receiver_error_pulse),
        .error_code          (receiver_error_code),
        .rx_busy             (receiver_busy)
    );

    // ========================================================================
    // Event latches and counters
    // ========================================================================

    always @(posedge s_axi_aclk)
    begin
        if (!s_axi_aresetn)
        begin
            response_valid_delayed <= 1'b0;
            error_latched <= 1'b0;
            last_error_code <= 4'd0;
            response_count <= 16'd0;
            error_count <= 16'd0;
        end
        else
        begin
            response_valid_delayed <= receiver_response_valid;

            if (receiver_clear_pulse)
            begin
                error_latched <= 1'b0;
                last_error_code <= 4'd0;
            end

            if (counters_clear_pulse)
            begin
                response_count <= 16'd0;
                error_count <= 16'd0;
            end

            if (
                receiver_response_valid
                &&
                !response_valid_delayed
            )
            begin
                response_count <= response_count + 1'b1;
            end

            if (receiver_error_pulse)
            begin
                error_latched <= 1'b1;
                last_error_code <= receiver_error_code;
                error_count <= error_count + 1'b1;
            end
        end
    end

    // ========================================================================
    // AXI write channel
    // ========================================================================

    always @(posedge s_axi_aclk)
    begin
        if (!s_axi_aresetn)
        begin
            aw_hold_valid <= 1'b0;
            awaddr_hold <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            w_hold_valid <= 1'b0;
            wdata_hold <= {C_S_AXI_DATA_WIDTH{1'b0}};
            wstrb_hold <= {(C_S_AXI_DATA_WIDTH/8){1'b0}};

            s_axi_bresp <= AXI_OKAY;
            s_axi_bvalid <= 1'b0;

            receiver_clear_pulse <= 1'b0;
            counters_clear_pulse <= 1'b0;
        end
        else
        begin
            receiver_clear_pulse <= 1'b0;
            counters_clear_pulse <= 1'b0;

            if (s_axi_awvalid && s_axi_awready)
            begin
                aw_hold_valid <= 1'b1;
                awaddr_hold <= s_axi_awaddr;
            end

            if (s_axi_wvalid && s_axi_wready)
            begin
                w_hold_valid <= 1'b1;
                wdata_hold <= s_axi_wdata;
                wstrb_hold <= s_axi_wstrb;
            end

            if (aw_hold_valid && w_hold_valid && !s_axi_bvalid)
            begin
                aw_hold_valid <= 1'b0;
                w_hold_valid <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= AXI_OKAY;

                case (awaddr_hold)
                    ADDR_COMMAND:
                    begin
                        if (wstrb_hold[0])
                        begin
                            if (wdata_hold[0])
                                receiver_clear_pulse <= 1'b1;

                            if (wdata_hold[1])
                                counters_clear_pulse <= 1'b1;
                        end
                    end

                    default:
                    begin
                        s_axi_bresp <= AXI_SLVERR;
                    end
                endcase
            end

            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;
        end
    end

    // ========================================================================
    // AXI read channel
    // ========================================================================

    always @(posedge s_axi_aclk)
    begin
        if (!s_axi_aresetn)
        begin
            s_axi_rdata <= {C_S_AXI_DATA_WIDTH{1'b0}};
            s_axi_rresp <= AXI_OKAY;
            s_axi_rvalid <= 1'b0;
        end
        else
        begin
            if (s_axi_arvalid && s_axi_arready)
            begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= AXI_OKAY;

                case (s_axi_araddr)
                    ADDR_COMMAND:
                        s_axi_rdata <= 32'd0;

                    ADDR_STATUS:
                        s_axi_rdata <= {
                            16'd0,
                            receiver_status,
                            last_error_code,
                            receiver_busy,
                            error_latched,
                            receiver_overrun,
                            receiver_response_valid
                        };

                    ADDR_TRIAL_ID:
                        s_axi_rdata <= {16'd0, receiver_trial_id};

                    ADDR_RESPONSE:
                        s_axi_rdata <= {
                            receiver_status,
                            receiver_uart_flags,
                            receiver_rx_payload,
                            receiver_rx_len
                        };

                    ADDR_COUNTS:
                        s_axi_rdata <= {error_count, response_count};

                    ADDR_LIVE:
                        s_axi_rdata <= {31'd0, live_sync2};

                    default:
                    begin
                        s_axi_rdata <= 32'hDEAD_BEEF;
                        s_axi_rresp <= AXI_SLVERR;
                    end
                endcase
            end

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
        end
    end

endmodule
