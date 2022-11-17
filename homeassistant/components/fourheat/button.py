"""The 4Heat integration switch."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ._4heat import FourHeatDevice
from .const import LOGGER
from .coordinator import FourHeatCoordinator
from .entity import (
    FourHeatAttributeEntity,
    FourHeatEntityDescription,
    _setup_descriptions,
    async_setup_entry_attribute_entities,
)


@dataclass
class FourHeatButtonDescription(FourHeatEntityDescription, ButtonEntityDescription):
    """Class to describe a Button entity."""

    supported: Callable = lambda _: True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons for device."""

    return async_setup_entry_attribute_entities(
        hass,
        config_entry,
        async_add_entities,
        _setup_descriptions(
            hass, config_entry, FourHeatButton, FourHeatButtonDescription
        ),
        FourHeatButton,
    )


class FourHeatButton(FourHeatAttributeEntity, ButtonEntity):
    """Representation of a 4Heat device."""

    entity_description: FourHeatButtonDescription

    def __init__(
        self,
        coordinator: FourHeatCoordinator,
        device: FourHeatDevice,
        attribute: str,
        description: FourHeatButtonDescription,
    ) -> None:
        """Initialize the button."""

        super().__init__(coordinator, device, attribute, description)
        self.entity_description = description
        LOGGER.debug("Additing button: %s", attribute)

    async def async_press(self) -> None:
        """Triggers the Shelly button press service."""
        await self.entity_description.press_action(self.coordinator)
