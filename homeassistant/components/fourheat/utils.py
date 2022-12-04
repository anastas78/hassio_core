"""4heat utilities helper."""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry

from .const import DOMAIN, LOGGER
from .coordinator import FourHeatCoordinator


def get_device_name(coordinator: FourHeatCoordinator) -> str:
    """Naming for device."""
    return coordinator.name


def get_device_entity_name(
    coordinator: FourHeatCoordinator,
    description: str | None = None,
) -> str:
    """Naming for device based switch and sensors."""
    device_entity_name = get_device_name(coordinator)

    if description:
        return f"{device_entity_name} {description}"

    return device_entity_name


@callback
def async_remove_fourheat_entity(
    hass: HomeAssistant, domain: str, unique_id: str
) -> None:
    """Remove a 4heat entity."""
    entity_reg = entity_registry.async_get(hass)
    entity_id = entity_reg.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id:
        LOGGER.debug("Removing entity: %s", entity_id)
        entity_reg.async_remove(entity_id)
