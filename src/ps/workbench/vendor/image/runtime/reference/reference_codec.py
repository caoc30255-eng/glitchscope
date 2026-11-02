"""Image-stream v0.6.9 proposal: software reference codec, not hardware evidence."""
import struct
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, Set, List

SOF_CFG = 0x55CC
SOF_ACK = 0x55CD
SOF_CLN = 0x55EE
SOF_CAK = 0x55EF
SOF_REQ = 0x55AA
SOF_RSP = 0x55BB
PROTO_VER = 0x02
MAX_PAYLOAD_LEN = 512
MAX_RETRY_LIMIT = 3
MAX_ITEMS_CAP = 64

STATUS_OK = 0x00
STATUS_REQ_CRC_ERR = 0x01
STATUS_LEN_ERR = 0x02
STATUS_UART_ERR = 0x03
STATUS_HOST_TIMEOUT = 0xFE

MASK_UNSENT = -1            # P0 2 闭环：从未提交过的项
MASK_MISSING = 0            # 已提交但在规定时间内未收到的项 (HOST_TIMEOUT)
MASK_CORRUPTED = 1          # 收到损坏数据且位置可信 (M == L, CRC错)
MASK_POSITION_UNCERTAIN = 2 # 收到部分数据 (M < L)，项内真实像素位置不可信
MASK_SILENT_CORRUPTED = 3   # DUT 报 STATUS_OK 但数据内容与源端不符
MASK_RETRY_EXHAUSTED = 4    # 重试次数达到上限仍未恢复
MASK_OK = 5                 # 校验与内容完全通过
MASK_CAPTURE_INVALID = 6    # CH1 有原始证据，但捕获/窗口/边界无效


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value):
    """Make an immutable, JSON-safe snapshot; never retain mutable flight refs."""
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    return value

