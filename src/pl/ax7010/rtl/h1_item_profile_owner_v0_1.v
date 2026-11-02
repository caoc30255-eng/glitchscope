`timescale 1ns / 1ps
// TYPE3A has a distinct payload layout: full one-slot pre-START context plus
// injection coordinates. It is not a record-bearing P1 identity payload.
module h1_item_profile_owner_v0_1 #(
    parameter integer CLK_HZ=50000000,BAUD=1000000
)(
    input wire clk,rst_n,external_fault,
    input wire current_valid,current_started,new_commit,actual_start,actual_retired,
    input wire [7:0] current_kind,
    input wire [15:0] current_len,
    input wire [255:0] current_identity,
    input wire event_valid,
    input wire [7:0] event_type,
    input wire [255:0] event_payload,
    output wire event_ready,
    output reg commit_valid,
    output reg [7:0] commit_type,held_profile_type,
    output reg [8:0] injection_count,
    output reg [255:0] commit_payload,
    input wire commit_ready,
    output reg prepared,
    output wire permitted,
    output reg injection_enable,
    output reg [15:0] injection_byte,injection_phase,injection_width,
    output reg [2:0] injection_bit,
    output reg [255:0] held_profile_payload,
    output reg [31:0] program_count,
    output reg fault,
    output reg [7:0] fault_code,
    output reg [255:0] first_bad_payload
);
    localparam integer PERIOD=CLK_HZ/BAUD;
    reg used;
    reg [255:0] binding;
    function [255:0] to_identity;
        input [255:0] p;
        begin
            to_identity=0;
            to_identity[95:0]=p[95:0];
            to_identity[167:136]=p[127:96];to_identity[175:168]=p[135:128];
            to_identity[191:176]=p[151:136];to_identity[207:192]=p[167:152];
            to_identity[215:208]=p[175:168];to_identity[223:216]=p[183:176];
        end
    endfunction
    wire [15:0] byte_pos={event_payload[199:192],event_payload[207:200]};
    wire [15:0] phase={event_payload[223:216],event_payload[231:224]};
    wire [15:0] width={event_payload[239:232],event_payload[247:240]};
    wire [16:0] window_end={1'b0,phase}+{1'b0,width};
    wire multi=(event_type===8'h3c);
    wire [8:0] requested_count=multi ? {1'b0,event_payload[255:248]}+9'd1 : 9'd1;
    wire [16:0] requested_limit={1'b0,byte_pos}+{8'd0,requested_count};
    wire fields_ok=(((event_type===8'h3a) || multi) &&
        (multi ? (event_payload[191:184]==1 && event_payload[183:176]==0) : event_payload[255:248]==0) && event_payload[191:184]<=1 &&
        event_payload[183:176]<=1 && event_payload[175:168]<=3 && event_payload[215:208]<=7 &&
        ((event_payload[191:184]==0 && event_payload[247:192]==0) ||
         (event_payload[191:184]==1 && current_len>=22 && byte_pos>=20 &&
          requested_limit<=({1'b0,current_len}-17'd2) && width!=0 && window_end<=PERIOD)))===1'b1;
    assign event_ready=!fault && !external_fault && !commit_valid &&
        !new_commit && !actual_start && !actual_retired;
    assign permitted=prepared && !used && current_valid && current_kind==3 &&
        current_identity==binding && !fault && !external_fault && !event_valid && !new_commit;
    always @(posedge clk) begin
        if(!rst_n) begin
            prepared<=0;used<=0;binding<=0;commit_valid<=0;commit_payload<=0;
            commit_type<=0;held_profile_type<=0;injection_count<=1;
            injection_enable<=0;injection_byte<=0;injection_phase<=0;injection_width<=0;injection_bit<=0;
            held_profile_payload<=0;program_count<=0;fault<=0;fault_code<=0;first_bad_payload<=0;
        end else begin
            if(commit_valid && commit_ready) commit_valid<=0;
            if(new_commit) begin
                prepared<=0;used<=0;injection_enable<=0;injection_byte<=0;injection_count<=1;held_profile_type<=0;
                injection_phase<=0;injection_width<=0;injection_bit<=0;
            end
            if(actual_retired) prepared<=0;
            if(!fault) begin
                if(external_fault) begin fault<=1;fault_code<=1;end
                else if(actual_start && current_kind==3) begin
                    if(!permitted) begin fault<=1;fault_code<=4;end
                    else begin used<=1;prepared<=0;end
                end else if(event_valid && event_ready) begin
                    if(!current_valid || current_started || used || current_kind!=3 ||
                        to_identity(event_payload)!=current_identity) begin
                        fault<=1;fault_code<=1;first_bad_payload<=event_payload;
                    end else if(!fields_ok) begin
                        fault<=1;fault_code<=3;first_bad_payload<=event_payload;
                    end else if(prepared && (event_type!=held_profile_type || event_payload!=held_profile_payload)) begin
                        fault<=1;fault_code<=2;first_bad_payload<=event_payload;
                    end else if(!prepared && program_count==32'hffffffff) begin
                        fault<=1;fault_code<=5;first_bad_payload<=event_payload;
                    end else begin
                        commit_valid<=1;commit_payload<=event_payload;commit_type<=event_type;
                        if(!prepared) begin
                            prepared<=1;binding<=current_identity;held_profile_payload<=event_payload;
                            held_profile_type<=event_type;injection_count<=requested_count;
                            injection_enable<=event_payload[184];injection_byte<=byte_pos;
                            injection_bit<=event_payload[210:208];injection_phase<=phase;injection_width<=width;
                            program_count<=program_count+1'b1;
                        end
                    end
                end
            end
        end
    end
endmodule
