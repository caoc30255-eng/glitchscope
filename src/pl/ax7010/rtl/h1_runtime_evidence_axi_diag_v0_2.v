`timescale 1ns / 1ps
// AX-local 4KiB MMIO candidate, no assigned physical base address.
// ACLK must be the same LIFE clock as the raw owner.
module h1_runtime_evidence_axi_diag_v0_2 #(parameter integer CLOCK_HZ=50000000)(
    input wire s_axi_aclk,s_axi_aresetn,
    input wire [11:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [11:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
    input wire core_quiescent,core_fault,external_fault,
    output wire hello_authorized,new_item_capacity,management_idle,
    output reg [31:0] active_epoch,authorized_session,output reg [7:0] expected_route,
    input wire record_valid,output wire record_ready,input wire [7:0] record_kind,
    input wire [31:0] record_epoch,record_session,record_seq,record_ticket,input wire [15:0] record_len,
    input wire byte_valid,output wire byte_ready,input wire [9:0] byte_index,input wire [7:0] byte_data,input wire byte_last,
    input wire finish_valid,output wire finish_ready,input wire [15:0] finish_raw_crc,
    output wire store_valid,input wire store_ready,output reg [7:0] store_kind,
    output reg [31:0] store_epoch,store_session,store_seq,store_ticket,store_record_id,
    output reg [15:0] store_len,store_raw_crc,
    output reg fault,output reg [7:0] fault_code,
    input wire diag_available,input wire [7:0] diag_kind,
    input wire [31:0] diag_epoch,diag_session,diag_seq,diag_ticket,input wire [15:0] diag_len,
    input wire diag_read_valid,input wire [7:0] diag_read_data,input wire diag_address_ready,
    output wire diag_enable,output reg [9:0] diag_addr
);
    localparam [1:0] EMPTY=0,ACQUIRE=1,SEALED=2,CONFIRM=3;
    reg [1:0] cache_state;
    reg authorized;
    reg diag_taken,diag_index_valid;
    reg [7:0] snap_kind;
    reg [31:0] snap_epoch,snap_session,snap_seq,snap_ticket;
    reg [15:0] snap_len;
    reg [9:0] diag_addr_d0,diag_addr_d1;
    reg [1:0] diag_enable_pipe;
    wire diag_binding=diag_taken && diag_available && diag_kind==snap_kind && diag_epoch==snap_epoch &&
        diag_session==snap_session && diag_seq==snap_seq && diag_ticket==snap_ticket && diag_len==snap_len;
    assign diag_enable=diag_binding && diag_index_valid && {6'd0,diag_addr}<snap_len;
    wire diag_data_ready=diag_enable && diag_address_ready && (&diag_enable_pipe) && diag_addr_d1==diag_addr && diag_read_valid;
    reg [7:0] cached_kind;
    reg [31:0] cached_epoch,cached_session,cached_seq,cached_ticket,local_generation;
    reg [15:0] cached_len,cached_crc;
    reg [9:0] written_count,read_count;
    reg [533:0] read_bitmap;
    reg [7:0] descriptor_read_mask;
    reg [7:0] cache[0:533];
    reg [31:0] last_store_id,last_store_ticket;
    reg aw_pending,w_pending;reg [11:0] aw_addr;reg [31:0] w_data;reg [3:0] w_strb;
    reg [31:0] stage_epoch,stage_session,stage_route;
    reg [31:0] proof_epoch,proof_kind,proof_session,proof_seq,proof_ticket,proof_len,proof_crc,proof_id,proof_generation;
    reg r_byte_mark,r_meta_mark;reg [9:0] r_byte_index;reg [2:0] r_meta_index;reg [31:0] r_generation;
    wire write_execute=aw_pending && w_pending && !s_axi_bvalid;
    wire runtime_execute=write_execute && (aw_addr==12'h01c || aw_addr==12'h020);
    wire safe=authorized && !fault && !external_fault && !core_fault && !runtime_execute;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid && (s_axi_araddr!=12'h074 || !diag_enable || diag_data_ready);
    assign hello_authorized=authorized && !fault && !core_fault && !external_fault;
    // Parent additionally matches the actual ingress session to authorized_session.
    assign new_item_capacity=safe && cache_state==EMPTY && local_generation!=32'hffffffff;
    assign management_idle=new_item_capacity && core_quiescent;
    assign record_ready=new_item_capacity && !s_axi_rvalid;
    assign byte_ready=safe && cache_state==ACQUIRE && written_count<cached_len;
    assign finish_ready=safe && cache_state==ACQUIRE && written_count==cached_len;
    assign store_valid=safe && cache_state==CONFIRM;
    wire proof_matches=proof_epoch==cached_epoch && proof_kind=={24'd0,cached_kind} &&
        proof_session==cached_session && proof_seq==cached_seq && proof_ticket==cached_ticket &&
        proof_len=={16'd0,cached_len} && proof_crc=={16'd0,cached_crc} &&
        proof_generation==local_generation && proof_id!=0;
    wire bad_header=record_valid && record_ready && (record_epoch!=active_epoch || record_ticket==0 || record_kind<1 || record_kind>4 || record_len>534);
    wire bad_byte=byte_valid && byte_ready && (byte_index!==written_count || byte_last!==({6'd0,written_count}+16'd1==cached_len));
    wire bad_finish=finish_valid && cache_state==ACQUIRE && !runtime_execute && (written_count!=cached_len || finish_raw_crc!==cached_crc);
    function [15:0] crc_byte;
        input [15:0] crc;input [7:0] value;integer b;reg [15:0] c;
        begin c=crc^{value,8'h00};for(b=0;b<8;b=b+1)c=c[15] ? (c<<1)^16'h1021 : c<<1;crc_byte=c;end
    endfunction
    wire [9:0] requested_index=(s_axi_araddr-12'h400)>>2;
    always @(posedge s_axi_aclk) begin
        if(!s_axi_aresetn) begin
            diag_taken<=0;diag_index_valid<=0;diag_addr<=0;diag_addr_d0<=0;diag_addr_d1<=0;diag_enable_pipe<=0;
            snap_kind<=0;snap_epoch<=0;snap_session<=0;snap_seq<=0;snap_ticket<=0;snap_len<=0;
            cache_state<=EMPTY;authorized<=0;active_epoch<=0;authorized_session<=0;expected_route<=0;
            fault<=0;fault_code<=0;cached_kind<=0;cached_epoch<=0;cached_session<=0;cached_seq<=0;cached_ticket<=0;
            cached_len<=0;cached_crc<=16'hffff;local_generation<=0;written_count<=0;read_count<=0;
            read_bitmap<=0;descriptor_read_mask<=0;last_store_id<=0;last_store_ticket<=0;
            store_kind<=0;store_epoch<=0;store_session<=0;store_seq<=0;store_ticket<=0;
            store_record_id<=0;store_len<=0;store_raw_crc<=0;
            aw_pending<=0;w_pending<=0;aw_addr<=0;w_data<=0;w_strb<=0;
            s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
            r_byte_mark<=0;r_meta_mark<=0;r_byte_index<=0;r_meta_index<=0;r_generation<=0;
            stage_epoch<=0;stage_session<=0;stage_route<=0;
            proof_epoch<=0;proof_kind<=0;proof_session<=0;proof_seq<=0;proof_ticket<=0;
            proof_len<=0;proof_crc<=0;proof_id<=0;proof_generation<=0;
        end else begin
            diag_addr_d0<=diag_addr;diag_addr_d1<=diag_addr_d0;
            diag_enable_pipe<={diag_enable_pipe[0],diag_enable};
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_pending<=1;aw_addr<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_pending<=1;w_data<=s_axi_wdata;w_strb<=s_axi_wstrb;end
            if(s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid<=0;
                // Only bytes/descriptors actually delivered by AXI R handshake count.
                if(r_generation==local_generation && cache_state==SEALED) begin
                    if(r_byte_mark && !read_bitmap[r_byte_index]) begin
                        read_bitmap[r_byte_index]<=1;read_count<=read_count+1'b1;
                    end
                    if(r_meta_mark) descriptor_read_mask[r_meta_index]<=1;
                end
            end
            if(s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
                r_byte_mark<=0;r_meta_mark<=0;r_generation<=local_generation;
                if(s_axi_araddr[1:0]!=0) s_axi_rresp<=2;
                else if(s_axi_araddr>=12'h400 && s_axi_araddr<=12'hc54) begin
                    if(cache_state!=EMPTY && requested_index<written_count) begin
                        s_axi_rdata<={24'd0,cache[requested_index]};
                        r_byte_mark<=cache_state==SEALED;r_byte_index<=requested_index;
                    end else s_axi_rresp<=2;
                end else if(s_axi_araddr>=12'h100 && s_axi_araddr<=12'h11c) begin
                    if(cache_state==EMPTY) s_axi_rresp<=2;
                    else begin
                        r_meta_mark<=cache_state==SEALED;r_meta_index<=s_axi_araddr[4:2];
                        case(s_axi_araddr)
                            12'h100:s_axi_rdata<={24'd0,cached_kind};
                            12'h104:s_axi_rdata<=cached_epoch;
                            12'h108:s_axi_rdata<=cached_session;
                            12'h10c:s_axi_rdata<=cached_seq;
                            12'h110:s_axi_rdata<=cached_ticket;
                            12'h114:s_axi_rdata<={16'd0,cached_len};
                            12'h118:s_axi_rdata<={16'd0,cached_crc};
                            12'h11c:s_axi_rdata<=local_generation;
                        endcase
                    end
                end else case(s_axi_araddr)
                    12'h000:s_axi_rdata<=32'h48354531;
                    12'h004:s_axi_rdata<={22'd0,new_item_capacity,(descriptor_read_mask==8'hff),
                        (read_count==cached_len && cache_state==SEALED),core_fault,core_quiescent,fault,
                        (cache_state==CONFIRM),(cache_state==SEALED),(cache_state!=EMPTY),authorized};
                    12'h008:s_axi_rdata<=CLOCK_HZ;
                    12'h00c:s_axi_rdata<={24'd0,fault_code};
                    12'h010:s_axi_rdata<=stage_epoch;
                    12'h014:s_axi_rdata<=stage_session;
                    12'h018:s_axi_rdata<=stage_route;
                    12'h024:s_axi_rdata<=active_epoch;
                    12'h028:s_axi_rdata<=authorized_session;
                    12'h02c:s_axi_rdata<={24'd0,expected_route};
                    12'h030:s_axi_rdata<={22'd0,read_count};
                    12'h034:s_axi_rdata<={24'd0,descriptor_read_mask};
                    12'h040:s_axi_rdata<=proof_epoch;
                    12'h044:s_axi_rdata<=proof_kind;
                    12'h048:s_axi_rdata<=proof_session;
                    12'h04c:s_axi_rdata<=proof_seq;
                    12'h050:s_axi_rdata<=proof_ticket;
                    12'h054:s_axi_rdata<=proof_len;
                    12'h058:s_axi_rdata<=proof_crc;
                    12'h05c:s_axi_rdata<=proof_id;
                    12'h060:s_axi_rdata<=proof_generation;
                    12'h070:s_axi_rdata<={22'd0,diag_addr};
                    12'h074:if(diag_data_ready) s_axi_rdata<={24'd0,diag_read_data};else s_axi_rresp<=2;
                    12'h078:s_axi_rdata<={28'd0,diag_available,diag_taken,diag_data_ready,diag_binding};
                    12'h07c:s_axi_rdata<=snap_ticket;
                    12'h080:s_axi_rdata<={16'd0,snap_len};
                    12'h084:s_axi_rdata<={24'd0,snap_kind};
                    12'h088:s_axi_rdata<=snap_session;
                    12'h08c:s_axi_rdata<=snap_seq;
                    12'h090:s_axi_rdata<=snap_epoch;
                    12'h068:s_axi_rdata<=last_store_id;
                    12'h06c:s_axi_rdata<=last_store_ticket;
                    default:s_axi_rresp<=2;
                endcase
            end
            if(!fault && (external_fault || core_fault)) begin fault<=1;fault_code<=1;end
            if(!fault && !external_fault && !core_fault) begin
                if(record_valid && record_ready) begin
                    if(record_epoch!=active_epoch || record_ticket==0 || record_kind<1 || record_kind>4 || record_len>534)
                        begin fault<=1;fault_code<=2;end
                    else begin
                        cached_kind<=record_kind;cached_epoch<=record_epoch;cached_session<=record_session;
                        cached_seq<=record_seq;cached_ticket<=record_ticket;cached_len<=record_len;
                        cached_crc<=16'hffff;written_count<=0;read_count<=0;read_bitmap<=0;descriptor_read_mask<=0;
                        local_generation<=local_generation+1'b1;cache_state<=ACQUIRE;
                    end
                end
                if(byte_valid && byte_ready) begin
                    if(byte_index!==written_count || byte_last!==({6'd0,written_count}+16'd1==cached_len))
                        begin fault<=1;fault_code<=3;end
                    else begin
                        cache[written_count]<=byte_data;written_count<=written_count+1'b1;
                        cached_crc<=crc_byte(cached_crc,byte_data);
                    end
                end
                if(finish_valid && cache_state==ACQUIRE && !runtime_execute) begin
                    if(written_count!=cached_len || finish_raw_crc!==cached_crc)
                        begin fault<=1;fault_code<=4;end
                    else if(finish_ready) cache_state<=SEALED;
                end
                if(store_valid && store_ready) begin
                    last_store_id<=store_record_id;last_store_ticket<=store_ticket;cache_state<=EMPTY;
                end
            end
            if(write_execute) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(w_strb!=4'hf || aw_addr[1:0]!=0) s_axi_bresp<=2;
                else case(aw_addr)
                    12'h010:stage_epoch<=w_data;
                    12'h014:stage_session<=w_data;
                    12'h018:stage_route<=w_data;
                    12'h01c:begin
                        if(w_data!=1 || !core_quiescent || cache_state!=EMPTY || record_valid || fault ||
                            core_fault || external_fault || stage_epoch<=active_epoch || stage_session==0 || stage_route>1)
                            s_axi_bresp<=2;
                        else begin authorized<=1;active_epoch<=stage_epoch;authorized_session<=stage_session;expected_route<=stage_route[7:0];end
                    end
                    12'h020:if(w_data!=1 || !core_quiescent || cache_state!=EMPTY || record_valid)
                        s_axi_bresp<=2;else authorized<=0;
                    12'h040:proof_epoch<=w_data;
                    12'h044:proof_kind<=w_data;
                    12'h048:proof_session<=w_data;
                    12'h04c:proof_seq<=w_data;
                    12'h050:proof_ticket<=w_data;
                    12'h054:proof_len<=w_data;
                    12'h058:proof_crc<=w_data;
                    12'h05c:proof_id<=w_data;
                    12'h060:proof_generation<=w_data;
                    12'h070:begin
                        if(!diag_binding || w_data>={16'd0,snap_len}) begin
                            s_axi_bresp<=2;diag_index_valid<=0;
                        end else begin diag_addr<=w_data[9:0];diag_index_valid<=1;diag_enable_pipe<=0;end
                    end
                    12'h078:begin
                        if(w_data!=1 || !diag_available || diag_ticket==0 || diag_len>534 || diag_kind<1 || diag_kind>4)
                            s_axi_bresp<=2;
                        else if(diag_taken) begin
                            if(!diag_binding) s_axi_bresp<=2;
                        end else begin
                            diag_taken<=1;snap_kind<=diag_kind;snap_epoch<=diag_epoch;
                            snap_session<=diag_session;snap_seq<=diag_seq;snap_ticket<=diag_ticket;snap_len<=diag_len;
                            diag_addr<=0;diag_index_valid<=diag_len!=0;diag_enable_pipe<=0;
                        end
                    end
                    12'h064:begin
                        if(w_data!=1 || cache_state!=SEALED || fault || core_fault || external_fault ||
                            s_axi_rvalid || read_count!=cached_len || descriptor_read_mask!=8'hff || !proof_matches) begin
                            s_axi_bresp<=2;
                            // A duplicate command while confirmation is pending cannot overwrite it.
                            if(!fault && !core_fault && !external_fault && !bad_header && !bad_byte && !bad_finish && cache_state!=CONFIRM) begin fault<=1;fault_code<=5;end
                        end else begin
                            store_kind<=proof_kind[7:0];store_epoch<=proof_epoch;store_session<=proof_session;
                            store_seq<=proof_seq;store_ticket<=proof_ticket;store_record_id<=proof_id;
                            store_len<=proof_len[15:0];store_raw_crc<=proof_crc[15:0];cache_state<=CONFIRM;
                        end
                    end
                    default:s_axi_bresp<=2;
                endcase
            end
        end
    end
endmodule
