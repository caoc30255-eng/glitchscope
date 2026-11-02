`timescale 1ns / 1ps

// Same-control-clock integration of old V1 response TX and proposed event TX.
// The real ctrl_response_controller supplies one pulse plus immutable fields.
module h1_p1_control_tx_bridge_mmio_v0_1 #(
    parameter integer CLK_HZ=100000000,
    parameter integer BAUD=230400,
    parameter integer TX_TIMEOUT_CLKS=1000000
)(
    input wire clk,rst_n,
    input wire legacy_request_pulse,
    input wire [78:0] legacy_request_desc,
    output wire legacy_response_accepted,
    output wire legacy_response_done,
    output wire legacy_response_busy_to_controller,
    output wire legacy_response_error,
    output wire [2:0] legacy_response_error_code,
    input wire event_request_valid,
    input wire [7:0] event_type,
    input wire [255:0] event_payload,
    output wire event_request_take,
    output wire event_frame_done,
    output wire uart_tx,
    output reg fault,
    output reg [7:0] fault_code
);
    wire held_valid,hold_fault;
    wire [78:0] held_desc;
    wire legacy_start,event_start,legacy_take;
    wire old_pin,old_busy,old_done,old_accepted,old_error;
    wire [2:0] old_error_code;
    wire event_pin,event_busy,event_done,event_accepted,event_error;
    wire [7:0] event_error_code,arbiter_error;
    wire arbiter_busy,arbiter_fault,old_complete,event_complete;
    // Give a same-edge one-clock legacy request time to enter its hold slot.
    wire event_can_start=event_request_valid && !legacy_request_pulse;
    wire [1:0] old_kind;
    wire [7:0] old_cmd,old_status,old_layer,old_code,old_a_byte,old_b_byte;
    wire [15:0] old_trial;
    wire [2:0] old_a_result,old_b_result;
    wire old_a_fe,old_b_fe,old_fault_seen;
    wire [1:0] old_a_count,old_b_count;
    assign {old_kind,old_cmd,old_trial,old_status,old_layer,old_code,
            old_a_result,old_a_byte,old_a_fe,old_a_count,
            old_b_result,old_b_byte,old_b_fe,old_b_count,old_fault_seen}=held_desc;
    assign legacy_response_accepted=old_accepted;
    assign legacy_response_done=old_done;
    assign legacy_response_error=old_error;
    assign legacy_response_error_code=old_error_code;
    assign legacy_response_busy_to_controller=held_valid || arbiter_busy || old_busy || event_busy;
    assign event_frame_done=event_complete;

    h1_p1_legacy_pulse_hold_v0_1 hold_old (
        .clk(clk),.rst_n(rst_n),.request_pulse(legacy_request_pulse),
        .request_desc(legacy_request_desc),.valid(held_valid),
        .held_desc(held_desc),.take(legacy_take),.fault(hold_fault)
    );
    ctrl_response_uart_tx #(.MAX_PAYLOAD(32),.CLK_HZ(CLK_HZ),.BAUD(BAUD)) old_tx (
        .clk(clk),.rst_n(rst_n),.response_start(legacy_start),
        .response_kind(old_kind),.original_cmd_type(old_cmd),.trial_id(old_trial),
        .status_code(old_status),.error_layer(old_layer),.error_code(old_code),
        .a_result(old_a_result),.a_byte(old_a_byte),.a_fe(old_a_fe),
        .a_event_count(old_a_count),.b_result(old_b_result),.b_byte(old_b_byte),
        .b_fe(old_b_fe),.b_event_count(old_b_count),.fault_seen(old_fault_seen),
        .uart_tx(old_pin),.response_accepted(old_accepted),
        .response_done(old_done),.response_busy(old_busy),
        .response_error(old_error),.response_error_code(old_error_code),
        .encoder_packet_busy(),.uart_tx_busy(),.uart_tx_done()
    );
    h1_p1_event_uart_tx_mmio_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),.IS_AX(1)) event_tx (
        .clk(clk),.rst_n(rst_n),.start(event_start),.event_type(event_type),
        .event_payload(event_payload),.accepted(event_accepted),
        .done(event_done),.busy(event_busy),.tx_pin(event_pin),
        .error(event_error),.error_code(event_error_code)
    );
    h1_p1_control_tx_arbiter_v0_1 #(.TIMEOUT_CLKS(TX_TIMEOUT_CLKS)) arbiter (
        .clk(clk),.rst_n(rst_n),.legacy_valid(held_valid),
        .legacy_start(legacy_start),.legacy_accepted(old_accepted),
        .legacy_done(old_done),.legacy_pin(old_pin),.legacy_take(legacy_take),
        .legacy_complete(old_complete),.event_valid(event_can_start),
        .event_start(event_start),.event_accepted(event_accepted),
        .event_done(event_done),.event_pin(event_pin),
        .event_take(event_request_take),.event_complete(event_complete),
        .tx_pin(uart_tx),.busy(arbiter_busy),.fault(arbiter_fault),
        .fault_code(arbiter_error)
    );
    always @(posedge clk) begin
        if(!rst_n) begin fault<=0;fault_code<=0;end
        else if(!fault) begin
            if(hold_fault) begin fault<=1;fault_code<=8'd1;end
            else if(arbiter_fault) begin fault<=1;fault_code<=8'd2;end
            else if(event_error) begin fault<=1;fault_code<=8'd3;end
            else if(old_error) begin fault<=1;fault_code<=8'd4;end
        end
    end
endmodule
