"""4heat exceptions."""
from __future__ import annotations


class FourHeatError(Exception):
    """Base class for 4heat errors."""


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
