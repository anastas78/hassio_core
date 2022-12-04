"""The 4Heat integration sensor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
class FourHeatNumberDescription(FourHeatEntityDescription, NumberEntityDescription):
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
            FourHeatNumber,
            FourHeatNumberDescription,
        ),
        FourHeatNumber,
    )


class FourHeatNumber(FourHeatAttributeEntity, NumberEntity):
    """Representation of a 4Heat device sensor."""

    entity_description: FourHeatNumberDescription

    def __init__(
        self,
        coordinator: FourHeatCoordinator,
        device: FourHeatDevice,
        attribute: str,
        description: FourHeatNumberDescription,
    ) -> None:
        """Initialize sensor."""

        super().__init__(coordinator, device, attribute, description)

        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

        LOGGER.debug("Additing number: %s", attribute)

    @property
    def native_value(self) -> float | None:
        """Return value of sensor."""
        if not self.attribute_value:
            return None
        return float(self.attribute_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set value."""
        if not self.unique_id:
            raise RuntimeError(f"No unique ID set to {self.attribute}")
        await self.coordinator.device.async_set_state(
            self.unique_id.split("-")[-1], int(value)
        )
        self.async_write_ha_state()
