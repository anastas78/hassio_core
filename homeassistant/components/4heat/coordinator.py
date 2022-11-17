"""Provides the 4heat DataUpdateCoordinator."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ._4heat import FourHeatDevice
from .const import (
    DATA_CONFIG_ENTRY,
    DOMAIN,
    ENTRY_RELOAD_COOLDOWN,
    LOGGER,
    RETRY_UPDATE,
    RETRY_UPDATE_SLEEP,
    SENSORS,
    UPDATE_INTERVAL,
)
from .exceptions import FourHeatError


@dataclass
class FourHeatEntryData:
    """Class for sharing data within a given config entry."""

    coordinator: FourHeatCoordinator | None = None


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
            self.sensors: dict[str, dict] = device.sensors
        self.platforms: dict[str, list[dict[str, dict]]] = self._build_platforms()
        entry.async_on_unload(self._debounced_reload.async_cancel)

        self._retry_update: int = 0
        self._update_is_running: bool = False

    @callback
    def _build_platforms(
        self,
    ) -> dict[str, list[dict[str, dict]]] | None:
        """Find available platforms."""
        platforms = {}
        for attr in self.sensors:
            try:
                sensor_conf = SENSORS[attr]
            except KeyError:
                LOGGER.warning(
                    "Sensor %s is not known. Please inform the mainteainer", attr
                )
                sensor_conf = {
                    "name": f"UN {attr}",
                    "platform": "sensor",
                }
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

    async def _async_update_data(self) -> None:
        """Update data via device library.

        Because of hardware bugs we try 'RETRY_UPDATE' times to get data from API, before setting Update failed.
        Only one copy of the update is allowed to lower the load on device.
        Temporary implementation for testing purposes
        """

        LOGGER.debug(
            "Trying update of data. Try %s of %s",
            self._retry_update + 1,
            RETRY_UPDATE,
        )
        LOGGER.debug("Last update success: %s", self.last_update_success)

        if self._update_is_running:
            LOGGER.debug("Last update try is still running. Canceling new one")
            return
        self._update_is_running = True
        while self._retry_update < RETRY_UPDATE:
            try:
                # if not self.device.initialized:
                #     await self.device.initialize()
                #     if not self.device.serial:
                #         self.device.fourheat["serial"] = self.entry.data["device_info"][
                #             "serial"
                #         ]
                #     self.sensors = self.device.sensors
                #     self.platforms = self._build_platforms()
                await self.device.async_update_data()
                self._retry_update = RETRY_UPDATE
            except FourHeatError as error:
                self._retry_update = self._retry_update + 1
                self.last_exception = error
                LOGGER.debug(
                    "Update of data try %s of %s failed: %s",
                    self._retry_update,
                    RETRY_UPDATE,
                    repr(error),
                )
                if self.last_update_success:
                    LOGGER.debug(
                        "Keeping old values for at least %s seconds more",
                        (RETRY_UPDATE - self._retry_update) * RETRY_UPDATE_SLEEP,
                    )
                    await asyncio.sleep(RETRY_UPDATE_SLEEP)
                else:
                    self.last_update_success = False
                    raise UpdateFailed(
                        f"No data current data available and update of data failed with: {error.args}"
                    ) from error
        self._retry_update = 0
        self._update_is_running = False

    def async_setup(self) -> None:
        """Set up the coordinator."""
        dev_reg = device_registry.async_get(self.hass)
        entry = dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            name=self.name,
            # connections={(device_registry.CONNECTION_NETWORK_MAC, self.mac)},
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
            return self.entry.data["device_info"]["serial"]
        return cast(str, self.device.serial)

    @property
    def manufacturer(self) -> str:
        """Manufacturer of the device."""
        return cast(str, self.device.manufacturer)
