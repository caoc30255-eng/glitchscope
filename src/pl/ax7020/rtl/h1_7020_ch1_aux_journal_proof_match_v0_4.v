`timescale 1ns/1ps
// Independent error/orphan queues. Both may enqueue on the same clock.
// Event432: pad1,epoch32,seq32,binding_present1,kind1,identity256,id32,
// flags4,has_byte1,data8,tick64. Kind0=error,1=orphan. ACK asserts persistence.
module h1_7020_ch1_aux_journal_axi_v0_1 #(
    parameter integer DEPTH=1024
)(
    input wire clk,rst_n,
    input wire [31:0] event_epoch,
    input wire binding_present,
    input wire [255:0] binding_identity,
    input wire [31:0] binding_record_id,
    input wire error_valid,error_has_byte,
    input wire [7:0] error_data,
    input wire [3:0] error_flags,
    input wire [63:0] error_tick,
    output wire error_ready,
    input wire orphan_valid,orphan_has_byte,
    input wire [7:0] orphan_data,
    input wire [3:0] orphan_flags,
    input wire [63:0] orphan_tick,
    output wire orphan_ready,
    output wire fault_latched,blocking_fault,
    output wire pending_events,
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
    localparam AW=$clog2(DEPTH);
    (* ram_style="block" *) reg [431:0] error_ram[0:DEPTH-1],orphan_ram[0:DEPTH-1];
    reg [AW-1:0] ew,er,ow,orr;
    reg [AW:0] error_count,orphan_count;
    reg [31:0] error_seq,orphan_seq,error_drops,orphan_drops;
    reg error_lost,orphan_lost,protocol_fault;
    reg [431:0] first_error_lost,first_orphan_lost;
    reg [7:0] error_lost_reason,orphan_lost_reason;
    reg [431:0] error_head_read,orphan_head_read,snapshot;
    reg head_is_orphan;
    wire [431:0] head_read=head_is_orphan ? orphan_head_read : error_head_read;
    reg snap_pending,snap_crc_busy,snap_valid;
    reg [5:0] crc_index;
    reg [15:0] snap_crc;
    reg [14:0] read_mask;
    reg [3:0] stage_mask;
    reg [3:0] staged_match; // valid only with fresh stage_mask for frozen snapshot
    reg [31:0] staged_epoch,staged_seq;
    reg staged_kind;
    reg [15:0] staged_crc;
    reg have_aw,have_w;
    reg [11:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    reg [31:0] read_value;
    reg [1:0] read_resp;
    reg [14:0] read_credit,r_credit;
    assign s_axi_awready=rst_n && !have_aw && !s_axi_bvalid;
    assign s_axi_wready=rst_n && !have_w && !s_axi_bvalid;
    assign s_axi_arready=rst_n && !s_axi_rvalid;
    wire write_exec=have_aw && have_w && !s_axi_bvalid;
    wire full_write=wstrb==15 && awaddr[1:0]==0;
    wire capture_error=write_exec && full_write && awaddr==12'h010 && wdata==1 &&
        !snap_valid && !snap_pending && !snap_crc_busy && error_count!=0 && !s_axi_rvalid && !s_axi_arvalid;
    wire capture_orphan=write_exec && full_write && awaddr==12'h010 && wdata==2 &&
        !snap_valid && !snap_pending && !snap_crc_busy && orphan_count!=0 && !s_axi_rvalid && !s_axi_arvalid;
    wire ack_attempt=write_exec && full_write && awaddr==12'h014 && wdata==1;
    // Snapshot and its CRC cannot change while snap_valid. Proof writes
    // already precede ACK execution; compare on those existing write edges.
    // Four-state unknowns reject exactly as in the original full equality.
    wire ack_match=(staged_match==4'hf)===1'b1;
    wire ack_ok=snap_valid && read_mask==15'h7fff && stage_mask==15 && ack_match && !s_axi_rvalid && !s_axi_arvalid;
    wire pop_error=ack_attempt && ack_ok && !snapshot[365];
    wire pop_orphan=ack_attempt && ack_ok && snapshot[365];
    assign fault_latched=error_lost || orphan_lost || protocol_fault;
    // Read-only drain barrier for the enclosing record retirement owner.
    assign pending_events=error_count!=0 || orphan_count!=0 || snap_valid || snap_pending || snap_crc_busy;
    wire context_ok=((binding_present===1'b0) || (binding_present===1'b1 && binding_record_id!=0 &&
        binding_identity[255:219]==0 && binding_identity[186:155]!=0 && binding_identity[119:88]!=0))===1'b1;
    wire epoch_ok=(event_epoch!=0 && context_ok)===1'b1;
    assign error_ready=rst_n && !fault_latched && epoch_ok && error_seq!=32'hffffffff && (error_count<DEPTH || pop_error);
    assign orphan_ready=rst_n && !fault_latched && epoch_ok && orphan_seq!=32'hffffffff && (orphan_count<DEPTH || pop_orphan);
    assign blocking_fault=fault_latched || (error_valid && !error_ready) || (orphan_valid && !orphan_ready);
    wire push_error=error_valid && error_ready;
    wire push_orphan=orphan_valid && orphan_ready;
    wire [431:0] error_event={1'b0,event_epoch,error_seq,binding_present,1'b0,
        binding_present ? binding_identity : 256'd0,binding_present ? binding_record_id : 32'd0,error_flags,error_has_byte,error_data,error_tick};
    wire [431:0] orphan_event={1'b0,event_epoch,orphan_seq,binding_present,1'b1,
        binding_present ? binding_identity : 256'd0,binding_present ? binding_record_id : 32'd0,orphan_flags,orphan_has_byte,orphan_data,orphan_tick};
    function [15:0] crc_byte;
        input [15:0] old;input [7:0] data;
        reg [15:0] c;integer k;
        begin c=old^{data,8'd0};for(k=0;k<8;k=k+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_byte=c;end
    endfunction
    function [31:0] word_of;
        input [431:0] packet;input [5:0] index;
        begin if(index==13)word_of={packet[15:0],16'd0};else word_of=packet[431-index*32 -:32];end
    endfunction
    // Explicit synchronous head reads; FIFO arrays never asynchronously peeked.
    // Each RAM has its own synchronous output register. The queue selector
    // is after those registers, rather than muxing two memories into one
    // register, so both independent memories can infer simple dual-port BRAM.
    // snap_pending still copies the selected head on the next clock; all AXI,
    // CRC, full-delivery credit and saved-ACK timing stays unchanged.
    always @(posedge clk)begin
        if(push_error)error_ram[ew]<=error_event;
        if(capture_error)error_head_read<=error_ram[er];
    end
    always @(posedge clk)begin
        if(push_orphan)orphan_ram[ow]<=orphan_event;
        if(capture_orphan)orphan_head_read<=orphan_ram[orr];
    end
    always @(posedge clk)begin
        if(!rst_n)head_is_orphan<=0;
        else if(capture_error || capture_orphan)head_is_orphan<=capture_orphan;
    end
    always @* begin
        read_value=0;read_resp=0;read_credit=0;
        case(s_axi_araddr)
            12'h000:read_value=32'h48314a31; // H1J1
            12'h004:read_value={26'd0,(snap_pending || snap_crc_busy),protocol_fault,orphan_lost,error_lost,fault_latched,snap_valid};
            12'h008:read_value=error_count;
            12'h00c:read_value=orphan_count;
            12'h018:if(snap_valid)begin read_value={16'd0,snap_crc};read_credit=15'h4000;end else read_resp=2;
            12'h030:read_value=error_seq;
            12'h034:read_value=orphan_seq;
            12'h038:read_value=error_drops;
            12'h03c:read_value=orphan_drops;
            12'h040:read_value={24'd0,error_lost_reason};
            12'h044:read_value={24'd0,orphan_lost_reason};
            12'h048:read_value={17'd0,read_mask};
            default:begin
                if(s_axi_araddr>=12'h100 && s_axi_araddr<=12'h134 && snap_valid)begin
                    read_value=word_of(snapshot,(s_axi_araddr-12'h100)>>2);read_credit=15'b1<<((s_axi_araddr-12'h100)>>2);
                end else if(s_axi_araddr>=12'h200 && s_axi_araddr<=12'h234 && error_lost)
                    read_value=word_of(first_error_lost,(s_axi_araddr-12'h200)>>2);
                else if(s_axi_araddr>=12'h240 && s_axi_araddr<=12'h274 && orphan_lost)
                    read_value=word_of(first_orphan_lost,(s_axi_araddr-12'h240)>>2);
                else read_resp=2;
            end
        endcase
        if(s_axi_araddr[1:0]!=0)read_resp=2;
        if(read_resp!=0)begin read_value=0;read_credit=0;end
    end
    always @(posedge clk)begin
        if(!rst_n)begin
            ew<=0;er<=0;ow<=0;orr<=0;error_count<=0;orphan_count<=0;error_seq<=1;orphan_seq<=1;
            error_drops<=0;orphan_drops<=0;error_lost<=0;orphan_lost<=0;protocol_fault<=0;
            first_error_lost<=0;first_orphan_lost<=0;error_lost_reason<=0;orphan_lost_reason<=0;
            snapshot<=0;snap_pending<=0;snap_crc_busy<=0;snap_valid<=0;crc_index<=0;snap_crc<=16'hffff;
            read_mask<=0;stage_mask<=0;staged_match<=0;staged_epoch<=0;staged_seq<=0;staged_kind<=0;staged_crc<=0;
            have_aw<=0;have_w<=0;awaddr<=0;wdata<=0;wstrb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;r_credit<=0;
        end else begin
            if(push_error)begin ew<=ew+1'b1;error_seq<=error_seq+1'b1;end
            if(push_orphan)begin ow<=ow+1'b1;orphan_seq<=orphan_seq+1'b1;end
            if(pop_error)er<=er+1'b1;
            if(pop_orphan)orr<=orr+1'b1;
            case({push_error,pop_error})
                2'b10:error_count<=error_count+1'b1;
                2'b01:error_count<=error_count-1'b1;
                default:;
            endcase
            case({push_orphan,pop_orphan})
                2'b10:orphan_count<=orphan_count+1'b1;
                2'b01:orphan_count<=orphan_count-1'b1;
                default:;
            endcase
            if(error_valid && !error_ready)begin
                if(error_drops!=32'hffffffff)error_drops<=error_drops+1'b1;
                if(!error_lost)begin error_lost<=1;first_error_lost<=error_event;
                    error_lost_reason<=!epoch_ok ? 2 : error_seq==32'hffffffff ? 3 : fault_latched ? 4 : 1;end
            end
            if(orphan_valid && !orphan_ready)begin
                if(orphan_drops!=32'hffffffff)orphan_drops<=orphan_drops+1'b1;
                if(!orphan_lost)begin orphan_lost<=1;first_orphan_lost<=orphan_event;
                    orphan_lost_reason<=!epoch_ok ? 2 : orphan_seq==32'hffffffff ? 3 : fault_latched ? 4 : 1;end
            end
            if(snap_pending)begin snapshot<=head_read;snap_pending<=0;snap_crc_busy<=1;crc_index<=0;snap_crc<=16'hffff;end
            else if(snap_crc_busy)begin
                snap_crc<=crc_byte(snap_crc,snapshot[431-crc_index*8 -:8]);
                if(crc_index==53)begin snap_crc_busy<=0;snap_valid<=1;end else crc_index<=crc_index+1'b1;
            end
            if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;awaddr<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready)begin have_w<=1;wdata<=s_axi_wdata;wstrb<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready)begin s_axi_rvalid<=0;read_mask<=read_mask|r_credit;end
            if(s_axi_arvalid && s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rdata<=read_value;s_axi_rresp<=read_resp;r_credit<=read_credit;
            end
            if(write_exec)begin
                have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=2;
                if(full_write)begin
                    case(awaddr)
                        12'h010:if(capture_error || capture_orphan)begin
                            snap_pending<=1;read_mask<=0;stage_mask<=0;staged_match<=0;s_axi_bresp<=0;
                        end
                        12'h014:if(wdata==1)begin
                            if(ack_ok)begin snap_valid<=0;read_mask<=0;stage_mask<=0;staged_match<=0;s_axi_bresp<=0;end
                            else protocol_fault<=1;
                        end
                        12'h020:if(snap_valid)begin staged_epoch<=wdata;stage_mask[0]<=1;staged_match[0]<=((wdata==snapshot[430:399])===1'b1);s_axi_bresp<=0;end
                        12'h024:if(snap_valid)begin staged_seq<=wdata;stage_mask[1]<=1;staged_match[1]<=((wdata==snapshot[398:367])===1'b1);s_axi_bresp<=0;end
                        12'h028:if(snap_valid && wdata<=1)begin staged_kind<=wdata[0];stage_mask[2]<=1;staged_match[2]<=((wdata[0]==snapshot[365])===1'b1);s_axi_bresp<=0;end
                        12'h02c:if(snap_valid && wdata[31:16]==0)begin staged_crc<=wdata[15:0];stage_mask[3]<=1;staged_match[3]<=((wdata[15:0]==snap_crc)===1'b1);s_axi_bresp<=0;end
                        default:;
                    endcase
                end
            end
        end
    end
    initial begin
        if(DEPTH<2 || DEPTH>1024 || (DEPTH&(DEPTH-1))!=0)$fatal(1,"Journal DEPTH must be a power of two in 2..1024");
    end
endmodule
