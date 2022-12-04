"""4heat entity helper."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import LOGGER, SENSORS
from .coordinator import FourHeatCoordinator, get_entry_data
from .exceptions import FourHeatError
from .fourheat import FourHeatDevice
from .utils import get_device_entity_name, get_device_name


@dataclass
class FourHeatEntityDescription(EntityDescription):
    """Class to describe a 4heat entity."""

    value: Callable[[Any], Any] = lambda val: val
    available: Callable[[FourHeatDevice], bool] | None = None
    # Callable (settings, device), return true if entity should be removed
    removal_condition: Callable[[dict, FourHeatDevice], bool] | None = None
    extra_state_attributes: Callable[[FourHeatCoordinator], dict | None] | None = None


class FourHeatEntity(CoordinatorEntity[FourHeatCoordinator]):
    """Helper class to represent a 4heat entity."""

    def __init__(
        self, coordinator: FourHeatCoordinator, device: FourHeatDevice
    ) -> None:
        """Initialize 4heat entity."""
        super().__init__(coordinator)
        self.device = device
        self._attr_name = get_device_name(coordinator)
        self._attr_should_poll = True
        self._attr_device_info = DeviceInfo(
            identifiers={("serial", str(coordinator.serial))}
        )
        self._attr_unique_id = f"{coordinator.serial}-{self._attr_name}"

    @property
    def available(self) -> bool:
        """Available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """When entity is added to HASS."""
        self.async_on_remove(self.coordinator.async_add_listener(self._update_callback))

    async def async_update(self) -> None:
        """Update entity with latest info."""
        await self.coordinator.async_request_refresh()

    @callback
    def _update_callback(self) -> None:
        """Handle device update."""
        self.async_write_ha_state()

    async def set_state(self, **kwargs: Any) -> Any:
        """Set entity state."""
        LOGGER.debug("Setting state for entity %s, state: %s", self.name, kwargs)
        try:
            await self.device.async_set_state(**kwargs)
            self.async_write_ha_state()
            return True
        except FourHeatError as err:
            self.coordinator.last_update_success = False
            raise HomeAssistantError(
                f"Setting state for entity {self.name} failed, state: {kwargs}, error: {err.args}"
            ) from err


class FourHeatAttributeEntity(FourHeatEntity, entity.Entity):
    """Helper class to represent a 4heat device attribute."""

    entity_description: FourHeatEntityDescription

    def __init__(
        self,
        coordinator: FourHeatCoordinator,
        device: FourHeatDevice,
        attribute: str,
        description: FourHeatEntityDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, device)
        self.attribute = attribute
        self.entity_description = description

        self._attr_unique_id: str = f"{super().unique_id}-{self.attribute}"
        self._attr_name = get_device_entity_name(coordinator, description.name)

    @property
    def attribute_value(self) -> StateType:
        """Value of sensor."""
        if not self.device:
            return None
        if (value := getattr(self.device, self.attribute)) is None:
            return None

        return cast(StateType, self.entity_description.value(value))

    # @property
    # def available(self) -> bool:
    #     """Available."""
    #     available = super().available

    #     if not available or not self.entity_description.available:
    #         return available

    #     return self.entity_description.available(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.entity_description.extra_state_attributes is None:
            return None
        return self.entity_description.extra_state_attributes(self.coordinator)


@callback
def async_setup_entry_attribute_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    sensors_descriptions: Mapping[str, FourHeatEntityDescription],
    sensor_class: Callable,
) -> None:
    """Set up entities for attributes."""
    coordinator = get_entry_data(hass)[config_entry.entry_id].coordinator

    assert coordinator
    entities: list[FourHeatAttributeEntity] = []

    for attribute in coordinator.sensors:
        description = sensors_descriptions.get(attribute)

        if description is None:
            continue

        # Filter and remove entities that according to settings should not create an entity
        # if description.removal_condition and description.removal_condition(
        #     coordinator.device.settings, coordinator.device
        # ):
        #     domain = sensor_class.__module__.split(".")[-1]
        #     unique_id = f"{coordinator.serial}-{coordinator.device.description}-{domain}-{sensor}"
        #     async_remove_fourheat_entity(hass, domain, unique_id)
        # else:
        entities.append(
            sensor_class(coordinator, coordinator.device, attribute, description)
        )

    if not entities:
        return
    async_add_entities(entities)


@callback
def _setup_descriptions(
    sensor_class: Callable[..., FourHeatAttributeEntity],
    description_class: Callable[[str], FourHeatEntityDescription],
) -> dict[str, FourHeatEntityDescription]:
    """Build descriptions from .const SENSORS by platform."""

    descriptions: dict[str, FourHeatEntityDescription] = {}
    for sensor, description in SENSORS.items():
        for sensor_desc in description:
            if sensor_desc["platform"] == sensor_class.__module__.split(".")[-1]:
                sensor_description = description_class(sensor)
                for key, value in sensor_desc.items():
                    setattr(sensor_description, key, value)
                descriptions[sensor] = sensor_description
    return descriptions
