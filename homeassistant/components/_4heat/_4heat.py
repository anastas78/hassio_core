"""Provides the 4heat device class."""
from __future__ import annotations

from ast import literal_eval
import asyncio
from dataclasses import dataclass
import ipaddress
from socket import AF_INET, SOCK_STREAM, gethostbyname, socket
from typing import Any, Literal, Union, cast

from homeassistant.const import STATE_OFF, STATE_ON

from .const import (
    CONF_MODE,
    CONF_MODES,
    DEVICE_STATE_SENSOR,
    ERROR_QUERY,
    GET_COMMAND,
    INFO_COMMAND,
    INFO_QUERY,
    LOGGER,
    OFF_COMMAND,
    ON_COMMAND,
    RESULT_ERROR,
    RESULT_INFO,
    RESULT_OK,
    RETRY_UPDATE_SLEEP,
    SET_COMMAND,
    SOCKET_BUFFER,
    SOCKET_TIMEOUT,
    STATES_OFF,
    TCP_PORT,
    UNBLOCK_COMMAND,
)
from .exceptions import (
    DeviceConnectionError,
    FourHeatCommandError,
    FourHeatError,
    InvalidCommand,
    InvalidMessage,
)


@dataclass
class ConnectionOptions:
    """4heat options for connection."""

    ip_address: str
    port: int = TCP_PORT
    mode: bool = False


IpOrOptionsType = Union[str, ConnectionOptions]


async def process_ip_or_options(ip_or_options: IpOrOptionsType) -> ConnectionOptions:
    """Return ConnectionOptions class from ip str or ConnectionOptions."""
    if isinstance(ip_or_options, str):
        options = ConnectionOptions(ip_or_options)
    else:
        options = ip_or_options

    try:
        ipaddress.ip_address(options.ip_address)
    except ValueError:
        loop = asyncio.get_running_loop()
        options.ip_address = await loop.run_in_executor(
            None, gethostbyname, options.ip_address
        )

    return options


