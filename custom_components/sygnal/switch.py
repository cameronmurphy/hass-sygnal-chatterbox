"""Switch platform for Sygnal Chatterbox zone on/off control."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, resolve_bit_offset
from .coordinator import SygnalCoordinator

WRITE_SETTLE_SECONDS = 3


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone switches."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]

    async_add_entities(
        SygnalZoneSwitch(coordinator, host, i)
        for i, zone in enumerate(coordinator.data.zones)
        if zone.is_valid
    )


class SygnalZoneSwitch(CoordinatorEntity[SygnalCoordinator], SwitchEntity):
    """On/off switch for a single zone."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SygnalCoordinator, host: str, zone_index: int
    ) -> None:
        super().__init__(coordinator)
        self._zone_index = zone_index
        self._optimistic_state: bool | None = None
        self._attr_unique_id = f"{host}_zone_{zone_index}_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Ignore coordinator updates while holding optimistic state."""
        if self._optimistic_state is not None:
            return
        super()._handle_coordinator_update()

    @property
    def name(self) -> str:
        return self.coordinator.data.zones[self._zone_index].name

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        return self.coordinator.data.zones[self._zone_index].is_on

    async def _async_write_and_hold(self, on: bool) -> None:
        """Write state, hold optimistic value, then refresh after delay."""
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        value = mask if on else 0
        self._optimistic_state = on
        self.async_write_ha_state()
        await self.coordinator.api.write_paray(offset, mask, value)
        await asyncio.sleep(WRITE_SETTLE_SECONDS)
        self._optimistic_state = None
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write_and_hold(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write_and_hold(False)
