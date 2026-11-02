`timescale 1ns / 1ps
// AX outbound stop-and-wait transport. Input is a ready/valid stream of
// distinct application events; a producer must not submit one event twice.
// The shared TX arbiter supplies take/done, not FIFO insertion confirmation.
module h1_p1_event_reliable_tx_v0_2 #(
    parameter integer ACK_TIMEOUT_CLKS=1000000,
    parameter integer TX_TIMEOUT_CLKS=2000000,
    parameter integer MAX_RETRIES=2
)(
    input wire clk,rst_n,external_fault,
    input wire event_valid,
    input wire [7:0] event_type,
    input wire [255:0] event_payload,
    output wire event_ready,
    output wire tx_valid,
    output wire [7:0] tx_type,
    output wire [255:0] tx_payload,
    input wire tx_take,tx_done,
    input wire ack_valid,
    input wire [7:0] ack_type,
    input wire [255:0] ack_payload,
    output wire ack_ready,
    output reg confirmed,
    output reg [7:0] confirmed_type,
    output reg [255:0] confirmed_payload,
    output reg fault,
    output reg [7:0] fault_code,
    output reg [2:0] pending_count,
    output reg [31:0] retry_count
);
    localparam [1:0] IDLE=0, OFFER=1, SENDING=2, WAIT_ACK=3;
    reg [1:0] state,rd_ptr,wr_ptr;
    reg [7:0] types[0:3];
    reg [255:0] payloads[0:3];
    reg [31:0] timer,retries;
    reg last_valid,physical_seen,ack_seen;
    reg [7:0] last_type;
    reg [255:0] last_payload;
    wire type_ok=(event_type>=8'h31 && event_type<=8'h33) || event_type==8'h38;
    wire fields_ok=event_payload[31:0]!=0 && event_payload[63:32]!=0 &&
        event_payload[135:104]!=0 && event_payload[103:99]==0 &&
        event_payload[223:216]<=1 &&
        ((event_type==8'h38 && event_payload[255:224]!=0) ||
         (event_type!=8'h38 && event_payload[255:224]==0));
    assign event_ready=!fault && !external_fault && pending_count<4;
    assign tx_valid=state==OFFER && !fault && !external_fault;
    assign tx_type=types[rd_ptr];
    assign tx_payload=payloads[rd_ptr];
    // Eight registered 32-bit comparisons replace the 256-bit combinational
    // reduction from asynchronous queue read through the state decision.
    reg ack_pending,ack_head_type,ack_previous_type,ack_qualified;
    reg [7:0] ack_head_parts,ack_previous_parts;
    integer part;
    assign ack_ready=!fault && !external_fault && !ack_pending;
    wire push=event_valid && event_ready && type_ok && fields_ok;
    wire ack_capture=ack_valid && ack_ready;
    wire ack_current=ack_pending && ack_head_type && (&ack_head_parts);
    wire ack_last=ack_pending && ack_previous_type && (&ack_previous_parts);
    wire known_ack=ack_current && ack_qualified;
    // Qualification is captured with the ACK, never upgraded by a later done.
    // A capture holds the head even if an earlier late ACK is already latched;
    // the new tuple must be checked before any release can occur.
    wire release_edge=state==WAIT_ACK || (state==SENDING && tx_done);
    wire pop=!fault && !external_fault && release_edge &&
        ((known_ack) || (ack_seen && !ack_capture && !ack_pending));
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;rd_ptr<=0;wr_ptr<=0;pending_count<=0;
            timer<=0;retries<=0;retry_count<=0;last_valid<=0;
            last_type<=0;last_payload<=0;physical_seen<=0;ack_seen<=0;confirmed<=0;
            confirmed_type<=0;confirmed_payload<=0;fault<=0;fault_code<=0;
            ack_pending<=0;ack_head_type<=0;ack_previous_type<=0;
            ack_qualified<=0;ack_head_parts<=0;ack_previous_parts<=0;
        end else begin
            confirmed<=0;
            ack_pending<=0;
            if(ack_capture) begin
                ack_pending<=1;
                ack_head_type<=pending_count!=0 && ack_type==(types[rd_ptr]+8'h40);
                ack_previous_type<=last_valid && ack_type==(last_type+8'h40);
                ack_qualified<=physical_seen || state==WAIT_ACK || (state==SENDING && tx_done);
                for(part=0;part<8;part=part+1) begin
                    ack_head_parts[part]<=ack_payload[part*32 +:32]==payloads[rd_ptr][part*32 +:32];
                    ack_previous_parts[part]<=ack_payload[part*32 +:32]==last_payload[part*32 +:32];
                end
            end
            if(!fault) begin
                if(external_fault) begin fault<=1;fault_code<=1;end
                else if(event_valid && event_ready && (!type_ok || !fields_ok)) begin
                    fault<=1;fault_code<=2;
                end else if(tx_take && state!=OFFER) begin fault<=1;fault_code<=3;end
                else if(tx_done && state!=SENDING) begin fault<=1;fault_code<=4;end
                else if(ack_pending && !known_ack && !ack_last) begin
                    fault<=1;fault_code<=5;
                end else begin
                    if(known_ack && !pop) ack_seen<=1;
                    if(push) begin
                        types[wr_ptr]<=event_type;payloads[wr_ptr]<=event_payload;
                        wr_ptr<=wr_ptr+1'b1;
                    end
                    case({push,pop})
                        2'b10:pending_count<=pending_count+1'b1;
                        2'b01:pending_count<=pending_count-1'b1;
                        default:pending_count<=pending_count;
                    endcase
                    if(pop) begin
                        confirmed<=1;confirmed_type<=types[rd_ptr];
                        confirmed_payload<=payloads[rd_ptr];
                        last_valid<=1;last_type<=types[rd_ptr];last_payload<=payloads[rd_ptr];
                        rd_ptr<=rd_ptr+1'b1;state<=IDLE;timer<=0;retries<=0;physical_seen<=0;ack_seen<=0;
                    end else case(state)
                        IDLE:if(pending_count!=0) begin state<=OFFER;timer<=0;end
                        OFFER:if(tx_take) begin state<=SENDING;timer<=0;end
                            else if(timer>=TX_TIMEOUT_CLKS-1) begin fault<=1;fault_code<=6;end
                            else timer<=timer+1'b1;
                        SENDING:if(tx_done) begin state<=WAIT_ACK;timer<=0;physical_seen<=1;end
                            else if(timer>=TX_TIMEOUT_CLKS-1) begin fault<=1;fault_code<=7;end
                            else timer<=timer+1'b1;
                        WAIT_ACK:if(timer>=ACK_TIMEOUT_CLKS-1) begin
                            // Give an ACK captured at the deadline its bounded
                            // one-cycle comparison before retry/exhaustion.
                            if(ack_capture) timer<=timer;
                            else
                            if(retries>=MAX_RETRIES) begin fault<=1;fault_code<=8;end
                            else begin retries<=retries+1'b1;retry_count<=retry_count+1'b1;
                                state<=OFFER;timer<=0;end
                        end else timer<=timer+1'b1;
                    endcase
                end
            end
        end
    end
endmodule
