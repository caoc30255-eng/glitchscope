`timescale 1ns / 1ps
// Fixed common-MMCM 50/100MHz + depth16 XPM CDC_SYNC_STAGES=2 reset contract.
module h1_board_reset_handoff_v0_2 #(
    parameter integer HOLD_CLKS=16, RECOVERY_CLKS=64
)(
    input wire life_clk,ctrl_clk,key_n,clock_locked,
    output reg core_reset_n=0,
    output wire io_ready
);
    wire release_async_n=key_n && clock_locked;
    (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg [2:0] life_release=0,ctrl_release=0;
    always @(posedge life_clk or negedge release_async_n)
        if(!release_async_n) life_release<=0;else life_release<={life_release[1:0],1'b1};
    always @(posedge ctrl_clk or negedge release_async_n)
        if(!release_async_n) ctrl_release<=0;else ctrl_release<={ctrl_release[1:0],1'b1};
    localparam [1:0] HOLD=0, RECOVER=1, RUN=2;
    reg [1:0] phase=HOLD;
    reg [31:0] ticks=0;
    reg reset_pending=0;
    wire domains_released=life_release[2] && ctrl_release[2];
    // core_reset_n has NO asynchronous set/reset. HOLD gives both real FIFO
    // reset inputs a sustained assertion; RECOVER allows the XPM reset FSMs
    // to complete before I/O opens. A reset during recovery is coalesced,
    // never reasserted into a busy FIFO. New loss restarts the quiet interval.
    always @(posedge life_clk) begin
        case(phase)
            HOLD:begin
                core_reset_n<=0;reset_pending<=0;
                if(!domains_released) ticks<=0;
                else if(ticks>=HOLD_CLKS-1) begin
                    core_reset_n<=1;phase<=RECOVER;ticks<=0;
                end else ticks<=ticks+1'b1;
            end
            RECOVER:begin
                if(!domains_released) begin reset_pending<=1;ticks<=0;end
                else if(ticks>=RECOVERY_CLKS-1) begin
                    ticks<=0;
                    if(reset_pending) begin core_reset_n<=0;phase<=HOLD;reset_pending<=0;end
                    else phase<=RUN;
                end else ticks<=ticks+1'b1;
            end
            RUN:if(!domains_released) begin
                core_reset_n<=0;phase<=HOLD;ticks<=0;reset_pending<=0;
            end
            default:begin core_reset_n<=0;phase<=HOLD;ticks<=0;reset_pending<=0;end
        endcase
    end
    // v0.12: remove the CTRL-release combinational launch into LIFE logic.
    // The original FIFO reset FSM is unchanged. Opening is one LIFE edge later;
    // loss of KEY/LOCK still clamps every external pin immediately.
    (* SHREG_EXTRACT="NO" *) reg life_io_ready=0;
    always @(posedge life_clk)
        life_io_ready<=domains_released && core_reset_n && phase==RUN;
    // life_release is already asynchronously cleared. This also masks a
    // sub-cycle KEY/LOCK pulse even if life_io_ready has not clocked yet.
    // No new asynchronous FF endpoint or timing exception is introduced.
    assign io_ready=release_async_n && life_release[2] && life_io_ready;
endmodule
