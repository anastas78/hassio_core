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
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._4heat import FourHeatDevice
from .const import LOGGER, SENSORS
from .coordinator import FourHeatCoordinator, get_entry_data
from .exceptions import DeviceConnectionError
from .utils import async_remove_fourheat_entity, get_device_entity_name, get_device_name


@dataclass
class FourHeatEntityDescription(EntityDescription):
    """Class to describe a 4heat entity."""

    value: Callable[[Any], Any] = lambda val: val
    available: Callable[[FourHeatDevice], bool] | None = None
    # Callable (settings, device), return true if entity should be removed
    removal_condition: Callable[[dict, FourHeatDevice], bool] | None = None
    extra_state_attributes: Callable[[FourHeatDevice], dict | None] | None = None


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

    async def async_update(self) -> None:
        """Update entity with latest info."""
        await self.coordinator.async_request_refresh()

    async def set_state(self, **kwargs: Any) -> Any:
        """Set entity state."""
        LOGGER.debug("Setting state for entity %s, state: %s", self.name, kwargs)
        try:
            await self.device.set_state(**kwargs)
            self.async_write_ha_state()
            return True
        except DeviceConnectionError as err:
            self.coordinator.last_update_success = False
            raise HomeAssistantError(
                f"Setting state for entity {self.name} failed, state: {kwargs}, error: {err.args}"
            ) from err

    @callback
    def _update_callback(self) -> None:
        """Handle device update."""
        self.async_write_ha_state()


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

    @property
    def available(self) -> bool:
        """Available."""
        available = super().available

        if not available or not self.entity_description.available:
            return available

        return self.entity_description.available(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.entity_description.extra_state_attributes is None:
            return None
        if not self.device.sensors:
            return None
        return self.entity_description.extra_state_attributes(self.device)

    @callback
    def _update_callback(self) -> None:
        """Handle device update."""
        self.async_write_ha_state()


@callback
def async_setup_entry_attribute_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    sensors: Mapping[str, FourHeatEntityDescription],
    # sensors: Callable[[FourHeatCoordinator], dict[str, FourHeatDeviceAttributeEntity]],
    sensor_class: Callable,
    # description_class: Callable[[RegistryEntry], FourHeatEntityDescription],
) -> None:
    """Set up entities for attributes."""
    coordinator = get_entry_data(hass)[config_entry.entry_id].coordinator

    assert coordinator
    if coordinator.device.initialized:
        # Set up entities for device attributes.
        assert coordinator.device
        # 1sensors_descriptions = sensors(coordinator)
        # sensors_descriptions = sensors
        entities = []
        # 1for sensor in coordinator.device.sensors:
        for sensor in sensors:
            # We get the real description of the sensor
            description = sensors[sensor]

            if description is None:
                continue

            # Filter out non-existing sensors and sensors without a value
            if getattr(coordinator.device, sensor, None) in (-1, None):
                continue

            # Filter and remove entities that according to settings should not create an entity
            if description.removal_condition and description.removal_condition(
                coordinator.device.settings, coordinator.device
            ):
                domain = sensor_class.__module__.split(".")[-1]
                unique_id = f"{coordinator.serial}-{coordinator.device.description}-{domain}-{sensor}"
                async_remove_fourheat_entity(hass, domain, unique_id)
            else:
                entities.append((sensor, description))
        if not entities:
            return

        async_add_entities(
            [
                sensor_class(coordinator, coordinator.device, sensor, description)
                for sensor, description in entities
            ]
        )
    # else:
    #     # Restore device attributes entities.
    #     entities = []

    #     ent_reg = entity_registry.async_get(hass)
    #     entries = entity_registry.async_entries_for_config_entry(
    #         ent_reg, config_entry.entry_id
    #     )

    #     domain = sensor_class.__module__.split(".")[-1]

    #     for entry in entries:
    #         if entry.domain != domain:
    #             continue

    #         attribute = entry.unique_id.split("-")[-1]
    #         # description = description_class(entry)
    #         description = sensors[attribute]

    #         entities.append(
    #             sensor_class(coordinator, coordinator.device, attribute, description)
    #         )

    #     if not entities:
    #         return

    #     async_add_entities(entities)


@callback
def _build_device_description(entry: RegistryEntry) -> FourHeatEntityDescription:
    """Build description when restoring device attribute entities."""
    return FourHeatEntityDescription(
        key="",
        name="",
        icon=entry.original_icon,
        unit_of_measurement=entry.unit_of_measurement,
        device_class=entry.original_device_class,
    )


@callback
def _setup_descriptions(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    sensor_class: Callable,
    description_class: Callable[[RegistryEntry], FourHeatEntityDescription],
) -> dict[str, FourHeatEntityDescription]:
    """Build descriptions from .const SENSORS by platform."""
    coordinator = get_entry_data(hass)[config_entry.entry_id].coordinator
    assert coordinator
    descriptions = {}
    if not coordinator.platforms:
        # restore from config entry
        for sensor, description in SENSORS.items():
            sensor_description = description_class(sensor)
            for sensor_desc in description:
                if sensor_desc["platform"] == sensor_class.__module__.split(".")[-1]:
                    for key, value in sensor_desc.items():
                        setattr(sensor_description, key, value)
                    descriptions[sensor] = sensor_description
        return descriptions

    # Set up descriptions for device attributes.
    for sensor in coordinator.platforms[sensor_class.__module__.split(".")[-1]]:
        sensor_id = list(sensor.keys())[0]
        sensor_conf = list(sensor.values())[0]
        sensor_description = description_class(sensor_id)
        for key, value in sensor_conf.items():
            setattr(sensor_description, key, value)
        descriptions[sensor_id] = sensor_description
    return descriptions
