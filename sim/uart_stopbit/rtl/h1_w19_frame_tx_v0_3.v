`timescale 1ns / 1ps
// Mechanical frame sender: caller owns immutable current RAM and START authorization.
// RAW framing is preserved; explicit cell timing and a registered masked pin are added. No STM success is invented.
module h1_w19_frame_tx_v0_3 #(
    parameter integer CLK_HZ=50000000, BAUD=1000000
)(
    input wire clk,rst_n,
    input wire launch,launch_authorized,current_valid,current_started,current_done,
    input wire [7:0] frame_kind,
    input wire [31:0] frame_session,frame_seq,
    input wire [15:0] frame_len,
    input wire abort_request,
    input wire rearm_request,rearm_authorized,
    input wire [31:0] rearm_session,rearm_seq,
    output reg [9:0] read_addr,
    input wire [7:0] read_data,
    output wire w19_tx,physical_start_take,launch_accept,data_bit_active,
    input wire mask_enable,
    input wire [2:0] mask_bit,
    input wire [15:0] mask_phase,mask_width,
    output wire masked_tx,mask_active,mask_mark,
    output wire [9:0] frame_byte_index,
    output wire [2:0] data_bit_index,
    output wire [31:0] data_bit_clock,
    output wire busy,
    output reg launch_taken,launch_rejected,rearm_taken,rearm_rejected,physical_start,physical_done,
    output reg [31:0] saved_session,saved_seq,
    output reg [15:0] saved_len,completed_bytes,
    output reg [7:0] saved_kind,
    output reg fault_latched,
    output reg [7:0] first_error,
    output reg [31:0] start_count,done_count,
    output reg [2:0] state
);
    localparam [2:0] IDLE=0,ADDRESS=1,WAIT_RAM=2,OFFER=3,WAIT_BYTE=4;
    reg [9:0] index;
    reg used;
    wire byte_ready,byte_busy,byte_done;
    wire descriptor_ok=launch_authorized===1'b1 && current_valid===1'b1 &&
        current_started===1'b0 && current_done===1'b0 && frame_len>=1 && frame_len<=534 &&
        (frame_kind==2 || frame_kind==3 || frame_kind==4) && frame_seq!=0;
    wire byte_valid=state==OFFER && !fault_latched && !abort_request;
    wire byte_reset_n=rst_n && !fault_latched && !abort_request;
    assign busy=state!=IDLE;
    assign launch_accept=rst_n && launch && !fault_latched && state==IDLE && !used && descriptor_ok && !abort_request;
    assign frame_byte_index=index;
    assign physical_start_take=state==OFFER && byte_ready && index==0 && !fault_latched && !abort_request;
    h1_uart_tx_byte_v0_2 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_byte(
        .clk(clk),.rst_n(byte_reset_n),.byte_valid(byte_valid),.byte_data(read_data),
        .byte_ready(byte_ready),.uart_tx(w19_tx),.busy(byte_busy),.byte_done(byte_done),
        .mask_enable(mask_enable),.mask_bit(mask_bit),.mask_phase(mask_phase),.mask_width(mask_width),
        .masked_tx(masked_tx),.mask_active(mask_active),.mask_mark(mask_mark),
        .data_bit_active(data_bit_active),.data_bit_index(data_bit_index),.data_bit_clock(data_bit_clock)
    );
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;index<=0;read_addr<=0;used<=0;
            launch_taken<=0;launch_rejected<=0;rearm_taken<=0;rearm_rejected<=0;physical_start<=0;physical_done<=0;
            saved_session<=0;saved_seq<=0;saved_len<=0;saved_kind<=0;completed_bytes<=0;
            fault_latched<=0;first_error<=0;start_count<=0;done_count<=0;
        end else begin
            launch_taken<=0;launch_rejected<=0;rearm_taken<=0;rearm_rejected<=0;physical_start<=0;physical_done<=0;
            if(rearm_request) begin
                if(rearm_authorized===1'b1 && !fault_latched && !abort_request && !busy && used &&
                    completed_bytes==saved_len && rearm_session===saved_session && rearm_seq===saved_seq && !launch) begin
                    used<=0;rearm_taken<=1;
                end else rearm_rejected<=1;
            end
            if(launch && (fault_latched || busy || used || !descriptor_ok || abort_request)) launch_rejected<=1;
            if(abort_request && busy && !fault_latched) begin
                // An explicitly aborted partial frame cannot emit physical_done.
                fault_latched<=1;first_error<=1;state<=IDLE;
            end else if(!fault_latched) case(state)
                IDLE: if(launch && !used && descriptor_ok && !abort_request) begin
                    saved_session<=frame_session;saved_seq<=frame_seq;saved_len<=frame_len;saved_kind<=frame_kind;
                    index<=0;read_addr<=0;completed_bytes<=0;launch_taken<=1;used<=1;state<=ADDRESS;
                end
                ADDRESS: begin read_addr<=index;state<=WAIT_RAM;end
                WAIT_RAM: state<=OFFER;
                OFFER: if(byte_ready) begin
                    if(index==0) begin physical_start<=1;start_count<=start_count+1'b1;end
                    state<=WAIT_BYTE;
                end
                WAIT_BYTE: if(byte_done) begin
                    completed_bytes<=completed_bytes+1'b1;
                    if({6'd0,index}+16'd1==saved_len) begin
                        physical_done<=1;done_count<=done_count+1'b1;state<=IDLE;
                    end else begin index<=index+1'b1;state<=ADDRESS;end
                end
                default: begin fault_latched<=1;first_error<=2;state<=IDLE;end
            endcase
        end
    end
    // Rearming requires externally qualified retirement and the saved physical identity.
endmodule
