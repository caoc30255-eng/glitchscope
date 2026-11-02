`timescale 1ns / 1ps

// Same-clock request gate: accept an inbound event only after the owner has
// durably committed the exact tuple; then send an immutable TYPE+0x40 ACK.
// One current request and one completed tuple are retained for stop-and-wait.
module h1_p1_event_commit_ack_profile_v0_1 #(
    parameter IS_AX=1
)(
    input wire clk,rst_n,
    input wire rx_valid,
    input wire [7:0] rx_type,
    input wire [255:0] rx_payload,
    output wire rx_ready,
    output wire store_valid,
    output wire [7:0] store_type,
    output wire [255:0] store_payload,
    input wire store_result_valid,
    input wire [7:0] store_result_type,
    input wire [255:0] store_result_payload,
    output wire ack_valid,
    output wire [7:0] ack_type,
    output wire [255:0] ack_payload,
    input wire ack_take,
    input wire ack_done,
    output reg fault,
    output reg [7:0] fault_code
);
    localparam [2:0] IDLE=0,WAIT_STORE=1,WAIT_TAKE=2,WAIT_DONE=3,FAULT=4;
    reg [2:0] state;
    reg [7:0] held_type,last_type;
    reg [255:0] held_payload,last_payload;
    reg last_valid;
    wire allowed_ax=rx_type==8'h30 || rx_type==8'h39 || rx_type==8'h3a || rx_type==8'h3c ||
        (rx_type>=8'h34 && rx_type<=8'h37);
    wire allowed_7020=(rx_type>=8'h31 && rx_type<=8'h33) || rx_type==8'h38;
    wire direction_ok=IS_AX ? allowed_ax : allowed_7020;
    wire rx_last_equal,rx_last_key_equal,result_held_equal,rx_held_equal;
    h1_control_equal_tree_v0_1 #(.WIDTH(256)) replay_equal (
        .a(rx_payload),.b(last_payload),.equal(rx_last_equal));
    h1_control_equal_tree_v0_1 #(.WIDTH(224)) replay_key_equal (
        .a(rx_payload[223:0]),.b(last_payload[223:0]),.equal(rx_last_key_equal));
    h1_control_equal_tree_v0_1 #(.WIDTH(256)) result_equal (
        .a(store_result_payload),.b(held_payload),.equal(result_held_equal));
    h1_control_equal_tree_v0_1 #(.WIDTH(256)) pending_equal (
        .a(rx_payload),.b(held_payload),.equal(rx_held_equal));
    wire exact_replay=last_valid && rx_type==last_type && rx_last_equal;
    wire same_key_changed=last_valid && rx_type==last_type &&
        rx_last_key_equal &&
        !rx_last_equal;
    wire store_match=store_result_type==held_type &&
        result_held_equal;
    wire pending_rx_match=rx_valid && rx_type==held_type &&
        rx_held_equal;
    assign rx_ready=(state==IDLE && rx_valid && direction_ok && exact_replay) ||
        (state==WAIT_STORE && pending_rx_match && store_result_valid && store_match);
    assign store_valid=(state==WAIT_STORE);
    assign store_type=held_type;
    assign store_payload=held_payload;
    assign ack_valid=(state==WAIT_TAKE);
    assign ack_type=held_type+8'h40;
    assign ack_payload=held_payload;

    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;
            held_type<=0;held_payload<=0;
            last_type<=0;last_payload<=0;last_valid<=0;
            fault<=0;fault_code<=0;
        end else begin
            case(state)
                IDLE: if(rx_valid) begin
                    if(!direction_ok) begin
                        fault<=1;fault_code<=8'd1;state<=FAULT;
                    end else if(same_key_changed) begin
                        fault<=1;fault_code<=8'd2;state<=FAULT;
                    end else if(exact_replay) begin
                        held_type<=last_type;
                        held_payload<=last_payload;
                        state<=WAIT_TAKE;
                    end else begin
                        held_type<=rx_type;
                        held_payload<=rx_payload;
                        state<=WAIT_STORE;
                    end
                end
                WAIT_STORE: if(!pending_rx_match) begin
                    fault<=1;fault_code<=8'd5;state<=FAULT;
                end else if(store_result_valid) begin
                    if(!store_match) begin
                        fault<=1;fault_code<=8'd3;state<=FAULT;
                    end else begin
                        last_type<=held_type;
                        last_payload<=held_payload;
                        last_valid<=1;
                        state<=WAIT_TAKE;
                    end
                end
                WAIT_TAKE: if(ack_take) state<=WAIT_DONE;
                WAIT_DONE: if(ack_done) state<=IDLE;
                FAULT: state<=FAULT;
                default: begin fault<=1;fault_code<=8'd4;state<=FAULT;end
            endcase
        end
    end
endmodule
