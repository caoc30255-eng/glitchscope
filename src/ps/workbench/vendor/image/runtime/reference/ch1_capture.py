"""v0.6.11 CH1 software reference model; not RTL or board evidence.

The trusted attempt/window is registered before receiving bytes. The exact
report length is derived only from the unverified on-wire header, then checked
against the complete frame CRC and trusted identity.
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Dict, Optional, Tuple

from reference_codec import ImagePacketCodec


REPORT_IDENTITY = ("run_id", "image_id", "trial_id", "item_index",
                   "attempt_id", "route_mode")
HEADER_LEN = 18
MAX_REPORT_LEN = 532
REASON_PRIORITY = {"EXACT_LENGTH": 0, "INTERBYTE_TIMEOUT": 1,
                   "EXTRA_BYTES": 2, "ATTEMPT_DEADLINE": 3,
                   "ABORTED": 4, "BUFFER_OVERFLOW": 5}


@dataclass
class Capture:
    capacity: int = 544
    max_report_len: int = MAX_REPORT_LEN
    idle_guard_ticks: int = 1
    trusted_identity: Optional[Dict[str, int]] = None
    route_epoch: Optional[int] = None
    slot: Optional[int] = None
    generation: Optional[int] = None
    window_start_tick: Optional[int] = None
    attempt_deadline_tick: Optional[int] = None
    raw: bytes = field(default=b"", init=False)
    samples: Tuple[dict, ...] = field(default_factory=tuple, init=False)
    orphans: Tuple[dict, ...] = field(default_factory=tuple, init=False)
    errors: Tuple[dict, ...] = field(default_factory=tuple, init=False)
    closed: bool = field(default=False, init=False)
    reason: Optional[str] = field(default=None, init=False)
    start_timestamp: Optional[int] = field(default=None, init=False)
    end_timestamp: Optional[int] = field(default=None, init=False)
    provisional_total: Optional[int] = field(default=None, init=False)
    header_issue: Optional[str] = field(default=None, init=False)
    parsed_report: Optional[dict] = field(default=None, init=False)
    terminal_result: Optional[str] = field(default=None, init=False)
    _binding_sealed: bool = field(default=False, init=False, repr=False)
    _observed_tick: Optional[int] = field(default=None, init=False, repr=False)
    _post_record_orphan_sink: Optional[Callable[[dict], None]] = field(
        default=None, init=False, repr=False)

    def __setattr__(self, name, value):
        if name == "_binding_sealed" and getattr(self, "_binding_sealed", False):
            raise AttributeError("binding seal cannot be cleared")
        locked = {"capacity", "max_report_len", "idle_guard_ticks",
                  "trusted_identity", "route_epoch", "slot", "generation",
                  "window_start_tick", "attempt_deadline_tick",
                  "raw", "samples", "orphans", "errors", "_observed_tick",
                  "_post_record_orphan_sink"}
        if getattr(self, "_binding_sealed", False) and name in locked:
            raise AttributeError(f"{name} was sealed before the first byte")
        terminal = {"closed", "reason", "end_timestamp", "raw",
                    "terminal_result", "parsed_report", "provisional_total",
                    "header_issue", "start_timestamp"}
        if getattr(self, "closed", False) and name in terminal:
            raise AttributeError(f"{name} is sealed after frame closure")
        object.__setattr__(self, name, value)

    def __post_init__(self):
        for name, value, lo in (("capacity", self.capacity, HEADER_LEN),
                                ("max_report_len", self.max_report_len, 20),
                                ("idle_guard_ticks", self.idle_guard_ticks, 1)):
            if not isinstance(value, int) or isinstance(value, bool) or value < lo:
                raise ValueError(f"{name} must be an integer >= {lo}")
        if self.max_report_len > MAX_REPORT_LEN:
            raise ValueError("max_report_len exceeds online protocol maximum")
        if self.trusted_identity is not None:
            if (set(self.trusted_identity) != set(REPORT_IDENTITY) or
                    any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                        for v in self.trusted_identity.values()) or
                    not isinstance(self.route_epoch, int) or isinstance(self.route_epoch, bool) or
                    not 0 <= self.route_epoch <= 0xFFFFFFFF or
                    not isinstance(self.slot, int) or isinstance(self.slot, bool) or
                    not 0 <= self.slot < 8 or
                    not isinstance(self.generation, int) or isinstance(self.generation, bool) or
                    not 1 <= self.generation <= 0xFFFFFFFF or
                    not isinstance(self.window_start_tick, int) or
                    isinstance(self.window_start_tick, bool) or
                    not isinstance(self.attempt_deadline_tick, int) or
                    isinstance(self.attempt_deadline_tick, bool) or
                    not 0 <= self.window_start_tick < self.attempt_deadline_tick <= 0xFFFFFFFFFFFFFFFF):
                raise ValueError("trusted attempt, route epoch, slot/generation and receive window must be pre-registered")
            self.trusted_identity = MappingProxyType(dict(self.trusted_identity))
        self._binding_sealed = True

    def _append_event(self, stream: str, event: dict):
        """Publish a detached, read-only event without exposing mutable backing state."""
        if stream == "orphans" and self._post_record_orphan_sink is not None:
            # Fail closed: a failed manager callback must not leave a Capture
            # orphan that the manager silently omitted from its evidence.
            self._post_record_orphan_sink(dict(event))
        object.__setattr__(self, stream,
                           getattr(self, stream) + (MappingProxyType(dict(event)),))

    def set_post_record_orphan_sink(self, sink: Callable[[dict], None]):
        """Bind a future-orphan observer exactly once; it cannot be replaced."""
        if not callable(sink):
            raise ValueError("orphan sink must be callable")
        if self._post_record_orphan_sink is not None:
            raise RuntimeError("orphan sink already bound")
        object.__setattr__(self, "_post_record_orphan_sink", sink)

    def _derive_untrusted_length(self):
        if self.raw[:2] != b"\x55\xBB":
            self.header_issue = "INVALID_SOF"
            return
        if self.raw[2] != 0x02:
            self.header_issue = "UNSUPPORTED_VERSION"
            return
        recvd_len = int.from_bytes(self.raw[16:18], "big")
        total = 20 + recvd_len
        if recvd_len > 512:
            self.header_issue = "RECVD_LEN_OUT_OF_RANGE"
        elif total > self.max_report_len or total > self.capacity:
            self.header_issue = "REPORT_EXCEEDS_BUFFER_BOUND"
        else:
            # This is a framing hint only. The header has not passed frame CRC.
            self.provisional_total = total

    def byte(self, value: int, timestamp: int, flags: int = 0):
        if (not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255 or
                not isinstance(flags, int) or isinstance(flags, bool) or not 0 <= flags <= 15 or
                not isinstance(timestamp, int) or isinstance(timestamp, bool) or
                not 0 <= timestamp <= 0xFFFFFFFFFFFFFFFF):
            raise ValueError("invalid byte, flags or 64-bit timestamp")
        if self._observed_tick is not None and timestamp < self._observed_tick:
            raise ValueError("events must arrive in nondecreasing tick order")
        object.__setattr__(self, "_observed_tick", timestamp)
        sample = {"data": value, "flags": flags, "timestamp": timestamp}
        if self.closed:
            if self.end_timestamp is not None and timestamp < self.end_timestamp:
                raise ValueError("orphan timestamp precedes frame close")
            if timestamp == self.end_timestamp and len(self.raw) >= self.capacity:
                self._append_event("errors", {"kind": "BUFFER_OVERFLOW", **sample})
                self.close("BUFFER_OVERFLOW", timestamp)
            elif (timestamp == self.end_timestamp and
                  (self.reason in ("EXACT_LENGTH", "EXTRA_BYTES") or
                   (self.reason == "INTERBYTE_TIMEOUT" and
                    self.provisional_total is not None and
                    len(self.raw) >= self.provisional_total)) and
                  (self.attempt_deadline_tick is None or
                   timestamp < self.attempt_deadline_tick)):
                # The closure tick is still provisional. A byte on that tick
                # belongs to this candidate, not the later orphan stream.
                object.__setattr__(self, "raw", self.raw + bytes((value,)))
                self._append_event("samples", sample)
                if flags:
                    self._append_event("errors", {"kind": "UART_FLAGS",
                                                  "offset": len(self.raw) - 1,
                                                  "timestamp": timestamp,
                                                  "flags": flags})
                self._append_event("errors", {"kind": "EXTRA_BYTES",
                                              "offset": len(self.raw) - 1,
                                              "timestamp": timestamp})
                self.close("EXTRA_BYTES", timestamp)
                return
            self._append_event("orphans", sample)
            self._append_event("errors", {"kind": "LATE_BYTE", **sample})
            return
        if self.window_start_tick is not None and timestamp < self.window_start_tick:
            self._append_event("orphans", sample)
            self._append_event("errors", {"kind": "BEFORE_WINDOW", **sample})
            return
        if self.attempt_deadline_tick is not None and timestamp >= self.attempt_deadline_tick:
            if timestamp == self.attempt_deadline_tick and len(self.raw) >= self.capacity:
                self._append_event("errors", {"kind": "BUFFER_OVERFLOW", **sample})
                self.close("BUFFER_OVERFLOW", timestamp)
                self._append_event("orphans", sample)
                return
            self.close("ATTEMPT_DEADLINE", timestamp)
            self._append_event("orphans", sample)
            self._append_event("errors", {"kind": "AT_OR_AFTER_DEADLINE", **sample})
            return
        if self.samples and timestamp < self.samples[-1]["timestamp"]:
            raise ValueError("timestamps must be monotonic within a frame")
        if len(self.raw) >= self.capacity:
            self._append_event("errors", {"kind": "BUFFER_OVERFLOW", **sample})
            self.close("BUFFER_OVERFLOW", timestamp)
            return
        if self.start_timestamp is None:
            self.start_timestamp = timestamp
        object.__setattr__(self, "raw", self.raw + bytes((value,)))
        self._append_event("samples", sample)
        if flags:
            self._append_event("errors", {"kind": "UART_FLAGS", "offset": len(self.raw) - 1,
                                          "timestamp": timestamp, "flags": flags})
        if len(self.raw) == HEADER_LEN:
            self._derive_untrusted_length()
        elif self.provisional_total is not None and len(self.raw) > self.provisional_total:
            self._append_event("errors", {"kind": "EXTRA_BYTES", "offset": len(self.raw) - 1,
                                          "timestamp": timestamp})
            # An observed extra byte is itself a terminal event. Do not wait
            # for a caller to pass EXTRA_BYTES as the timer close reason.
            self.close("EXTRA_BYTES", timestamp)

    def close(self, reason: str, timestamp: int):
        if reason not in REASON_PRIORITY:
            raise ValueError("invalid close reason")
        if (not isinstance(timestamp, int) or isinstance(timestamp, bool) or
                not 0 <= timestamp <= 0xFFFFFFFFFFFFFFFF or
                (not self.closed and self.samples and
                 timestamp < self.samples[-1]["timestamp"])):
            raise ValueError("invalid end timestamp")
        if self._observed_tick is not None and timestamp < self._observed_tick:
            raise ValueError("events must arrive in nondecreasing tick order")
        deadline = self.attempt_deadline_tick
        if reason == "ATTEMPT_DEADLINE" and deadline is not None and timestamp < deadline:
            raise ValueError("deadline event precedes registered tick")
        object.__setattr__(self, "_observed_tick", timestamp)
        if deadline is not None and timestamp > deadline and not self.closed:
            # A late caller cannot backdate ABORT/overflow to the deadline.
            reason, timestamp = "ATTEMPT_DEADLINE", deadline
        elif deadline is not None and timestamp == deadline and reason not in (
                "BUFFER_OVERFLOW", "ABORTED", "ATTEMPT_DEADLINE"):
            reason = "ATTEMPT_DEADLINE"
        if self.closed:
            # Sequential API calls at the same tick are still one logical tick.
            # A higher-priority event may promote the provisional outcome only
            # at that tick; later events cannot rewrite it.
            if (timestamp != self.end_timestamp or
                    REASON_PRIORITY[reason] <= REASON_PRIORITY[self.reason]):
                return False
            object.__setattr__(self, "reason", reason)
            object.__setattr__(self, "parsed_report", None)
            object.__setattr__(self, "terminal_result", self._classify_closed())
            return True
        if reason == "EXACT_LENGTH" and (
                self.trusted_identity is None or self.header_issue is not None or
                self.provisional_total is None or
                len(self.raw) != self.provisional_total or not self.samples or
                timestamp - self.samples[-1]["timestamp"] < self.idle_guard_ticks):
            raise ValueError("exact closure requires pre-registered attempt, full header-derived length and idle guard")
        self.reason = reason
        self.end_timestamp = timestamp
        self.terminal_result = self._classify_closed()
        self.closed = True
        return True

    def classify(self):
        """Return the current outcome; it may improve in priority on this tick."""
        if not self.closed:
            return "OPEN"
        return self.terminal_result

    @property
    def finalized(self):
        """True only after the closure tick has been retired."""
        return (self.closed and self._observed_tick is not None and
                self._observed_tick > self.end_timestamp)

    def classify_final(self):
        """The result safe for a consumer to accept as terminal."""
        if not self.closed:
            return "OPEN"
        return self.terminal_result if self.finalized else "PENDING_TICK"

    def retire_tick(self, timestamp: int):
        """Advance the event watermark without inventing a UART byte."""
        if (not isinstance(timestamp, int) or isinstance(timestamp, bool) or
                not 0 <= timestamp <= 0xFFFFFFFFFFFFFFFF or
                (self._observed_tick is not None and
                 timestamp < self._observed_tick)):
            raise ValueError("invalid or decreasing retirement tick")
        if (not self.closed and self.attempt_deadline_tick is not None and
                timestamp >= self.attempt_deadline_tick):
            self.close("ATTEMPT_DEADLINE", timestamp)
        object.__setattr__(self, "_observed_tick", timestamp)
        return self.finalized

    def _classify_closed(self):
        for reason, status in (("BUFFER_OVERFLOW", "INVALID_CAPTURE_OVERFLOW"),
                               ("ABORTED", "INVALID_ABORTED"),
                               ("ATTEMPT_DEADLINE", "INVALID_ATTEMPT_DEADLINE"),
                               ("EXTRA_BYTES", "INVALID_EXTRA_BYTES")):
            if self.reason == reason:
                return status
        if self.header_issue is not None:
            return "INVALID_HEADER_" + self.header_issue
        if self.reason == "INTERBYTE_TIMEOUT":
            return "INVALID_UNCLOSED_FRAME_TIMEOUT"
        if self.trusted_identity is None:
            return "UNASSOCIATED_RAW"
        if self.reason != "EXACT_LENGTH" or self.provisional_total is None:
            return "INVALID_UNCLOSED_FRAME"
        if any(e["kind"] in ("UART_FLAGS", "EXTRA_BYTES") for e in self.errors):
            return "INVALID_CH1_UART_OR_EXTRA_BYTES"
        report = ImagePacketCodec.decode_report(bytes(self.raw))
        if not report["valid"]:
            return "INVALID_" + report["status"]
        if any(report[k] != self.trusted_identity[k] for k in REPORT_IDENTITY):
            return "INVALID_REPORT_IDENTITY"
        self.parsed_report = MappingProxyType(dict(report))
        # STATUS can report a genuine DUT error; it is not a CH1 parse failure.
        return "VALID_DUT_REPORT"
