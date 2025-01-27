"""Update coordinators for rainbird."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime
import logging
from typing import TypeVar

import async_timeout
from pyrainbird.async_client import AsyncRainbirdController, RainbirdApiException

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MANUFACTURER, TIMEOUT_SECONDS

UPDATE_INTERVAL = datetime.timedelta(minutes=1)

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass
class RainbirdDeviceState:
    """Data retrieved from a Rain Bird device."""

    zones: set[int]
    active_zones: set[int]
    rain: bool
    rain_delay: int


class RainbirdUpdateCoordinator(DataUpdateCoordinator[RainbirdDeviceState]):
    """Coordinator for rainbird API calls."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        controller: AsyncRainbirdController,
        serial_number: str,
    ) -> None:
        """Initialize ZoneStateUpdateCoordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_method=self._async_update_data,
            update_interval=UPDATE_INTERVAL,
        )
        self._controller = controller
        self._serial_number = serial_number
        self._zones: set[int] | None = None

    @property
    def controller(self) -> AsyncRainbirdController:
        """Return the API client for the device."""
        return self._controller

    @property
    def serial_number(self) -> str:
        """Return the device serial number."""
        return self._serial_number

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the device."""
        return DeviceInfo(
            default_name=f"{MANUFACTURER} Controller",
            identifiers={(DOMAIN, self._serial_number)},
            manufacturer=MANUFACTURER,
        )

    async def _async_update_data(self) -> RainbirdDeviceState:
        """Fetch data from Rain Bird device."""
        try:
            async with async_timeout.timeout(TIMEOUT_SECONDS):
                return await self._fetch_data()
        except RainbirdApiException as err:
            raise UpdateFailed(f"Error communicating with Device: {err}") from err

    async def _fetch_data(self) -> RainbirdDeviceState:
        """Fetch data from the Rain Bird device."""
        (zones, states, rain, rain_delay) = await asyncio.gather(
            self._fetch_zones(),
            self._controller.get_zone_states(),
            self._controller.get_rain_sensor_state(),
            self._controller.get_rain_delay(),
        )
        return RainbirdDeviceState(
            zones=set(zones),
            active_zones={zone for zone in zones if states.active(zone)},
            rain=rain,
            rain_delay=rain_delay,
        )

    async def _fetch_zones(self) -> set[int]:
        """Fetch the zones from the device, caching the results."""
        if self._zones is None:
            available_stations = await self._controller.get_available_stations()
            self._zones = {
                zone
                for zone in range(1, available_stations.stations.count + 1)
                if available_stations.stations.active(zone)
            }
        return self._zones
