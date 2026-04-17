"""Constants for the Sygnal Chatterbox integration."""

DOMAIN = "sygnal"
CONF_HOST = "host"
ENDPOINT = "/Connect12/file.lvjson"
NUM_ZONES = 12
PARAY_SIZE = 137
EE_SIZE = 200
MAX_FETCH = 128
SCAN_INTERVAL_SECONDS = 30


def resolve_bit_offset(base_offset: int, mask: int) -> tuple[int, int]:
    """Resolve a multi-byte mask to (offset, byte_mask).

    Replicates the JS lvBits extender logic: if mask overflows a byte,
    shift the offset up and the mask down until it fits in the low 8 bits.
    """
    while mask and not (mask & 0xFF):
        base_offset += 1
        mask >>= 8
    return base_offset, mask & 0xFF


def scale_setpoint_raw_to_eng(raw: int) -> float:
    """Convert raw byte (unsigned, two's complement for negatives) to 15.0..30.0 C.

    The JS uses lvScaled with x1=-15, x2=15, y1=15.0, y2=30.0.
    Raw stored as unsigned byte: -15 = 241 (0xF1), +15 = 15.
    """
    signed = raw if raw < 128 else raw - 256
    return round(15.0 + (signed + 15) * 15.0 / 30.0, 1)


def scale_setpoint_eng_to_raw(eng: float) -> int:
    """Convert 15.0..30.0 C back to raw byte."""
    signed = round((eng - 15.0) * 30.0 / 15.0) - 15
    return signed & 0xFF


def scale_actual_temp(raw: int) -> float | None:
    """Convert raw 1..254 to 0.5..127.0 C. None if out of range."""
    if raw < 1 or raw > 254:
        return None
    return round(0.5 + (raw - 1) * 126.5 / 253.0, 1)


def scale_percent(raw: int) -> float:
    """Convert raw 0..255 to 0..100%."""
    return round(raw * 100.0 / 255.0, 1)


def scale_percent_100(raw: int) -> float:
    """Convert raw 0..100 to 0..100% (1:1 for 7-bit values)."""
    return round(raw * 100.0 / 127.0, 1) if raw <= 127 else 100.0
