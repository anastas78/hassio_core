"""4heat exceptions."""
from __future__ import annotations


class FourHeatError(Exception):
    """Base class for aioshelly errors."""


class ConnectionClosed(FourHeatError):
    """Exception raised when the connection is closed."""


class InvalidMessage(FourHeatError):
    """Exception raised when an invalid message is received."""


class NotInitialized(FourHeatError):
    """Raised if device is not initialized."""


class DeviceConnectionError(FourHeatError):
    """Exception indicates device connection errors."""


class CommandError(FourHeatError):
    """Exception indicates command execution errors."""


class InvalidCommand(FourHeatError):
    """Exception raised when invalid command is received."""