class FourHeatDevice:
    """Represents a 4heat device."""

    def __init__(
        self,
        name: str,
        host: str,
        port: int = TCP_PORT,
        mode: bool = False
        # self, name: str, options : ConnectionOptions
    ) -> None:
        """Initialize 4heat device."""
        self.name = name
        self.host = host
        self.port = port
        self.mode = CONF_MODE[mode]
        self.options: ConnectionOptions  # TODO move all connection options here
        self.fourheat: dict[str, Any] | None = None  # TODO get serial, model i.e
        self._settings: dict[
            str, Any
        ] | None = None  # TODO if we need to store something
        self._status: dict[str, Any] | None = None
        self.sensors: dict[str, dict] | None = None
        self.commands: dict[str, list] = CONF_MODES[self.mode]
        self.initialized: bool = False
        self._initializing: bool = False
        self._last_error: FourHeatError | None = None
        self._command_is_running: str = ""

        # self.cfgChanged

    @classmethod
    async def create(
        cls,
        name: str,
        host: str,
        port: int = TCP_PORT,
        mode: bool = False,
        initialize: bool = True,
    ) -> FourHeatDevice:
        """Create a new device instance."""
        instance = cls(name, host, port, mode)
        if initialize:
            await instance.initialize()
            return instance
        return instance

    async def initialize(self, async_init: bool = False) -> None:
        """Initialize connection and check which sensors are supported."""
        if self._initializing:
            raise RuntimeError("Already initializing")
        self._initializing = True
        self.initialized = False
        LOGGER.debug(
            "Initializing device- %s:%s:%s, mode:%s",
            self.name,
            self.host,
            self.port,
            self.mode,
        )
        sensors = {}
        try:
            await self.update_fourheat()
            if not async_init:
                # result = await self.send_and_receive(INFO_QUERY)
                result = await self.async_send_command(INFO_COMMAND)
                assert result
                if result["result"] == RESULT_ERROR:
                    result = await self.send_and_receive(ERROR_QUERY)
                elif result["result"] in [RESULT_INFO, RESULT_OK]:
                    for item in result["sensors"]:
                        LOGGER.debug(
                            "sensor: %s, type: %s, value: %s",
                            item["id"],
                            item["sensor_type"],
                            item["value"],
                        )
                        sensors[item["id"]] = {
                            "sensor_type": item["sensor_type"],
                            "value": item["value"],
                        }
                    self.sensors = sensors
                    self.initialized = True
                else:
                    self._last_error = InvalidMessage(
                        f"Unknown initialization result: {result['result']}. Please inform maintainer."
                    )
                    raise self._last_error
        except (FourHeatCommandError, DeviceConnectionError) as err:
            LOGGER.debug(
                "Could not fetch data from API at %s: %s", self.host, self._last_error
            )
            raise FourHeatError(self._last_error) from err
        else:
            self._status = getattr(self, DEVICE_STATE_SENSOR)
        finally:
            self._initializing = False

    async def async_update_data(self) -> None:
        """Fetch new data from 4heat."""
        try:
            LOGGER.debug(
                "Fetching new data from device %s:%s",
                self.host,
                self.port,
            )
            result = await self.send_and_receive(INFO_QUERY)
            # result = await self.async_send_command("info")
            LOGGER.debug("4heat data received:%s", result)
            if result["result"] == RESULT_ERROR:
                error_query = []
                assert self.sensors
                for sensor in self.sensors:
                    # ask for data for all registred sensors
                    error_query.append(f"I{sensor}{str(0).zfill(12)}")
                # error_query = GET_QUERY + error_query
                # result = await self.send_and_receive(error_query)
                result = await self.async_send_command("get", error_query)
                LOGGER.debug("4heat data received:%s", result)
            elif result["result"] == RESULT_INFO or RESULT_OK:
                # TODO how is the auto add boolean working in HASS
                for item in result["sensors"]:
                    if item["id"] not in self.sensors:
                        # add missing sensor
                        self.sensors[item["id"]] = {
                            "sensor_type": item["sensor_type"],
                            "value": item["value"],
                        }
                    else:
                        self.sensors[item["id"]].update(item)
                LOGGER.debug("Updated sensors: %s", self.sensors)
                self._last_error = None
        except DeviceConnectionError as err:
            LOGGER.debug("4heat data update failed with:%s", str(err))
            raise self._last_error from err

    async def send_and_receive(self, query: list) -> dict[str, str | list]:
        """Communication with 4heat device.

        Returns dict {
            result : TYPE str
            sensors: SENSORS dict{
                id : unique_id
                sensor_type: type B or J
                value: value int
            }
        """
        while bool(self._command_is_running):
            await asyncio.sleep(1)
            LOGGER.debug("Waiting previous command to finish... ")
        try:
            self._command_is_running = query
            data = {}
            soc = socket(AF_INET, SOCK_STREAM)
            soc.settimeout(SOCKET_TIMEOUT)
            soc.connect((self.host, self.port))
            # 4heat insists on double quotes..... Single quotes give empty answer
            msg = bytes("[" + ", ".join(f'"{item}"' for item in query) + "]", "utf-8")
            LOGGER.debug("Message sent: %s", msg)
            soc.send(msg)
            result = soc.recv(SOCKET_BUFFER).decode()
            LOGGER.debug("Result received: %s", result)
            soc.close()
            if result:
                result = literal_eval(result)
                data["result"] = result[0]
                data["sensors"] = []
                # if data["result"] in [RESULT_INFO, RESULT_OK]:
                # if data["result"] == query[0]:
                for sensor in result[2:]:
                    if len(sensor) > 6:
                        data["sensors"].append(
                            {
                                "id": sensor[1:6],
                                "sensor_type": sensor[0],
                                "value": int(sensor[7:]),
                            }
                        )
                    # else:
                    #     # we have ERR answer
                    #     data["sensors"].append({"id": sensor})
                self._last_error = None
                self._command_is_running = None
                return data
            self._last_error = DeviceConnectionError("Got empty answer")
            raise self._last_error
        except Exception as err:
            self._last_error = DeviceConnectionError(
                f"Unsuccessful communication with {self.host}:{self.port} - {str(err)}"
            )
            asyncio.create_task(
                self._i_am_lazy()
            )  # give the lazy module 5 sec to recover
            raise self._last_error from err

    async def _i_am_lazy(self) -> None:
        """4heat module is constatly rebooting or getting disconnected under load (and not only then....)."""
        LOGGER.debug("Blocking following commands for %s seconds", RETRY_UPDATE_SLEEP)
        await asyncio.sleep(RETRY_UPDATE_SLEEP)
        self._command_is_running = None
        return

    async def async_send_command(
        self, command: str, arg: list = None
    ) -> dict | bool | None:
        """Send command."""
        LOGGER.debug(
            "Sending command %s%s",
            command,
            str(f" with arguments: {arg}" if arg else "."),
        )
        if command in self.commands:
            if arg:
                query = self.commands[command] + arg
            else:
                query = self.commands[command]
            try:
                result = await self.send_and_receive(query)
                if command == INFO_COMMAND:
                    if result == RESULT_ERROR:
                        self.async_update_status()
                        LOGGER.debug("Received %s. Started status update", RESULT_ERROR)
                    else:
                        LOGGER.debug("Command %s returned: %s", command, result)
                        return result
                if command == GET_COMMAND:
                    LOGGER.debug("Command %s returned: %s", command, result)
                    return result
                if (
                    command == SET_COMMAND
                    and result["result"] == query[0]
                    and result["sensors"][0]["id"] == query[2][1:6]
                    and result["sensors"][0]["value"] == int(query[2][7:])
                    and result["sensors"][0]["sensor_type"] == "A"
                ):
                    LOGGER.debug("Command '%s' successfully executed", command)
                    return True

                if (
                    command in [ON_COMMAND, OFF_COMMAND, UNBLOCK_COMMAND]
                    and result["result"] == query[0]
                    and result["sensors"][0]["id"] == query[2][1:6]
                    and result["sensors"][0]["value"] == 0
                    and result["sensors"][0]["sensor_type"] == "I"
                ):
                    LOGGER.debug("Command %s successfully executed", command)
                    return True
                raise InvalidMessage(
                    f"Unknown answer {result} to command:{command}. Executed query: {query}. Please inform maintainer!"
                )
            except DeviceConnectionError as err:
                raise FourHeatCommandError(
                    f"Unsuccessful excecution of command {command} - {str(err)}"
                ) from err
        else:
            raise InvalidCommand(
                f"Command {command} is not implemented. Contact maintainer."
            )

    async def update_fourheat(self) -> None:
        """Update device settings."""
        # TODO get a way to find more info about the device
        self.fourheat = {
            "model": "4heat device",
            "serial": None,
            "manufacturer": "4heat",
        }

    async def async_set_state(self, attr: str, value: int) -> bool:
        """Setting state of a 4heat device attribute."""

        if attr not in self.sensors:
            raise AttributeError(f"Device doesn't have such attribute {attr}")
        if self.sensors[attr]["sensor_type"] == "J":
            raise AttributeError("Attribute is read only")
        arg = [f"B{attr}{str(value).zfill(12)}"]
        try:
            await self.async_send_command("set", arg)
            self.sensors[attr]["value"] = value
            return True
        except (FourHeatCommandError, InvalidMessage, InvalidCommand) as err:
            raise FourHeatCommandError(
                f"Exception on setting value of {attr} - {str(err)}"
            ) from err

    async def async_get_state(self, attr: str | list) -> dict[str, str | list]:
        """Geting state of a 4heat device attribute."""

        if isinstance(attr, str) and attr not in self.sensors:
            raise AttributeError(f"Device doesn't have such attribute {attr}")
        if not all(item in self.sensors for item in attr):
            raise AttributeError("Device doesn't have one of the attributes asked")
        arg = []
        if isinstance(attr, list):
            for item in attr:
                arg.append([f"I{item}{str(0).zfill(12)}"])
        else:
            arg = [f"I{attr}{str(0).zfill(12)}"]
        try:
            result = await self.async_send_command("get", arg)
            for sensor in result["sensors"]:
                self.sensors[sensor["id"]]["value"] = sensor["value"]
                self.sensors[sensor["id"]]["sensor_type"] = sensor["sensor_type"]
            return result
        except (FourHeatCommandError, InvalidMessage, InvalidCommand) as err:
            raise FourHeatCommandError(
                f"Exception on getting value of {attr} - {str(err)}"
            ) from err

    def info(self, attr: str) -> dict[str, Any]:
        """Return info over attribute."""
        if not self.initialized:
            return None
        return self.sensors[attr]

    def __getattr__(self, attr: str) -> str | None:
        """Get attribute."""
        if not self.initialized:
            return None
        if attr not in self.attributes:
            raise AttributeError(
                f"Device {self.device.model} has no attribute '{attr}'"
            )
        return self.sensors[attr].get("value")

    @property
    def ip_address(self) -> str:
        """Device ip address."""
        return self.options.ip_address

    @property
    def settings(self) -> dict[str, Any]:
        """Get device settings."""
        if not self.initialized:
            return None
        return self._settings

    @property
    def status(self) -> Literal["on", "off"] | None:
        """Get device status."""
        if not self.initialized:
            return None
        return (
            STATE_ON
            if getattr(self, DEVICE_STATE_SENSOR) not in STATES_OFF
            else STATE_OFF
        )

    @property
    def model(self) -> str:
        """Device model."""
        if not self.initialized:
            return None
        return cast(str, self.fourheat["model"])

    @property
    def serial(self) -> str:
        """Device model."""
        if not self.initialized:
            return None
        return cast(str, self.fourheat["serial"]) or None

    @property
    def manufacturer(self) -> str:
        """Device manufacturer."""
        if not self.initialized:
            return None
        assert self.fourheat
        return cast(str, self.fourheat["manufacturer"]) or None

    # # @property
    # def hostname(self) -> str:
    #     """Device hostname."""
    #     return cast(str, self.settings["device"]["hostname"])

    @property
    def last_error(self) -> FourHeatError | None:
        """Return the last error."""
        return self._last_error

    @property
    def attributes(self) -> list | None:
        """Get all attributes."""
        if not self.initialized:
            return None
        return self.sensors
