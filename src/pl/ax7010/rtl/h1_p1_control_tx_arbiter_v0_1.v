`timescale 1ns / 1ps

// One physical control TX pin shared by an existing RESULT frame engine and
// a proposed event frame engine. A grant remains owned until physical done.
module h1_p1_control_tx_arbiter_v0_1 #(
    parameter integer TIMEOUT_CLKS = 1000000
)(
    input  wire clk,
    input  wire rst_n,
    input  wire legacy_valid,
    output reg  legacy_start,
    input  wire legacy_accepted,
    input  wire legacy_done,
    input  wire legacy_pin,
    output wire legacy_take,
    output reg  legacy_complete,
    input  wire event_valid,
    output reg  event_start,
    input  wire event_accepted,
    input  wire event_done,
    input  wire event_pin,
    output wire event_take,
    output reg  event_complete,
    output wire tx_pin,
    output wire busy,
    output reg  fault,
    output reg [7:0] fault_code
);
    localparam [1:0] IDLE=0, WAIT_ACCEPT=1, RUN=2, FAULT=3;
    reg [1:0] state;
    reg owner_event;
    reg prefer_event;
    reg [31:0] elapsed;
    wire chosen_accepted=owner_event ? event_accepted : legacy_accepted;
    wire chosen_done=owner_event ? event_done : legacy_done;
    assign legacy_take=(state==WAIT_ACCEPT && !owner_event && legacy_accepted);
    assign event_take=(state==WAIT_ACCEPT && owner_event && event_accepted);
    assign busy=(state!=IDLE);
    assign tx_pin=(state==IDLE) ? 1'b1 : (owner_event ? event_pin : legacy_pin);

    always @(posedge clk) begin
        if (!rst_n) begin
            state<=IDLE;
            owner_event<=0;
            prefer_event<=0;
            elapsed<=0;
            legacy_start<=0;
            event_start<=0;
            legacy_complete<=0;
            event_complete<=0;
            fault<=0;
            fault_code<=0;
        end else begin
            legacy_start<=0;
            event_start<=0;
            legacy_complete<=0;
            event_complete<=0;
            case(state)
                IDLE: begin
                    elapsed<=0;
                    if (legacy_valid || event_valid) begin
                        if (event_valid && (!legacy_valid || prefer_event)) begin
                            owner_event<=1;
                            event_start<=1;
                        end else begin
                            owner_event<=0;
                            legacy_start<=1;
                        end
                        state<=WAIT_ACCEPT;
                    end
                end
                WAIT_ACCEPT: begin
                    if (chosen_done) begin
                        fault<=1;
                        fault_code<=8'd1; // done before accepted
                        state<=FAULT;
                    end else if (chosen_accepted) begin
                        elapsed<=0;
                        state<=RUN;
                    end else if (elapsed>=TIMEOUT_CLKS-1) begin
                        fault<=1;
                        fault_code<=8'd2; // launch not accepted
                        state<=FAULT;
                    end else elapsed<=elapsed+1'b1;
                end
                RUN: begin
                    if (chosen_done) begin
                        if (owner_event) begin
                            event_complete<=1;
                            prefer_event<=0;
                        end else begin
                            legacy_complete<=1;
                            prefer_event<=1;
                        end
                        state<=IDLE;
                    end else if (elapsed>=TIMEOUT_CLKS-1) begin
                        fault<=1;
                        fault_code<=8'd3; // final stop not completed
                        state<=FAULT;
                    end else elapsed<=elapsed+1'b1;
                end
                FAULT: begin
                    // Keep pin ownership; controlled reset is required.
                    state<=FAULT;
                end
                default: begin
                    fault<=1;
                    fault_code<=8'd4;
                    state<=FAULT;
                end
            endcase
        end
    end
endmodule
