"""Switch platform for Sygnal Chatterbox zone on/off control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, resolve_bit_offset
from .coordinator import SygnalCoordinator


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
        """Clear optimistic state only when device confirms the value."""
        if self._optimistic_state is not None:
            actual = self.coordinator.data.zones[self._zone_index].is_on
            if actual == self._optimistic_state:
                self._optimistic_state = None
            else:
                return  # keep holding until device catches up
        super()._handle_coordinator_update()

    @property
    def name(self) -> str:
        return self.coordinator.data.zones[self._zone_index].name

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        return self.coordinator.data.zones[self._zone_index].is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        self._optimistic_state = True
        self.async_write_ha_state()
        await self.coordinator.api.write_paray(offset, mask, mask)

    async def async_turn_off(self, **kwargs: Any) -> None:
        offset, mask = resolve_bit_offset(29, 1 << self._zone_index)
        self._optimistic_state = False
        self.async_write_ha_state()
        await self.coordinator.api.write_paray(offset, mask, 0)
