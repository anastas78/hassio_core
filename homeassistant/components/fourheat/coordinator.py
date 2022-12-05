"""Provides the 4heat DataUpdateCoordinator."""
from __future__ import annotations

from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DATA_CONFIG_ENTRY,
    DOMAIN,
    ENTRY_RELOAD_COOLDOWN,
    LOGGER,
    SENSORS,
    UPDATE_INTERVAL,
)
from .exceptions import FourHeatError
from .fourheat import FourHeatDevice


@dataclass
class FourHeatEntryData:
    """Class for sharing data within a given config entry."""

    coordinator: FourHeatCoordinator | None = None
    device: FourHeatDevice | None = None


def get_entry_data(hass: HomeAssistant) -> dict[str, FourHeatEntryData]:
    """Return 4heat entry data for a given config entry."""
    return cast(dict[str, FourHeatEntryData], hass.data[DOMAIN][DATA_CONFIG_ENTRY])


class FourHeatCoordinator(DataUpdateCoordinator):
    """Class to manage fetching 4heat data."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, device: FourHeatDevice
    ) -> None:
        """Init the coorditator."""
        self.device_id: str | None = None
        self.hass = hass
        self.entry = entry
        self.device = device
        self.sensors: dict[str, dict] = {}
        self.platforms: dict[str, list[dict[str, dict]]] = {}
        self._update_is_running: bool = False
        self.unload_platforms: dict | None = None

        super().__init__(
            hass,
            LOGGER,
            name=device.name,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self._debounced_reload: Debouncer[Coroutine[Any, Any, None]] = Debouncer(
            hass,
            LOGGER,
            cooldown=ENTRY_RELOAD_COOLDOWN,
            immediate=False,
            function=self._async_reload_entry,
        )
        if not self.device.initialized:
            sensors = {}
            ent_reg = entity_registry.async_get(hass)
            entries = entity_registry.async_entries_for_config_entry(
                ent_reg, self.entry.entry_id
            )
            for sensor in entries:
                sensors[sensor.unique_id.split("-")[-1]] = {
                    "sensor_type": None,
                    "value": None,
                }
            self.sensors = sensors
        else:
            self.sensors = device.sensors
        self.platforms = self.build_platforms()

        entry.async_on_unload(self._debounced_reload.async_cancel)
        entry.async_on_unload(
            self.async_add_listener(self._async_device_updates_handler)
        )

    @callback
    def build_platforms(
        self,
    ) -> dict[str, list[dict[str, dict]]]:
        """Find available platforms."""
        platforms: dict[str, list] = {}
        if not self.sensors:
            return platforms
        for attr in self.sensors:
            try:
                sensor_conf = SENSORS[attr]
            except KeyError:
                LOGGER.warning(
                    "Sensor %s is not known. Please inform the mainteainer", attr
                )
                sensor_conf = [
                    {
                        "name": f"UN {attr}",
                        "platform": "sensor",
                    }
                ]
            for sensor in sensor_conf:
                sensor_description = {}
                keys = {}
                try:
                    platform = str(sensor["platform"])
                except KeyError:
                    LOGGER.warning(
                        "Mandatory config entry 'platforms' for sensor %s is missing. Please contact maintainer",
                        attr,
                    )
                    platform = "sensor"
                for key, value in sensor.items():
                    if key != "platform":
                        if value:
                            keys[key] = value
                        else:
                            LOGGER.debug(
                                "Empty value for %s in sensor %s configuration",
                                key,
                                attr,
                            )
                if keys:
                    sensor_description[attr] = keys

                if platform not in platforms:
                    platforms[platform] = []
                platforms[platform].append(sensor_description)
        return platforms

    async def _async_reload_entry(self) -> None:
        """Reload entry."""
        LOGGER.debug("Reloading entry %s", self.name)
        await self.hass.config_entries.async_reload(self.entry.entry_id)

    @callback
    def _async_device_updates_handler(self) -> None:
        """Finish async init."""
        if self.sensors.keys() != self.device.sensors.keys():
            self.unload_platforms = self.platforms
            self.sensors = self.device.sensors
            self.platforms = self.build_platforms()
            self.async_setup()
            self.hass.async_create_task(
                self.hass.config_entries.async_forward_entry_setups(
                    self.entry, self.platforms
                )
            )
            self.hass.async_create_task(self._debounced_reload.async_call())

    async def _async_update_data(self, init: bool = False) -> None:
        """Update data via device library."""

        LOGGER.debug("Trying update of data")
        LOGGER.debug("Last update success: %s", self.last_update_success)

        if self._update_is_running:
            LOGGER.debug("Last update try is still running. Canceling new one")
            return
        self._update_is_running = True

        try:
            await self.device.async_update_data()
        except FourHeatError as error:
            self.last_exception = error
            LOGGER.debug(
                "Update of data failed: %s",
                repr(error),
            )
            raise UpdateFailed from error
        finally:
            self._update_is_running = False

    def async_setup(self) -> None:
        """Set up the coordinator."""
        dev_reg = device_registry.async_get(self.hass)
        entry = dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            identifiers={("serial", str(self.serial))},
        )
        self.device_id = entry.id

    @property
    def model(self) -> str:
        """Get model of the device."""
        return cast(str, self.device.model)

    @property
    def serial(self) -> str:
        """Get serial of the device."""
        if not self.device.initialized or not self.device.serial:
            if self.entry.unique_id:
                return self.entry.unique_id
            return self.entry.entry_id
        return self.device.serial

    @property
    def manufacturer(self) -> str:
        """Manufacturer of the device."""
        return cast(str, self.device.manufacturer)

    def info(self, attr: str) -> dict[str, Any] | None:
        """Return info over attribute."""
        return self.sensors[attr]
