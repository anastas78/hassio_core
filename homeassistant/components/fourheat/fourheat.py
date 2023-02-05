"""Provides the 4heat device class."""
from __future__ import annotations

from ast import literal_eval
import asyncio
from dataclasses import dataclass
import ipaddress

# import queue
from socket import AF_INET, SOCK_STREAM, gethostbyname, socket
from typing import Any, Literal, Union, cast

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.typing import StateType

from .const import (
    CONF_MODE,
    CONF_MODES,
    DEVICE_STATE_SENSOR,
    GET_COMMAND,
    INFO_COMMAND,
    LOGGER,
    OFF_COMMAND,
    ON_COMMAND,
    ON_ERROR_QUERY,
    RESULT_ERROR,
    RESULT_INFO,
    RESULT_OK,
    RETRY_UPDATE,
    RETRY_UPDATE_SLEEP,
    SET_COMMAND,
    SOCKET_BUFFER,
    SOCKET_TIMEOUT,
    STATES_OFF,
    TCP_PORT,
    UNBLOCK_COMMAND,
)
from .exceptions import (
    CommandError,
    DeviceConnectionError,
    FourHeatError,
    InvalidCommand,
    InvalidMessage,
    NotInitialized,
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
        self.options: ConnectionOptions  # TO DO move all connection options here
        self.fourheat: dict[str, Any] | None = None  # TO DO get serial, model i.e
        # self.settings: dict[str, Any] | None = None  # TO DO move monitored conditions
        self._status: dict[str, Any] | None = None
        self.sensors: dict[str, dict] = {}
        self.commands: dict[str, list] = CONF_MODES[self.mode]
        self.initialized: bool = False
        self._initializing: bool = False
        self._last_error: FourHeatError | None = None
        self._command_is_running: list | None = None
        # self._command_queue = queue.PriorityQueue()

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
        try:
            await self.update_fourheat()
            self.sensors = {}
            if not async_init:
                sensors = await self.async_send_command(command="init")
                if sensors:
                    for item in sensors:
                        LOGGER.debug(
                            "sensor: %s, type: %s, value: %s",
                            item["id"],
                            item["sensor_type"],
                            item["value"],
                        )
                        self.sensors[item["id"]] = {
                            "sensor_type": item["sensor_type"],
                            "value": item["value"],
                        }
                    self.initialized = True
                else:
                    raise NotInitialized("Init got None result! Inform maintainer!")
        except CommandError as err:
            LOGGER.debug(
                "Could not fetch data from API at %s: %s", self.host, self._last_error
            )
            raise NotInitialized(self._last_error) from err
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
            result = await self.async_send_command("info")
            LOGGER.debug("4heat data received:%s", result)
            # TO DO how is the auto add boolean working in HASS
            if result:
                for item in result:
                    if item["id"] not in self.sensors:
                        # add missing sensor
                        self.sensors[item["id"]] = {
                            "sensor_type": item["sensor_type"],
                            "value": item["value"],
                        }
                    else:
                        self.sensors[item["id"]].update(item)
                LOGGER.debug("Updated sensors: %s", self.sensors)
            else:
                raise CommandError("Update got None result! Inform maintainer!")
        except CommandError as err:
            LOGGER.debug("4heat data update failed with:%s", str(err))
            raise FourHeatError from self._last_error

    async def _send_and_receive(self, query: list) -> tuple[str, list[dict]]:
        """Communication with 4heat device.

        Returns tuple (
            result : TYPE str,
            sensors: dict{
                id : unique_id
                sensor_type: type B or J
                value: int
            )
        """

        while bool(self._command_is_running):
            await asyncio.sleep(1)
            LOGGER.debug(
                "Waiting previous command %s to finish... ",
                self._command_is_running,
            )
        try:
            self._command_is_running = query
            soc = socket(AF_INET, SOCK_STREAM)
            soc.settimeout(SOCKET_TIMEOUT)
            soc.connect((self.host, self.port))
            # 4heat insists on double quotes..... Single quotes give empty answer
            msg = bytes("[" + ", ".join(f'"{item}"' for item in query) + "]", "utf-8")
            LOGGER.debug("Sending message: %s", msg)
            soc.send(msg)
            result = soc.recv(SOCKET_BUFFER).decode()
            LOGGER.debug("Result received: %s", result)
            soc.close()
            if result:
                try:
                    result = literal_eval(result)
                    sensors = []
                    for sensor in result[2:]:
                        if len(sensor) > 6:
                            sensors.append(
                                {
                                    "id": sensor[1:6],
                                    "sensor_type": sensor[0],
                                    "value": int(sensor[7:]),
                                }
                            )
                    self._last_error = None
                    self._command_is_running = None
                    return (result[0], sensors)
                except SyntaxError as error:
                    self._last_error = DeviceConnectionError(
                        f"Got malformed answer from device - {str(error)}"
                    )
            self._last_error = DeviceConnectionError("Got empty answer")
        except OSError as err:
            self._last_error = DeviceConnectionError(
                f"Unsuccessful communication with {self.host}:{self.port} - {str(err)}"
            )
        LOGGER.debug(
            "On running: %s, got last_error: %s",
            self._command_is_running,
            self._last_error,
        )

        asyncio.create_task(self._i_am_lazy())  # give the lazy module 5 sec to recover
        raise DeviceConnectionError from self._last_error

    async def _i_am_lazy(self) -> None:
        """4heat module is constatly rebooting or getting disconnected under load (and not only then....)."""
        LOGGER.debug("Blocking following commands for %s seconds", RETRY_UPDATE_SLEEP)
        await asyncio.sleep(RETRY_UPDATE_SLEEP)
        self._command_is_running = None
        return

    async def async_send_command(
        self, command: str, arg: list | None = None, retry: bool = True
    ) -> list[dict] | None:
        """Send command."""
        LOGGER.debug(
            "Sending command %s%s",
            command,
            str(f" with arguments: {arg}" if arg else "."),
        )
        while not self.initialized:
            if command == "init":
                command = "info"
                break
            try:
                await self.initialize()
            except NotInitialized:
                LOGGER.debug("Can't initialize %s - %s", self.name, self._last_error)
        if command in self.commands:
            if arg:
                query = self.commands[command] + arg
            else:
                query = self.commands[command]
            retries = RETRY_UPDATE if retry else 1
            retry_step = 1
            while retry_step <= retries:
                try:
                    LOGGER.debug("Try: %s from %s", retry_step, retries)
                    (result, sensors) = await self._send_and_receive(query)
                    break
                except DeviceConnectionError:
                    retry_step += 1
            else:
                raise CommandError(
                    f"Unsuccessful execution of command {command} - {str(self._last_error)}"
                ) from self._last_error

            if command == INFO_COMMAND:
                if result == RESULT_ERROR:
                    LOGGER.debug(
                        "Received result %s. Started minimal status update",
                        result,
                    )
                    return await self.async_send_command("get", ON_ERROR_QUERY)
                if result == RESULT_INFO:
                    LOGGER.debug(
                        "Command %s returned: %s and sensors %s",
                        command,
                        result,
                        sensors,
                    )
                    return sensors
            if result == RESULT_OK:
                if command == GET_COMMAND:
                    LOGGER.debug(
                        "Command %s returned: %s with sensors: %s",
                        command,
                        result,
                        sensors,
                    )
                    return sensors
                if (
                    command == SET_COMMAND
                    and sensors[0]["id"] == query[2][1:6]
                    and sensors[0]["value"] == int(query[2][7:])
                    and sensors[0]["sensor_type"] == "A"
                ):
                    LOGGER.debug("Command '%s' successfully executed", command)
                    return None

                if (
                    command in [ON_COMMAND, OFF_COMMAND, UNBLOCK_COMMAND]
                    and sensors[0]["id"] == query[2][1:6]
                    and sensors[0]["value"] == 0
                    and sensors[0]["sensor_type"] == "I"
                ):
                    LOGGER.debug("Command %s successfully executed", command)
                    return None
            raise InvalidMessage(
                f"Unknown answer {result} to command:{command}. Executed query: {query}. Please inform maintainer!"
            )
        raise InvalidCommand(
            f"Command {command} is not implemented. Contact maintainer."
        )

    async def update_fourheat(self) -> None:
        """Update device settings."""
        # TO DO get a way to find more info about the device
        self.fourheat = {
            "model": "4heat device",
            "serial": None,
            "manufacturer": "4heat",
        }

    async def async_set_state(self, attr: str, value: StateType) -> bool:
        """Set 4heat device attribute."""

        if attr not in self.sensors:
            raise AttributeError(f"Device doesn't have such attribute {attr}")
        if self.sensors[attr]["sensor_type"] == "J":
            raise AttributeError("Attribute is read only")
        if not value:
            raise AttributeError("Can't set value to None")
        arg = [f"B{attr}{str(int(value)).zfill(12)}"]
        try:
            await self.async_send_command("set", arg)
            self.sensors[attr]["value"] = value
            return True
        except (CommandError, InvalidMessage, InvalidCommand) as err:
            raise FourHeatError(
                f"Exception on setting value of {attr} - {str(err)}"
            ) from err

    # async def async_get_state(self, attr: str | list) -> None:  # dict[str, str | list]:
    #     """Getting state of a 4heat device attribute."""

    #     # if isinstance(attr, str) and attr not in self.sensors:
    #     #     raise AttributeError(f"Device doesn't have such attribute {attr}")
    #     # if not all(item in self.sensors for item in attr):
    #     #     raise AttributeError("Device doesn't have one of the attributes asked")
    #     arg = []
    #     if isinstance(attr, list):
    #         for item in attr:
    #             if item not in self.sensors:
    #                 raise AttributeError(f"Device doesn't have such attribute {item}")
    #             arg.append([f"I{item}{str(0).zfill(12)}"])
    #     else:
    #         if attr not in self.sensors:
    #             raise AttributeError(f"Device doesn't have such attribute {attr}")
    #         arg.append([f"I{attr}{str(0).zfill(12)}"])
    #     try:
    #         sensors = await self.async_send_command("get", arg)
    #         for sensor in sensors:
    #             self.sensors[sensor["id"]]["value"] = sensor["value"]
    #             self.sensors[sensor["id"]]["sensor_type"] = sensor["sensor_type"]
    #     except (CommandError, InvalidMessage, InvalidCommand) as err:
    #         raise FourHeatError(
    #             f"Exception on getting value of {attr} - {str(err)}"
    #         ) from err

    def info(self, attr: str) -> dict[str, Any] | None:
        """Return info over attribute."""
        if not self.initialized:
            return None
        return self.sensors[attr]

    def __getattr__(self, attr: str) -> str | None:
        """Get attribute."""
        if not self.attributes:
            return None
        if attr not in self.attributes:
            raise AttributeError(f"Device {self.model} has no attribute '{attr}'")
        return self.sensors[attr].get("value")

    @property
    def ip_address(self) -> str:
        """Device ip address."""
        return self.options.ip_address

    # @property
    # def settings(self) -> dict[str, Any] | None:
    #     """Get device settings."""
    #     if not self.initialized:
    #         return None
    #     return self.settings

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
    def model(self) -> str | None:
        """Device model."""
        if not self.fourheat:
            return None
        return cast(str, self.fourheat["model"]) or None

    @property
    def serial(self) -> str | None:
        """Device model."""
        if not self.fourheat:
            return None
        return cast(str, self.fourheat["serial"]) or None

    @property
    def manufacturer(self) -> str | None:
        """Device manufacturer."""
        if not self.fourheat:
            return None
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
        if not self.sensors:
            return None
        return list(self.sensors)
