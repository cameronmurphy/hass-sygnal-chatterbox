"""Number platform for Sygnal Chatterbox zone temperature setpoints."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, scale_setpoint_eng_to_raw
from .coordinator import SygnalCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up zone temperature setpoint numbers."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]

    async_add_entities(
        SygnalZoneSetpoint(coordinator, host, i)
        for i, zone in enumerate(coordinator.data.zones)
        if zone.is_valid
    )


class SygnalZoneSetpoint(CoordinatorEntity[SygnalCoordinator], NumberEntity):
    """Temperature setpoint for a single zone."""

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 15.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator: SygnalCoordinator, host: str, zone_index: int
    ) -> None:
        super().__init__(coordinator)
        self._zone_index = zone_index
        self._attr_unique_id = f"{host}_zone_{zone_index}_setpoint"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @property
    def name(self) -> str:
        return f"{self.coordinator.data.zones[self._zone_index].name} Setpoint"

    @property
    def native_value(self) -> float | None:
        zone = self.coordinator.data.zones[self._zone_index]
        if zone.mode == "T":
            return zone.set_temp
        return None

    async def async_set_native_value(self, value: float) -> None:
        raw = scale_setpoint_eng_to_raw(value)
        await self.coordinator.api.write_paray(3 + self._zone_index, 0xFF, raw)
        await self.coordinator.async_request_refresh()
