`timescale 1ns / 1ps

// ============================================================
// AXI4-Lite Wrapper for 8-Channel Raw Snapshot Tester
// CAP-06C V1.0
//
// Register map:
//
// 0x00 COMMAND        WO
//      bit 0: ARM pulse
//      bit 1: soft-reset pulse
//
// 0x04 CONFIG         RW
//      bit 0:     trigger_enable
//      bits 10:8: trigger_channel
//
// 0x08 STATUS         RO
//      bit 0: armed
//      bit 1: busy
//      bit 2: done
//      bit 3: trigger_seen
//      bit 4: snapshot read-data valid
//      bit 5: frontend trigger pulse
//
// 0x0C SAMPLE_COUNT   RO
//
// 0x10 TRIGGER_OFFSET RO
//
// 0x14 ADDRESSES      RO
//      Backward-compatible low address bytes.
//      bits 7:0:  window_start_addr low byte
//      bits 15:8: trigger_addr low byte
//
// 0x18 READ_INDEX     RW
//      Writing automatically starts one snapshot-memory read.
//
// 0x1C READ_DATA      RO
//      bits 7:0: snapshot data
//      bit 8:    data valid
//
// 0x20 LIVE_SAMPLE    RO
//
// 0x24 RISE_VECTOR    RO
//
// 0x28 ADDRESS_FULL   RO
//      bits 11:0:  complete window_start_addr
//      bits 15:12: reserved
//      bits 27:16: complete trigger_addr
//      bits 31:28: reserved
//
// Supported Snapshot address widths:
//
//      SNAP_ADDR_WIDTH <= 12
//
// Existing 5-bit configuration and formal 12-bit configuration
// use the same register map.
// ============================================================

module raw_snapshot_axi_lite_v1
#(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 6,

    parameter integer CHANNEL_COUNT       = 8,
    parameter integer CHANNEL_INDEX_WIDTH = 3,

    parameter integer SNAP_ADDR_WIDTH = 5,
    parameter integer SNAP_DEPTH      = 32,
    parameter integer PRE_COUNT       = 8,
    parameter integer POST_COUNT      = 4
)
(
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

    input  wire [CHANNEL_COUNT-1:0]          async_i,

    output wire                              snapshot_done,
    output wire                              snapshot_busy,
    output wire                              snapshot_trigger_seen,

    output wire                              frontend_trigger_pulse_o,
    output wire [CHANNEL_COUNT-1:0]          synchronized_sample_o
);

    // ========================================================
    // Register addresses
    // ========================================================

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_COMMAND =
        6'h00;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_CONFIG =
        6'h04;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_STATUS =
        6'h08;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_SAMPLE_COUNT =
        6'h0C;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_TRIGGER_OFFSET =
        6'h10;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_ADDRESSES =
        6'h14;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_READ_INDEX =
        6'h18;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_READ_DATA =
        6'h1C;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_LIVE_SAMPLE =
        6'h20;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_RISE_VECTOR =
        6'h24;

    localparam [C_S_AXI_ADDR_WIDTH-1:0]
        ADDR_ADDRESS_FULL =
        6'h28;

    // ========================================================
    // AXI response values
    // ========================================================

    localparam [1:0] AXI_OKAY =
        2'b00;

    localparam [1:0] AXI_SLVERR =
        2'b10;

    // ========================================================
    // AXI write-channel holding registers
    // ========================================================

    reg aw_hold_valid;

    reg [C_S_AXI_ADDR_WIDTH-1:0]
        awaddr_hold;

    reg w_hold_valid;

    reg [C_S_AXI_DATA_WIDTH-1:0]
        wdata_hold;

    reg [(C_S_AXI_DATA_WIDTH/8)-1:0]
        wstrb_hold;

    // AW and W channels are accepted independently.

    assign s_axi_awready =
        !aw_hold_valid
        &&
        !s_axi_bvalid;

    assign s_axi_wready =
        !w_hold_valid
        &&
        !s_axi_bvalid;

    // Only one read response may be outstanding.

    assign s_axi_arready =
        !s_axi_rvalid;

    // ========================================================
    // Software-visible configuration
    // ========================================================

    reg trigger_enable_reg;

    reg [CHANNEL_INDEX_WIDTH-1:0]
        trigger_channel_reg;

    reg [SNAP_ADDR_WIDTH-1:0]
        snapshot_read_index_reg;

    // One-clock command pulses.

    reg arm_pulse;
    reg soft_reset_pulse;

    // ========================================================
    // Snapshot read bridge
    // ========================================================

    reg snapshot_rd_en;
    reg snapshot_read_pending;

    wire [CHANNEL_COUNT-1:0]
        snapshot_rd_data;

    wire snapshot_rd_valid;

    reg [CHANNEL_COUNT-1:0]
        snapshot_read_data_reg;

    reg snapshot_read_data_valid_reg;

    // ========================================================
    // Snapshot status and metadata
    // ========================================================

    wire snapshot_armed;

    wire [SNAP_ADDR_WIDTH:0]
        snapshot_sample_count;

    wire [SNAP_ADDR_WIDTH:0]
        snapshot_trigger_offset;

    wire [SNAP_ADDR_WIDTH-1:0]
        snapshot_window_start;

    wire [SNAP_ADDR_WIDTH-1:0]
        snapshot_trigger_addr;

    // ========================================================
    // Twelve-bit address normalization
    //
    // Small configurations are zero-extended.
    // The formal 4096-point configuration already uses
    // SNAP_ADDR_WIDTH=12.
    // ========================================================

    wire [11:0] snapshot_window_start_12;
    wire [11:0] snapshot_trigger_addr_12;

    assign snapshot_window_start_12 =
    {
        {(12-SNAP_ADDR_WIDTH){1'b0}},
        snapshot_window_start
    };

    assign snapshot_trigger_addr_12 =
    {
        {(12-SNAP_ADDR_WIDTH){1'b0}},
        snapshot_trigger_addr
    };

    // ========================================================
    // Frontend diagnostic signals
    // ========================================================

    wire [CHANNEL_COUNT-1:0]
        synchronized_sample;

    wire [CHANNEL_COUNT-1:0]
        rise_vector;

    wire selected_level;
    wire frontend_trigger_pulse;

    assign synchronized_sample_o =
        synchronized_sample;

    assign frontend_trigger_pulse_o =
        frontend_trigger_pulse;

    // ========================================================
    // Integrated capture block
    // ========================================================

    raw_snapshot_tester_8ch_v1
    #(
        .CHANNEL_COUNT
        (
            CHANNEL_COUNT
        ),

        .CHANNEL_INDEX_WIDTH
        (
            CHANNEL_INDEX_WIDTH
        ),

        .ADDR_WIDTH
        (
            SNAP_ADDR_WIDTH
        ),

        .DEPTH
        (
            SNAP_DEPTH
        ),

        .PRE_COUNT
        (
            PRE_COUNT
        ),

        .POST_COUNT
        (
            POST_COUNT
        )
    )
    u_snapshot_tester
    (
        .clk
        (
            s_axi_aclk
        ),

        .rst_n
        (
            s_axi_aresetn
        ),

        .soft_reset
        (
            soft_reset_pulse
        ),

        .async_i
        (
            async_i
        ),

        .arm
        (
            arm_pulse
        ),

        .trigger_enable
        (
            trigger_enable_reg
        ),

        .trigger_channel
        (
            trigger_channel_reg
        ),

        .rd_en
        (
            snapshot_rd_en
        ),

        .rd_index
        (
            snapshot_read_index_reg
        ),

        .rd_data
        (
            snapshot_rd_data
        ),

        .rd_valid
        (
            snapshot_rd_valid
        ),

        .armed
        (
            snapshot_armed
        ),

        .busy
        (
            snapshot_busy
        ),

        .done
        (
            snapshot_done
        ),

        .trigger_seen
        (
            snapshot_trigger_seen
        ),

        .sample_count
        (
            snapshot_sample_count
        ),

        .trigger_offset
        (
            snapshot_trigger_offset
        ),

        .window_start_addr
        (
            snapshot_window_start
        ),

        .trigger_addr
        (
            snapshot_trigger_addr
        ),

        .synchronized_sample
        (
            synchronized_sample
        ),

        .rise_vector
        (
            rise_vector
        ),

        .selected_level
        (
            selected_level
        ),

        .frontend_trigger_pulse
        (
            frontend_trigger_pulse
        )
    );

    // ========================================================
    // AXI write channel and Snapshot read control
    // ========================================================

    always @(posedge s_axi_aclk)
    begin
        if (!s_axi_aresetn)
        begin
            aw_hold_valid <=
                1'b0;

            awaddr_hold <=
                {C_S_AXI_ADDR_WIDTH{1'b0}};

            w_hold_valid <=
                1'b0;

            wdata_hold <=
                {C_S_AXI_DATA_WIDTH{1'b0}};

            wstrb_hold <=
                {(C_S_AXI_DATA_WIDTH/8){1'b0}};

            s_axi_bresp <=
                AXI_OKAY;

            s_axi_bvalid <=
                1'b0;

            trigger_enable_reg <=
                1'b1;

            trigger_channel_reg <=
                3'd2;

            snapshot_read_index_reg <=
                {SNAP_ADDR_WIDTH{1'b0}};

            arm_pulse <=
                1'b0;

            soft_reset_pulse <=
                1'b0;

            snapshot_rd_en <=
                1'b0;

            snapshot_read_pending <=
                1'b0;

            snapshot_read_data_reg <=
                {CHANNEL_COUNT{1'b0}};

            snapshot_read_data_valid_reg <=
                1'b0;
        end

        else
        begin
            // Command signals are one-clock pulses.

            arm_pulse <=
                1'b0;

            soft_reset_pulse <=
                1'b0;

            snapshot_rd_en <=
                1'b0;

            // ------------------------------------------------
            // Capture write address
            // ------------------------------------------------

            if (
                s_axi_awvalid
                &&
                s_axi_awready
            )
            begin
                aw_hold_valid <=
                    1'b1;

                awaddr_hold <=
                    s_axi_awaddr;
            end

            // ------------------------------------------------
            // Capture write data
            // ------------------------------------------------

            if (
                s_axi_wvalid
                &&
                s_axi_wready
            )
            begin
                w_hold_valid <=
                    1'b1;

                wdata_hold <=
                    s_axi_wdata;

                wstrb_hold <=
                    s_axi_wstrb;
            end

            // ------------------------------------------------
            // Complete write after both AW and W arrive
            // ------------------------------------------------

            if (
                aw_hold_valid
                &&
                w_hold_valid
                &&
                !s_axi_bvalid
            )
            begin
                aw_hold_valid <=
                    1'b0;

                w_hold_valid <=
                    1'b0;

                s_axi_bvalid <=
                    1'b1;

                s_axi_bresp <=
                    AXI_OKAY;

                case (awaddr_hold)

                    // =========================================
                    // COMMAND
                    // =========================================

                    ADDR_COMMAND:
                    begin
                        if (wstrb_hold[0])
                        begin
                            if (wdata_hold[0])
                            begin
                                arm_pulse <=
                                    1'b1;

                                snapshot_read_data_valid_reg <=
                                    1'b0;
                            end

                            if (wdata_hold[1])
                            begin
                                soft_reset_pulse <=
                                    1'b1;

                                snapshot_read_pending <=
                                    1'b0;

                                snapshot_read_data_valid_reg <=
                                    1'b0;
                            end
                        end
                    end

                    // =========================================
                    // CONFIG
                    // =========================================

                    ADDR_CONFIG:
                    begin
                        if (wstrb_hold[0])
                        begin
                            trigger_enable_reg <=
                                wdata_hold[0];
                        end

                        if (wstrb_hold[1])
                        begin
                            trigger_channel_reg <=
                                wdata_hold[10:8];
                        end
                    end

                    // =========================================
                    // READ INDEX
                    //
                    // Writing the index automatically schedules
                    // one registered Snapshot RAM read.
                    // =========================================

                    ADDR_READ_INDEX:
                    begin
                        if (wstrb_hold[0])
                        begin
                            snapshot_read_index_reg <=
                                wdata_hold
                                [SNAP_ADDR_WIDTH-1:0];

                            snapshot_read_pending <=
                                1'b1;

                            snapshot_read_data_valid_reg <=
                                1'b0;
                        end
                    end

                    // =========================================
                    // Unsupported or read-only address
                    // =========================================

                    default:
                    begin
                        s_axi_bresp <=
                            AXI_SLVERR;
                    end

                endcase
            end

            // ------------------------------------------------
            // AXI write-response handshake
            // ------------------------------------------------

            if (
                s_axi_bvalid
                &&
                s_axi_bready
            )
            begin
                s_axi_bvalid <=
                    1'b0;
            end

            // ------------------------------------------------
            // Launch Snapshot RAM read
            // ------------------------------------------------

            if (snapshot_read_pending)
            begin
                snapshot_read_pending <=
                    1'b0;

                snapshot_rd_en <=
                    1'b1;
            end

            // ------------------------------------------------
            // Latch Snapshot RAM response
            // ------------------------------------------------

            if (snapshot_rd_valid)
            begin
                snapshot_read_data_reg <=
                    snapshot_rd_data;

                snapshot_read_data_valid_reg <=
                    1'b1;
            end
        end
    end

    // ========================================================
    // AXI read channel
    // ========================================================

    always @(posedge s_axi_aclk)
    begin
        if (!s_axi_aresetn)
        begin
            s_axi_rdata <=
                {C_S_AXI_DATA_WIDTH{1'b0}};

            s_axi_rresp <=
                AXI_OKAY;

            s_axi_rvalid <=
                1'b0;
        end

        else
        begin
            // ------------------------------------------------
            // Accept one AXI read address
            // ------------------------------------------------

            if (
                s_axi_arvalid
                &&
                s_axi_arready
            )
            begin
                s_axi_rvalid <=
                    1'b1;

                s_axi_rresp <=
                    AXI_OKAY;

                case (s_axi_araddr)

                    // =========================================
                    // COMMAND
                    // =========================================

                    ADDR_COMMAND:
                    begin
                        s_axi_rdata <=
                            32'd0;
                    end

                    // =========================================
                    // CONFIG
                    // =========================================

                    ADDR_CONFIG:
                    begin
                        s_axi_rdata <=
                        {
                            21'd0,
                            trigger_channel_reg,
                            7'd0,
                            trigger_enable_reg
                        };
                    end

                    // =========================================
                    // STATUS
                    // =========================================

                    ADDR_STATUS:
                    begin
                        s_axi_rdata <=
                        {
                            26'd0,
                            frontend_trigger_pulse,
                            snapshot_read_data_valid_reg,
                            snapshot_trigger_seen,
                            snapshot_done,
                            snapshot_busy,
                            snapshot_armed
                        };
                    end

                    // =========================================
                    // SAMPLE COUNT
                    // =========================================

                    ADDR_SAMPLE_COUNT:
                    begin
                        s_axi_rdata <=
                        {
                            {(31-SNAP_ADDR_WIDTH){1'b0}},
                            snapshot_sample_count
                        };
                    end

                    // =========================================
                    // TRIGGER OFFSET
                    // =========================================

                    ADDR_TRIGGER_OFFSET:
                    begin
                        s_axi_rdata <=
                        {
                            {(31-SNAP_ADDR_WIDTH){1'b0}},
                            snapshot_trigger_offset
                        };
                    end

                    // =========================================
                    // BACKWARD-COMPATIBLE LOW ADDRESSES
                    //
                    // bits 7:0  = window start low byte
                    // bits 15:8 = trigger address low byte
                    // =========================================

                    ADDR_ADDRESSES:
                    begin
                        s_axi_rdata <=
                        {
                            16'd0,
                            snapshot_trigger_addr_12[7:0],
                            snapshot_window_start_12[7:0]
                        };
                    end

                    // =========================================
                    // SNAPSHOT READ INDEX
                    // =========================================

                    ADDR_READ_INDEX:
                    begin
                        s_axi_rdata <=
                        {
                            {(32-SNAP_ADDR_WIDTH){1'b0}},
                            snapshot_read_index_reg
                        };
                    end

                    // =========================================
                    // SNAPSHOT READ DATA
                    // =========================================

                    ADDR_READ_DATA:
                    begin
                        s_axi_rdata <=
                        {
                            23'd0,
                            snapshot_read_data_valid_reg,
                            snapshot_read_data_reg
                        };
                    end

                    // =========================================
                    // LIVE SYNCHRONIZED SAMPLE
                    // =========================================

                    ADDR_LIVE_SAMPLE:
                    begin
                        s_axi_rdata <=
                        {
                            {(32-CHANNEL_COUNT){1'b0}},
                            synchronized_sample
                        };
                    end

                    // =========================================
                    // RISING-EDGE VECTOR
                    // =========================================

                    ADDR_RISE_VECTOR:
                    begin
                        s_axi_rdata <=
                        {
                            {(32-CHANNEL_COUNT){1'b0}},
                            rise_vector
                        };
                    end

                    // =========================================
                    // FULL 12-BIT PHYSICAL ADDRESSES
                    //
                    // bits 11:0  = window start
                    // bits 15:12 = reserved
                    // bits 27:16 = trigger address
                    // bits 31:28 = reserved
                    // =========================================

                    ADDR_ADDRESS_FULL:
                    begin
                        s_axi_rdata <=
                        {
                            4'd0,
                            snapshot_trigger_addr_12,
                            4'd0,
                            snapshot_window_start_12
                        };
                    end

                    // =========================================
                    // Unsupported address
                    // =========================================

                    default:
                    begin
                        s_axi_rdata <=
                            32'hDEAD_BEEF;

                        s_axi_rresp <=
                            AXI_SLVERR;
                    end

                endcase
            end

            // ------------------------------------------------
            // AXI read-response handshake
            // ------------------------------------------------

            if (
                s_axi_rvalid
                &&
                s_axi_rready
            )
            begin
                s_axi_rvalid <=
                    1'b0;
            end
        end
    end

endmodule