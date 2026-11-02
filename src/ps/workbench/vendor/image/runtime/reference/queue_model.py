"""v0.6.3 proposal: software model of the trusted eight-slot 7020 queue.

This is not RTL, a register driver, or a hardware verification result.
"""

FIELDS = ("run_id", "image_id", "trial_id", "item_index", "item_total",
          "attempt_id", "route_mode", "payload_len", "trusted_src_crc",
          "route_epoch", "rx_profile", "d", "s")
WIDTHS = (32, 8, 16, 16, 16, 8, 8, 16, 16, 32, 8, 8, 8)
IDENTITY = ("run_id", "image_id", "trial_id", "item_index", "attempt_id",
            "route_mode", "route_epoch")


class Gateway7020DeviceSimulator:
    """FILL -> ARMED -> BUSY -> DRAIN -> IDLE; slots release on keyed ACK."""

    def __init__(self):
        self.shadow = {}
        self.shadow_mask = set()
        self.slots = [None] * 8
        self.generations = [0] * 8
        self.slot_versions = [0] * 8
        self.order = []
        self.phase = "FILL"
        self.commit_seq = 0
        self.last_accepted_seq = 0
        self.pending_reject = False
        self.latest_reject_seq = None
        self.last_acknowledged_reject = None
        self.fault_status = None
        self.last_commit = None
        self.events = []
        self.aborting = False
        self.started_trials = set()
        self.crc_table = None
        self.crc_table_identity = None
        self.crc_written = set()

    def _latch_fault(self, reason, **identity):
        """A wrap fault is permanent for this session; retain its first evidence."""
        if self.fault_status is None:
            self.fault_status = reason
            self.events.append({"kind": "FAULT", "reason": reason, **identity})
        return self.fault_status

    def begin_crc_table(self, run_id, image_id, count):
        if (self.fault_status is not None or self.phase != "FILL" or self.order or
                not isinstance(count, int) or isinstance(count, bool) or
                not 1 <= count <= 64):
            return False
        self.crc_table_identity = (run_id, image_id)
        self.crc_table = [None] * count
        self.crc_written.clear()
        return True

    def write_crc_entry(self, index, value):
        if (self.fault_status is not None or self.phase != "FILL" or
                self.order or self.crc_table is None or
                not isinstance(index, int) or isinstance(index, bool) or
                not 0 <= index < len(self.crc_table) or
                not isinstance(value, int) or isinstance(value, bool) or
                not 0 <= value <= 0xFFFF):
            return False
        self.crc_table[index] = value
        self.crc_written.add(index)
        return True

    @property
    def crc_table_valid(self):
        return self.crc_table is not None and len(self.crc_written) == len(self.crc_table)

    def load_crc_table(self, run_id, image_id, crc_values):
        if self.fault_status is not None or self.phase != "FILL" or self.order:
            return False
        if (not isinstance(crc_values, (list, tuple)) or
                not 1 <= len(crc_values) <= 64 or
                any(not isinstance(v, int) or isinstance(v, bool) or
                    not 0 <= v <= 0xFFFF for v in crc_values)):
            return False
        if not self.begin_crc_table(run_id, image_id, len(crc_values)):
            return False
        for index, value in enumerate(crc_values):
            self.write_crc_entry(index, value)
        return True

    def read_crc_table(self):
        return self.crc_table_identity, None if self.crc_table is None else tuple(self.crc_table)

    def _change_slot(self, slot):
        """One atomic slot mutation; RTL must expose only stable even versions."""
        if self.slot_versions[slot] >= 0xFFFFFFFE:
            self._latch_fault("SLOT_SEQ_WRAP_REQUIRES_RESET",
                              slot=slot, generation=self.generations[slot])
            raise RuntimeError("SLOT_SEQ_WRAP_REQUIRES_RESET")
        self.slot_versions[slot] += 2

    def write_shadow(self, field, value):
        if self.fault_status is not None or self.phase != "FILL" or field not in FIELDS:
            return False
        width = WIDTHS[FIELDS.index(field)]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 1 << width:
            return False
        self.shadow[field] = value
        self.shadow_mask.add(field)
        return True

    def clear_shadow(self):
        if self.fault_status is not None or self.phase != "FILL":
            return False
        self.shadow.clear()
        self.shadow_mask.clear()
        return True

    def commit(self):
        """Return a receipt; a bus write completing is not acceptance."""
        if self.fault_status is not None:
            reason = self.fault_status
        elif self.commit_seq == 0xFFFFFFFF:
            reason = self._latch_fault("COMMIT_SEQ_WRAP_REQUIRES_RESET")
        else:
            self.commit_seq += 1
            reason = self._validate_commit()
        slot = None
        generation = None
        if reason == "ACCEPTED":
            slot = next(i for i, entry in enumerate(self.slots) if entry is None)
            generation = (self.generations[slot] + 1) & 0xFFFFFFFF
            if generation == 0:
                reason = self._latch_fault("GENERATION_WRAP_REQUIRES_RESET",
                                           slot=slot, generation=self.generations[slot])
            elif self.slot_versions[slot] >= 0xFFFFFFFE:
                reason = self._latch_fault("SLOT_SEQ_WRAP_REQUIRES_RESET",
                                           slot=slot, generation=self.generations[slot])
            else:
                self._change_slot(slot)
                self.generations[slot] = generation
                self.slots[slot] = {**self.shadow, "slot": slot,
                                    "generation": generation, "state": "QUEUED"}
                self.order.append(slot)
                self.clear_shadow()
                self.last_accepted_seq = self.commit_seq
        self.pending_reject = reason != "ACCEPTED"
        if self.pending_reject:
            self.latest_reject_seq = self.commit_seq
            self.events.append({"kind": "COMMIT_REJECTED", "seq": self.commit_seq,
                                "reason": reason})
        else:
            self.latest_reject_seq = None
            self.last_acknowledged_reject = None
        self.last_commit = {"seq": self.commit_seq, "status": reason,
                            "slot": slot if reason == "ACCEPTED" else None,
                            "generation": generation if reason == "ACCEPTED" else None}
        return dict(self.last_commit)

    def _validate_commit(self):
        if self.phase != "FILL":
            return "REJECT_PHASE"
        if self.shadow_mask != set(FIELDS):
            return "REJECT_INCOMPLETE"
        if len(self.order) == 8:
            return "REJECT_FULL"
        if not self.crc_table_valid:
            return "REJECT_CRC_TABLE_INCOMPLETE"
        e = self.shadow
        if not (1 <= e["item_total"] <= 64 and
                0 <= e["item_index"] < e["item_total"] and
                0 <= e["attempt_id"] <= 3 and
                e["route_mode"] in (0, 1) and
                1 <= e["payload_len"] <= 512 and
                e["rx_profile"] in (0, 1, 2)):
            return "REJECT_RANGE"
        if (self.crc_table_identity != (e["run_id"], e["image_id"]) or
                self.crc_table is None or len(self.crc_table) != e["item_total"] or
                self.crc_table[e["item_index"]] != e["trusted_src_crc"]):
            return "REJECT_CRC_TABLE_MISMATCH"
        if any(self.slots[i]["trial_id"] == e["trial_id"] and
               self.slots[i]["run_id"] == e["run_id"] for i in self.order):
            return "REJECT_DUPLICATE_TRIAL"
        if (e["run_id"], e["trial_id"]) in self.started_trials:
            return "REJECT_DUPLICATE_TRIAL"
        if self.order:
            first = self.slots[self.order[0]]
            if any(e[k] != first[k] for k in ("run_id", "image_id", "route_mode", "route_epoch")):
                return "REJECT_BATCH_MISMATCH"
        return "ACCEPTED"

    def read_slot(self, slot):
        entry = self.slots[slot]
        return None if entry is None else dict(entry)

    def read_consistent_slot(self, slot, interleave=None):
        before = self.slot_versions[slot]
        entry = self.read_slot(slot)
        if interleave is not None:
            interleave()
        after = self.slot_versions[slot]
        return entry if before == after and before % 2 == 0 else None

    def read_slot_version(self, slot):
        return self.slot_versions[slot]

    def acknowledge_reject(self, expected_count, expected_last_accepted_seq,
                           expected_rejected_commit_seq):
        """Bind host attestation to the exact latest rejected COMMIT."""
        receipt = (expected_count, expected_last_accepted_seq,
                   expected_rejected_commit_seq)
        if (self.phase != "FILL" or self.fault_status is not None or
                not self.pending_reject):
            return (not self.pending_reject and
                    receipt == self.last_acknowledged_reject and
                    self.fault_status is None)
        if (not self.order or
                expected_count != len(self.order) or
                expected_last_accepted_seq != self.last_accepted_seq or
                expected_rejected_commit_seq != self.latest_reject_seq):
            return False
        self.pending_reject = False
        self.last_acknowledged_reject = receipt
        self.events.append({"kind": "REJECT_ACKED", "count": expected_count,
                            "last_accepted_seq": self.last_accepted_seq,
                            "rejected_commit_seq": expected_rejected_commit_seq})
        return True

    def arm(self, expected_count, expected_last_seq):
        if (self.phase != "FILL" or not self.order or
                self.fault_status is not None or
                self.pending_reject or expected_count != len(self.order) or
                expected_last_seq != self.last_accepted_seq or
                not self.crc_table_valid):
            return False
        self.phase = "ARMED"
        return True

    def start_next(self):
        if self.phase not in ("ARMED", "BUSY") or self.aborting or self.fault_status:
            return None
        if any(self.slots[i]["state"] == "STARTED" for i in self.order):
            return None
        for slot in self.order:
            entry = self.slots[slot]
            if entry["state"] == "QUEUED":
                self._change_slot(slot)
                entry["state"] = "STARTED"
                self.started_trials.add((entry["run_id"], entry["trial_id"]))
                self.phase = "BUSY"
                return dict(entry)
        self.phase = "DRAIN"
        return None

    def finish(self, slot, generation, result, evidence_ref):
        if self.fault_status:
            return False
        entry = self.read_slot(slot)
        if (entry is None or entry["generation"] != generation or
                entry["state"] != "STARTED" or not result or not evidence_ref):
            return False
        self._change_slot(slot)
        self.slots[slot]["state"] = "TERMINAL"
        self.slots[slot]["result"] = result
        self.slots[slot]["evidence_ref"] = evidence_ref
        self.events.append({"slot": slot, "generation": generation,
                            "identity": {k: entry[k] for k in IDENTITY},
                            "result": result, "evidence_ref": evidence_ref})
        if not any(self.slots[i]["state"] in ("QUEUED", "STARTED") for i in self.order):
            self.phase = "DRAIN"
        return True

    def abort(self):
        if self.phase not in ("ARMED", "BUSY", "DRAIN"):
            return False
        if any(self.slot_versions[slot] >= 0xFFFFFFFE
               for slot in self.order if self.slots[slot]["state"] == "QUEUED"):
            self._latch_fault("SLOT_SEQ_WRAP_REQUIRES_RESET")
            raise RuntimeError("SLOT_SEQ_WRAP_REQUIRES_RESET")
        self.aborting = True
        for slot in self.order:
            entry = self.slots[slot]
            if entry["state"] == "QUEUED":
                self._change_slot(slot)
                entry["state"] = "TERMINAL"
                entry["result"] = "ABORTED_UNSENT"
                entry["evidence_ref"] = "abort_event"
                self.events.append({"slot": slot, "generation": entry["generation"],
                                    "identity": {k: entry[k] for k in IDENTITY},
                                    "result": "ABORTED_UNSENT", "evidence_ref": "abort_event"})
        self.phase = "DRAIN"
        return True

    def ack_result(self, slot, generation, identity):
        if self.fault_status:
            return False
        entry = self.read_slot(slot)
        if (entry is None or entry["state"] != "TERMINAL" or
                entry["generation"] != generation or
                identity != {k: entry[k] for k in IDENTITY}):
            return False
        self._change_slot(slot)
        self.slots[slot] = None
        self.order.remove(slot)
        if not self.order and self.phase == "DRAIN":
            self.phase = "FILL"
            self.aborting = False
        return True
