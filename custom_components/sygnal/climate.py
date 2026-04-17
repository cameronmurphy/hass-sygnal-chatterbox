"""Climate platform for the Sygnal Chatterbox integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, scale_setpoint_eng_to_raw
from .coordinator import SygnalCoordinator

_LOGGER = logging.getLogger(__name__)

WRITE_HOLD_SECONDS = 5

HA_HVAC_TO_SYGNAL = {
    HVACMode.FAN_ONLY: 0,   # Vent
    HVACMode.COOL: 1,
    HVACMode.HEAT: 2,
    HVACMode.HEAT_COOL: 3,  # Auto
}

SYGNAL_TO_HA_HVAC = {
    "V": HVACMode.FAN_ONLY,
    "C": HVACMode.COOL,
    "H": HVACMode.HEAT,
    "A": HVACMode.HEAT_COOL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]
    async_add_entities([SygnalSystemClimate(coordinator, host)])


class SygnalSystemClimate(CoordinatorEntity[SygnalCoordinator], ClimateEntity):
    """Climate entity for the overall AC system."""

    _attr_has_entity_name = True
    _attr_name = "AC System"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 15.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [
        HVACMode.FAN_ONLY,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.HEAT_COOL,
    ]

    def __init__(self, coordinator: SygnalCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._host = host
        self._optimistic_mode: HVACMode | None = None
        self._optimistic_temp: float | None = None
        self._attr_unique_id = f"{host}_system"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates while holding optimistic state."""
        if self._optimistic_mode is not None or self._optimistic_temp is not None:
            return
        super()._handle_coordinator_update()

    @property
    def hvac_mode(self) -> HVACMode:
        if self._optimistic_mode is not None:
            return self._optimistic_mode
        return SYGNAL_TO_HA_HVAC.get(
            self.coordinator.data.hvac_mode, HVACMode.HEAT_COOL
        )

    @property
    def hvac_action(self) -> HVACAction:
        data = self.coordinator.data
        if data.unit_is_cooling:
            return HVACAction.COOLING
        if data.unit_is_heating:
            return HVACAction.HEATING
        if data.hvac_mode == "V":
            return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.return_temp

    @property
    def target_temperature(self) -> float | None:
        if self._optimistic_temp is not None:
            return self._optimistic_temp
        return self.coordinator.data.ac_set_temp

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        value = HA_HVAC_TO_SYGNAL.get(hvac_mode)
        if value is not None:
            self._optimistic_mode = hvac_mode
            self.async_write_ha_state()
            await self.coordinator.api.write_paray(44, 3, value)
            await asyncio.sleep(WRITE_HOLD_SECONDS)
            self._optimistic_mode = None
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._optimistic_temp = temp
            self.async_write_ha_state()
            raw = scale_setpoint_eng_to_raw(temp)
            await self.coordinator.api.write_paray(1, 0xFF, raw)
            await asyncio.sleep(WRITE_HOLD_SECONDS)
            self._optimistic_temp = None
            await self.coordinator.async_request_refresh()
