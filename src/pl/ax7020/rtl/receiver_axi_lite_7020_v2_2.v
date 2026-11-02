`timescale 1ns / 1ps
// B2 offline AXI4-Lite proposal. 32-bit data, 8-bit local byte address.
// No physical base address, PS instance, image sideband, or Gateway is assigned.
module receiver_axi_lite_7020_v2_2 (
    input wire s_axi_aclk,input wire s_axi_aresetn,input wire ch0_async,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,input wire s_axi_rready,
    output wire [31:0] active_window_o,
    output wire a_event_o,output wire b_event_o,
    output wire [7:0] a_event_byte_o,output wire [7:0] b_event_byte_o,
    output wire a_event_fe_o,output wire b_event_fe_o
);
    reg aw_pending,w_pending;
    reg [7:0] aw_addr;
    reg [31:0] w_data;
    reg [3:0] w_strb;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid;
    reg [15:0] shadow_id;
    reg [7:0] shadow_cfg;
    reg [31:0] shadow_window;
    reg cmd_valid;
    reg [2:0] cmd;
    wire rsp_valid,configured,ready,result_valid;
    wire [3:0] rsp_code;
    wire [1:0] state,reason;
    wire [15:0] active_id;
    wire [2:0] active_d;
    wire signed [3:0] active_s;
    wire [31:0] active_window,first_a,first_b,elapsed;
    wire [7:0] byte_a,byte_b,count_a,count_b;
    wire fe_a,fe_b,overflow_a,overflow_b;
    assign active_window_o=active_window;
    reg [3:0] last_rsp;
    reg [15:0] command_sequence;
    receiver_trial_7020_v2_2 core(
        .clk(s_axi_aclk),.rst_n(s_axi_aresetn),.ch0_async(ch0_async),
        .cmd_valid(cmd_valid),.cmd(cmd),.shadow_trial_id(shadow_id),
        .shadow_d(shadow_cfg[2:0]),.shadow_s(shadow_cfg[7:4]),.shadow_window_clks(shadow_window),
        .rsp_valid(rsp_valid),.rsp_code(rsp_code),.configured(configured),.state(state),
        .active_trial_id(active_id),.active_d(active_d),.active_s(active_s),
        .active_window_clks(active_window),.ready_to_start(ready),.result_valid(result_valid),
        .result_reason(reason),.a_byte(byte_a),.b_byte(byte_b),.a_fe(fe_a),.b_fe(fe_b),
        .a_count(count_a),.b_count(count_b),.a_count_overflow(overflow_a),.b_count_overflow(overflow_b),
        .a_first_cycle(first_a),.b_first_cycle(first_b),.elapsed_clks(elapsed),
        .rx_ce_o(),.rx_sync_o(),.a_event(a_event_o),.b_event(b_event_o),
        .a_event_byte(a_event_byte_o),.b_event_byte(b_event_byte_o),
        .a_event_fe(a_event_fe_o),.b_event_fe(b_event_fe_o));
    integer lane;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            aw_pending<=0;w_pending<=0;aw_addr<=0;w_data<=0;w_strb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;shadow_id<=0;shadow_cfg<=8'h01;
            shadow_window<=1200;cmd_valid<=0;cmd<=0;last_rsp<=0;command_sequence<=0;
        end else begin
            cmd_valid<=0;
            if(rsp_valid)begin last_rsp<=rsp_code;command_sequence<=command_sequence+1'b1;end
            if(s_axi_awvalid && s_axi_awready)begin aw_pending<=1;aw_addr<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready)begin w_pending<=1;w_data<=s_axi_wdata;w_strb<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(aw_pending && w_pending && !s_axi_bvalid)begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                case(aw_addr)
                    8'h04: if(w_strb[0])begin
                        if(w_data[7:3]!=0 || w_data[2:0]<1 || w_data[2:0]>4)
                            s_axi_bresp<=2'b10;
                        else begin cmd<=w_data[2:0];cmd_valid<=1;end
                    end
                    8'h10:begin
                        if(w_strb[0])shadow_id[7:0]<=w_data[7:0];
                        if(w_strb[1])shadow_id[15:8]<=w_data[15:8];
                    end
                    8'h14:if(w_strb[0])shadow_cfg<={w_data[7:4],1'b0,w_data[2:0]};
                    8'h18:for(lane=0;lane<4;lane=lane+1)
                        if(w_strb[lane])shadow_window[lane*8 +: 8]<=w_data[lane*8 +: 8];
                    default:s_axi_bresp<=2'b10;
                endcase
            end
        end
    end
    always @(posedge s_axi_aclk)begin
        if(!s_axi_aresetn)begin s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;end
        else begin
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rresp<=0;
                case(s_axi_araddr)
                    8'h00:s_axi_rdata<=32'h52420220; // "RB", interface v2.2.0
                    8'h04:s_axi_rdata<=0;
                    8'h08:s_axi_rdata<={27'd0,result_valid,ready,configured,state};
                    8'h0c:s_axi_rdata<={command_sequence,12'd0,last_rsp};
                    8'h10:s_axi_rdata<={16'd0,shadow_id};
                    8'h14:s_axi_rdata<={24'd0,shadow_cfg};
                    8'h18:s_axi_rdata<=shadow_window;
                    8'h20:s_axi_rdata<={16'd0,active_id};
                    8'h24:s_axi_rdata<={24'd0,active_s,1'b0,active_d};
                    8'h28:s_axi_rdata<=active_window;
                    8'h30:s_axi_rdata<={30'd0,reason};
                    8'h34:s_axi_rdata<={7'd0,overflow_a,count_a,7'd0,fe_a,byte_a};
                    8'h38:s_axi_rdata<={7'd0,overflow_b,count_b,7'd0,fe_b,byte_b};
                    8'h3c:s_axi_rdata<=first_a;
                    8'h40:s_axi_rdata<=first_b;
                    8'h44:s_axi_rdata<=elapsed;
                    default:begin s_axi_rdata<=32'hdeadbeef;s_axi_rresp<=2'b10;end
                endcase
            end
        end
    end
endmodule
