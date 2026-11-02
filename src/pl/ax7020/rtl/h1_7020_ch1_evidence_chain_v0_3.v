`timescale 1ns/1ps
// One-clock CH1 capture/export/cache/journal/retirement chain. No PS or board pins assigned.
module h1_7020_ch1_evidence_chain_v0_3 #(
 parameter integer JOURNAL_DEPTH=1024, IDLE_GUARD_TICKS=10000, INTERBYTE_TICKS=200000,
 CLK_HZ=100000000, BAUD=1000000
)(
 input wire clk,rst_n,uart_rx,
 input wire [63:0] tick,
 input wire [31:0] evidence_epoch,
 input wire arm,
 input wire [1:0] arm_kind,
 input wire [255:0] arm_identity,
 input wire [31:0] arm_record_id,
 input wire [63:0] start_tick,deadline_tick,
 input wire physical_done,
 input wire [255:0] done_identity,
 input wire abort_event,external_fault,release_request,session_can_retire,
 output wire fault_latched,record_valid,record_active,aux_pending,retired_take,
 output wire [15:0] raw_count,
 output wire [7:0] terminal_reason,
 output wire [31:0] retire_count,
 output wire core_retire_ready,
 output wire [31:0] retired_epoch,retired_record_id,
 output wire [255:0] retired_identity,
 input wire [13:0] main_awaddr,
 input wire  main_awvalid,
 output wire  main_awready,
 input wire [31:0] main_wdata,
 input wire [3:0] main_wstrb,
 input wire  main_wvalid,
 output wire  main_wready,
 output wire [1:0] main_bresp,
 output wire  main_bvalid,
 input wire  main_bready,
 input wire [13:0] main_araddr,
 input wire  main_arvalid,
 output wire  main_arready,
 output wire [31:0] main_rdata,
 output wire [1:0] main_rresp,
 output wire  main_rvalid,
 input wire  main_rready,
 input wire [11:0] aux_awaddr,
 input wire  aux_awvalid,
 output wire  aux_awready,
 input wire [31:0] aux_wdata,
 input wire [3:0] aux_wstrb,
 input wire  aux_wvalid,
 output wire  aux_wready,
 output wire [1:0] aux_bresp,
 output wire  aux_bvalid,
 input wire  aux_bready,
 input wire [11:0] aux_araddr,
 input wire  aux_arvalid,
 output wire  aux_arready,
 output wire [31:0] aux_rdata,
 output wire [1:0] aux_rresp,
 output wire  aux_rvalid,
 input wire  aux_rready
);
 wire capture_fault,export_fault,cache_fault,guard_fault,journal_fault,journal_block;
 reg epoch_fault,close_sent;
 reg [31:0] bound_epoch;
 assign retired_epoch=bound_epoch;
 assign retired_record_id=saved_record_id;
 assign retired_identity=saved_identity;
 wire epoch_changed=record_active && evidence_epoch!=bound_epoch;
 wire common_fault=external_fault || epoch_fault || epoch_changed || capture_fault || export_fault || cache_fault || guard_fault || journal_block;
 assign fault_latched=common_fault;
 wire accepted_arm=arm && evidence_epoch!=0 && !common_fault;
 wire rx_valid,rx_error_event;wire [7:0] rx_data;wire [3:0] rx_flags;
 wire fe;
 assign rx_flags=fe ? 4'b0010 : 4'd0;assign rx_error_event=fe;
 ctrl_uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) receiver(.clk(clk),.rst_n(rst_n),.uart_rx(uart_rx),.rx_data(rx_data),.rx_valid(rx_valid),.framing_error(fe),.rx_busy());
 always @(posedge clk)begin
  if(!rst_n)begin epoch_fault<=0;bound_epoch<=0;close_sent<=0;end
  else begin
   if((arm && evidence_epoch==0) || epoch_changed)epoch_fault<=1;
   if(accepted_arm && !record_active)begin bound_epoch<=evidence_epoch;close_sent<=0;end
   else if(record_valid && !close_sent)close_sent<=1;
  end
 end
 wire record_close=record_valid && !close_sent;
 wire [9:0] owner_read_addr;
 wire [7:0] read_data;
 wire [3:0] read_flags;
 wire [63:0] read_tick;
 wire  read_valid;
 wire  error_ready;
 wire  error_event_valid;
 wire  error_has_byte;
 wire [7:0] error_data;
 wire [3:0] error_flags;
 wire [63:0] error_tick;
 wire  orphan_ready;
 wire  orphan_valid;
 wire  orphan_has_byte;
 wire [7:0] orphan_data;
 wire [3:0] orphan_flags;
 wire [63:0] orphan_tick;
 wire [31:0] orphan_count;

 wire  closed;
 wire [255:0] saved_identity;
 wire [31:0] saved_record_id;
 wire [1:0] saved_kind;
 wire [15:0] management_status;
 wire [63:0] record_close_tick;
 wire [63:0] saved_start_tick;
 wire [63:0] saved_deadline_tick;
 wire [15:0] expected_total;
 wire  report_valid;
 wire [31:0] uart_error_count;
 wire [3:0] uart_flags_seen;
 wire [63:0] first_uart_error_tick;
 wire [7:0] report_status;
 wire [7:0] report_uart_flags;

 wire [7:0] capture_first_error;
 wire [7:0] first_lost_data;
 wire [3:0] first_lost_flags;
 wire [63:0] first_lost_tick;
 wire  first_lost_has_byte;
h1_7020_ch1_capture_v0_4 #(.IDLE_GUARD_TICKS(IDLE_GUARD_TICKS),.INTERBYTE_TICKS(INTERBYTE_TICKS)) capture(
.clk(clk),
.rst_n(rst_n),
.tick(tick),
.arm(accepted_arm),
.arm_kind(arm_kind),
.arm_identity(arm_identity),
.arm_record_id(arm_record_id),
.start_tick(start_tick),
.deadline_tick(deadline_tick),
.rx_valid(rx_valid),
.rx_data(rx_data),
.rx_flags(rx_flags),
.rx_error_event(rx_error_event),
.abort_event(abort_event),
.record_ack(retired_take),
.read_addr(owner_read_addr),
.read_data(read_data),
.read_flags(read_flags),
.read_tick(read_tick),
.read_valid(read_valid),
.error_ready(error_ready),
.error_event_valid(error_event_valid),
.error_has_byte(error_has_byte),
.error_data(error_data),
.error_flags(error_flags),
.error_tick(error_tick),
.orphan_ready(orphan_ready),
.orphan_valid(orphan_valid),
.orphan_has_byte(orphan_has_byte),
.orphan_data(orphan_data),
.orphan_flags(orphan_flags),
.orphan_tick(orphan_tick),
.orphan_count(orphan_count),
.active(record_active),
.closed(closed),
.record_valid(record_valid),
.saved_identity(saved_identity),
.saved_record_id(saved_record_id),
.saved_kind(saved_kind),
.management_status(management_status),
.terminal_reason(terminal_reason),
.record_close_tick(record_close_tick),
.saved_start_tick(saved_start_tick),
.saved_deadline_tick(saved_deadline_tick),
.raw_count(raw_count),
.expected_total(expected_total),
.report_valid(report_valid),
.uart_error_count(uart_error_count),
.uart_flags_seen(uart_flags_seen),
.first_uart_error_tick(first_uart_error_tick),
.report_status(report_status),
.report_uart_flags(report_uart_flags),
.fault_latched(capture_fault),
.first_error(capture_first_error),
.first_lost_data(first_lost_data),
.first_lost_flags(first_lost_flags),
.first_lost_tick(first_lost_tick),
.first_lost_has_byte(first_lost_has_byte)
);
 wire [639:0] record_metadata={1'b0,saved_identity,saved_record_id,saved_kind,terminal_reason,raw_count,saved_start_tick,saved_deadline_tick,record_close_tick,report_valid,report_status,report_uart_flags,management_status,uart_error_count,uart_flags_seen,first_uart_error_tick};
 wire descriptor_valid,descriptor_ready,sample_valid,sample_ready,finish_valid,finish_ready;
 wire [671:0] descriptor;wire [9:0] sample_index;wire [7:0] sample_data;wire [3:0] sample_flags;wire [63:0] sample_tick;
 wire [15:0] descriptor_crc,samples_crc;
 wire proof_valid,proof_ready,proof_accepted,store_valid,store_take;
 wire [31:0] proof_epoch,proof_record_id,store_record_id;wire [255:0] proof_identity,store_identity;
 wire [15:0] proof_count,proof_descriptor_crc,proof_samples_crc;
 wire [7:0] export_first_fault,cache_first_fault;
 wire retired_ready,retired_valid,guard_pending,guard_retire_fire;
 // Delay capture/cache release until guard handoff; abort, new ARM and done cannot share it.
 assign retired_valid=guard_pending && !common_fault && !aux_pending && !error_event_valid && !orphan_valid && !arm && !abort_event && !physical_done;
 wire owner_read_claim;
h1_7020_ch1_evidence_export_v0_1 exporter(
.clk(clk),
.rst_n(rst_n),
.record_valid(record_valid),
.record_metadata(record_metadata),
.evidence_epoch(bound_epoch),
.external_fault(common_fault),
.read_addr(owner_read_addr),
.read_claim(owner_read_claim),
.read_valid(read_valid),
.read_data(read_data),
.read_flags(read_flags),
.read_tick(read_tick),
.descriptor_valid(descriptor_valid),
.descriptor_ready(descriptor_ready),
.descriptor(descriptor),
.sample_valid(sample_valid),
.sample_ready(sample_ready),
.sample_index(sample_index),
.sample_data(sample_data),
.sample_flags(sample_flags),
.sample_tick(sample_tick),
.finish_valid(finish_valid),
.finish_ready(finish_ready),
.descriptor_crc(descriptor_crc),
.samples_crc(samples_crc),
.proof_submit(proof_valid && proof_ready),
.proof_epoch(proof_epoch),
.proof_record_id(proof_record_id),
.proof_identity(proof_identity),
.proof_count(proof_count),
.proof_descriptor_crc(proof_descriptor_crc),
.proof_samples_crc(proof_samples_crc),
.proof_ready(proof_ready),
.proof_accepted(proof_accepted),
.store_valid(store_valid),
.store_ready(1'b1),
.store_take(store_take),
.store_identity(store_identity),
.store_record_id(store_record_id),
.fault_latched(export_fault),
.first_fault(export_first_fault)
);
h1_7020_ch1_evidence_axi_v0_1 cache(
.clk(clk),
.rst_n(rst_n),
.external_fault(common_fault),
.descriptor_valid(descriptor_valid),
.descriptor_ready(descriptor_ready),
.descriptor_data(descriptor),
.sample_valid(sample_valid),
.sample_ready(sample_ready),
.sample_index(sample_index),
.sample_data(sample_data),
.sample_flags(sample_flags),
.sample_tick(sample_tick),
.finish_valid(finish_valid),
.finish_ready(finish_ready),
.finish_descriptor_crc(descriptor_crc),
.finish_samples_crc(samples_crc),
.proof_valid(proof_valid),
.proof_ready(proof_ready),
.proof_epoch(proof_epoch),
.proof_record_id(proof_record_id),
.proof_identity(proof_identity),
.proof_count(proof_count),
.proof_descriptor_crc(proof_descriptor_crc),
.proof_samples_crc(proof_samples_crc),
.retired_valid(retired_valid),
.retired_ready(retired_ready),
.retired_take(retired_take),
.retired_epoch(bound_epoch),
.retired_record_id(saved_record_id),
.retired_identity(saved_identity),
.s_axi_awaddr(main_awaddr),
.s_axi_awvalid(main_awvalid),
.s_axi_awready(main_awready),
.s_axi_wdata(main_wdata),
.s_axi_wstrb(main_wstrb),
.s_axi_wvalid(main_wvalid),
.s_axi_wready(main_wready),
.s_axi_bresp(main_bresp),
.s_axi_bvalid(main_bvalid),
.s_axi_bready(main_bready),
.s_axi_araddr(main_araddr),
.s_axi_arvalid(main_arvalid),
.s_axi_arready(main_arready),
.s_axi_rdata(main_rdata),
.s_axi_rresp(main_rresp),
.s_axi_rvalid(main_rvalid),
.s_axi_rready(main_rready),
.fault_latched(cache_fault),
.first_fault(cache_first_fault)
);
h1_7020_ch1_aux_journal_axi_v0_1 #(.DEPTH(JOURNAL_DEPTH)) journal(
.clk(clk),
.rst_n(rst_n),
.event_epoch(evidence_epoch),
.binding_present(record_active),
.binding_identity(saved_identity),
.binding_record_id(saved_record_id),
.error_valid(error_event_valid),
.error_has_byte(error_has_byte),
.error_data(error_data),
.error_flags(error_flags),
.error_tick(error_tick),
.error_ready(error_ready),
.orphan_valid(orphan_valid),
.orphan_has_byte(orphan_has_byte),
.orphan_data(orphan_data),
.orphan_flags(orphan_flags),
.orphan_tick(orphan_tick),
.orphan_ready(orphan_ready),
.fault_latched(journal_fault),
.blocking_fault(journal_block),
.pending_events(aux_pending),
.s_axi_awaddr(aux_awaddr),
.s_axi_awvalid(aux_awvalid),
.s_axi_awready(aux_awready),
.s_axi_wdata(aux_wdata),
.s_axi_wstrb(aux_wstrb),
.s_axi_wvalid(aux_wvalid),
.s_axi_wready(aux_wready),
.s_axi_bresp(aux_bresp),
.s_axi_bvalid(aux_bvalid),
.s_axi_bready(aux_bready),
.s_axi_araddr(aux_araddr),
.s_axi_arvalid(aux_arvalid),
.s_axi_arready(aux_arready),
.s_axi_rdata(aux_rdata),
.s_axi_rresp(aux_rresp),
.s_axi_rvalid(aux_rvalid),
.s_axi_rready(aux_rready)
);
h1_ch1_retire_guard_v0_1 guard(
.clk(clk),
.rst_n(rst_n),
.bind_start(accepted_arm),
.bind_identity(arm_identity),
.start_tick(start_tick),
.deadline_tick(deadline_tick),
.physical_done(physical_done),
.done_identity(done_identity),
.record_close(record_close),
.record_identity(saved_identity),
.record_id(saved_record_id),
.terminal_reason(terminal_reason),
.close_tick(record_close_tick),
.watermark_valid(1'b1),
.watermark_tick(tick),
.store_ack(store_take),
.store_identity(store_identity),
.store_record_id(store_record_id),
.release_request(release_request && !aux_pending && !error_event_valid && !orphan_valid),
.session_can_retire(session_can_retire),
.retired_ack(retired_take),
.external_fault(common_fault),
.retire_fire(guard_retire_fire),
.retire_ready(core_retire_ready),
.retire_session(),
.retire_seq(),
.active(),
.done_seen(),
.closed_seen(),
.stored_seen(),
.handoff_pending(guard_pending),
.saved_identity(),
.saved_record_id(),
.saved_reason(),
.saved_start(),
.saved_deadline(),
.saved_close(),
.event_watermark(),
.fault_latched(guard_fault),
.first_error(),
.retire_count(retire_count)
);
endmodule
