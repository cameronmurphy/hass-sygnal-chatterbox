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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, resolve_bit_offset, scale_setpoint_eng_to_raw
from .coordinator import SygnalCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]

    async_add_entities(
        SygnalZoneClimate(coordinator, host, i)
        for i, zone in enumerate(coordinator.data.zones)
        if zone.is_valid
    )


class SygnalZoneClimate(CoordinatorEntity[SygnalCoordinator], ClimateEntity):
    """Climate entity for a single zone.

    The zone has two modes: Off and the current system mode (Heat/Cool/Vent/Auto).
    The active mode label updates dynamically to match the system.
    """

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

    def __init__(
        self, coordinator: SygnalCoordinator, host: str, zone_index: int
    ) -> None:
        super().__init__(coordinator)
        self._host = host
        self._zone_index = zone_index
        self._optimistic_on: bool | None = None
        self._optimistic_temp: float | None = None
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

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic_on is not None:
            if self._zone.is_on == self._optimistic_on:
                self._optimistic_on = None
            else:
                return
        if self._optimistic_temp is not None:
            if self._zone.set_temp == self._optimistic_temp:
                self._optimistic_temp = None
            else:
                return
        super()._handle_coordinator_update()

    @property
    def name(self) -> str:
        return self._zone.name

    @property
    def hvac_mode(self) -> HVACMode:
        is_on = self._optimistic_on if self._optimistic_on is not None else self._zone.is_on
        return HVACMode.HEAT_COOL if is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        is_on = self._optimistic_on if self._optimistic_on is not None else self._zone.is_on
        if not is_on:
            return HVACAction.OFF
        if self._zone.is_cooling:
            return HVACAction.COOLING
        if self._zone.is_heating:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._zone.actual_temp

    @property
    def target_temperature(self) -> float | None:
        if self._optimistic_temp is not None:
            return self._optimistic_temp
        if self._zone.mode == "T":
            return self._zone.set_temp
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_turn_on(self) -> None:
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        self._optimistic_on = True
        self.async_write_ha_state()
        await self.coordinator.api.write_paray(offset, mask, mask)

    async def async_turn_off(self) -> None:
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        self._optimistic_on = False
        self.async_write_ha_state()
        await self.coordinator.api.write_paray(offset, mask, 0)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._optimistic_temp = temp
            self.async_write_ha_state()
            raw = scale_setpoint_eng_to_raw(temp)
            await self.coordinator.api.write_paray(3 + self._zone_index, 0xFF, raw)
