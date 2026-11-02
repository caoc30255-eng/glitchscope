`timescale 1ns / 1ps

// Complete A5 5A 01 TYPE 20 PAYLOAD32 CRC16 event frame.
// Uses the existing V1 byte UART engine and reports done after final stop.
module h1_p1_event_uart_tx_mmio_v0_1 #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 230400,
    parameter IS_AX = 1
)(
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire [7:0] event_type,
    input wire [255:0] event_payload,
    output reg accepted,
    output reg done,
    output wire busy,
    output wire tx_pin,
    output reg error,
    output reg [7:0] error_code
);
    localparam [1:0] IDLE=0, PREP=1, LAUNCH=2, WAIT_BYTE=3;
    reg [1:0] state;
    reg [7:0] held_type;
    reg [255:0] held_payload;
    reg [5:0] prep_index, frame_index;
    reg [15:0] crc_reg, held_crc;
    reg [7:0] tx_data;
    reg tx_start;
    wire tx_busy,tx_done;
    assign busy=(state!=IDLE);

    wire [7:0] source_type = event_type >= 8'h70 ? event_type-8'h40 : event_type;
    wire allowed_ax=(event_type>=8'h31 && event_type<=8'h33) ||
        event_type==8'h38 || event_type==8'h70 || event_type==8'h79 || event_type==8'h7a || event_type==8'h7c ||
        (event_type>=8'h74 && event_type<=8'h77);
    wire allowed_7020=event_type==8'h30 || event_type==8'h39 || event_type==8'h3a || event_type==8'h3c ||
        (event_type>=8'h34 && event_type<=8'h37) ||
        (event_type>=8'h71 && event_type<=8'h73) || event_type==8'h78;
    wire direction_ok=IS_AX ? (allowed_ax || event_type==8'h7b) : allowed_7020;
    wire [31:0] session={event_payload[31:24],event_payload[23:16],
                         event_payload[15:8],event_payload[7:0]};
    wire [31:0] seq={event_payload[63:56],event_payload[55:48],
                     event_payload[47:40],event_payload[39:32]};
    wire [31:0] generation={event_payload[135:128],event_payload[127:120],
                            event_payload[119:112],event_payload[111:104]};
    wire [31:0] record_id={event_payload[255:248],event_payload[247:240],
                           event_payload[239:232],event_payload[231:224]};
    wire profile_fields_ok=event_payload[31:0]!=0 && event_payload[63:32]!=0 &&
        event_payload[183:176]<=1 && event_payload[175:168]<=3 && event_payload[191:184]<=1 &&
        event_payload[215:208]<=7 && (source_type==8'h3c ? (event_payload[191:184]==1 && event_payload[183:176]==0) : event_payload[255:248]==0);
    wire mmio_fields_ok=session!=0 && seq!=0 && event_payload[64+:8]<=2 && event_payload[72+:8]>=1 && event_payload[72+:8]<=16 && event_payload[96+:8]<=1 && event_payload[104+:8]<=3 && event_payload[120+:8]==0;
    wire fields_ok=event_type==8'h7b ? mmio_fields_ok : (source_type==8'h3a || source_type==8'h3c) ? profile_fields_ok :session!=0 && seq!=0 &&
        event_payload[103:99]==0 && event_payload[223:216]<=8'd1 &&
        ((source_type==8'h30 && generation==0 && record_id==0) ||
         (source_type>=8'h31 && source_type<=8'h33 &&
          generation!=0 && record_id==0) ||
         (source_type>=8'h34 && source_type<=8'h39 &&
          generation!=0 && record_id!=0));

    function [15:0] crc16_next;
        input [15:0] old_crc;
        input [7:0] data;
        reg [15:0] c;
        integer bit_index;
        begin
            c=old_crc ^ {data,8'h00};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                c=c[15] ? (c<<1)^16'h1021 : c<<1;
            crc16_next=c;
        end
    endfunction
    function [7:0] body_byte;
        input [5:0] index;
        input [7:0] typ;
        input [255:0] payload;
        begin
            if(index==0) body_byte=8'h01;
            else if(index==1) body_byte=typ;
            else if(index==2) body_byte=8'h20;
            else body_byte=payload[(index-3)*8 +:8];
        end
    endfunction
    function [7:0] frame_byte;
        input [5:0] index;
        input [7:0] typ;
        input [255:0] payload;
        input [15:0] crc;
        begin
            if(index==0) frame_byte=8'ha5;
            else if(index==1) frame_byte=8'h5a;
            else if(index==2) frame_byte=8'h01;
            else if(index==3) frame_byte=typ;
            else if(index==4) frame_byte=8'h20;
            else if(index<=36) frame_byte=payload[(index-5)*8 +:8];
            else if(index==37) frame_byte=crc[15:8];
            else frame_byte=crc[7:0];
        end
    endfunction

    ctrl_uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) byte_tx (
        .clk(clk),.rst_n(rst_n),.tx_data(tx_data),.tx_start(tx_start),
        .uart_tx(tx_pin),.tx_busy(tx_busy),.tx_done(tx_done)
    );
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;held_type<=0;held_payload<=0;
            prep_index<=0;frame_index<=0;crc_reg<=16'hffff;held_crc<=0;
            tx_data<=0;tx_start<=0;accepted<=0;done<=0;
            error<=0;error_code<=0;
        end else begin
            accepted<=0;done<=0;tx_start<=0;
            if(start && state!=IDLE && !error) begin
                error<=1;error_code<=8'd2; // busy request, current frame retained
            end
            case(state)
                IDLE: if(start && !error) begin
                    if(!direction_ok || !fields_ok) begin
                        error<=1;error_code<=8'd1;
                    end else begin
                        held_type<=event_type;
                        held_payload<=event_payload;
                        prep_index<=0;
                        frame_index<=0;
                        crc_reg<=16'hffff;
                        accepted<=1;
                        state<=PREP;
                    end
                end
                PREP: begin
                    crc_reg<=crc16_next(crc_reg,body_byte(prep_index,held_type,held_payload));
                    if(prep_index==6'd34) begin
                        held_crc<=crc16_next(crc_reg,body_byte(prep_index,held_type,held_payload));
                        state<=LAUNCH;
                    end else prep_index<=prep_index+1'b1;
                end
                LAUNCH: if(!tx_busy) begin
                    tx_data<=frame_byte(frame_index,held_type,held_payload,held_crc);
                    tx_start<=1;
                    state<=WAIT_BYTE;
                end
                WAIT_BYTE: if(tx_done) begin
                    if(frame_index==6'd38) begin
                        done<=1;
                        state<=IDLE;
                    end else begin
                        frame_index<=frame_index+1'b1;
                        state<=LAUNCH;
                    end
                end
                default: begin error<=1;error_code<=8'd3;state<=IDLE;end
            endcase
        end
    end
endmodule
