`timescale 1ns/1ps
// One complete record cache. Software persistence assertion follows delivered
// unique AXI reads; exact actual-retirement feedback alone frees the cache.
module h1_7020_ch1_evidence_axi_v0_1(
    input wire clk,rst_n,external_fault,
    input wire descriptor_valid,
    output wire descriptor_ready,
    input wire [671:0] descriptor_data,
    input wire sample_valid,
    output wire sample_ready,
    input wire [9:0] sample_index,
    input wire [7:0] sample_data,
    input wire [3:0] sample_flags,
    input wire [63:0] sample_tick,
    input wire finish_valid,
    output wire finish_ready,
    input wire [15:0] finish_descriptor_crc,finish_samples_crc,
    output wire proof_valid,
    input wire proof_ready,
    output wire [31:0] proof_epoch,proof_record_id,
    output wire [255:0] proof_identity,
    output wire [15:0] proof_count,proof_descriptor_crc,proof_samples_crc,
    input wire retired_valid,
    output wire retired_ready,retired_take,
    input wire [31:0] retired_epoch,retired_record_id,
    input wire [255:0] retired_identity,
    input wire [13:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [13:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    output reg fault_latched,
    output reg [7:0] first_fault
);
    localparam IDLE=0,CLEAR=1,DCRC=2,SAMPLES=3,SCRC=4,SEALED=5,PROOF=6,DONE=7,FAULT=8;
    reg [3:0] state;
    reg [671:0] saved_descriptor;
    (* ram_style="block" *) reg [79:0] samples[0:543];
    (* ram_style="distributed" *) reg [2:0] sample_masks[0:543];
    reg [79:0] saved_sample,ram_read_word;
    reg [9:0] clear_index;
    reg [6:0] crc_index;
    reg [15:0] dcrc,scrc,received_count,sample_read_count;
    reg [31:0] last_epoch,last_generation;
    reg [63:0] last_sample_tick;
    reg [20:0] descriptor_mask;
    reg [2:0] footer_mask;
    reg [4:0] descriptor_read_count;
    reg [2:0] footer_read_count;
    reg [11:0] stage_mask;
    reg [31:0] staged_epoch,staged_id;
    reg [255:0] staged_identity;
    reg [15:0] staged_count,staged_dcrc,staged_scrc;
    reg have_aw,have_w;
    reg [13:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    reg ram_pending;
    reg [1:0] r_kind,r_part;
    reg [9:0] r_index;
    reg [31:0] read_value;
    reg [1:0] read_resp,read_kind,read_part;
    reg [9:0] read_index;
    reg read_is_ram;
    wire [15:0] count=saved_descriptor[340:325];
    wire [9:0] incoming_ram_index=(s_axi_araddr-14'h0400)>>4;
    wire cache_present=state!=IDLE;
    wire footer_stable=state==SEALED || state==PROOF || state==DONE;
    wire stream_ok=rst_n && !fault_latched && !external_fault && !retired_valid;
    assign descriptor_ready=state==IDLE && stream_ok;
    assign sample_ready=state==SAMPLES && received_count<count && stream_ok;
    assign finish_ready=state==SAMPLES && received_count==count && stream_ok;
    wire descriptor_take=descriptor_valid && descriptor_ready;
    wire descriptor_ok=(descriptor_data[671:640]!=0 && descriptor_data[639]==0 && descriptor_data[638:602]==0 &&
        descriptor_data[569:538]!=0 && descriptor_data[502:471]!=0 && descriptor_data[382:351]!=0 &&
        descriptor_data[350:349]>=1 && descriptor_data[348:341]>=1 && descriptor_data[348:341]<=7 &&
        descriptor_data[340:325]<=544 && descriptor_data[324:261]<descriptor_data[260:197] &&
        descriptor_data[196:133]>=descriptor_data[324:261] && descriptor_data[196:133]<=descriptor_data[260:197] &&
        descriptor_data[132]==(descriptor_data[348:341]==1) &&
        (descriptor_data[348:341]!=1 || (descriptor_data[350:349]==1 ?
            (descriptor_data[340:325]>=20 && descriptor_data[340:325]<=532) : descriptor_data[340:325]==12)) &&
        (descriptor_data[348:341]!=5 || descriptor_data[196:133]==descriptor_data[260:197]) &&
        (descriptor_data[196:133]!=descriptor_data[260:197] || descriptor_data[348:341]>=5) &&
        (descriptor_data[671:640]>last_epoch || (descriptor_data[671:640]==last_epoch &&
            descriptor_data[502:471]>last_generation)))===1'b1;
    wire sample_take=sample_valid && sample_ready;
    wire sample_ok=(sample_index==received_count && sample_index<544 &&
        sample_tick>=saved_descriptor[324:261] && sample_tick<saved_descriptor[260:197] &&
        (received_count==0 || sample_tick>=last_sample_tick))===1'b1;
    wire proof_fields_ok=(staged_epoch==saved_descriptor[671:640] && staged_id==saved_descriptor[382:351] &&
        staged_identity===saved_descriptor[638:383] && staged_count==count && staged_dcrc==dcrc && staged_scrc==scrc)===1'b1;
    wire all_delivered=descriptor_mask==21'h1fffff && footer_mask==7 && sample_read_count==count*3;
    assign proof_valid=rst_n && state==PROOF && !fault_latched && !external_fault && !retired_valid;
    assign proof_epoch=saved_descriptor[671:640];
    assign proof_record_id=saved_descriptor[382:351];
    assign proof_identity=saved_descriptor[638:383];
    assign proof_count=count;assign proof_descriptor_crc=dcrc;assign proof_samples_crc=scrc;
    assign retired_ready=rst_n && state==DONE && !fault_latched && !external_fault &&
        !s_axi_rvalid && !ram_pending && !s_axi_bvalid && !have_aw && !have_w &&
        !s_axi_arvalid && !s_axi_awvalid && !s_axi_wvalid;
    wire retirement_ok=(retired_epoch==proof_epoch && retired_record_id==proof_record_id && retired_identity===proof_identity)===1'b1;
    assign retired_take=retired_valid && retired_ready && retirement_ok;
    assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
    assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
    assign s_axi_arready=rst_n && !s_axi_rvalid && !ram_pending;
    wire ar_take=s_axi_arvalid && s_axi_arready;
    function [15:0] crc_byte;
        input [15:0] old;input [7:0] data;
        reg [15:0] c;integer i;
        begin c=old^{data,8'd0};for(i=0;i<8;i=i+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_byte=c;end
    endfunction
    task fault;
        input [7:0] code;
        begin fault_latched<=1;first_fault<=code;state<=FAULT;end
    endtask
    // No reset on memory contents. received_count/cache state gate every read.
    always @(posedge clk)begin
        if(sample_take && sample_ok)samples[sample_index]<={4'd0,sample_data,sample_flags,sample_tick};
        if(ar_take && read_is_ram && read_resp==0)ram_read_word<=samples[incoming_ram_index];
    end
    // Byte enables/coverage masks are initialized sequentially before sampling.
    always @(posedge clk)begin
        if(rst_n && state==CLEAR && !fault_latched)sample_masks[clear_index]<=0;
        else if(rst_n && s_axi_rvalid && s_axi_rready && s_axi_rresp==0 && r_kind==2)
            sample_masks[r_index]<=sample_masks[r_index] | (3'b001<<r_part);
    end
    always @* begin
        read_value=0;read_resp=0;read_kind=0;read_part=0;read_index=0;read_is_ram=0;
        case(s_axi_araddr)
            14'h0000:read_value=32'h48314331; // H1C1
            14'h0004:read_value={16'd0,4'd0,state,3'd0,fault_latched,state==DONE,state==PROOF,footer_stable,cache_present};
            14'h0008:begin read_value={16'd0,count};read_kind=3;read_index=0;end
            14'h000c:read_value={16'd0,received_count};
            14'h0010:read_value=saved_descriptor[671:640];
            14'h0014:begin read_value={16'd0,dcrc};read_kind=3;read_index=1;end
            14'h0018:begin read_value={16'd0,scrc};read_kind=3;read_index=2;end
            14'h001c:read_value=24+count*3;
            14'h0020:read_value=descriptor_read_count+footer_read_count+sample_read_count;
            14'h0024:read_value={24'd0,first_fault};
            default:begin
                if(s_axi_araddr>=14'h0100 && s_axi_araddr<=14'h0150)begin
                    read_index=(s_axi_araddr-14'h0100)>>2;read_kind=1;
                    read_value=saved_descriptor[671-read_index*32 -:32];
                    if(!cache_present)read_resp=2;
                end else if(s_axi_araddr>=14'h0400 && s_axi_araddr<14'h2600 && s_axi_araddr[3:2]<3 &&
                    cache_present && state!=CLEAR && incoming_ram_index<received_count)begin
                    read_is_ram=1;read_kind=2;read_index=incoming_ram_index;read_part=s_axi_araddr[3:2];
                end else read_resp=2;
            end
        endcase
        if(read_kind==3 && !footer_stable)read_resp=2;
        if(s_axi_araddr[1:0]!=0)read_resp=2;
        if(read_resp!=0)begin read_value=0;read_kind=0;read_is_ram=0;end
    end
    always @(posedge clk)begin
        if(!rst_n)begin
            state<=IDLE;saved_descriptor<=0;saved_sample<=0;received_count<=0;last_sample_tick<=0;
            clear_index<=0;crc_index<=0;dcrc<=16'hffff;scrc<=16'hffff;last_epoch<=0;last_generation<=0;
            descriptor_mask<=0;footer_mask<=0;descriptor_read_count<=0;footer_read_count<=0;sample_read_count<=0;
            stage_mask<=0;staged_epoch<=0;staged_id<=0;staged_identity<=0;staged_count<=0;staged_dcrc<=0;staged_scrc<=0;
            have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;
            ram_pending<=0;r_kind<=0;r_index<=0;r_part<=0;fault_latched<=0;first_fault<=0;
        end else begin
            if(s_axi_awvalid && s_axi_awready)begin awaddr<=s_axi_awaddr;have_aw<=1;end
            if(s_axi_wvalid && s_axi_wready)begin wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;have_w<=1;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready)begin
                s_axi_rvalid<=0;
                if(s_axi_rresp==0)begin
                    case(r_kind)
                        1:if(!descriptor_mask[r_index])begin descriptor_mask[r_index]<=1;descriptor_read_count<=descriptor_read_count+1'b1;end
                        2:if(!sample_masks[r_index][r_part])sample_read_count<=sample_read_count+1'b1;
                        3:if(!footer_mask[r_index])begin footer_mask[r_index]<=1;footer_read_count<=footer_read_count+1'b1;end
                        default:;
                    endcase
                end
            end
            if(ram_pending)begin
                ram_pending<=0;s_axi_rvalid<=1;s_axi_rresp<=0;
                case(r_part)
                    0:s_axi_rdata<=ram_read_word[79:48];
                    1:s_axi_rdata<=ram_read_word[47:16];
                    default:s_axi_rdata<={ram_read_word[15:0],16'd0};
                endcase
            end
            if(ar_take)begin
                r_kind<=read_kind;r_index<=read_index;r_part<=read_part;s_axi_rresp<=read_resp;
                if(read_is_ram)ram_pending<=1;
                else begin s_axi_rvalid<=1;s_axi_rdata<=read_value;end
            end
            if(!fault_latched)begin
                if(external_fault)fault(6);
                else if(retired_valid && (state!=DONE || !retirement_ok))fault(7);
                else if(retired_take)begin state<=IDLE;received_count<=0;end
                else case(state)
                    IDLE:if(descriptor_take)begin
                        saved_descriptor<=descriptor_data;received_count<=0;last_sample_tick<=0;
                        descriptor_mask<=0;footer_mask<=0;descriptor_read_count<=0;footer_read_count<=0;sample_read_count<=0;
                        stage_mask<=0;clear_index<=0;crc_index<=0;dcrc<=16'hffff;scrc<=16'hffff;
                        if(descriptor_ok)begin
                            state<=CLEAR;last_epoch<=descriptor_data[671:640];last_generation<=descriptor_data[502:471];
                        end
                        else fault(1);
                    end
                    CLEAR:if(clear_index==543)begin state<=DCRC;crc_index<=0;end
                        else clear_index<=clear_index+1'b1;
                    DCRC:begin
                        dcrc<=crc_byte(dcrc,saved_descriptor[671-crc_index*8 -:8]);
                        if(crc_index==83)begin state<=SAMPLES;crc_index<=0;end
                        else crc_index<=crc_index+1'b1;
                    end
                    SAMPLES:begin
                        if(sample_take)begin
                            if(!sample_ok)fault(2);
                            else begin
                                saved_sample<={4'd0,sample_data,sample_flags,sample_tick};
                                last_sample_tick<=sample_tick;received_count<=received_count+1'b1;crc_index<=0;state<=SCRC;
                            end
                        end else if(finish_valid && finish_ready)begin
                            if((finish_descriptor_crc==dcrc && finish_samples_crc==scrc)===1'b1)state<=SEALED;
                            else fault(3);
                        end
                    end
                    SCRC:begin
                        scrc<=crc_byte(scrc,saved_sample[79-crc_index*8 -:8]);
                        if(crc_index==9)begin state<=SAMPLES;crc_index<=0;end
                        else crc_index<=crc_index+1'b1;
                    end
                    PROOF:if(proof_valid && proof_ready)state<=DONE;
                    default:;
                endcase
            end
            if(have_aw && have_w && !s_axi_bvalid)begin
                have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
                if(wstrb==15 && awaddr[1:0]==0 && !fault_latched && !external_fault && !retired_valid)begin
                    if(state==SEALED)begin
                        case(awaddr)
                            14'h0030:begin staged_epoch<=wdata;stage_mask[0]<=1;s_axi_bresp<=0;end
                            14'h0034:begin staged_id<=wdata;stage_mask[1]<=1;s_axi_bresp<=0;end
                            14'h0038:if(wdata[31:16]==0)begin staged_count<=wdata[15:0];stage_mask[2]<=1;s_axi_bresp<=0;end
                            14'h003c:begin staged_dcrc<=wdata[31:16];staged_scrc<=wdata[15:0];stage_mask[3]<=1;s_axi_bresp<=0;end
                            14'h0060:if(wdata==1)begin
                                if(!all_delivered || s_axi_rvalid || ram_pending || s_axi_arvalid || stage_mask!=12'hfff)fault(5);
                                else if(!proof_fields_ok)fault(4);
                                else begin state<=PROOF;s_axi_bresp<=0;end
                            end
                            default:if(awaddr>=14'h0040 && awaddr<=14'h005c)begin
                                staged_identity[255-((awaddr-14'h0040)>>2)*32 -:32]<=wdata;
                                stage_mask[4+((awaddr-14'h0040)>>2)]<=1;s_axi_bresp<=0;
                            end
                        endcase
                    end else if((state==PROOF || state==DONE) && awaddr==14'h0060 && wdata==1 && proof_fields_ok)
                        s_axi_bresp<=0; // repeated commit never enqueues another proof
                end
            end
        end
    end
endmodule
