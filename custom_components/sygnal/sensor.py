"""Sensor platform for the Sygnal Chatterbox integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SygnalCoordinator, SygnalData


@dataclass(frozen=True, kw_only=True)
class SygnalSensorDescription(SensorEntityDescription):
    """Describe a Sygnal sensor."""

    value_fn: Callable[[SygnalData], float | None]


SENSOR_DESCRIPTIONS: tuple[SygnalSensorDescription, ...] = (
    SygnalSensorDescription(
        key="return_temp",
        name="Return Air Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.return_temp,
    ),
    SygnalSensorDescription(
        key="indoor_coil_temp",
        name="Indoor Coil Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.indoor_coil_temp,
    ),
    SygnalSensorDescription(
        key="outside_temp",
        name="Outside Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.outside_temp if d.outside_temp_present else None,
    ),
    SygnalSensorDescription(
        key="cool_call",
        name="Cooling Demand",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: d.cool_call,
    ),
    SygnalSensorDescription(
        key="heat_call",
        name="Heating Demand",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: d.heat_call,
    ),
    SygnalSensorDescription(
        key="fan_speed",
        name="Fan Speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: d.fan_speed,
    ),
    SygnalSensorDescription(
        key="compressor_loading",
        name="Compressor Loading",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: d.compressor_loading,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: SygnalCoordinator = hass.data[DOMAIN][entry.entry_id]
    host = entry.data["host"]

    async_add_entities(
        SygnalSensor(coordinator, host, desc) for desc in SENSOR_DESCRIPTIONS
    )


class SygnalSensor(CoordinatorEntity[SygnalCoordinator], SensorEntity):
    """Sensor entity for the Sygnal Chatterbox."""

    entity_description: SygnalSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SygnalCoordinator,
        host: str,
        description: SygnalSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{host}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name="Sygnal Chatterbox",
            manufacturer="Sygnal",
            model="Connect12",
        )

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)
