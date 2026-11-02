`timescale 1ns / 1ps
// Configuration qualification is separate from H1 admission and retirement.
// Owner's success_seen attests the exact stored CONFIG response; this module
// promotes it only on actual core retirement and revokes it on a new epoch.
module h1_stm_cfg_qualification_v0_1(
    input wire clk,rst_n,external_fault,
    input wire new_commit,
    input wire [7:0] commit_kind,current_kind,
    input wire [31:0] active_session,route_epoch,
    input wire [255:0] current_identity,physical_identity,
    input wire actual_retired,cfg_success_seen,
    input wire [31:0] ch1_record,
    output reg ready,
    output wire item_eligible,
    output reg [255:0] approved_identity,
    output reg [31:0] approved_record,approval_count
);
    function [31:0] unpack32;
        input [31:0] value;
        begin unpack32={value[7:0],value[15:8],value[23:16],value[31:24]};end
    endfunction
    wire same_context=current_identity[31:0]==approved_identity[31:0] &&
        current_identity[95:64]==approved_identity[95:64] &&
        current_identity[175:136]==approved_identity[175:136] &&
        current_identity[223:216]==approved_identity[223:216];
    wire live_context=active_session==unpack32(approved_identity[31:0]) &&
        route_epoch==unpack32(approved_identity[95:64]);
    assign item_eligible=ready && current_kind==3 && same_context && live_context &&
        !external_fault && !(new_commit && (commit_kind==2 || commit_kind==4));
    always @(posedge clk) begin
        if(!rst_n) begin
            ready<=0;approved_identity<=0;approved_record<=0;approval_count<=0;
        end else begin
            // Revocation wins a same-edge retirement success. Preserve audit
            // identity/record when revoking; reset starts a fresh audit epoch.
            if(external_fault || (ready && !live_context) ||
                (new_commit && (commit_kind==2 || commit_kind==4))) ready<=0;
            else if(actual_retired && current_kind==2) begin
                ready<=cfg_success_seen && ch1_record!=0 &&
                    physical_identity[135:104]!=0 &&
                    active_session==unpack32(physical_identity[31:0]) &&
                    route_epoch==unpack32(physical_identity[95:64]);
                if(cfg_success_seen && ch1_record!=0 && physical_identity[135:104]!=0 &&
                    active_session==unpack32(physical_identity[31:0]) &&
                    route_epoch==unpack32(physical_identity[95:64])) begin
                    approved_identity<=physical_identity;approved_record<=ch1_record;
                    if(approval_count!=32'hffffffff) approval_count<=approval_count+1'b1;
                end
            end
        end
    end
endmodule
