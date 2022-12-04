"""Config flow for 4heat."""
from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_MODE,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_PORT,
)

# from requests.exceptions import ConnectionError
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, LOGGER, SENSORS, TCP_PORT
from .exceptions import DeviceConnectionError
from .fourheat import FourHeatDevice


class FourHeatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """4Heat config flow."""

    VERSION = 1

    host: str = ""
    info: dict[str, Any] = {}

    def _host_in_configuration_exists(self, host) -> bool:
        """Return True if site_id exists in configuration."""

        if host in four_heat_entries(self.hass):
            return True
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show initial dialog."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME))
            host = str(user_input.get(CONF_HOST))
            port = user_input.get(CONF_PORT, TCP_PORT)
            try:
                device = await FourHeatDevice.create(name, host, port, initialize=True)
                self.info = user_input
                self.info["sensors"] = device.sensors
                self.info["device_info"] = {
                    "model": device.model,
                    "manufacturer": device.manufacturer,
                    "serial": device.serial,
                }
            except DeviceConnectionError:
                errors["host"] = "cannot_connect"
            else:
                if device.serial:
                    await self.async_set_unique_id(device.serial)
                    self._abort_if_unique_id_configured({CONF_HOST: host})
                    self.info["device_info"]["serial"] = device.serial
                elif self._host_in_configuration_exists(host):
                    LOGGER.debug("host_exists")
                    errors["host"] = "host_exists"
                else:
                    await self.async_set_unique_id(self.flow_id)
                    self.info["device_info"]["serial"] = self.flow_id
                return await self.async_step_sensors()
        else:
            name = "Stove"
            host = "192.168.0.0"

        host_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=name): str,
                vol.Required(CONF_HOST, default=host): str,
                vol.Optional(CONF_PORT, default=80, description=CONF_PORT): cv.port,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=host_schema,
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm which sensors to use."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(self.info.get(CONF_NAME))
            host = str(self.info.get(CONF_HOST))
            port = self.info.get(CONF_PORT, TCP_PORT)
            mode: bool = bool(user_input.get(CONF_MODE)) | False
            sensors: list[str] = user_input.get(CONF_MONITORED_CONDITIONS, [])
            device_info = str(self.info.get("device_info"))
            if "all" in sensors:
                sensors = self.info.get("sensors", [])
            result = self.async_create_entry(
                title=name,
                data={
                    CONF_HOST: host,
                    CONF_MODE: mode,
                    CONF_PORT: port,
                    CONF_MONITORED_CONDITIONS: sensors,
                    "device_info": device_info,
                },
            )
            return result
        mode = False
        sensors = self.info.get("sensors", [])
        if not sensors:
            errors["host"] = "cannot_connect"
        else:
            sensors_dict: dict[str, str] = {}
            sensors_dict["all"] = "Use all sensors"
            for sensor in sensors:
                sensors_dict[sensor] = cast(str, SENSORS[sensor][0]["name"])
            device_schema = vol.Schema(
                {
                    vol.Optional(CONF_MODE, default=False, description=CONF_MODE): bool,
                    vol.Optional(
                        CONF_MONITORED_CONDITIONS,
                    ): cv.multi_select(sensors_dict),
                }
            )
        return self.async_show_form(
            step_id="sensors", data_schema=device_schema, errors=errors
        )


@callback
def four_heat_entries(hass: HomeAssistant):
    """Return the hosts for the domain."""
    return {
        (entry.data[CONF_HOST]) for entry in hass.config_entries.async_entries(DOMAIN)
    }
