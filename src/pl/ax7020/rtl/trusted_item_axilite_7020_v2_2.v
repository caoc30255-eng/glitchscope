`timescale 1ns / 1ps
// PROVISIONAL B2/B3 metadata control block. Local offsets only; no base address.
// All inputs including event pulses are synchronous to s_axi_aclk.
// One item in flight. This block does not carry image payload or STM32 reports.
module trusted_item_axilite_7020_v2_2 (
    input wire s_axi_aclk,input wire s_axi_aresetn,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,input wire s_axi_rready,
    input wire observed_event,input wire forwarded_event,input wire dropped_event,
    input wire report_event,input wire host_timeout_event,
    output reg arm_pulse,output reg start_pulse,output reg ack_pulse,
    output reg [3:0] meta_state,output wire meta_result_valid,
    output reg [31:0] active_run_id,output reg [31:0] active_trial_id,
    output reg [7:0] active_image_id,output reg [7:0] active_attempt_id,
    output reg [7:0] active_route_mode,output reg [7:0] active_rx_profile,
    output reg [15:0] active_item_index,
    output reg [15:0] active_item_total,output reg [15:0] active_payload_len,
    output reg [15:0] active_source_crc
);
    localparam IDLE=0,COMMITTED=1,ARMED=2,STARTED=3,OBSERVED=4,
               FORWARDED=5,DROPPED=6,REPORTED=7,HOST_TIMEOUT=8;
    localparam OK=0,BAD_STATE=1,INCOMPLETE=2,BAD_RANGE=3,DUPLICATE=4;
    reg aw_pending,w_pending;
    reg [7:0] aw_addr;
    reg [31:0] w_data;
    reg [3:0] w_strb;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid;
    assign meta_result_valid=(meta_state==REPORTED || meta_state==HOST_TIMEOUT);

    reg [31:0] sh_run,sh_trial,sh_identity,sh_item,sh_integrity;
    reg [3:0] written_run,written_trial,written_identity,written_item,written_integrity;
    reg [31:0] last_run,last_trial;
    reg last_key_valid;
    reg [15:0] meta_sequence;
    reg [3:0] meta_response;
    reg [7:0] event_flags;
    integer lane;
    wire event_any=observed_event|forwarded_event|dropped_event|
                   report_event|host_timeout_event;
    wire complete_shadow=(written_run==4'hf && written_trial==4'hf &&
                          written_identity==4'hf &&
                          written_item==4'hf && written_integrity==4'hf);
    wire valid_range=(sh_identity[23:16]<=1 && sh_identity[31:24]<=1 &&
                      sh_item[31:16]!=0 &&
                      sh_item[15:0]<sh_item[31:16] &&
                      sh_integrity[15:0]!=0 && sh_integrity[15:0]<=512);
    wire fresh_key=(!last_key_valid || sh_run>last_run ||
                   (sh_run==last_run && sh_trial>last_trial));
    wire report_ready=(active_route_mode==0) ?
                      (meta_state>=STARTED && meta_state<=DROPPED) :
                      (meta_state==FORWARDED || meta_state==DROPPED);

    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            aw_pending<=0;w_pending<=0;aw_addr<=0;w_data<=0;w_strb<=0;
            s_axi_bresp<=0;s_axi_bvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
            s_axi_rvalid<=0;arm_pulse<=0;start_pulse<=0;ack_pulse<=0;meta_state<=IDLE;
            sh_run<=0;sh_trial<=0;sh_identity<=0;sh_item<=0;sh_integrity<=0;
            written_run<=0;written_trial<=0;written_identity<=0;
            written_item<=0;written_integrity<=0;
            active_run_id<=0;active_trial_id<=0;active_image_id<=0;
            active_attempt_id<=0;active_route_mode<=0;active_rx_profile<=0;
            active_item_index<=0;
            active_item_total<=0;active_payload_len<=0;active_source_crc<=0;
            last_run<=0;last_trial<=0;last_key_valid<=0;
            meta_sequence<=0;meta_response<=0;event_flags<=0;
        end else begin
            arm_pulse<=0;start_pulse<=0;ack_pulse<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_pending<=1;aw_addr<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin
                w_pending<=1;w_data<=s_axi_wdata;w_strb<=s_axi_wstrb;
            end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;
                case(s_axi_araddr)
                    8'h50:s_axi_rdata<=32'h4d490100; // MI version 1, single slot
                    8'h54:s_axi_rdata<=sh_run;
                    8'h58:s_axi_rdata<=sh_trial;
                    8'h5c:s_axi_rdata<=sh_identity;
                    8'h60:s_axi_rdata<=sh_item;
                    8'h64:s_axi_rdata<=sh_integrity;
                    8'h68:s_axi_rdata<=0;
                    8'h6c:s_axi_rdata<={16'd0,event_flags,4'd0,meta_state};
                    8'h70:s_axi_rdata<=active_run_id;
                    8'h74:s_axi_rdata<=active_trial_id;
                    8'h78:s_axi_rdata<={active_rx_profile,active_route_mode,
                                         active_attempt_id,active_image_id};
                    8'h7c:s_axi_rdata<={active_item_total,active_item_index};
                    8'h80:s_axi_rdata<={active_source_crc,active_payload_len};
                    8'h84:s_axi_rdata<={12'd0,meta_response,meta_sequence};
                    default:begin s_axi_rdata<=32'hdeadbeef;s_axi_rresp<=2'b10;end
                endcase
            end

            if(observed_event && meta_state==STARTED) begin
                meta_state<=OBSERVED;event_flags[0]<=1;
            end
            if(forwarded_event && meta_state==OBSERVED) begin
                meta_state<=FORWARDED;event_flags[1]<=1;
            end
            if(dropped_event && (meta_state==STARTED || meta_state==OBSERVED)) begin
                meta_state<=DROPPED;event_flags[2]<=1;
            end
            if(report_event && report_ready) begin
                meta_state<=REPORTED;event_flags[3]<=1;
            end
            if(host_timeout_event && meta_state>=STARTED && meta_state<=DROPPED) begin
                meta_state<=HOST_TIMEOUT;event_flags[4]<=1;
            end

            if(aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                case(aw_addr)
                    8'h54,8'h58,8'h5c,8'h60,8'h64: begin
                        if(meta_state!=IDLE || event_any) s_axi_bresp<=2'b10;
                        else for(lane=0;lane<4;lane=lane+1)
                            if(w_strb[lane]) case(aw_addr)
                                8'h54:begin sh_run[lane*8 +: 8]<=w_data[lane*8 +: 8];
                                             written_run[lane]<=1;end
                                8'h58:begin sh_trial[lane*8 +: 8]<=w_data[lane*8 +: 8];
                                             written_trial[lane]<=1;end
                                8'h5c:begin sh_identity[lane*8 +: 8]<=w_data[lane*8 +: 8];
                                             written_identity[lane]<=1;end
                                8'h60:begin sh_item[lane*8 +: 8]<=w_data[lane*8 +: 8];
                                             written_item[lane]<=1;end
                                8'h64:begin sh_integrity[lane*8 +: 8]<=w_data[lane*8 +: 8];
                                             written_integrity[lane]<=1;end
                            endcase
                    end
                    8'h68:if(w_strb[0]) begin
                        meta_sequence<=meta_sequence+1'b1;
                        meta_response<=OK;
                        if(event_any) begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                        else case(w_data[7:0])
                            8'd1:if(meta_state!=IDLE) begin
                                meta_response<=BAD_STATE;s_axi_bresp<=2'b10;
                            end else if(!complete_shadow) begin
                                meta_response<=INCOMPLETE;s_axi_bresp<=2'b10;
                            end else if(!valid_range) begin
                                meta_response<=BAD_RANGE;s_axi_bresp<=2'b10;
                            end else if(!fresh_key) begin
                                meta_response<=DUPLICATE;s_axi_bresp<=2'b10;
                            end else begin
                                active_run_id<=sh_run;active_trial_id<=sh_trial;
                                active_image_id<=sh_identity[7:0];
                                active_attempt_id<=sh_identity[15:8];
                                active_route_mode<=sh_identity[23:16];
                                active_rx_profile<=sh_identity[31:24];
                                active_item_index<=sh_item[15:0];
                                active_item_total<=sh_item[31:16];
                                active_payload_len<=sh_integrity[15:0];
                                active_source_crc<=sh_integrity[31:16];
                                last_run<=sh_run;last_trial<=sh_trial;
                                last_key_valid<=1;meta_state<=COMMITTED;event_flags<=0;
                            end
                            8'd2:if(meta_state==COMMITTED)begin meta_state<=ARMED;arm_pulse<=1;end
                                 else begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                            8'd3:if(meta_state==ARMED)begin meta_state<=STARTED;start_pulse<=1;end
                                 else begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                            8'd4:if(meta_result_valid)begin meta_state<=IDLE;ack_pulse<=1;
                                written_run<=0;written_trial<=0;written_identity<=0;
                                written_item<=0;written_integrity<=0;end
                                 else begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                            8'd5:if(report_ready)
                                     begin meta_state<=REPORTED;event_flags[3]<=1;end
                                 else begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                            8'd6:if(meta_state>=STARTED && meta_state<=DROPPED)
                                     begin meta_state<=HOST_TIMEOUT;event_flags[4]<=1;end
                                 else begin meta_response<=BAD_STATE;s_axi_bresp<=2'b10;end
                            default:begin meta_response<=BAD_RANGE;s_axi_bresp<=2'b10;end
                        endcase
                    end
                    default:s_axi_bresp<=2'b10;
                endcase
            end
        end
    end
endmodule
