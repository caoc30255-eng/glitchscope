`timescale 1ns / 1ps
// LIFE-domain stream adapter. Does not manufacture durable storage proof.
module h1_raw_evidence_owner_diag_v0_2(
    input wire clk,rst_n,external_fault,
    input wire [31:0] route_epoch,
    input wire evidence_ready,evidence_read_valid,
    input wire [7:0] evidence_kind,evidence_read_data,
    input wire [31:0] evidence_session,evidence_seq,evidence_ticket,
    input wire [15:0] evidence_len,
    output wire [9:0] evidence_read_addr,
    output wire record_valid,input wire record_ready,
    output reg [7:0] record_kind,
    output reg [31:0] record_epoch,record_session,record_seq,record_ticket,
    output reg [15:0] record_len,
    output wire byte_valid,input wire byte_ready,
    output wire [9:0] byte_index,output reg [7:0] byte_data,output wire byte_last,
    output wire finish_valid,input wire finish_ready,
    output reg [15:0] raw_crc,
    input wire store_valid,
    input wire [7:0] store_kind,
    input wire [31:0] store_epoch,store_session,store_seq,store_ticket,store_record_id,
    input wire [15:0] store_len,store_raw_crc,
    output wire store_ready,
    output wire evidence_ack,
    output wire [31:0] ack_session,ack_seq,ack_ticket,
    output reg ack_issued,
    output reg [31:0] saved_record_id,
    output reg fault,output reg [7:0] fault_code,
    input wire diagnostic_enable,input wire [9:0] diagnostic_addr,
    output wire diagnostic_address_ready
);
    localparam [3:0] IDLE=0,HEADER=1,ADDRESS=2,READ_WAIT=3,DATA=4,FINISH=5,STORE=6,DROP=7;
    reg [3:0] state;
    reg [9:0] index;
    reg [31:0] last_epoch,last_ticket;
    reg last_valid;
    wire active=state>=HEADER && state<=STORE;
    wire binding_ok=evidence_ready && route_epoch==record_epoch &&
        evidence_kind==record_kind && evidence_session==record_session && evidence_seq==record_seq &&
        evidence_ticket==record_ticket && evidence_len==record_len;
    wire safe=!fault && !external_fault && binding_ok;
    wire proof_ok=store_kind==record_kind && store_epoch==record_epoch &&
        store_session==record_session && store_seq==record_seq && store_ticket==record_ticket &&
        store_len==record_len && store_raw_crc==raw_crc && store_record_id!=0;
    // Only synchronous LIFE registers drive the BRAM address mux/data.
    // Asynchronous visibility revocation remains in the backend, not this mux.
    reg diagnostic_selected;
    reg [9:0] diagnostic_addr_hold;
    always @(posedge clk) begin
        if(!rst_n) begin diagnostic_selected<=0;diagnostic_addr_hold<=0;end
        else begin
            diagnostic_selected<=fault && diagnostic_enable;
            if(fault && diagnostic_enable) diagnostic_addr_hold<=diagnostic_addr;
        end
    end
    assign evidence_read_addr=diagnostic_selected ? diagnostic_addr_hold : index;
    assign diagnostic_address_ready=diagnostic_selected && fault && diagnostic_enable && diagnostic_addr_hold==diagnostic_addr;
    assign record_valid=state==HEADER && safe;
    assign byte_valid=state==DATA && safe;
    assign byte_index=index;assign byte_last={6'd0,index}+16'd1==record_len;
    assign finish_valid=state==FINISH && safe;
    assign store_ready=state==STORE && safe;
    assign evidence_ack=store_valid && store_ready && proof_ok;
    assign ack_session=record_session;assign ack_seq=record_seq;assign ack_ticket=record_ticket;
    function [15:0] crc_byte;
        input [15:0] crc;input [7:0] value;integer bitno;reg [15:0] c;
        begin c=crc^{value,8'h00};for(bitno=0;bitno<8;bitno=bitno+1)
            c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_byte=c;end
    endfunction
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;index<=0;raw_crc<=16'hffff;byte_data<=0;
            record_kind<=0;record_epoch<=0;record_session<=0;record_seq<=0;record_ticket<=0;record_len<=0;
            saved_record_id<=0;ack_issued<=0;fault<=0;fault_code<=0;
            last_valid<=0;last_epoch<=0;last_ticket<=0;
        end else begin
            ack_issued<=0;
            if(!fault) begin
                if(external_fault) begin fault<=1;fault_code<=1;end
                else if(active && !binding_ok) begin fault<=1;fault_code<=2;end
                else if(store_valid && (state!=STORE || !proof_ok)) begin fault<=1;fault_code<=3;end
                else case(state)
                    IDLE:if(evidence_ready) begin
                        if(route_epoch==0 || evidence_ticket==0 ||
                            evidence_kind<1 || evidence_kind>4 || evidence_len>534 ||
                            (last_valid && route_epoch==last_epoch && evidence_ticket<=last_ticket))
                            begin fault<=1;fault_code<=4;end
                        else begin
                            record_kind<=evidence_kind;record_epoch<=route_epoch;record_session<=evidence_session;
                            record_seq<=evidence_seq;record_ticket<=evidence_ticket;record_len<=evidence_len;
                            index<=0;raw_crc<=16'hffff;state<=HEADER;
                        end
                    end
                    HEADER:if(record_ready) state<=record_len==0 ? FINISH : ADDRESS;
                    ADDRESS:state<=READ_WAIT;
                    READ_WAIT:if(evidence_read_valid) begin byte_data<=evidence_read_data;state<=DATA;end
                        else begin fault<=1;fault_code<=5;end
                    DATA:if(byte_ready) begin
                        raw_crc<=crc_byte(raw_crc,byte_data);
                        if(byte_last) state<=FINISH;
                        else begin index<=index+1'b1;state<=ADDRESS;end
                    end
                    FINISH:if(finish_ready) state<=STORE;
                    STORE:if(evidence_ack) begin
                        ack_issued<=1;saved_record_id<=store_record_id;
                        last_valid<=1;last_epoch<=record_epoch;last_ticket<=record_ticket;state<=DROP;
                    end
                    DROP:if(!evidence_ready) state<=IDLE;
                    default:begin fault<=1;fault_code<=6;end
                endcase
            end
        end
    end
endmodule
