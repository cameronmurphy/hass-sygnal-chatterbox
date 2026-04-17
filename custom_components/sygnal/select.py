"""Select platform for Sygnal Chatterbox system HVAC mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SygnalCoordinator

OPTIONS = ["Heat", "Cool", "Auto", "Vent"]

OPTION_TO_SYGNAL = {"Vent": 0, "Cool": 1, "Heat": 2, "Auto": 3}

SYGNAL_TO_OPTION = {"V": "Vent", "C": "Cool", "H": "Heat", "A": "Auto"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the system mode select."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]
    async_add_entities([SygnalModeSelect(coordinator, host)])


class SygnalModeSelect(CoordinatorEntity[SygnalCoordinator], SelectEntity):
    """Select entity for the system HVAC mode."""

    _attr_has_entity_name = True
    _attr_name = "AC Mode"
    _attr_options = OPTIONS
    _attr_icon = "mdi:air-conditioner"

    def __init__(self, coordinator: SygnalCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._optimistic_value: str | None = None
        self._attr_unique_id = f"{host}_ac_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._optimistic_value is not None:
            actual = SYGNAL_TO_OPTION.get(self.coordinator.data.hvac_mode)
            if actual == self._optimistic_value:
                self._optimistic_value = None
            else:
                return
        super()._handle_coordinator_update()

    @property
    def current_option(self) -> str | None:
        if self._optimistic_value is not None:
            return self._optimistic_value
        return SYGNAL_TO_OPTION.get(self.coordinator.data.hvac_mode, "Auto")

    async def async_select_option(self, option: str) -> None:
        value = OPTION_TO_SYGNAL.get(option)
        if value is not None:
            self._optimistic_value = option
            self.async_write_ha_state()
            await self.coordinator.api.write_paray(44, 3, value)
