`timescale 1ns / 1ps
// Lifecycle-domain pulse capture. Queue insertion records physical facts;
// acceptance by this queue is neither peer ACK nor a core retirement proof.
module h1_p1_notification_capture_v0_1(
    input wire clk,rst_n,external_fault,
    input wire actual_start,physical_done,physical_mark,actual_retired,
    input wire [255:0] start_identity,physical_identity,retired_identity,
    output wire event_valid,
    output wire [7:0] event_type,
    output wire [255:0] event_payload,
    input wire event_ready,
    output reg [2:0] pending_count,
    output reg fault,
    output reg [7:0] fault_code,first_lost_type,
    output reg [255:0] first_lost_payload
);
    reg [1:0] rd_ptr,wr_ptr;
    reg [7:0] types[0:3];
    reg [255:0] payloads[0:3];
    wire pulse=actual_start || physical_done || physical_mark || actual_retired;
    wire collision=(actual_start && (physical_done || physical_mark || actual_retired)) ||
        (physical_done && (physical_mark || actual_retired)) || (physical_mark && actual_retired);
    wire [7:0] typ=actual_start ? 8'h31 : physical_done ? 8'h32 : physical_mark ? 8'h33 : 8'h38;
    wire [255:0] value=actual_start ? start_identity : actual_retired ? retired_identity : physical_identity;
    assign event_valid=pending_count!=0 && !fault && !external_fault;
    assign event_type=types[rd_ptr];
    assign event_payload=payloads[rd_ptr];
    wire pop=event_valid && event_ready;
    wire capacity=pending_count<4 || pop;
    always @(posedge clk) begin
        if(!rst_n) begin
            rd_ptr<=0;wr_ptr<=0;pending_count<=0;fault<=0;fault_code<=0;
            first_lost_type<=0;first_lost_payload<=0;
        end else if(!fault) begin
            if(external_fault || collision || (pulse && !capacity)) begin
                fault<=1;fault_code<=external_fault ? 1 : collision ? 2 : 3;
                if(pulse) begin first_lost_type<=typ;first_lost_payload<=value;end
            end else begin
                if(pulse) begin types[wr_ptr]<=typ;payloads[wr_ptr]<=value;wr_ptr<=wr_ptr+1'b1;end
                if(pop) rd_ptr<=rd_ptr+1'b1;
                case({pulse,pop})
                    2'b10:pending_count<=pending_count+1'b1;
                    2'b01:pending_count<=pending_count-1'b1;
                    default:pending_count<=pending_count;
                endcase
            end
        end
    end
endmodule
