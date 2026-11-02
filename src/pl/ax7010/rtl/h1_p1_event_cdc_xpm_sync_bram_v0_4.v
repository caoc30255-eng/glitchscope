`timescale 1ns / 1ps

// XPM asynchronous FIFO transports the coherent word. The credit latch keeps
// the external contract at one in-flight item despite the primitive depth16.
// Common reset epoch is required; independent single-domain reset unsupported.
module h1_p1_event_cdc_xpm_v0_2 #(
    parameter integer WIDTH=264
)(
    input wire src_clk,dst_clk,rst_n,
    input wire src_valid,
    input wire [WIDTH-1:0] src_data,
    output wire src_ready,
    output wire dst_valid,
    output wire [WIDTH-1:0] dst_data,
    input wire dst_ready
);
    (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg [1:0] src_reset_pipe,dst_reset_pipe;
    wire ack_sync;
    reg [3:0] source_guard;
    reg ack_toggle,inflight,launch_ack;
    wire src_run=src_reset_pipe[1];
    wire dst_run=dst_reset_pipe[1];
    wire full,empty,wr_reset_busy,rd_reset_busy;
    wire write_take=src_valid && src_ready;
    wire read_take=dst_valid && dst_ready;
    // Capture a complete offered word before driving any XPM BRAM write pin.
    // These private controls have synchronous reset only. Common reset may
    // discard a pre-reset pending operation; it never confirms that epoch.
    reg fifo_write_pending=1'b0,fifo_read_pending=1'b0;
    reg [WIDTH-1:0] fifo_write_data;
    always @(posedge src_clk) begin
        if(!rst_n) fifo_write_pending<=0;
        else fifo_write_pending<=write_take;
        if(write_take) fifo_write_data<=src_data;
    end
    always @(posedge dst_clk) begin
        if(!rst_n) fifo_read_pending<=0;
        else fifo_read_pending<=read_take;
    end
    assign src_ready=src_run && source_guard[3] && !wr_reset_busy && !full && !inflight && !fifo_write_pending;
    assign dst_valid=dst_run && !rd_reset_busy && !empty && !fifo_read_pending;

    always @(posedge src_clk or negedge rst_n) begin
        if(!rst_n) src_reset_pipe<=0;
        else src_reset_pipe<={src_reset_pipe[0],1'b1};
    end
    always @(posedge dst_clk or negedge rst_n) begin
        if(!rst_n) dst_reset_pipe<=0;
        else dst_reset_pipe<={dst_reset_pipe[0],1'b1};
    end
    always @(posedge dst_clk or negedge rst_n) begin
        if(!rst_n) ack_toggle<=0;
        else if(!dst_run) ack_toggle<=0;
        else if(fifo_read_pending && !rd_reset_busy && !empty) ack_toggle<=~ack_toggle;
    end
    always @(posedge src_clk or negedge rst_n) begin
        if(!rst_n) begin
            source_guard<=0;inflight<=0;launch_ack<=0;
        end else if(!src_run) begin
            source_guard<=0;inflight<=0;launch_ack<=0;
        end else begin
            // xpm_cdc_single has no runtime reset port. Quarantine source
            // admission while the common-reset ack=0 traverses its two stages.
            source_guard<={source_guard[2:0],1'b1};
            if(write_take) begin inflight<=1;launch_ack<=ack_sync;end
            else if(inflight && ack_sync!=launch_ack) inflight<=0;
        end
    end

    xpm_cdc_single #(
        .DEST_SYNC_FF(2),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)
    ) consumption_ack_sync (
        .src_clk(dst_clk),.src_in(ack_toggle),
        .dest_clk(src_clk),.dest_out(ack_sync)
    );

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("block"),.ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0),.SIM_ASSERT_CHK(1),
        .FIFO_WRITE_DEPTH(16),.WRITE_DATA_WIDTH(WIDTH),
        .READ_DATA_WIDTH(WIDTH),.WR_DATA_COUNT_WIDTH(5),
        .RD_DATA_COUNT_WIDTH(5),.CDC_SYNC_STAGES(2),
        .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),
        .FULL_RESET_VALUE(0),.DOUT_RESET_VALUE("0"),
        .USE_ADV_FEATURES("0000"),.PROG_FULL_THRESH(9),.PROG_EMPTY_THRESH(5)
    ) coherent_fifo (
        .sleep(1'b0),.rst(!src_run),
        .wr_clk(src_clk),.wr_en(fifo_write_pending),.din(fifo_write_data),
        .full(full),.wr_rst_busy(wr_reset_busy),
        .prog_full(),.wr_data_count(),.overflow(),.almost_full(),.wr_ack(),
        .rd_clk(dst_clk),.rd_en(fifo_read_pending),.dout(dst_data),
        .empty(empty),.rd_rst_busy(rd_reset_busy),
        .prog_empty(),.rd_data_count(),.underflow(),.almost_empty(),.data_valid(),
        .injectsbiterr(1'b0),.injectdbiterr(1'b0),.sbiterr(),.dbiterr()
    );
endmodule