def crc16_ccitt_false(data: bytes, poly=0x1021, init=0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

class ImagePacketCodec:
    @staticmethod
    def encode_config(run_id: int, image_id: int, width: int, height: int, total_bytes: int,
                      item_total: int, chunk_size: int, sha256_bytes: bytes, item_crc_list: List[int]) -> bytes:
        if len(sha256_bytes) != 32:
            raise ValueError("sha256_bytes must be 32 bytes")
        if not (1 <= item_total <= MAX_ITEMS_CAP):
            raise ValueError(f"item_total {item_total} exceeds hardware cap {MAX_ITEMS_CAP}")
        if not (1 <= chunk_size <= MAX_PAYLOAD_LEN):
            raise ValueError(f"chunk_size {chunk_size} invalid")
        if total_bytes != width * height:
            raise ValueError(f"total_bytes {total_bytes} != width*height {width*height}")
        expected_items = (total_bytes + chunk_size - 1) // chunk_size
        if item_total != expected_items:
            raise ValueError(f"item_total {item_total} != expected {expected_items}")
        if len(item_crc_list) != item_total:
            raise ValueError("item_crc_list length must match item_total")

        hdr = struct.pack(">B I B B B H H I H H 32s",
                          PROTO_VER, run_id, image_id, 0x01, 0x00, width, height, total_bytes,
                          item_total, chunk_size, sha256_bytes)
        crc_bytes = bytearray()
        for c in item_crc_list:
            crc_bytes.extend(struct.pack(">H", c))

        data_to_crc = hdr + bytes(crc_bytes)
        frame_crc = crc16_ccitt_false(data_to_crc)
        return struct.pack(">H", SOF_CFG) + data_to_crc + struct.pack(">H", frame_crc)

    @staticmethod
    def decode_config(frame: bytes) -> Dict:
        if len(frame) < 58:
            return {"status": "INVALID_CFG_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_CFG:
            return {"status": "INVALID_SOF", "valid": False}

        ver, run_id, img_id, pix_fmt, ch_order, w, h, t_bytes, i_total, c_size, sha = struct.unpack(">B I B B B H H I H H 32s", frame[2:54])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        if pix_fmt != 0x01 or ch_order != 0x00:
            return {"status": "UNSUPPORTED_PIXEL_FORMAT", "valid": False}
        if not (1 <= i_total <= MAX_ITEMS_CAP) or not (1 <= c_size <= MAX_PAYLOAD_LEN):
            return {"status": "CONFIG_CAP_EXCEEDED", "valid": False}
        if t_bytes != w * h:
            return {"status": "CONFIG_CONSISTENCY_ERR", "valid": False}
        if i_total != (t_bytes + c_size - 1) // c_size:
            return {"status": "CONFIG_CONSISTENCY_ERR", "valid": False}

        expected_frame_len = 56 + 2 * i_total
        if len(frame) != expected_frame_len:
            return {"status": "CONFIG_LEN_MISMATCH", "valid": False}

        rx_crc, = struct.unpack(">H", frame[-2:])
        calc_crc = crc16_ccitt_false(frame[2:-2])
        if calc_crc != rx_crc:
            return {"status": "CRC_MISMATCH", "valid": False}

        crc_list = []
        for i in range(i_total):
            c_val, = struct.unpack(">H", frame[54 + i*2 : 56 + i*2])
            crc_list.append(c_val)

        return {
            "status": "OK", "valid": True, "version": ver, "run_id": run_id, "image_id": img_id,
            "pixel_format": pix_fmt, "channel_order": ch_order,
            "width": w, "height": h, "total_bytes": t_bytes, "item_total": i_total,
            "chunk_size": c_size, "sha256": sha, "item_crc_list": crc_list, "frame_crc": rx_crc
        }

    @staticmethod
    def encode_config_ack(run_id: int, image_id: int, status: int = 0x0000) -> bytes:
        data = struct.pack(">B I B H", PROTO_VER, run_id, image_id, status)
        crc = crc16_ccitt_false(data)
        return struct.pack(">H", SOF_ACK) + data + struct.pack(">H", crc)

    @staticmethod
    def decode_config_ack(frame: bytes) -> Dict:
        if len(frame) != 12:
            return {"status": "INVALID_ACK_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_ACK:
            return {"status": "INVALID_SOF", "valid": False}
        ver, run_id, img_id, status = struct.unpack(">B I B H", frame[2:10])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        rx_crc, = struct.unpack(">H", frame[10:12])
        if crc16_ccitt_false(frame[2:10]) != rx_crc:
            return {"status": "CRC_MISMATCH", "valid": False}
        return {"status": "OK", "valid": True, "version": ver, "run_id": run_id, "image_id": img_id, "ack_status": status}

    @staticmethod
    def encode_cleanup(run_id: int, image_id: int) -> bytes:
        data = struct.pack(">B I B H", PROTO_VER, run_id, image_id, 0x0001)
        crc = crc16_ccitt_false(data)
        return struct.pack(">H", SOF_CLN) + data + struct.pack(">H", crc)

    @staticmethod
    def decode_cleanup(frame: bytes) -> Dict:
        if len(frame) != 12:
            return {"status": "INVALID_CLEANUP_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_CLN:
            return {"status": "INVALID_SOF", "valid": False}
        ver, run_id, img_id, cmd = struct.unpack(">B I B H", frame[2:10])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        if cmd != 0x0001:
            return {"status": "INVALID_COMMAND", "valid": False}
        rx_crc, = struct.unpack(">H", frame[10:12])
        if crc16_ccitt_false(frame[2:10]) != rx_crc:
            return {"status": "CRC_MISMATCH", "valid": False}
        return {"status": "OK", "valid": True, "run_id": run_id, "image_id": img_id, "cmd": cmd}

    @staticmethod
    def encode_cleanup_ack(run_id: int, image_id: int, status: int = 0x0000) -> bytes:
        data = struct.pack(">B I B H", PROTO_VER, run_id, image_id, status)
        crc = crc16_ccitt_false(data)
        return struct.pack(">H", SOF_CAK) + data + struct.pack(">H", crc)

    @staticmethod
    def decode_cleanup_ack(frame: bytes) -> Dict:
        if len(frame) != 12:
            return {"status": "INVALID_CLEANUP_ACK_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_CAK:
            return {"status": "INVALID_SOF", "valid": False}
        ver, run_id, img_id, status = struct.unpack(">B I B H", frame[2:10])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        rx_crc, = struct.unpack(">H", frame[10:12])
        if crc16_ccitt_false(frame[2:10]) != rx_crc:
            return {"status": "CRC_MISMATCH", "valid": False}
        return {"status": "OK", "valid": True, "run_id": run_id, "image_id": img_id, "status": status}

    @staticmethod
    def encode_item(run_id: int, image_id: int, trial_id: int, item_index: int, item_total: int,
                    attempt_id: int, route_mode: int, payload: bytes) -> bytes:
        p_len = len(payload)
        if p_len == 0 or p_len > MAX_PAYLOAD_LEN:
            raise ValueError(f"Payload length {p_len} invalid")
        if not (1 <= item_total <= MAX_ITEMS_CAP) or not (0 <= item_index < item_total):
            raise ValueError(f"Invalid index {item_index} for total {item_total}")
        if route_mode not in (0, 1):
            raise ValueError(f"Invalid route_mode {route_mode}")
        if not (0 <= attempt_id <= MAX_RETRY_LIMIT):
            raise ValueError(f"Invalid attempt_id {attempt_id}")
        if not (0 <= trial_id <= 65535):
            raise ValueError(f"trial_id {trial_id} exceeds uint16 range (0..65535)")

        src_crc = crc16_ccitt_false(payload)
        hdr = struct.pack(">B I B H H H B B H H",
                          PROTO_VER, run_id, image_id, trial_id, item_index, item_total,
                          attempt_id, route_mode, src_crc, p_len)
        data_to_crc = hdr + payload
        frame_crc = crc16_ccitt_false(data_to_crc)
        return struct.pack(">H", SOF_REQ) + data_to_crc + struct.pack(">H", frame_crc)

    @staticmethod
    def encode_gateway_forward_item(run_id: int, image_id: int, trial_id: int, item_index: int, item_total: int,
                                    attempt_id: int, route_mode: int, trusted_src_crc: int, decoded_payload: bytes) -> bytes:
        p_len = len(decoded_payload)
        if p_len == 0 or p_len > MAX_PAYLOAD_LEN:
            raise ValueError(f"Payload length {p_len} invalid")
        if not (0 <= trial_id <= 65535):
            raise ValueError(f"trial_id {trial_id} exceeds uint16 range")
        if not (1 <= item_total <= MAX_ITEMS_CAP) or not (0 <= item_index < item_total):
            raise ValueError("Invalid item index or total")
        if not (0 <= attempt_id <= MAX_RETRY_LIMIT) or route_mode != 1:
            raise ValueError("Invalid Gateway attempt or route")
        if not (0 <= trusted_src_crc <= 0xFFFF):
            raise ValueError("Invalid trusted source CRC")
        hdr = struct.pack(">B I B H H H B B H H",
                          PROTO_VER, run_id, image_id, trial_id, item_index, item_total,
                          attempt_id, route_mode, trusted_src_crc, p_len)
        data_to_crc = hdr + decoded_payload
        frame_crc = crc16_ccitt_false(data_to_crc)
        return struct.pack(">H", SOF_REQ) + data_to_crc + struct.pack(">H", frame_crc)

    # v0.6: a bad outer CRC is forwarded only when the actual payload also
    # differs from the independent trusted source CRC.
    @staticmethod
    def gateway_forward_filter(raw_ch0_frame: bytes, expected_flight: Dict, trusted_bram_crc: int,
                               decoded_payload: bytes, uart_flags: int = 0, is_duplicate_event: bool = False,
                               hardware_overflow: bool = False, boundary_complete: bool = True,
                               decoded_source: Optional[str] = None, selected_source: Optional[str] = None,
                               event_route_epoch: Optional[int] = None,
                               trusted_route_epoch: Optional[int] = None) -> Tuple[bool, str, Optional[bytes]]:
        if decoded_source not in ("A", "B") or selected_source not in ("A", "B"):
            return False, "DROP_MISSING_RX_SOURCE", None
        if decoded_source != selected_source:
            return False, "DROP_WRONG_RX_SOURCE", None
        if (event_route_epoch is None or trusted_route_epoch is None or
                event_route_epoch != trusted_route_epoch):
            return False, "DROP_ROUTE_EPOCH_MISMATCH", None
        if hardware_overflow:
            return False, "DROP_HARDWARE_BUFFER_OVERFLOW", None
        if not boundary_complete:
            return False, "DROP_UNCLOSED_FRAME", None
        if uart_flags & ~0x0F:
            return False, "DROP_UNKNOWN_UART_FLAGS", None
        if uart_flags & 0x01:
            return False, "DROP_HARDWARE_PARITY_ERROR", None
        if uart_flags & 0x08:
            return False, "DROP_HARDWARE_ORE_OVERRUN", None
        if uart_flags & 0x02:
            return False, "DROP_HARDWARE_FRAMING_ERROR", None
        if uart_flags & 0x04:
            return False, "DROP_HARDWARE_NOISE_ERROR", None
        if is_duplicate_event:
            return False, "DROP_DUPLICATE_CH0_EVENT", None

        if len(raw_ch0_frame) < 22:
            return False, "DROP_FRAME_TOO_SHORT", None
        sof, = struct.unpack(">H", raw_ch0_frame[0:2])
        if sof != SOF_REQ:
            return False, "DROP_INVALID_SOF", None

        # 解码前 20 字节头部字段
        ver, run_id, img_id, trial_id, idx, total, attempt, route, rx_src_crc, p_len = struct.unpack(">B I B H H H B B H H", raw_ch0_frame[2:20])

        # 校验整帧物理长度必须与头部载荷长度严格一致
        if len(raw_ch0_frame) != 20 + p_len + 2:
            return False, "DROP_FRAME_LENGTH_MISMATCH", None

        required = ("run_id", "image_id", "trial_id", "item_index",
                    "item_total", "attempt_id", "route_mode", "payload_len")
        if not isinstance(expected_flight, dict) or any(
                key not in expected_flight for key in required):
            return False, "DROP_INCOMPLETE_TRUSTED_FLIGHT", None
        if any(not isinstance(expected_flight[key], int) or
               isinstance(expected_flight[key], bool) for key in required):
            return False, "DROP_INVALID_TRUSTED_FLIGHT", None
        if (not isinstance(trusted_bram_crc, int) or
            isinstance(trusted_bram_crc, bool) or
            not (0 <= trusted_bram_crc <= 0xFFFF)):
            return False, "DROP_INVALID_TRUSTED_CRC", None
        if (expected_flight["route_mode"] != 1 or
            not (1 <= expected_flight["item_total"] <= MAX_ITEMS_CAP) or
            not (0 <= expected_flight["item_index"] < expected_flight["item_total"]) or
            not (0 <= expected_flight["attempt_id"] <= MAX_RETRY_LIMIT) or
            not (1 <= expected_flight["payload_len"] <= MAX_PAYLOAD_LEN)):
            return False, "DROP_INVALID_TRUSTED_FLIGHT", None
        if not (1 <= total <= MAX_ITEMS_CAP and 0 <= idx < total and
                0 <= attempt <= MAX_RETRY_LIMIT and 1 <= p_len <= MAX_PAYLOAD_LEN):
            return False, "DROP_HEADER_RANGE", None

        # 完整可信头部 8 维核对 (P0 1 核心闭环)
        if ver != PROTO_VER:
            return False, "DROP_HEADER_VERSION_MISMATCH", None
        if run_id != expected_flight["run_id"]:
            return False, "DROP_HEADER_RUN_ID_MISMATCH", None
        if img_id != expected_flight["image_id"]:
            return False, "DROP_HEADER_IMAGE_ID_MISMATCH", None
        if trial_id != expected_flight["trial_id"]:
            return False, "DROP_HEADER_TRIAL_ID_MISMATCH", None
        if idx != expected_flight["item_index"]:
            return False, "DROP_HEADER_ITEM_INDEX_MISMATCH", None
        if total != expected_flight["item_total"]:
            return False, "DROP_HEADER_ITEM_TOTAL_MISMATCH", None
        if attempt != expected_flight["attempt_id"]:
            return False, "DROP_HEADER_ATTEMPT_ID_MISMATCH", None
        if route != expected_flight["route_mode"]:
            return False, "DROP_HEADER_ROUTE_MODE_MISMATCH", None
        if p_len != expected_flight["payload_len"]:
            return False, "DROP_HEADER_PAYLOAD_LEN_MISMATCH", None
        if rx_src_crc != trusted_bram_crc:
            return False, "DROP_HEADER_SOURCE_CRC_MISMATCH", None
        if len(decoded_payload) != p_len:
            return False, "DROP_DECODED_PAYLOAD_LEN_MISMATCH", None
        if decoded_payload != raw_ch0_frame[20:20 + p_len]:
            return False, "DROP_DECODED_PAYLOAD_PROVENANCE_MISMATCH", None

        received_frame_crc, = struct.unpack(">H", raw_ch0_frame[-2:])
        input_crc_ok = (crc16_ccitt_false(raw_ch0_frame[2:-2]) == received_frame_crc)
        payload_crc_ok = (crc16_ccitt_false(decoded_payload) == trusted_bram_crc)

        if not input_crc_ok and payload_crc_ok:
            return False, "DROP_FRAME_CRC_ONLY_OR_AMBIGUOUS", None
        if input_crc_ok and not payload_crc_ok:
            return False, "DROP_INCONSISTENT_SOURCE_CRC", None

        # 头部完全可信，重组转发帧：保留可信源 CRC，并计算外层新 FRAME_CRC
        fwd_frame = ImagePacketCodec.encode_gateway_forward_item(
            run_id, img_id, trial_id, idx, total, attempt, route,
            trusted_bram_crc, decoded_payload
        )
        reason = "FORWARD_CLEAN" if input_crc_ok else "FORWARD_ACTUAL_BAD_PAYLOAD"
        return True, reason, fwd_frame

    @staticmethod
    def decode_item(frame: bytes) -> Dict:
        if len(frame) < 22:
            return {"status": "INVALID_FRAME_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_REQ:
            return {"status": "INVALID_SOF", "valid": False}

        ver, run_id, img_id, trial_id, idx, total, attempt, route, src_crc, p_len = struct.unpack(">B I B H H H B B H H", frame[2:20])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        if not (1 <= total <= MAX_ITEMS_CAP) or idx >= total:
            return {"status": "INVALID_INDEX_OR_TOTAL", "valid": False}
        if attempt > MAX_RETRY_LIMIT:
            return {"status": "INVALID_ATTEMPT_ID", "valid": False}
        if route not in (0, 1):
            return {"status": "INVALID_ROUTE_MODE", "valid": False}
        if p_len > MAX_PAYLOAD_LEN or p_len == 0 or len(frame) != 20 + p_len + 2:
            return {"status": "FRAME_LEN_MISMATCH", "valid": False}

        payload = frame[20:20+p_len]
        rx_crc, = struct.unpack(">H", frame[20+p_len:22+p_len])
        calc_crc = crc16_ccitt_false(frame[2:20+p_len])
        frame_crc_ok = (calc_crc == rx_crc)

        calc_src_crc = crc16_ccitt_false(payload)
        source_payload_crc_ok = (calc_src_crc == src_crc)

        overall_valid = frame_crc_ok and source_payload_crc_ok
        status_str = "OK" if overall_valid else ("CRC_MISMATCH" if not frame_crc_ok else "SOURCE_PAYLOAD_CRC_MISMATCH")

        return {
            "status": status_str, "valid": overall_valid,
            "frame_crc_ok": frame_crc_ok, "source_payload_crc_ok": source_payload_crc_ok,
            "version": ver, "run_id": run_id, "image_id": img_id,
            "trial_id": trial_id, "item_index": idx, "item_total": total,
            "attempt_id": attempt, "route_mode": route, "src_crc": src_crc,
            "payload_len": p_len, "payload": payload, "frame_crc": rx_crc
        }

    @staticmethod
    def encode_report(run_id: int, image_id: int, trial_id: int, item_index: int,
                      attempt_id: int, route_mode: int, uart_flags: int, result_status: int,
                      recvd_data: bytes) -> bytes:
        m_len = len(recvd_data)
        if m_len > MAX_PAYLOAD_LEN:
            raise ValueError(f"recvd_data length {m_len} exceeds max {MAX_PAYLOAD_LEN}")
        if result_status not in (STATUS_OK, STATUS_REQ_CRC_ERR, STATUS_LEN_ERR, STATUS_UART_ERR):
            raise ValueError(f"Invalid result_status {result_status}")
        if not (0 <= uart_flags <= 0x0F):
            raise ValueError(f"Invalid uart_flags {uart_flags}")
        if route_mode not in (0, 1):
            raise ValueError(f"Invalid route_mode {route_mode}")
        if not (0 <= item_index < MAX_ITEMS_CAP and
                0 <= attempt_id <= MAX_RETRY_LIMIT):
            raise ValueError("Invalid report item index or attempt")

        hdr = struct.pack(">B I B H H B B B B H",
                          PROTO_VER, run_id, image_id, trial_id, item_index,
                          attempt_id, route_mode, uart_flags, result_status, m_len)
        data_to_crc = hdr + recvd_data
        crc = crc16_ccitt_false(data_to_crc)
        return struct.pack(">H", SOF_RSP) + data_to_crc + struct.pack(">H", crc)

    @staticmethod
    def decode_report(frame: bytes) -> Dict:
        if len(frame) < 20:
            return {"status": "INVALID_REPORT_LEN", "valid": False}
        sof, = struct.unpack(">H", frame[0:2])
        if sof != SOF_RSP:
            return {"status": "INVALID_SOF", "valid": False}

        ver, run_id, img_id, trial_id, idx, attempt, route, flags, r_status, m_len = struct.unpack(">B I B H H B B B B H", frame[2:18])
        if ver != PROTO_VER:
            return {"status": "UNSUPPORTED_VERSION", "valid": False}
        if m_len > MAX_PAYLOAD_LEN or len(frame) != 18 + m_len + 2:
            return {"status": "REPORT_LEN_MISMATCH", "valid": False}
        if r_status not in (STATUS_OK, STATUS_REQ_CRC_ERR, STATUS_LEN_ERR, STATUS_UART_ERR):
            return {"status": "INVALID_RESULT_STATUS", "valid": False}
        if flags > 0x0F or route not in (0, 1):
            return {"status": "INVALID_FLAGS_OR_ROUTE", "valid": False}
        if idx >= MAX_ITEMS_CAP or attempt > MAX_RETRY_LIMIT:
            return {"status": "INVALID_REPORT_IDENTITY_RANGE", "valid": False}

        recvd_data = frame[18:18 + m_len]
        rx_crc, = struct.unpack(">H", frame[18 + m_len:20 + m_len])
        calc_crc = crc16_ccitt_false(frame[2:18 + m_len])
        if calc_crc != rx_crc:
            return {"status": "REPORT_CRC_MISMATCH", "valid": False}

        return {
            "status": "OK", "valid": True, "version": ver, "run_id": run_id, "image_id": img_id,
            "trial_id": trial_id, "item_index": idx, "attempt_id": attempt, "route_mode": route,
            "uart_flags": flags, "result_status": r_status, "recvd_len": m_len, "recvd_data": recvd_data,
            "frame_crc": rx_crc
        }

# =========================================================================
# 硬件设备 Python 软件参考模型 (明确标注：用于逻辑仿真验证，非实板证据)
# =========================================================================
class AX7010DeviceSimulator:
    """AX7010 发送端 Python 软件参考模型：模拟 BRAM 映射表与配置处理"""
    def __init__(self):
        self.bram_crc_table: Dict[int, int] = {}
        self.config_applied = False
        self.applied_run_id = 0
        self.applied_image_id = 0

    def receive_config(self, cfg_frame: bytes) -> bytes:
        dec = ImagePacketCodec.decode_config(cfg_frame)
        if not dec["valid"]:
            return ImagePacketCodec.encode_config_ack(0, 0, status=0x0001)

        self.applied_run_id = dec["run_id"]
        self.applied_image_id = dec["image_id"]
        self.bram_crc_table = {idx: dec["item_crc_list"][idx] for idx in range(dec["item_total"])}
        self.config_applied = True
        return ImagePacketCodec.encode_config_ack(dec["run_id"], dec["image_id"], status=0x0000)

    def readback_bram_crc_list(self) -> List[int]:
        if not self.config_applied:
            return []
        return [self.bram_crc_table[i] for i in range(len(self.bram_crc_table))]

from queue_model import Gateway7020DeviceSimulator

class ImageStreamManager:
    """管理整图切块、In-flight 6 维事务核对、防伪造坏图重组与全证据链"""
    def __init__(self, run_id: int, image_id: int, raw_bytes: bytes, chunk_size: int = 256, route_mode: int = 0):
        if len(raw_bytes) == 0:
            raise ValueError("raw_bytes cannot be empty")
        if not (1 <= chunk_size <= MAX_PAYLOAD_LEN):
            raise ValueError("chunk_size outside 1..512")
        if route_mode not in (0, 1):
            raise ValueError("route_mode must be Direct or Gateway")
        if (len(raw_bytes) + chunk_size - 1) // chunk_size > MAX_ITEMS_CAP:
            raise ValueError("image exceeds 64-item reference limit")
        self.run_id = run_id
        self.image_id = image_id
        self.raw_bytes = raw_bytes
        self.total_bytes = len(raw_bytes)
        self.orig_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        self.chunk_size = chunk_size
        self.route_mode = route_mode
        self.chunks = [raw_bytes[i:i+chunk_size] for i in range(0, len(raw_bytes), chunk_size)]
        self.total_items = len(self.chunks)

        self.trusted_source_crcs = [crc16_ccitt_false(c) for c in self.chunks]
        self.flight_status: Dict[int, Dict] = {}
        self.raw_observed_chunks: Dict[int, bytes] = {}
        self.retry_observed_history: List[Dict] = []
        self.attempt_history: List[Dict] = []
        self.late_capture_events: List[Dict] = []
        self.audit_log: List[Dict] = []
        self.persisted_audit_archive: List[Dict] = []

        self.first_round_chunks: Dict[int, bytes] = {}
        self.first_round_mask: Dict[int, int] = {i: MASK_UNSENT for i in range(self.total_items)}
        self.recovered_chunks: Dict[int, bytes] = {}
        self.failed_indices: Set[int] = set()
        self.attempt_counts: Dict[int, int] = {i: 0 for i in range(self.total_items)}
        self.used_trial_ids: Set[int] = set()
        self.first_round_locked = False
        self.capture_handles = {}
        self._capture_sink_bound = {}

    def _audit(self, item_index: int, event: str, **kwargs):
        entry = {
            "run_id": self.run_id, "image_id": self.image_id,
            "item_index": item_index, "event": event, "utc": _utc_now()
        }
        entry.update(_json_safe(kwargs))
        self.audit_log.append(entry)
        self.persisted_audit_archive.append(entry)

    def bind_capture_attempt(self, item_index: int, *, route_epoch: int,
                             slot: int, generation: int,
                             window_start_tick: int,
                             attempt_deadline_tick: int,
                             idle_guard_ticks: int = 2,
                             capacity: int = 544):
        """Create the sole CH1 capture handle for this committed attempt."""
        flight = self.flight_status.get(item_index)
        if (flight is None or not flight["submitted"] or flight["done"] or
                flight.get("capture_binding") is not None):
            return None
        fields = (route_epoch, slot, generation, window_start_tick,
                  attempt_deadline_tick)
        if any(not isinstance(value, int) or isinstance(value, bool)
               for value in fields):
            return None
        if not (0 <= route_epoch <= 0xFFFFFFFF and 0 <= slot < 8 and
                1 <= generation <= 0xFFFFFFFF and
                0 <= window_start_tick < attempt_deadline_tick <= 0xFFFFFFFFFFFFFFFF):
            return None
        from ch1_capture import Capture

        identity = {"run_id": self.run_id, "image_id": self.image_id,
                    "trial_id": flight["trial_id"], "item_index": item_index,
                    "attempt_id": flight["attempt_id"],
                    "route_mode": flight["route_mode"]}
        capture = Capture(trusted_identity=identity, route_epoch=route_epoch,
                          slot=slot, generation=generation,
                          window_start_tick=window_start_tick,
                          attempt_deadline_tick=attempt_deadline_tick,
                          idle_guard_ticks=idle_guard_ticks, capacity=capacity)
        flight["capture_binding"] = {
            "route_epoch": route_epoch, "slot": slot, "generation": generation,
            "window_start_tick": window_start_tick,
            "attempt_deadline_tick": attempt_deadline_tick,
        }
        self.capture_handles[item_index] = capture
        self._audit(item_index, "CAPTURE_ATTEMPT_BOUND", trial_id=flight["trial_id"],
                    attempt_id=flight["attempt_id"], **flight["capture_binding"])
        return capture

    def _verified_capture(self, item_index: int, flight: Optional[Dict],
                          capture, parsed_report: Optional[Dict],
                          raw_report: Optional[bytes]) -> Tuple[Dict, bytes, str]:
        from ch1_capture import Capture

        if not isinstance(capture, Capture) or not capture.finalized:
            raise ValueError("received report requires a finalized CH1 capture")
        if (flight is None or flight.get("capture_binding") is None or
                self.capture_handles.get(item_index) is not capture):
            raise ValueError("CH1 capture was not pre-registered with this flight")
        identity = {"run_id": self.run_id, "image_id": self.image_id,
                    "trial_id": flight["trial_id"], "item_index": item_index,
                    "attempt_id": flight["attempt_id"],
                    "route_mode": flight["route_mode"]}
        if (capture.trusted_identity is None or
                dict(capture.trusted_identity) != identity or
                any(getattr(capture, key) != value
                    for key, value in flight["capture_binding"].items())):
            raise ValueError("CH1 capture identity, slot, epoch or window mismatch")
        raw = bytes(capture.raw)
        if raw_report is not None and bytes(raw_report) != raw:
            raise ValueError("raw_report is not the complete sealed CH1 capture")
        outcome = capture.classify_final()
        if outcome == "VALID_DUT_REPORT":
            decoded = ImagePacketCodec.decode_report(raw)
            if (not decoded["valid"] or capture.parsed_report is None or
                    dict(capture.parsed_report) != decoded or
                    (parsed_report is not None and parsed_report != decoded)):
                raise ValueError("parsed report differs from finalized CH1 bytes")
            return decoded, raw, outcome
        if parsed_report is not None:
            raise ValueError("invalid CH1 capture cannot be supplied as a valid report")
        return {"valid": False, "status": outcome}, raw, outcome

    def _verified_host_timeout(self, item_index: int, flight: Optional[Dict],
                               timeout_tick: Optional[int]):
        if (flight is None or flight.get("capture_binding") is None or
                not isinstance(timeout_tick, int) or isinstance(timeout_tick, bool) or
                not 0 <= timeout_tick <= 0xFFFFFFFFFFFFFFFF or
                timeout_tick <= flight["capture_binding"]["attempt_deadline_tick"]):
            raise ValueError("HOST_TIMEOUT requires a tick after the registered deadline")
        capture = self.capture_handles.get(item_index)
        if (capture is None or capture.raw or
                (capture.closed and capture.reason != "ATTEMPT_DEADLINE")):
            raise ValueError("received CH1 bytes or another terminal reason forbid HOST_TIMEOUT")
        if not capture.finalized:
            capture.retire_tick(timeout_tick)
        if capture.classify_final() != "INVALID_ATTEMPT_DEADLINE":
            raise ValueError("deadline was not finalized")

    def _record_attempt(self, item_index: int, event: str, flight: Optional[Dict],
                         raw_report: Optional[bytes], parsed_report: Optional[Dict],
                         received_at_utc: Optional[str] = None, capture=None):
        raw = bytes(raw_report) if raw_report is not None else None
        entry = {
            "utc": received_at_utc or _utc_now(),
            "run_id": self.run_id, "image_id": self.image_id,
            "item_index": item_index, "event": event,
            "trial_id": flight.get("trial_id") if flight else None,
            "attempt_id": flight.get("attempt_id") if flight else None,
            "route_mode": flight.get("route_mode") if flight else None,
            "raw_report_hex": raw.hex() if raw is not None else None,
            "raw_report_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "parsed_report": _json_safe(parsed_report),
            "capture_status": capture.classify_final() if capture is not None else None,
            "capture_reason": capture.reason if capture is not None else None,
            "capture_end_tick": capture.end_timestamp if capture is not None else None,
            "capture_slot": capture.slot if capture is not None else None,
            "capture_generation": capture.generation if capture is not None else None,
            "capture_route_epoch": capture.route_epoch if capture is not None else None,
            "capture_window_start_tick": capture.window_start_tick if capture is not None else None,
            "capture_deadline_tick": capture.attempt_deadline_tick if capture is not None else None,
            "capture_samples": [dict(event) for event in capture.samples] if capture is not None else None,
            "capture_errors": [dict(event) for event in capture.errors] if capture is not None else None,
            "capture_orphans": [dict(event) for event in capture.orphans] if capture is not None else None,
        }
        if (capture is not None and self.capture_handles.get(item_index) is capture
                and self._capture_sink_bound.get(item_index) is not capture):
            # The attempt entry is an immutable point-in-time snapshot. Any
            # orphan arriving after it was recorded needs its own evidence
            # stream, including if the manager later releases the handle.
            identity = {key: entry[key] for key in (
                "run_id", "image_id", "item_index", "trial_id", "attempt_id",
                "route_mode", "capture_slot", "capture_generation",
                "capture_route_epoch")}
            def on_late_orphan(sample, identity=identity):
                late = {**identity, "sample": dict(sample)}
                lengths = (len(self.late_capture_events), len(self.audit_log),
                           len(self.persisted_audit_archive))
                try:
                    self.late_capture_events.append(late)
                    self._audit(item_index, "LATE_CH1_ORPHAN",
                                **{key: value for key, value in late.items()
                                   if key not in ("run_id", "image_id", "item_index")})
                except Exception:
                    del self.late_capture_events[lengths[0]:]
                    del self.audit_log[lengths[1]:]
                    del self.persisted_audit_archive[lengths[2]:]
                    raise
            capture.set_post_record_orphan_sink(on_late_orphan)
            self._capture_sink_bound[item_index] = capture
        self.attempt_history.append(entry)
        return entry

    def archive_and_seal(self, output_dir: str) -> Dict[str, str]:
        """Create an exclusive immutable snapshot; never overwrite an old seal."""
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        seal = root / f"run_{self.run_id}_image_{self.image_id}_{stamp}_{uuid.uuid4().hex[:8]}"
        seal.mkdir(exist_ok=False)
        log_path = seal / "audit_log.jsonl"
        bin_path = seal / "raw_observed_chunks.bin"
        retry_path = seal / "retry_history.jsonl"
        attempt_path = seal / "attempt_history.jsonl"
        late_path = seal / "late_capture_events.jsonl"
        state_path = seal / "state_snapshot.json"
        manifest_path = seal / "integrity_manifest.sha256"

        with log_path.open("x", encoding="utf-8") as f:
            for entry in self.persisted_audit_archive:
                f.write(json.dumps(_json_safe(entry), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        with bin_path.open("xb") as f:
            for idx in sorted(self.raw_observed_chunks.keys()):
                data = self.raw_observed_chunks[idx]
                f.write(struct.pack(">H H", idx, len(data)) + data)
            f.flush()
            os.fsync(f.fileno())

        with retry_path.open("x", encoding="utf-8") as f:
            for r_entry in self.retry_observed_history:
                f.write(json.dumps(_json_safe(r_entry), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        with attempt_path.open("x", encoding="utf-8") as f:
            for entry in self.attempt_history:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        with late_path.open("x", encoding="utf-8") as f:
            for entry in self.late_capture_events:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        state = {
            "sealed_utc": _utc_now(), "run_id": self.run_id,
            "image_id": self.image_id, "route_mode": self.route_mode,
            "source_sha256": self.orig_sha256,
            "total_bytes": self.total_bytes, "total_items": self.total_items,
            "chunk_size": self.chunk_size,
            "first_round_locked": self.first_round_locked,
            "first_round_mask": self.first_round_mask,
            "failed_indices": sorted(self.failed_indices),
            "attempt_counts": self.attempt_counts,
            "used_trial_ids": sorted(self.used_trial_ids),
            "recovered_indices": sorted(self.recovered_chunks),
            "late_capture_event_count": len(self.late_capture_events),
        }
        with state_path.open("x", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        files = (log_path, bin_path, retry_path, attempt_path, late_path, state_path)
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        with manifest_path.open("x", encoding="utf-8") as f:
            for path in files:
                f.write(f"{hashes[path.name]}  {path.name}\n")
            f.flush()
            os.fsync(f.fileno())

        return {
            "seal_dir": str(seal), "log_path": str(log_path),
            "bin_path": str(bin_path), "retry_path": str(retry_path),
            "attempt_path": str(attempt_path), "late_path": str(late_path),
            "state_path": str(state_path),
            "manifest_path": str(manifest_path),
            "sha_log": hashes[log_path.name], "sha_bin": hashes[bin_path.name],
            "sha_retry": hashes[retry_path.name], "sha_attempt": hashes[attempt_path.name],
            "sha_late": hashes[late_path.name],
            "sha_state": hashes[state_path.name],
        }

    def cleanup(self):
        self.flight_status.clear()
        self.first_round_chunks.clear()
        self.first_round_mask = {i: MASK_UNSENT for i in range(self.total_items)}
        self.recovered_chunks.clear()
        self.failed_indices.clear()
        self.attempt_counts = {i: 0 for i in range(self.total_items)}
        self.first_round_locked = False
        self.capture_handles.clear()
        self._capture_sink_bound.clear()

    def get_config_packet(self, width: int = 128, height: int = 128) -> bytes:
        sha_bytes = bytes.fromhex(self.orig_sha256)
        return ImagePacketCodec.encode_config(
            self.run_id, self.image_id, width, height, self.total_bytes,
            self.total_items, self.chunk_size, sha_bytes, self.trusted_source_crcs
        )

    def submit_request(self, item_index: int, trial_id: int, attempt_id: int) -> bytes:
        if not (0 <= item_index < self.total_items):
            raise ValueError("item_index outside this image")
        if trial_id in self.used_trial_ids:
            raise ValueError(f"trial_id {trial_id} has already been used in this run")
        curr_flight = self.flight_status.get(item_index)

        if curr_flight and curr_flight["submitted"] and not curr_flight["done"]:
            raise RuntimeError(f"Item {item_index} already in-flight (trial={curr_flight['trial_id']}), re-submission forbidden")

        if not self.first_round_locked:
            if curr_flight and curr_flight["done"]:
                raise RuntimeError(f"Item {item_index} already completed in first round, re-submission forbidden")
            if attempt_id != 0:
                raise RuntimeError("Non-zero attempt_id forbidden before first round is locked")
        else:
            if item_index not in self.failed_indices:
                raise RuntimeError(f"Item {item_index} already recovered or not failed, retry forbidden")
            expected_attempt = self.attempt_counts[item_index] + 1
            if attempt_id != expected_attempt:
                raise RuntimeError(f"Invalid attempt_id {attempt_id}, expected strict sequential {expected_attempt}")

        if attempt_id > MAX_RETRY_LIMIT:
            self.first_round_mask[item_index] = MASK_RETRY_EXHAUSTED
            self._audit(item_index, "RETRY_EXHAUSTED", attempt_id=attempt_id)
            raise RuntimeError(f"Item {item_index} exceeded max retry limit {MAX_RETRY_LIMIT}")

        # 先编码，若参数非法（如 trial_id 越界等）抛异常时，不影响内部状态！
        encoded_pkt = ImagePacketCodec.encode_item(
            self.run_id, self.image_id, trial_id, item_index, self.total_items,
            attempt_id, self.route_mode, self.chunks[item_index]
        )

        self.capture_handles.pop(item_index, None)
        self.flight_status[item_index] = {
            "run_id": self.run_id,
            "image_id": self.image_id,
            "trial_id": trial_id,
            "attempt_id": attempt_id,
            "route_mode": self.route_mode,
            "submitted": True,
            "done": False,
            "capture_binding": None,
        }
        self.attempt_counts[item_index] = attempt_id
        self.used_trial_ids.add(trial_id)
        self._audit(item_index, "REQUEST_SUBMITTED", trial_id=trial_id,
                    attempt_id=attempt_id, route_mode=self.route_mode,
                    request_hex=encoded_pkt.hex(),
                    request_sha256=hashlib.sha256(encoded_pkt).hexdigest())

        return encoded_pkt

    def record_first_round_report(self, item_index: int, parsed_report: Optional[Dict] = None,
                                  raw_report: Optional[bytes] = None,
                                  received_at_utc: Optional[str] = None,
                                  timeout_confirmed: bool = False,
                                  capture=None,
                                  timeout_tick: Optional[int] = None) -> bool:
        flight = self.flight_status.get(item_index)
        if timeout_confirmed:
            if capture is not None or parsed_report is not None or raw_report is not None:
                raise ValueError("received report and HOST_TIMEOUT are mutually exclusive")
            self._verified_host_timeout(item_index, flight, timeout_tick)
            raw = None
            capture = self.capture_handles[item_index]
        else:
            if timeout_tick is not None:
                raise ValueError("timeout_tick is only for HOST_TIMEOUT")
            if capture is None:
                raise ValueError("received report requires a finalized CH1 capture")
            try:
                parsed_report, raw, _ = self._verified_capture(
                    item_index, flight, capture, parsed_report, raw_report)
            except ValueError as exc:
                if getattr(capture, "finalized", False):
                    self._record_attempt(item_index, "REJECT_CH1_CAPTURE", flight,
                                         bytes(capture.raw), None, received_at_utc,
                                         capture=capture)
                    self._audit(item_index, "REJECT_CH1_CAPTURE", reason=str(exc))
                    return False
                raise
        if self.first_round_locked:
            self._record_attempt(item_index, "LATE_FIRST_ROUND_REPORT", flight,
                                 raw, parsed_report, received_at_utc, capture=capture)
            self._audit(item_index, "REJECT_LATE_FIRST_ROUND_REPORT")
            return False

        expected_len = len(self.chunks[item_index])

        if flight is None or not flight["submitted"] or flight["done"]:
            self._record_attempt(item_index, "REJECT_UNSUBMITTED_OR_ALREADY_DONE",
                                 flight, raw, parsed_report, received_at_utc,
                                 capture=capture)
            self._audit(item_index, "REJECT_UNSUBMITTED_OR_ALREADY_DONE", report=parsed_report)
            return False

        self._record_attempt(item_index,
                             "FIRST_ROUND_HOST_TIMEOUT" if parsed_report is None else "FIRST_ROUND_RX",
                             flight, raw, parsed_report, received_at_utc,
                             capture=capture)

        if parsed_report is None:
            self.first_round_chunks[item_index] = bytes(expected_len)
            self.raw_observed_chunks[item_index] = b""
            self.first_round_mask[item_index] = MASK_MISSING
            self.failed_indices.add(item_index)
            self._audit(item_index, "EVENT_HOST_TIMEOUT", flight=flight,
                        timeout_tick=timeout_tick)
            flight["done"] = True
            return True

        if not parsed_report.get("valid", False):
            self.first_round_chunks[item_index] = bytes(expected_len)
            self.raw_observed_chunks[item_index] = b""
            self.first_round_mask[item_index] = MASK_CAPTURE_INVALID
            self.failed_indices.add(item_index)
            self._audit(item_index, "EVENT_INVALID_CH1_CAPTURE", report=parsed_report)
            flight["done"] = True
            return True

        if (parsed_report["run_id"] != self.run_id or
            parsed_report["image_id"] != self.image_id or
            parsed_report["item_index"] != item_index or
            parsed_report["trial_id"] != flight["trial_id"] or
            parsed_report["attempt_id"] != 0 or
            parsed_report["route_mode"] != self.route_mode):
            self._audit(item_index, "REJECT_MISMATCHED_OR_DUPLICATE_REPORT",
                        report=parsed_report, expected_flight=flight)
            return False

        recvd_data = parsed_report["recvd_data"]
        r_status = parsed_report["result_status"]
        uart_flags = parsed_report["uart_flags"]
        recvd_len = parsed_report["recvd_len"]

        self.raw_observed_chunks[item_index] = recvd_data

        if r_status == STATUS_OK and uart_flags == 0 and recvd_len == expected_len:
            if recvd_data == self.chunks[item_index]:
                self.first_round_chunks[item_index] = recvd_data
                self.first_round_mask[item_index] = MASK_OK
                self.recovered_chunks[item_index] = recvd_data
                self.failed_indices.discard(item_index)
            else:
                self.first_round_chunks[item_index] = recvd_data
                self.first_round_mask[item_index] = MASK_SILENT_CORRUPTED
                self.failed_indices.add(item_index)
        else:
            if recvd_len < expected_len:
                self.first_round_chunks[item_index] = bytes(expected_len)
                self.first_round_mask[item_index] = MASK_POSITION_UNCERTAIN
            else:
                self.first_round_chunks[item_index] = recvd_data[:expected_len]
                self.first_round_mask[item_index] = MASK_CORRUPTED
            self.failed_indices.add(item_index)

        flight["done"] = True
        return True

    # A pending item becomes HOST_TIMEOUT only after the caller explicitly
    # records that its own registered deadline expired.
    def lock_first_round(self, timed_out_ticks: Optional[Dict[int, int]] = None):
        pending = {idx for idx, fl in self.flight_status.items()
                   if fl["submitted"] and not fl["done"]}
        if pending != set(timed_out_ticks or ()):
            raise RuntimeError("pending first-round items need registered timeout ticks")
        for idx in pending:
            self._verified_host_timeout(idx, self.flight_status[idx],
                                        timed_out_ticks[idx])
        for idx in range(self.total_items):
            fl = self.flight_status.get(idx)
            if fl is None:
                # 从未提交过的项标为 UNSENT
                self.first_round_mask[idx] = MASK_UNSENT
                self.first_round_chunks[idx] = bytes(len(self.chunks[idx]))
                self._audit(idx, "EVENT_UNSENT_ON_LOCK")
            elif not fl["done"]:
                # Host confirmed this submitted item's registered deadline expired.
                self._record_attempt(idx, "FIRST_ROUND_HOST_TIMEOUT_ON_LOCK", fl,
                                     None, None,
                                     capture=self.capture_handles[idx])
                expected_len = len(self.chunks[idx])
                self.first_round_chunks[idx] = bytes(expected_len)
                self.raw_observed_chunks[idx] = b""
                self.first_round_mask[idx] = MASK_MISSING
                self.failed_indices.add(idx)
                self._audit(idx, "EVENT_HOST_TIMEOUT",
                            timeout_tick=timed_out_ticks[idx])
                fl["done"] = True
        self.first_round_locked = True

    # P0 2 闭环：完整记录重传轮次实际数据与状态证据
    def record_retry_report(self, item_index: int, parsed_report: Optional[Dict] = None,
                            raw_report: Optional[bytes] = None,
                            received_at_utc: Optional[str] = None,
                            timeout_confirmed: bool = False,
                            capture=None,
                            timeout_tick: Optional[int] = None) -> bool:
        flight = self.flight_status.get(item_index)
        if timeout_confirmed:
            if capture is not None or parsed_report is not None or raw_report is not None:
                raise ValueError("received report and RETRY_HOST_TIMEOUT are mutually exclusive")
            self._verified_host_timeout(item_index, flight, timeout_tick)
            raw = None
            capture = self.capture_handles[item_index]
        else:
            if timeout_tick is not None:
                raise ValueError("timeout_tick is only for RETRY_HOST_TIMEOUT")
            if capture is None:
                raise ValueError("retry report requires a finalized CH1 capture")
            try:
                parsed_report, raw, _ = self._verified_capture(
                    item_index, flight, capture, parsed_report, raw_report)
            except ValueError as exc:
                if getattr(capture, "finalized", False):
                    self._record_attempt(item_index, "REJECT_RETRY_CH1_CAPTURE", flight,
                                         bytes(capture.raw), None, received_at_utc,
                                         capture=capture)
                    self._audit(item_index, "REJECT_RETRY_CH1_CAPTURE", reason=str(exc))
                    return False
                raise
        if not self.first_round_locked:
            self._record_attempt(item_index, "RETRY_REJECT_BEFORE_LOCK", flight,
                                 raw, parsed_report, received_at_utc,
                                 capture=capture)
            return False
        if item_index not in self.failed_indices:
            self._record_attempt(item_index, "RETRY_REJECT_NOT_FAILED", flight,
                                 raw, parsed_report, received_at_utc,
                                 capture=capture)
            return False

        if flight is None or not flight["submitted"] or flight["done"]:
            self._record_attempt(item_index, "RETRY_REJECT_NO_ACTIVE_FLIGHT", flight,
                                 raw, parsed_report, received_at_utc,
                                 capture=capture)
            return False

        self._record_attempt(item_index,
                             "RETRY_HOST_TIMEOUT" if parsed_report is None else "RETRY_RX",
                             flight, raw, parsed_report, received_at_utc,
                             capture=capture)

        report_entry = {
            "item_index": item_index,
            "trial_id": flight["trial_id"],
            "attempt_id": flight["attempt_id"],
            "route_mode": flight["route_mode"],
            "parsed_report_valid": parsed_report.get("valid", False) if parsed_report else False,
            "capture_status": capture.classify_final() if capture is not None else None,
            "timeout_tick": timeout_tick,
            "result_status": parsed_report.get("result_status") if parsed_report else STATUS_HOST_TIMEOUT,
            "uart_flags": parsed_report.get("uart_flags") if parsed_report else 0,
            "recvd_data": parsed_report.get("recvd_data", b"") if parsed_report else b"",
            "raw_report": raw,
            "raw_report_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "received_at_utc": received_at_utc or _utc_now(),
        }
        self.retry_observed_history.append(report_entry)

        if parsed_report is None or not parsed_report.get("valid", False):
            flight["done"] = True
            if flight["attempt_id"] >= MAX_RETRY_LIMIT:
                self.first_round_mask[item_index] = MASK_RETRY_EXHAUSTED
                self._audit(item_index, "RETRY_EXHAUSTED", attempt_id=flight["attempt_id"])
            return False

        if (parsed_report["run_id"] != self.run_id or
            parsed_report["image_id"] != self.image_id or
            parsed_report["item_index"] != item_index or
            parsed_report["trial_id"] != flight["trial_id"] or
            parsed_report["attempt_id"] != flight["attempt_id"] or
            parsed_report["route_mode"] != self.route_mode):
            self._audit(item_index, "RETRY_REJECT_IDENTITY_MISMATCH",
                        report=parsed_report, expected=flight)
            return False

        expected_len = len(self.chunks[item_index])
        recvd_data = parsed_report["recvd_data"]

        if (parsed_report["result_status"] == STATUS_OK and
            parsed_report["uart_flags"] == 0 and
            len(recvd_data) == expected_len and
            recvd_data == self.chunks[item_index]):
            self.recovered_chunks[item_index] = recvd_data
            self.failed_indices.discard(item_index)
            flight["done"] = True
            return True
        else:
            flight["done"] = True
            if flight["attempt_id"] >= MAX_RETRY_LIMIT:
                self.first_round_mask[item_index] = MASK_RETRY_EXHAUSTED
                self._audit(item_index, "RETRY_EXHAUSTED", attempt_id=flight["attempt_id"])
            return False

    def build_first_bad_image(self) -> bytes:
        out = bytearray()
        for idx in range(self.total_items):
            expected_len = len(self.chunks[idx])
            data = self.first_round_chunks.get(idx, bytes(expected_len))
            out.extend(data[:expected_len])
        return bytes(out[:self.total_bytes])

    def build_recovered_image(self) -> Tuple[bool, Optional[bytes]]:
        if len(self.failed_indices) > 0 or len(self.recovered_chunks) != self.total_items:
            return False, None
        out = bytearray()
        for idx in range(self.total_items):
            out.extend(self.recovered_chunks[idx])
        img = bytes(out[:self.total_bytes])
        if hashlib.sha256(img).hexdigest() == self.orig_sha256:
            return True, img
        return False, None
