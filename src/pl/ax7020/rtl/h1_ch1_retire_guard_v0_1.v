`timescale 1ns / 1ps
// Qualified evidence retirement, not a UART parser or persistence implementation.
module h1_ch1_retire_guard_v0_1 (
    input wire clk,rst_n,
    input wire bind_start,
    input wire [255:0] bind_identity,
    input wire [63:0] start_tick,deadline_tick,
    input wire physical_done,
    input wire [255:0] done_identity,
    input wire record_close,
    input wire [255:0] record_identity,
    input wire [31:0] record_id,
    input wire [7:0] terminal_reason,
    input wire [63:0] close_tick,
    input wire watermark_valid,
    input wire [63:0] watermark_tick,
    input wire store_ack,
    input wire [255:0] store_identity,
    input wire [31:0] store_record_id,
    input wire release_request,session_can_retire,retired_ack,external_fault,
    output wire retire_fire,retire_ready,
    output wire [31:0] retire_session,retire_seq,
    output reg active,done_seen,closed_seen,stored_seen,handoff_pending,
    output reg [255:0] saved_identity,
    output reg [31:0] saved_record_id,
    output reg [7:0] saved_reason,
    output reg [63:0] saved_start,saved_deadline,saved_close,event_watermark,
    output reg fault_latched,
    output reg [7:0] first_error,
    output reg [31:0] retire_count
);
    // Identity = {reserved37, H1 session32, seq32, route_epoch32, slot3,
    // generation32, run32, image8, trial16, item16, attempt8, route8}.
    // Reasons: 1 valid report, 2 invalid report, 3 interbyte timeout,
    // 4 extra bytes, 5 deadline, 6 aborted, 7 capture overflow.
    reg [31:0] last_generation;
    wire bind_ok=bind_identity[255:219]==0 && bind_identity[186:155]!=0 &&
        bind_identity[119:88]!=0 && bind_identity[119:88]>last_generation && start_tick<deadline_tick &&
        start_tick>=(watermark_valid ? watermark_tick : event_watermark);
    wire finalized=closed_seen && event_watermark>saved_close;
    wire close_ok=active && record_identity===saved_identity && record_id!=0 &&
        terminal_reason>=1 && terminal_reason<=7 && close_tick>=saved_start && close_tick<=saved_deadline &&
        (terminal_reason!=5 || close_tick==saved_deadline) &&
        (close_tick!=saved_deadline || terminal_reason>=5) &&
        (!closed_seen || (record_id==saved_record_id && terminal_reason==saved_reason && close_tick==saved_close));
    wire store_ok=active && finalized && store_identity===saved_identity && store_record_id==saved_record_id;
    wire bad_bind=bind_start && (active || !bind_ok);
    wire bad_done=physical_done && (!active || done_identity!==saved_identity);
    wire bad_close=record_close && !close_ok;
    wire bad_store=store_ack && !store_ok;
    wire bad_watermark=watermark_valid && watermark_tick<event_watermark;
    wire bad_retired=retired_ack && (!active || !handoff_pending);
    wire event_bad=bad_bind || bad_done || bad_close || bad_store || bad_watermark || bad_retired || external_fault;
    assign retire_session=saved_identity[218:187];
    assign retire_seq=saved_identity[186:155];
    assign retire_ready=active && done_seen && finalized && stored_seen && !handoff_pending && !fault_latched;
    // Same-edge mutations/invalid evidence veto release before the consumer samples it.
    assign retire_fire=retire_ready && release_request && session_can_retire && !event_bad &&
        !bind_start && !physical_done && !record_close && !store_ack && !retired_ack;
    always @(posedge clk) begin
        if(!rst_n) begin
            active<=0;done_seen<=0;closed_seen<=0;stored_seen<=0;handoff_pending<=0;
            saved_identity<=0;saved_record_id<=0;saved_reason<=0;
            saved_start<=0;saved_deadline<=0;saved_close<=0;event_watermark<=0;
            fault_latched<=0;first_error<=0;retire_count<=0;last_generation<=0;
        end else if(!fault_latched) begin
            if(event_bad) begin
                fault_latched<=1;
                if(external_fault) first_error<=7;
                else if(bad_bind) first_error<=1;
                else if(bad_done) first_error<=2;
                else if(bad_close) first_error<=3;
                else if(bad_store) first_error<=4;
                else if(bad_watermark) first_error<=5;
                else first_error<=6;
            end else begin
                if(watermark_valid) event_watermark<=watermark_tick;
                if(bind_start) begin
                    active<=1;done_seen<=0;closed_seen<=0;stored_seen<=0;handoff_pending<=0;
                    saved_identity<=bind_identity;saved_start<=start_tick;saved_deadline<=deadline_tick;
                    saved_close<=0;saved_record_id<=0;saved_reason<=0;
                    last_generation<=bind_identity[119:88];
                end
                if(physical_done) done_seen<=1;
                if(record_close && !closed_seen) begin
                    closed_seen<=1;saved_record_id<=record_id;saved_reason<=terminal_reason;saved_close<=close_tick;
                end
                if(store_ack) stored_seen<=1;
                if(retire_fire) handoff_pending<=1;
                if(retired_ack) begin
                    active<=0;handoff_pending<=0;retire_count<=retire_count+1'b1;
                end
            end
        end
    end
endmodule
