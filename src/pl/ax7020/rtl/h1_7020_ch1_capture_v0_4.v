`timescale 1ns / 1ps
// Single trusted attempt. Byte events from UART frontend; complete raw/flags/tick evidence RAM.
module h1_7020_ch1_capture_v0_4 #(
    parameter integer CAPACITY=544, IDLE_GUARD_TICKS=10000, INTERBYTE_TICKS=200000
)(
    input wire clk,rst_n,
    input wire [63:0] tick,
    input wire arm,
    input wire [1:0] arm_kind, // 1 REPORT, 2 CONFIG_ACK, 3 CLEANUP_ACK
    input wire [255:0] arm_identity,
    input wire [31:0] arm_record_id,
    input wire [63:0] start_tick,deadline_tick,
    input wire rx_valid,
    input wire [7:0] rx_data,
    input wire [3:0] rx_flags,
    input wire rx_error_event,abort_event,
    input wire record_ack,
    input wire [9:0] read_addr,
    output reg [7:0] read_data,
    output reg [3:0] read_flags,
    output reg [63:0] read_tick,
    output reg read_valid,
    input wire error_ready,
    output wire error_event_valid,error_has_byte,
    output wire [7:0] error_data,
    output wire [3:0] error_flags,
    output wire [63:0] error_tick,
    input wire orphan_ready,
    output wire orphan_valid,orphan_has_byte,
    output wire [7:0] orphan_data,
    output wire [3:0] orphan_flags,
    output wire [63:0] orphan_tick,
    output reg [31:0] orphan_count,
    output reg active,closed,record_valid,
    output reg [255:0] saved_identity,
    output reg [31:0] saved_record_id,
    output reg [1:0] saved_kind,
    output wire [15:0] management_status,
    output reg [7:0] terminal_reason,
    output reg [63:0] record_close_tick,
    output wire [63:0] saved_start_tick,saved_deadline_tick,
    output reg [15:0] raw_count,expected_total,
    output reg report_valid,
    output reg [31:0] uart_error_count,
    output reg [3:0] uart_flags_seen,
    output reg [63:0] first_uart_error_tick,
    output wire [7:0] report_status,report_uart_flags,
    output reg fault_latched,
    output reg [7:0] first_error,
    output reg [7:0] first_lost_data,
    output reg [3:0] first_lost_flags,
    output reg [63:0] first_lost_tick,
    output reg first_lost_has_byte
);
    (* ram_style="block" *) reg [75:0] sample_ram[0:CAPACITY-1];
    reg [143:0] header;
    reg [15:0] crc_state,received_crc;
    reg [63:0] saved_start,saved_deadline,last_activity,last_tick;
    assign saved_start_tick=saved_start;assign saved_deadline_tick=saved_deadline;
    reg expected_known,uart_bad,seen_activity;
    reg [31:0] last_generation;
    wire activity=rx_valid || rx_error_event;
    wire in_window=tick>=saved_start && tick<saved_deadline;
    // Only provisional closure-tick events may extend the old candidate.
    wire same_close_candidate=closed && !record_valid && tick==record_close_tick &&
        terminal_reason<5 && expected_known && raw_count>=expected_total && tick<saved_deadline;
    wire candidate_byte=active && rx_valid && in_window && (!closed || same_close_candidate);
    assign error_event_valid=active && in_window && (!closed || same_close_candidate) && activity &&
        (rx_error_event || rx_flags!=0);
    assign error_has_byte=rx_valid;assign error_data=rx_data;assign error_flags=rx_flags;assign error_tick=tick;
    wire overflow_spill=active && rx_valid && raw_count>=CAPACITY && tick<=saved_deadline &&
        (!closed || (!record_valid && tick==record_close_tick));
    assign orphan_valid=activity && (!active || !in_window || (closed && !same_close_candidate) || overflow_spill);
    assign orphan_has_byte=rx_valid;
    assign orphan_data=rx_data;assign orphan_flags=rx_flags;assign orphan_tick=tick;
    assign report_status=saved_kind==1 ? header[23:16] : 8'd0;
    assign report_uart_flags=saved_kind==1 ? header[31:24] : 8'd0;
    assign management_status=saved_kind!=1 ? header[31:16] : 16'd0;
    wire report_fields_ok=header[143:128]==16'h55bb && header[127:120]==2 && header[15:0]<=512 &&
        header[23:16]<=3 && header[31:24]<=15 && header[39:32]<=1 && header[63:48]<64 && header[47:40]<=3;
    wire report_identity_ok=header[119:88]==saved_identity[87:56] && header[87:80]==saved_identity[55:48] &&
        header[79:64]==saved_identity[47:32] && header[63:48]==saved_identity[31:16] &&
        header[47:40]==saved_identity[15:8] && header[39:32]==saved_identity[7:0];
    wire ack_fields_ok=header[95:80]==(saved_kind==2 ? 16'h55cd : 16'h55ef) && header[79:72]==2;
    wire ack_identity_ok=header[71:40]==saved_identity[87:56] && header[39:32]==saved_identity[55:48];
    wire fields_ok=saved_kind==1 ? report_fields_ok : ack_fields_ok;
    wire identity_ok=saved_kind==1 ? report_identity_ok : ack_identity_ok;
    wire candidate_ok=fields_ok && identity_ok && !uart_bad && crc_state==received_crc;
    reg [7:0] closing_reason;
    reg [63:0] closing_tick;
    always @* begin
        closing_reason=0;closing_tick=tick;
        if(active && (!closed || (!record_valid && tick==record_close_tick))) begin
            if(tick>saved_deadline && !closed) begin closing_reason=5;closing_tick=saved_deadline;end
            else if((candidate_byte && raw_count>=CAPACITY) ||
                (rx_valid && tick==saved_deadline && raw_count>=CAPACITY)) closing_reason=7;
            else if(abort_event) closing_reason=6;
            else if(tick>=saved_deadline && !closed) begin closing_reason=5;closing_tick=saved_deadline;end
            else if(candidate_byte && expected_known && raw_count>=expected_total) closing_reason=4;
            else if(closed && same_close_candidate && rx_error_event && terminal_reason<3) closing_reason=2;
            else if(!closed && !activity && expected_known && raw_count==expected_total &&
                tick-last_activity>=IDLE_GUARD_TICKS) closing_reason=candidate_ok ? 1 : 2;
            else if(!closed && !activity && seen_activity && tick-last_activity>=INTERBYTE_TICKS) closing_reason=3;
        end
    end
    function [15:0] crc_next;
        input [15:0] old;
        input [7:0] value;
        reg [15:0] c;integer i;
        begin c=old^{value,8'd0};for(i=0;i<8;i=i+1) c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_next=c;end
    endfunction
    always @(posedge clk) begin
        if(!rst_n) begin read_data<=0;read_flags<=0;read_tick<=0;read_valid<=0;end
        else begin
            read_valid<=active && read_addr<raw_count && read_addr<CAPACITY;
            if(active && read_addr<raw_count && read_addr<CAPACITY) begin
                {read_data,read_flags,read_tick}<=sample_ram[read_addr];
            end else begin read_data<=0;read_flags<=0;read_tick<=0;end
        end
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            active<=0;closed<=0;record_valid<=0;saved_identity<=0;saved_record_id<=0;terminal_reason<=0;
            record_close_tick<=0;raw_count<=0;expected_total<=0;report_valid<=0;header<=0;saved_kind<=0;
            crc_state<=16'hffff;received_crc<=0;expected_known<=0;uart_bad<=0;seen_activity<=0;
            saved_start<=0;saved_deadline<=0;last_activity<=0;last_tick<=0;last_generation<=0;
            orphan_count<=0;fault_latched<=0;first_error<=0;first_lost_data<=0;first_lost_flags<=0;first_lost_tick<=0;first_lost_has_byte<=0;
            uart_error_count<=0;uart_flags_seen<=0;first_uart_error_tick<=0;
        end else begin
            last_tick<=tick;
            if(orphan_valid) begin
                if(orphan_count!=32'hffffffff) orphan_count<=orphan_count+1'b1;
            end
            if(((orphan_valid && !orphan_ready) || (error_event_valid && !error_ready)) && !fault_latched) begin
                fault_latched<=1;first_error<=orphan_valid && !orphan_ready ? 5 : 6;
                first_lost_data<=rx_data;first_lost_flags<=rx_flags;first_lost_tick<=tick;first_lost_has_byte<=rx_valid;
            end
            if(!fault_latched) begin
                if(tick<last_tick) begin fault_latched<=1;first_error<=1;end
                else if(arm && (active || arm_kind<1 || arm_kind>3 || arm_identity[255:219]!=0 || arm_identity[186:155]==0 ||
                    arm_identity[119:88]==0 || arm_identity[119:88]<=last_generation || arm_record_id==0 ||
                    start_tick<tick || start_tick>=deadline_tick || activity)) begin fault_latched<=1;first_error<=2;end
                else if(record_ack && (!active || !record_valid ||
                    (activity && (!orphan_valid || !orphan_ready)) || abort_event)) begin fault_latched<=1;first_error<=3;end
                else if(record_ack) begin active<=0;record_valid<=0;end
                else if(arm) begin
                    active<=1;closed<=0;record_valid<=0;saved_identity<=arm_identity;saved_record_id<=arm_record_id;saved_kind<=arm_kind;
                    saved_start<=start_tick;saved_deadline<=deadline_tick;last_activity<=start_tick;last_generation<=arm_identity[119:88];
                    terminal_reason<=0;record_close_tick<=0;raw_count<=0;expected_total<=arm_kind==1 ? 0 : 12;report_valid<=0;
                    header<=0;crc_state<=16'hffff;received_crc<=0;expected_known<=arm_kind!=1;uart_bad<=0;seen_activity<=0;
                    uart_error_count<=0;uart_flags_seen<=0;first_uart_error_tick<=0;
                end else begin
                    if(active && (!closed || same_close_candidate) && activity && in_window) begin
                        last_activity<=tick;seen_activity<=1;
                        if(rx_flags!=0 || rx_error_event) begin
                            uart_bad<=1;uart_flags_seen<=uart_flags_seen|rx_flags;
                            if(uart_error_count==0) first_uart_error_tick<=tick;
                            if(uart_error_count!=32'hffffffff) uart_error_count<=uart_error_count+1'b1;
                        end
                    end
                    if(candidate_byte && raw_count<CAPACITY) begin
                        sample_ram[raw_count]<={rx_data,rx_flags,tick};
                        raw_count<=raw_count+1'b1;
                        if(raw_count<18) header<={header[135:0],rx_data};
                        if(saved_kind==1 && raw_count==17 && header[135:120]==16'h55bb && header[119:112]==2 &&
                            {header[7:0],rx_data}<=512 && {header[7:0],rx_data}+20<=CAPACITY) begin
                            expected_total<={header[7:0],rx_data}+20;expected_known<=1;
                        end
                        if(raw_count>=2 && (!expected_known || raw_count<expected_total-2)) crc_state<=crc_next(crc_state,rx_data);
                        if(expected_known && raw_count==expected_total-2) received_crc[15:8]<=rx_data;
                        if(expected_known && raw_count==expected_total-1) received_crc[7:0]<=rx_data;
                    end
                    if(closing_reason!=0 && (!closed || closing_reason>terminal_reason)) begin
                        closed<=1;terminal_reason<=closing_reason;record_close_tick<=closing_tick;
                        report_valid<=closing_reason==1;
                    end
                    // Finalize only a live binding; retired closed metadata is diagnostic history.
                    if(active && closed && tick>record_close_tick) record_valid<=1;
                end
            end
        end
    end
    initial begin
        if(CAPACITY<20 || CAPACITY>1024 || IDLE_GUARD_TICKS<1 || INTERBYTE_TICKS<=IDLE_GUARD_TICKS)
            $fatal(1,"Invalid CH1 capture profile");
    end
endmodule
