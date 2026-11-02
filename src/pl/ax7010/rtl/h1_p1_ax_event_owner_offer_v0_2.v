`timescale 1ns / 1ps
// 50MHz owner for trusted H1/current-bank lifecycle evidence. No CH1 UART here.
module h1_p1_ax_event_owner_offer_v0_2(
    input wire clk,rst_n,
    input wire current_valid,
    input wire [7:0] current_kind,
    input wire [255:0] current_window_identity,
    input wire actual_start,
    // Independent unaccepted START offer; never feed START acceptance into retirement veto.
    input wire start_offer,
    input wire [255:0] actual_identity,
    input wire actual_mark_required,
    input wire physical_done,physical_mark,
    input wire [255:0] physical_identity,
    input wire tx_done_fenced,core_retire_ready,core_retired,external_fault,
    input wire event_valid,
    input wire [7:0] event_type,
    input wire [255:0] event_payload,
    output wire event_ready,
    output reg commit_valid,
    output reg [7:0] commit_type,
    output reg [255:0] commit_payload,
    input wire commit_ready,
    output wire start_authorized,retire_request,
    output reg window_armed,active,done_seen,mark_seen,terminal_seen,stored_seen,mark_stored,
    output reg [255:0] active_identity,
    output reg [31:0] ch1_record,mark_record,
    output reg cfg_success_seen,
    output reg fault,
    output reg [7:0] fault_code
);
    reg [255:0] window_identity;
    reg mark_required,retire_pending;
    reg [255:0] retirement_payload;
    function [223:0] no_generation;
        input [255:0] value;
        begin no_generation=value[223:0];no_generation[135:104]=0;end
    endfunction
    wire key_match=event_payload[223:0]==active_identity[223:0];
    wire [31:0] record_word={event_payload[231:224],event_payload[239:232],
        event_payload[247:240],event_payload[255:248]};
    wire physical_match=physical_identity[223:0]==active_identity[223:0];
    assign event_ready=!fault && !external_fault && !commit_valid && !retire_pending &&
        !physical_done && !physical_mark && !actual_start && !core_retired;
    assign start_authorized=window_armed && current_valid && !active && !fault &&
        !external_fault && current_window_identity==window_identity && !event_valid;
    assign retire_request=retire_pending && active && done_seen && tx_done_fenced &&
        terminal_seen && stored_seen && (!mark_required || (mark_seen && mark_stored)) &&
        core_retire_ready && !fault && !external_fault && !event_valid &&
        !physical_done && !physical_mark && !start_offer;
    always @(posedge clk) begin
        if(!rst_n) begin
            window_armed<=0;active<=0;done_seen<=0;mark_seen<=0;cfg_success_seen<=0;
            terminal_seen<=0;stored_seen<=0;mark_stored<=0;
            window_identity<=0;active_identity<=0;ch1_record<=0;mark_record<=0;
            mark_required<=0;retire_pending<=0;retirement_payload<=0;
            commit_valid<=0;commit_type<=0;commit_payload<=0;fault<=0;fault_code<=0;
        end else begin
            if(commit_valid && commit_ready) commit_valid<=0;
            if(!fault) begin
                if(external_fault) begin fault<=1;fault_code<=1;end
                else if(actual_start) begin
                    if(!start_authorized || !window_armed || active || !current_valid ||
                        current_window_identity!=window_identity ||
                        no_generation(actual_identity)!=no_generation(window_identity) ||
                        actual_identity[135:104]==0 || actual_identity[255:224]!=0) begin
                        fault<=1;fault_code<=2;
                    end else begin
                        active<=1;active_identity<=actual_identity;window_armed<=0;
                        mark_required<=actual_mark_required;done_seen<=0;mark_seen<=0;
                        terminal_seen<=0;stored_seen<=0;mark_stored<=0;
                        ch1_record<=0;mark_record<=0;cfg_success_seen<=0;
                    end
                end else if((physical_done || physical_mark) && (!active || !physical_match)) begin
                    fault<=1;fault_code<=3;
                end else if(core_retired) begin
                    if(!retire_pending || !active || !done_seen || !tx_done_fenced ||
                        !terminal_seen || !stored_seen || (mark_required && (!mark_seen || !mark_stored))) begin
                        fault<=1;fault_code<=4;
                    end else begin
                        active<=0;retire_pending<=0;
                        commit_valid<=1;commit_type<=8'h37;commit_payload<=retirement_payload;
                    end
                end else begin
                    if(physical_done) done_seen<=1;
                    if(physical_mark) begin
                        if(!mark_required || mark_seen) begin fault<=1;fault_code<=5;end
                        else mark_seen<=1;
                    end
                    if(event_valid && event_ready) begin
                        if(event_type==8'h30) begin
                            if(!current_valid || active || window_armed ||
                                event_payload!=current_window_identity ||
                                event_payload[135:104]!=0 || record_word!=0) begin
                                fault<=1;fault_code<=6;
                            end else begin
                                window_armed<=1;window_identity<=event_payload;
                                commit_valid<=1;commit_type<=event_type;commit_payload<=event_payload;
                            end
                        end else if(!active || !key_match || record_word==0) begin
                            fault<=1;fault_code<=7;
                        end else if(event_type==8'h34 && !terminal_seen) begin
                            terminal_seen<=1;ch1_record<=record_word;
                            commit_valid<=1;commit_type<=event_type;commit_payload<=event_payload;
                        end else if(event_type==8'h35 && terminal_seen && !stored_seen && record_word==ch1_record) begin
                            stored_seen<=1;
                            commit_valid<=1;commit_type<=event_type;commit_payload<=event_payload;
                        end else if(event_type==8'h36 && mark_required && mark_seen && !mark_stored) begin
                            mark_stored<=1;mark_record<=record_word;
                            commit_valid<=1;commit_type<=event_type;commit_payload<=event_payload;
                        end else if(event_type==8'h39 && current_kind==2 && !cfg_success_seen &&
                            terminal_seen && stored_seen && record_word==ch1_record && done_seen && tx_done_fenced) begin
                            cfg_success_seen<=1;
                            commit_valid<=1;commit_type<=event_type;commit_payload<=event_payload;
                        end else if(event_type==8'h37 && terminal_seen && stored_seen &&
                            record_word==ch1_record && done_seen && tx_done_fenced &&
                            (!mark_required || (mark_seen && mark_stored))) begin
                            retire_pending<=1;retirement_payload<=event_payload;
                        end else begin fault<=1;fault_code<=8;end
                    end
                end
            end
        end
    end
endmodule
