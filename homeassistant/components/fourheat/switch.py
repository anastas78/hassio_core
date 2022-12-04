"""The 4Heat integration switch."""
from __future__ import annotations

# from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
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
class FourHeatSwitchDescription(FourHeatEntityDescription, SwitchEntityDescription):
    """Class to describe a device switch."""

    # description: Callable[[str, FourHeatEntityDescription]] | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch for the device."""

    return async_setup_entry_attribute_entities(
        hass,
        config_entry,
        async_add_entities,
        _setup_descriptions(
            FourHeatSwitch,
            FourHeatSwitchDescription,
        ),
        FourHeatSwitch,
    )


class FourHeatSwitch(FourHeatAttributeEntity, SwitchEntity):
    """Representation of a 4Heat switch."""

    entity_description: FourHeatSwitchDescription

    def __init__(
        self,
        coordinator: FourHeatCoordinator,
        device: FourHeatDevice,
        attribute: str,
        description: FourHeatSwitchDescription,
    ) -> None:
        """Initialize the switch."""

        super().__init__(coordinator, device, attribute, description)
        self.control_result: str | None = None
        # self._attr_device_class = description.device_class
        LOGGER.debug("Additing switch: %s", attribute)

    @property
    def is_on(self) -> bool:
        """If switch is on."""
        if self.control_result:
            return self.control_result == STATE_ON
        return self.device.status == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on 4heat."""
        # await self.set_state(command=SERVICE_TURN_ON)
        await self.device.async_send_command(SERVICE_TURN_ON)
        self.control_result = STATE_ON
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off 4heat."""
        # self.control_result = await self.set_state(command=SERVICE_TURN_OFF)
        await self.device.async_send_command(SERVICE_TURN_OFF)
        self.control_result = STATE_OFF
        self.async_write_ha_state()

    @callback
    def _update_callback(self) -> None:
        """When device updates, clear control result that overrides state."""
        self.control_result = None
        super()._update_callback()
