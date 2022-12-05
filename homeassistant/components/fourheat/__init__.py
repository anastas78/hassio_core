"""The 4heat integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant, ServiceCall, callback, valid_entity_id
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType

from .const import DATA_CONFIG_ENTRY, DOMAIN, LOGGER
from .coordinator import FourHeatCoordinator, FourHeatEntryData, get_entry_data
from .exceptions import FourHeatError, NotInitialized
from .fourheat import FourHeatDevice


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the 4heat component."""
    hass.data[DOMAIN] = {DATA_CONFIG_ENTRY: {}}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 4heat from a config entry."""

    get_entry_data(hass)[entry.entry_id] = FourHeatEntryData()
    name = entry.title
    host = str(entry.data.get("host"))
    port = int(str(entry.data.get("port")))
    mode = bool(entry.data.get("mode"))

    LOGGER.debug("Setting up device %s", entry.title)
    # async init
    device = await FourHeatDevice.create(name, host, port, mode, False)
    # try:
    #     device = await FourHeatDevice.create(name, host, port, mode, False)
    # except FourHeatError as err:
    #     raise ConfigEntryNotReady(str(err)) from err
    fourheat_entry_data = get_entry_data(hass)[entry.entry_id]

    fourheat_entry_data.coordinator = FourHeatCoordinator(hass, entry, device)
    fourheat_entry_data.coordinator.async_setup()
    if not fourheat_entry_data.coordinator.platforms:
        # it is the first init of device
        try:
            await device.initialize()
            fourheat_entry_data.coordinator.sensors = device.sensors
            fourheat_entry_data.coordinator.platforms = (
                fourheat_entry_data.coordinator.build_platforms()
            )
        except FourHeatError as err:
            raise ConfigEntryNotReady(str(err)) from err
    await hass.config_entries.async_forward_entry_setups(
        entry, fourheat_entry_data.coordinator.platforms
    )

    @callback
    async def async_handle_set_value(call: ServiceCall) -> None:
        """Handle the service call to set a value."""
        entity_id = call.data.get("entity_id", "")
        value = call.data.get("value", 5)
        val = 1
        if isinstance(value, str):
            if value.isnumeric():
                val = int(value)
            elif valid_entity_id(value):
                entity_state = hass.states.get(value)
                if entity_state is not None:
                    val = int(float(entity_state.state))
        else:
            val = value

        if valid_entity_id(entity_id):
            ent_reg = entity_registry.async_get(hass)
            entry = ent_reg.async_get(entity_id)
            assert fourheat_entry_data.coordinator

            try:
                assert entry is not None
                await fourheat_entry_data.coordinator.device.async_set_state(
                    entry.unique_id.split("-")[-1], val
                )
                fourheat_entry_data.coordinator.async_update_listeners()
            except FourHeatError as error:
                LOGGER.exception("Setting %s to %s failed: %s", entity_id, value, error)
        else:
            LOGGER.error('"%s" is no valid entity ID', entity_id)

    async def async_turn_on(call: ServiceCall) -> None:
        if not fourheat_entry_data.coordinator:
            raise NotInitialized
        await fourheat_entry_data.coordinator.device.async_send_command(SERVICE_TURN_ON)

    async def async_turn_off(call: ServiceCall) -> None:
        if not fourheat_entry_data.coordinator:
            raise NotInitialized
        await fourheat_entry_data.coordinator.device.async_send_command(
            SERVICE_TURN_OFF
        )

    hass.services.async_register(DOMAIN, "set_value", async_handle_set_value)
    hass.services.async_register(DOMAIN, "turn_on", async_turn_on)
    hass.services.async_register(DOMAIN, "turn_off", async_turn_off)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""
    fourheat_entry_data = get_entry_data(hass)[entry.entry_id]

    if not fourheat_entry_data.coordinator:
        return True
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, fourheat_entry_data.coordinator.platforms
    ):
        get_entry_data(hass).pop(entry.entry_id)

    return unload_ok
