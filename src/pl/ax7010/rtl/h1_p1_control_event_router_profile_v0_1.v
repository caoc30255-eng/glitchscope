`timescale 1ns / 1ps

// Control-clock-domain demultiplexer after the legacy CRC-checked packet parser.
// IS_AX=1: 7020->AX requests and ACKs for AX-originated events.
// IS_AX=0: AX->7020 requests and ACKs for 7020-originated events.
// One held tuple per path. Later consumers implement event ACK/replay policy.
module h1_p1_control_event_router_profile_v0_1 #(
    parameter IS_AX = 1
)(
    input  wire         clk,
    input  wire         rst_n,
    input  wire         packet_valid,
    input  wire [7:0]   packet_type,
    input  wire [7:0]   packet_len,
    input  wire [255:0] packet_payload,
    output reg          event_valid,
    input  wire         event_ready,
    output reg [7:0]    event_type,
    output reg [255:0]  event_payload,
    output reg          legacy_valid,
    input  wire         legacy_ready,
    output reg [7:0]    legacy_type,
    output reg [7:0]    legacy_len,
    output reg [255:0]  legacy_payload,
    output reg          route_fault,
    output reg [7:0]    route_error,
    output reg [7:0]    first_type
);
    // Error 1=length, 2=field encoding, 3=wrong direction,
    //       4=event overrun/conflict, 5=legacy overrun/conflict.
    wire is_event_type = (packet_type==8'h3c || packet_type==8'h7c || (packet_type >= 8'h30 && packet_type <= 8'h3a) ||
                          (packet_type >= 8'h70 && packet_type <= 8'h7a));
    wire [7:0] source_type = packet_type >= 8'h70 ? packet_type - 8'h40 : packet_type;
    wire event_payload_equal,legacy_payload_equal;
    h1_control_equal_tree_v0_1 #(.WIDTH(256)) event_equal (
        .a(event_payload),.b(packet_payload),.equal(event_payload_equal));
    h1_control_equal_tree_v0_1 #(.WIDTH(256)) legacy_equal (
        .a(legacy_payload),.b(packet_payload),.equal(legacy_payload_equal));
    wire direction_ok_ax = packet_type == 8'h30 || packet_type == 8'h39 || packet_type == 8'h3a || packet_type == 8'h3c ||
        (packet_type >= 8'h34 && packet_type <= 8'h37) ||
        packet_type == 8'h71 || packet_type == 8'h72 ||
        packet_type == 8'h73 || packet_type == 8'h78;
    wire direction_ok_7020 = (packet_type >= 8'h31 && packet_type <= 8'h33) ||
        packet_type == 8'h38 || packet_type == 8'h70 || packet_type == 8'h79 || packet_type == 8'h7a || packet_type == 8'h7c ||
        (packet_type >= 8'h74 && packet_type <= 8'h77);
    wire direction_ok = IS_AX ? direction_ok_ax : direction_ok_7020;
    wire [31:0] session = {packet_payload[31:24],packet_payload[23:16],
                           packet_payload[15:8],packet_payload[7:0]};
    wire [31:0] seq = {packet_payload[63:56],packet_payload[55:48],
                       packet_payload[47:40],packet_payload[39:32]};
    wire [31:0] generation = {packet_payload[135:128],packet_payload[127:120],
                              packet_payload[119:112],packet_payload[111:104]};
    wire [31:0] record_id = {packet_payload[255:248],packet_payload[247:240],
                             packet_payload[239:232],packet_payload[231:224]};
    wire profile_fields_ok=packet_payload[31:0]!=0 && packet_payload[63:32]!=0 &&
        packet_payload[183:176]<=1 && packet_payload[175:168]<=3 &&
        packet_payload[191:184]<=1 && packet_payload[215:208]<=7 && (source_type==8'h3c ? (packet_payload[191:184]==1 && packet_payload[183:176]==0) : packet_payload[255:248]==0);
    wire fields_ok = (source_type==8'h3a || source_type==8'h3c) ? profile_fields_ok : session != 0 && seq != 0 &&
        packet_payload[103:99] == 0 && packet_payload[223:216] <= 8'd1 &&
        ((source_type == 8'h30 && generation == 0 && record_id == 0) ||
         (source_type >= 8'h31 && source_type <= 8'h33 &&
          generation != 0 && record_id == 0) ||
         (source_type >= 8'h34 && source_type <= 8'h39 &&
          generation != 0 && record_id != 0));

    always @(posedge clk) begin
        if (!rst_n) begin
            event_valid <= 0;
            event_type <= 0;
            event_payload <= 0;
            legacy_valid <= 0;
            legacy_type <= 0;
            legacy_len <= 0;
            legacy_payload <= 0;
            route_fault <= 0;
            route_error <= 0;
            first_type <= 0;
        end else begin
            if (event_valid && event_ready) event_valid <= 0;
            if (legacy_valid && legacy_ready) legacy_valid <= 0;
            if (packet_valid && !route_fault) begin
                if (is_event_type) begin
                    if (packet_len != 8'd32) begin
                        route_fault <= 1;
                        route_error <= 8'd1;
                        first_type <= packet_type;
                    end else if (!fields_ok) begin
                        route_fault <= 1;
                        route_error <= 8'd2;
                        first_type <= packet_type;
                    end else if (!direction_ok) begin
                        route_fault <= 1;
                        route_error <= 8'd3;
                        first_type <= packet_type;
                    end else if (event_valid && !event_ready) begin
                        if (event_type != packet_type || !event_payload_equal) begin
                            route_fault <= 1;
                            route_error <= 8'd4;
                            first_type <= packet_type;
                        end
                        // Exact replay while pending cannot replace the original tuple.
                    end else begin
                        event_valid <= 1;
                        event_type <= packet_type;
                        event_payload <= packet_payload;
                    end
                end else if (legacy_valid && !legacy_ready) begin
                    if (legacy_type != packet_type || legacy_len != packet_len ||
                        !legacy_payload_equal) begin
                        route_fault <= 1;
                        route_error <= 8'd5;
                        first_type <= packet_type;
                    end
                end else begin
                    legacy_valid <= 1;
                    legacy_type <= packet_type;
                    legacy_len <= packet_len;
                    legacy_payload <= packet_payload;
                end
            end
        end
    end
endmodule
