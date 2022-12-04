"""The 4Heat integration sensor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import LOGGER
from .coordinator import FourHeatCoordinator
from .entity import (
    FourHeatAttributeEntity,
    FourHeatEntityDescription,
    _setup_descriptions,
    async_setup_entry_attribute_entities,
)
from .fourheat import FourHeatDevice


@dataclass
class FourHeatSensorDescription(FourHeatEntityDescription, SensorEntityDescription):
    """Class to describe a device sensor."""


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for device."""
    return async_setup_entry_attribute_entities(
        hass,
        config_entry,
        async_add_entities,
        _setup_descriptions(
            FourHeatSensor,
            FourHeatSensorDescription,
        ),
        FourHeatSensor,
    )


class FourHeatSensor(FourHeatAttributeEntity, SensorEntity):
    """Representation of a 4Heat device sensor."""

    entity_description: FourHeatSensorDescription

    def __init__(
        self,
        coordinator: FourHeatCoordinator,
        device: FourHeatDevice,
        attribute: str,
        description: FourHeatSensorDescription,
    ) -> None:
        """Initialize sensor."""

        super().__init__(coordinator, device, attribute, description)

        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

        LOGGER.debug("Additing sensor: %s", attribute)

    @property
    def native_value(self) -> StateType:
        """Return value of sensor."""
        return self.attribute_value
