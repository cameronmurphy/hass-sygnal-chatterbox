"""Climate platform for the Sygnal Chatterbox integration."""

from __future__ import annotations

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, resolve_bit_offset, scale_setpoint_eng_to_raw
from .coordinator import SygnalCoordinator, SygnalData

_LOGGER = logging.getLogger(__name__)

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

    entities: list[ClimateEntity] = [SygnalSystemClimate(coordinator, host)]

    for i, zone in enumerate(coordinator.data.zones):
        if zone.is_valid:
            entities.append(SygnalZoneClimate(coordinator, host, i))

    async_add_entities(entities)


class SygnalSystemClimate(CoordinatorEntity[SygnalCoordinator], ClimateEntity):
    """Climate entity for the overall AC system."""

    _attr_has_entity_name = True
    _attr_name = "AC System"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 15.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _attr_hvac_modes = [
        HVACMode.FAN_ONLY,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.HEAT_COOL,
    ]

    def __init__(self, coordinator: SygnalCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._host = host
        self._attr_unique_id = f"{host}_system"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @property
    def hvac_mode(self) -> HVACMode:
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
        return self.coordinator.data.ac_set_temp

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        value = HA_HVAC_TO_SYGNAL.get(hvac_mode)
        if value is not None:
            await self.coordinator.api.write_paray(44, 3, value)
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            raw = scale_setpoint_eng_to_raw(temp)
            await self.coordinator.api.write_paray(1, 0xFF, raw)
            await self.coordinator.async_request_refresh()


class SygnalZoneClimate(CoordinatorEntity[SygnalCoordinator], ClimateEntity):
    """Climate entity for a single zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 15.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO]

    def __init__(
        self, coordinator: SygnalCoordinator, host: str, zone_index: int
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._zone_index = zone_index
        self._attr_unique_id = f"{host}_zone_{zone_index}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @property
    def _zone(self):
        return self.coordinator.data.zones[self._zone_index]

    @property
    def name(self) -> str:
        return self._zone.name

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.AUTO if self._zone.is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        zone = self._zone
        if not zone.is_on:
            return HVACAction.OFF
        if zone.is_cooling:
            return HVACAction.COOLING
        if zone.is_heating:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._zone.actual_temp

    @property
    def target_temperature(self) -> float | None:
        if self._zone.mode == "T":
            return self._zone.set_temp
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        value = mask if hvac_mode != HVACMode.OFF else 0
        await self.coordinator.api.write_paray(offset, mask, value)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            raw = scale_setpoint_eng_to_raw(temp)
            await self.coordinator.api.write_paray(3 + self._zone_index, 0xFF, raw)
            await self.coordinator.async_request_refresh()
