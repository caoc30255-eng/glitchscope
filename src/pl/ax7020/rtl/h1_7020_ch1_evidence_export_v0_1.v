`timescale 1ns/1ps
// Single terminal record exporter. Submit is a command, not a stallable valid.
// Metadata[639:0]: reserved1,identity256,id32,kind2,reason8,count16,
// start64,deadline64,close64,frame_valid1,status8,wire_flags8,ack_status16,
// uart_errors32,observed_flags4,first_error_tick64.
module h1_7020_ch1_evidence_export_v0_1(
    input wire clk,rst_n,
    input wire record_valid,
    input wire [639:0] record_metadata,
    input wire [31:0] evidence_epoch,
    input wire external_fault,
    output reg [9:0] read_addr,
    output wire read_claim,
    input wire read_valid,
    input wire [7:0] read_data,
    input wire [3:0] read_flags,
    input wire [63:0] read_tick,
    output wire descriptor_valid,
    input wire descriptor_ready,
    output reg [671:0] descriptor,
    output wire sample_valid,
    input wire sample_ready,
    output reg [9:0] sample_index,
    output wire [7:0] sample_data,
    output wire [3:0] sample_flags,
    output wire [63:0] sample_tick,
    output wire finish_valid,
    input wire finish_ready,
    output reg [15:0] descriptor_crc,samples_crc,
    input wire proof_submit,
    input wire [31:0] proof_epoch,proof_record_id,
    input wire [255:0] proof_identity,
    input wire [15:0] proof_count,proof_descriptor_crc,proof_samples_crc,
    output wire proof_ready,
    output reg proof_accepted,
    output wire store_valid,
    input wire store_ready,
    output wire store_take,
    output wire [255:0] store_identity,
    output wire [31:0] store_record_id,
    output reg fault_latched,
    output reg [7:0] first_fault
);
    localparam IDLE=0,DCRC=1,DOUT=2,FETCH=3,RWAIT=4,LATCH=5,SCRC=6,SOUT=7,FINISH=8,PROOF=9,STORE=10,DONE=11;
    reg [3:0] state;
    reg [6:0] crc_index;
    reg [79:0] sample_word;
    reg [31:0] last_epoch,last_generation;
    reg [63:0] last_sample_tick;
    wire [15:0] count=descriptor[340:325];
    wire same_record={evidence_epoch,record_metadata}===descriptor;
    wire proof_match=(proof_epoch==descriptor[671:640] && proof_identity===descriptor[638:383] &&
        proof_record_id==descriptor[382:351] && proof_count==count &&
        proof_descriptor_crc==descriptor_crc && proof_samples_crc==samples_crc)===1'b1;
    wire metadata_ok=(record_metadata[639]==0 && record_metadata[638:602]==0 &&
        record_metadata[569:538]!=0 && record_metadata[382:351]!=0 &&
        record_metadata[350:349]>=1 && record_metadata[348:341]>=1 && record_metadata[348:341]<=7 &&
        record_metadata[340:325]<=544 && record_metadata[324:261]<record_metadata[260:197] &&
        record_metadata[132]==(record_metadata[348:341]==1) &&
        (record_metadata[348:341]!=1 || (record_metadata[350:349]==1 ?
            (record_metadata[340:325]>=20 && record_metadata[340:325]<=532) : record_metadata[340:325]==12)) &&
        record_metadata[196:133]>=record_metadata[324:261] && record_metadata[196:133]<=record_metadata[260:197] &&
        (record_metadata[348:341]!=5 || record_metadata[196:133]==record_metadata[260:197]) &&
        (record_metadata[196:133]!=record_metadata[260:197] || record_metadata[348:341]>=5) &&
        evidence_epoch!=0 && (evidence_epoch>last_epoch ||
        (evidence_epoch==last_epoch && record_metadata[502:471]>last_generation)) && record_metadata[502:471]!=0)===1'b1;
    wire event_ok=record_valid && same_record && !fault_latched && !external_fault;
    assign descriptor_valid=state==DOUT && event_ok;
    assign sample_valid=state==SOUT && event_ok;
    assign finish_valid=state==FINISH && event_ok;
    assign proof_ready=state==PROOF && event_ok;
    assign store_valid=state==STORE && event_ok && !proof_submit;
    assign store_take=store_valid && store_ready;
    assign store_identity=descriptor[638:383];
    assign store_record_id=descriptor[382:351];
    assign {sample_data,sample_flags,sample_tick}=sample_word[75:0];
    assign read_claim=(state==FETCH || state==RWAIT || state==LATCH) && !fault_latched && !external_fault;
    function [15:0] crc_byte;
        input [15:0] old;input [7:0] data;
        reg [15:0] c;integer i;
        begin c=old^{data,8'd0};for(i=0;i<8;i=i+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_byte=c;end
    endfunction
    task fault;
        input [7:0] reason;
        begin fault_latched<=1;first_fault<=reason;end
    endtask
    always @(posedge clk)begin
        if(!rst_n)begin
            state<=IDLE;read_addr<=0;descriptor<=0;sample_index<=0;sample_word<=0;crc_index<=0;
            descriptor_crc<=16'hffff;samples_crc<=16'hffff;proof_accepted<=0;
            last_epoch<=0;last_generation<=0;last_sample_tick<=0;fault_latched<=0;first_fault<=0;
        end else begin
            proof_accepted<=0;
            if(!fault_latched)begin
                if(external_fault)fault(4);
                else if(state!=IDLE && state!=DONE && (!record_valid || !same_record))fault(2);
                else if(proof_submit)begin
                    if(state!=PROOF && state!=STORE && state!=DONE)fault(1);
                    else if(!proof_match)fault(3);
                    else begin proof_accepted<=1;if(state==PROOF)state<=STORE;end
                end else case(state)
                    IDLE:if(record_valid)begin
                        if(!metadata_ok)fault(5);
                        else begin
                            descriptor<={evidence_epoch,record_metadata};state<=DCRC;crc_index<=0;
                            descriptor_crc<=16'hffff;samples_crc<=16'hffff;sample_index<=0;last_sample_tick<=0;
                            last_epoch<=evidence_epoch;last_generation<=record_metadata[502:471];
                        end
                    end
                    DCRC:begin
                        descriptor_crc<=crc_byte(descriptor_crc,descriptor[671-crc_index*8 -: 8]);
                        if(crc_index==83)begin state<=DOUT;crc_index<=0;end
                        else crc_index<=crc_index+1'b1;
                    end
                    DOUT:if(descriptor_ready)state<=count==0 ? FINISH : FETCH;
                    FETCH:begin read_addr<=sample_index;state<=RWAIT;end
                    RWAIT:state<=LATCH;
                    LATCH:if(read_valid!==1'b1 || read_tick<descriptor[324:261] || read_tick>=descriptor[260:197] ||
                        (sample_index!=0 && read_tick<last_sample_tick))fault(6);
                        else begin sample_word<={4'd0,read_data,read_flags,read_tick};last_sample_tick<=read_tick;crc_index<=0;state<=SCRC;end
                    SCRC:begin
                        samples_crc<=crc_byte(samples_crc,sample_word[79-crc_index*8 -: 8]);
                        if(crc_index==9)begin state<=SOUT;crc_index<=0;end
                        else crc_index<=crc_index+1'b1;
                    end
                    SOUT:if(sample_ready)begin
                        if(sample_index+1==count)state<=FINISH;
                        else begin sample_index<=sample_index+1'b1;state<=FETCH;end
                    end
                    FINISH:if(finish_ready)state<=PROOF;
                    PROOF:state<=PROOF;
                    STORE:if(store_ready)state<=DONE;
                    DONE:if(!record_valid)state<=IDLE;
                    default:fault(7);
                endcase
            end
        end
    end
endmodule
