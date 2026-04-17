"""Data coordinator for the Sygnal Chatterbox integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SygnalApi
from .const import (
    DOMAIN,
    NUM_ZONES,
    SCAN_INTERVAL_SECONDS,
    resolve_bit_offset,
    scale_actual_temp,
    scale_percent,
    scale_setpoint_raw_to_eng,
)

_LOGGER = logging.getLogger(__name__)

HVAC_MODE_LABELS = ["V", "C", "H", "A"]  # Vent, Cool, Heat, Auto


@dataclass
class ZoneData:
    """Parsed data for a single zone."""

    index: int
    name: str = ""
    is_valid: bool = False
    is_on: bool = False
    mode: str = "F"  # "F" = Flow, "T" = Temp
    set_temp: float = 22.0
    actual_temp: float | None = None
    actual_pos: float = 0.0
    set_vav: float = 0.0
    is_cooling: bool = False
    is_heating: bool = False


@dataclass
class SygnalData:
    """Parsed data from the Chatterbox device."""

    zones: list[ZoneData] = field(default_factory=list)
    hvac_mode: str = "A"  # V/C/H/A
    ac_set_temp: float = 22.0
    return_temp: float | None = None
    indoor_coil_temp: float | None = None
    outside_temp: float | None = None
    outside_temp_present: bool = False
    cool_call: float = 0.0
    heat_call: float = 0.0
    fan_speed: float = 0.0
    compressor_loading: float = 0.0
    unit_is_cooling: bool = False
    unit_is_heating: bool = False


class SygnalCoordinator(DataUpdateCoordinator[SygnalData]):
    """Coordinator that polls the Chatterbox device."""

    def __init__(self, hass: HomeAssistant, api: SygnalApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.zone_names: list[str] = [f"Zone {i + 1}" for i in range(NUM_ZONES)]

    async def async_fetch_zone_names(self) -> None:
        """Fetch zone names from the EE table (offsets 104-199)."""
        try:
            ee = await self.api.fetch_ee(start=104, length=96)
            for i in range(NUM_ZONES):
                name_bytes = ee[i * 8 : i * 8 + 8]
                name = ""
                for b in name_bytes:
                    if 0x20 <= b <= 0x7E:
                        name += chr(b)
                    else:
                        name = ""
                        break
                if name.strip():
                    self.zone_names[i] = name.strip()
        except Exception:
            _LOGGER.debug("Could not fetch zone names, using defaults")

    async def _async_update_data(self) -> SygnalData:
        """Fetch and parse the paray table."""
        try:
            paray = await self.api.fetch_paray()
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err

        if len(paray) < 137:
            raise UpdateFailed(f"Incomplete paray data: {len(paray)} bytes")

        data = SygnalData()

        # Global AC data
        data.ac_set_temp = scale_setpoint_raw_to_eng(paray[1])
        data.hvac_mode = HVAC_MODE_LABELS[paray[44] & 3]
        data.return_temp = scale_actual_temp(paray[133])
        data.indoor_coil_temp = scale_actual_temp(paray[130])
        data.outside_temp = scale_actual_temp(paray[90])
        data.outside_temp_present = bool(paray[120] & 128)
        data.cool_call = scale_percent(paray[104])
        data.heat_call = scale_percent(paray[105])
        data.fan_speed = scale_percent(paray[134])
        data.compressor_loading = scale_percent(paray[128])
        data.unit_is_cooling = bool(paray[126] & 1)
        data.unit_is_heating = bool(paray[126] & 2)

        # Per-zone data
        for i in range(NUM_ZONES):
            zone = ZoneData(index=i, name=self.zone_names[i])

            # znIsValid: offset 78+i, bit 1
            zone.is_valid = bool(paray[78 + i] & 1)

            # znOnOff: offset 29, bit (1<<i)
            off, mask = resolve_bit_offset(29, 1 << i)
            zone.is_on = bool(paray[off] & mask)

            # znMode: offset 74, bit (1<<i), 0=Flow, 1=Temp
            off, mask = resolve_bit_offset(74, 1 << i)
            zone.mode = "T" if (paray[off] & mask) else "F"

            # znSetTemp: offset 3+i
            zone.set_temp = scale_setpoint_raw_to_eng(paray[3 + i])

            # znActTemp: offset 91+i
            zone.actual_temp = scale_actual_temp(paray[91 + i])

            # znActPos: offset 108+i (0..255 -> 0..100%)
            zone.actual_pos = scale_percent(paray[108 + i])

            # znSetVav: offset 31+i, mask 0x7f (0..100%)
            raw_vav = paray[31 + i] & 0x7F
            zone.set_vav = round(raw_vav * 100.0 / 127.0, 1)

            # znIsCooling: offset 78+i, bit 4
            zone.is_cooling = bool(paray[78 + i] & 4)
            # znIsHeating: offset 78+i, bit 8 -> resolves to offset 79+i? No...
            # Actually bit 8 at offset 78+i: mask=8 fits in one byte
            zone.is_heating = bool(paray[78 + i] & 8)

            data.zones.append(zone)

        return data
