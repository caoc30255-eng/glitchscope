`timescale 1ns/1ps
// One AXI-Lite transaction outstanding per direction. All writes full-strobe.
// RX release is an explicit software persistence assertion after delivered reads;
// this block cannot prove filesystem durability or authorize 7010 retirement.
module h1_7020_axi_transport_v0_2 #(
    parameter integer CLK_HZ=100000000,BAUD=2000000
)(
    input wire clk,rst_n,
    output wire saved_take,transport_fault,status_pending,
    output wire [143:0] saved_raw,
    output wire [4:0] saved_length,
    output wire [2:0] saved_reason,
    output wire [31:0] saved_ticket,ticket_count,
    input wire h1_rx_pin,
    output wire h1_tx_pin,
    input wire [11:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [11:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready
);
    reg have_aw,have_w;
    reg [11:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
    assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
    assign s_axi_arready=rst_n && !s_axi_rvalid;
    wire load_ready,launch_ready,launch_take,tx_active,tx_done,tx_fault;
    wire [9:0] packet_length;
    reg load_valid,launch_valid;
    reg [7:0] load_data;
    reg load_last;
    wire event_valid,overflow,stream_pending;
    wire [143:0] event_raw;
    wire [4:0] event_len;
    wire [2:0] event_reason,queue_count;
    wire [151:0] first_lost;
    wire [31:0] crc_errors,format_errors,fe_errors,timeouts,rx_frames;
    reg event_take;
    reg [31:0] tx_frames;
    reg snapshot_valid;
    reg [151:0] snapshot;
    reg [31:0] ticket;
    reg [6:0] read_mask,r_credit;
    reg [31:0] read_value;
    reg [1:0] read_resp;
    reg [6:0] read_credit;
    h1_7020_packet_tx_v0_1 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) tx(
        .clk(clk),.rst_n(rst_n),.load_valid(load_valid),.load_data(load_data),
        .load_last(load_last),.load_ready(load_ready),.launch_valid(launch_valid),
        .launch_ready(launch_ready),.launch_take(launch_take),.uart_tx(h1_tx_pin),
        .frame_active(tx_active),.frame_done(tx_done),.saved_length(packet_length),.length_fault(tx_fault)
    );
    h1_7020_status_rx_v0_2 #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) rx(
        .clk(clk),.rst_n(rst_n),.uart_rx(h1_rx_pin),.event_valid(event_valid),
        .stream_pending(stream_pending),.event_take(event_take),.event_raw(event_raw),.event_length(event_len),
        .event_reason(event_reason),.queue_count(queue_count),.overflow_fault(overflow),
        .first_lost_event(first_lost),.crc_errors(crc_errors),.format_errors(format_errors),
        .framing_errors(fe_errors),.partial_timeouts(timeouts),.completed_frames(rx_frames)
    );
    // Observe the actual FIFO pop edge, not the earlier B response.
    assign saved_take=event_take && event_valid;
    assign saved_raw=snapshot[143:0];
    assign saved_length=snapshot[148:144];
    assign saved_reason=snapshot[151:149];
    assign saved_ticket=ticket;
    assign ticket_count=ticket;
    assign transport_fault=tx_fault || overflow;
    assign status_pending=stream_pending || snapshot_valid || event_take;
    always @* begin
        read_value=0;read_resp=0;read_credit=0;
        case(s_axi_araddr)
            12'h000:read_value=32'h48315431; // H1T1
            12'h004:read_value={21'd0,queue_count,1'b0,tx_fault,overflow,snapshot_valid,event_valid,tx_active,launch_ready,load_ready};
            12'h008:read_value=CLK_HZ;
            12'h00c:read_value=tx_frames;
            12'h020:read_value={22'd0,packet_length};
            12'h040:begin read_value=ticket;read_credit=7'b0000001;end
            12'h044:begin read_value={21'd0,snapshot[151:149],3'd0,snapshot[148:144]};read_credit=7'b0000010;end
            12'h048:begin read_value=snapshot[143:112];read_credit=7'b0000100;end
            12'h04c:begin read_value=snapshot[111:80];read_credit=7'b0001000;end
            12'h050:begin read_value=snapshot[79:48];read_credit=7'b0010000;end
            12'h054:begin read_value=snapshot[47:16];read_credit=7'b0100000;end
            12'h058:begin read_value={snapshot[15:0],16'd0};read_credit=7'b1000000;end
            12'h05c:read_value={25'd0,read_mask};
            12'h060:read_value=crc_errors;
            12'h064:read_value=format_errors;
            12'h068:read_value=fe_errors;
            12'h06c:read_value=timeouts;
            12'h070:read_value=rx_frames;
            12'h080:read_value={24'd0,first_lost[151:144]};
            12'h084:read_value=first_lost[143:112];
            12'h088:read_value=first_lost[111:80];
            12'h08c:read_value=first_lost[79:48];
            12'h090:read_value=first_lost[47:16];
            12'h094:read_value={first_lost[15:0],16'd0};
            default:read_resp=2;
        endcase
        if(read_credit!=0 && !snapshot_valid)begin read_value=0;read_resp=2;read_credit=0;end
        if(s_axi_araddr[1:0]!=0)begin read_value=0;read_resp=2;read_credit=0;end
    end
    always @(posedge clk) begin
        if(!rst_n)begin
            have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
            s_axi_bresp<=0;s_axi_bvalid<=0;s_axi_rresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;
            load_valid<=0;load_last<=0;load_data<=0;launch_valid<=0;event_take<=0;
            tx_frames<=0;snapshot_valid<=0;snapshot<=0;ticket<=0;read_mask<=0;r_credit<=0;
        end else begin
            load_valid<=0;launch_valid<=0;event_take<=0;
            if(tx_done)tx_frames<=tx_frames+1'b1;
            if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(have_aw && have_w && !s_axi_bvalid)begin
                have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
                if(wstrb==4'hf && awaddr[1:0]==0)begin
                    case(awaddr)
                        12'h010:if(load_ready && wdata[31:9]==0 && !overflow)begin
                            load_data<=wdata[7:0];load_last<=wdata[8];load_valid<=1;s_axi_bresp<=0;
                        end
                        12'h018:if(wdata==1 && launch_ready && !overflow)begin launch_valid<=1;s_axi_bresp<=0;end
                        12'h030:if(wdata==1 && event_valid && !snapshot_valid && !event_take && !s_axi_rvalid && !s_axi_arvalid && ticket!=32'hffffffff)begin
                            snapshot<={event_reason,event_len,event_raw};snapshot_valid<=1;
                            ticket<=ticket+1'b1;read_mask<=0;s_axi_bresp<=0;
                        end
                        12'h034:if(snapshot_valid && wdata==ticket && read_mask==7'h7f &&
                            !s_axi_rvalid && !s_axi_arvalid && event_valid && snapshot=={event_reason,event_len,event_raw})begin
                            event_take<=1;snapshot_valid<=0;read_mask<=0;s_axi_bresp<=0;
                        end
                        default:s_axi_bresp<=2;
                    endcase
                end
            end
            if(s_axi_rvalid && s_axi_rready)begin
                s_axi_rvalid<=0;
                if(snapshot_valid && s_axi_rresp==0)read_mask<=read_mask|r_credit;
            end
            if(s_axi_arvalid && s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_resp;r_credit<=read_credit;
            end
        end
    end
endmodule
