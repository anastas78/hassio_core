"""Constants for the 4heat integration."""
from logging import Logger, getLogger
from typing import Final

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.number import NumberMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

DOMAIN = "fourheat"
LOGGER: Logger = getLogger(__package__)

ENTRY_RELOAD_COOLDOWN = 20
DATA_CONFIG_ENTRY: Final = "config_entry"

TCP_PORT = 80
SOCKET_BUFFER = 1024
SOCKET_TIMEOUT = 10
UPDATE_INTERVAL = 15  # Time in seconds between updates
RETRY_UPDATE = 10
RETRY_UPDATE_SLEEP = 5
ON_COMMAND = SERVICE_TURN_ON
OFF_COMMAND = SERVICE_TURN_OFF
UNBLOCK_COMMAND = "unblock"
SET_COMMAND = "set"
GET_COMMAND = "get"
INFO_COMMAND = "info"
# TO DO move to schema not const
# EXECUTE = {"info": "SEL", "command": "SEC", "config": {"network": "CF7"}}
# EXECUTE_INFOS = {"all": "0"}
# EXECUTE_COMMANDS = {"set": "1", "get": "3"}
# EXECUTE_CONFIGS = {"network": {"erase": "0", "info": "4"}}

# fmt: off
INFO_QUERY = ["SEL", "0"]  # Ask for a list of all sensors
SET_QUERY = ["SEC", "1"]  # SET sensor value ["SEC","1","B{sensor}{str(value).zfill(12)}"]
GET_QUERY = ["SEC", "3"]  # GET sensor value ["SEC","3","I{sensor}{str(value).zfill(12)}"]
ON_ERROR_QUERY = [
    "I30001000000000000",
    "I30002000000000000",
    "I30017000000000000"
]   # Get basic info - State, Error, Water Temp

RESULT_INFO = "SEL"
RESULT_OK = "SEC"
RESULT_ERROR = "ERR"
DEVICE_STATE_SENSOR = "30001"
UNBLOCK_QUERY = ["SEC", "1", "J30255000000000001"]  # Full Unblock
OFF_QUERY = ["SEC", "1", "J30254000000000001"]  # Full OFF
ON_QUERY = ["SEC", "1", "J30253000000000001"]  # Full ON

OFF_QUERY_LEGACY = ["SEC", "1", "1"]  # Legacy OFF
ON_QUERY_LEGACY = ["SEC", "1", "0"]  # Legacy ON
# fmt: on

CONF_MODE = {True: "legacy", False: "full"}
CONF_MODES = {
    "full": {
        SERVICE_TURN_ON: ON_QUERY,
        SERVICE_TURN_OFF: OFF_QUERY,
        UNBLOCK_COMMAND: UNBLOCK_QUERY,
        INFO_COMMAND: INFO_QUERY,
        SET_COMMAND: SET_QUERY,
        GET_COMMAND: GET_QUERY,
    },
    "legacy": {
        SERVICE_TURN_ON: ON_QUERY_LEGACY,
        SERVICE_TURN_OFF: OFF_QUERY_LEGACY,
        INFO_COMMAND: INFO_QUERY,
        SET_COMMAND: SET_QUERY,
        GET_COMMAND: GET_QUERY,
    },
}
# TO DO 20211 is potentionally MAX POWER or must be made configurable
MAX_POWER = 5

STATE_NAMES = {
    0: "OFF",
    1: "Check Up",
    2: "Ignition",
    3: "Stabilization",
    4: "Ignition",
    5: "Run",
    6: "Modulation",
    7: "Extinguishing",
    8: "Safety",
    9: "Block",
    10: "RecoverIgnition",
    11: "Standby",
    30: "Ignition",
    31: "Ignition",
    32: "Ignition",
    33: "Ignition",
    34: "Ignition",
}
STATES_OFF = [0, 7, 8, 9]

ERROR_NAMES = {
    0: "No",
    1: "Safety Thermostat HV1: signalled also in case of Stove OFF",
    2: "Safety PressureSwitch HV2: signalled with Combustion Fan ON",
    3: "Extinguishing for Exhausting Temperature lowering",
    4: "Extinguishing for water over Temperature",
    5: "Extinguishing for Exhausting over Temperature",
    6: "unknown",
    7: "Encoder Error: No Encoder Signal (in case of P25=1 or 2)",
    8: "Encoder Error: Combustion Fan regulation failed (in case of P25=1 or 2)",
    9: "Low pressure in to the Boiler",
    10: "High pressure in to the Boiler Error",
    11: "DAY and TIME not correct due to prolonged absence of Power Supply",
    12: "Failed Ignition",
    13: "Ignition",
    14: "Ignition",
    15: "Lack of Voltage Supply",
    16: "Ignition",
    17: "Ignition",
    18: "Lack of Voltage Supply",
}

POWER_NAMES = {
    1: "P1",
    2: "P2",
    3: "P3",
    4: "P4",
    5: "P5",
    6: "P6",
    7: "Auto",
}

if MAX_POWER:
    for x in range(1, MAX_POWER + 1):
        POWER_NAMES[x] = "P" + str(x)
    POWER_NAMES[MAX_POWER + 1] = "Auto"

SENSORS: dict[str, list[dict]] = {
    # Sensors list (str, dict(str,str|list))
    # "id": str                 unique_id coming from device
    #   [   optional list of dict if one id is going to utilize more platforms
    #       {
    #     Required:
    #     "name" : str          Description of the sensor
    #     "platform": str     Which platform will that sensor utilize, i.e ["sensor", "switch", "button"]
    #
    #     Optional: All attributes which the entity / platform has, i.e
    #     "native_unit_of_measurement" : str        unit_of_measurement
    #     "entity_category" :
    #     "device_class" :
    #     "state_class":
    #     "extra_state_attribute":
    #     "value": lambda : .....
    #       }
    #   ]
    "30001": [
        {
            "name": "State",
            "platform": "sensor",
            "device_class": BinarySensorDeviceClass.RUNNING,
            "value": lambda value: STATE_NAMES[value],
            "extra_state_attributes": lambda device: {
                "Device serial:": device.serial,
                "Sensor type:": device.info("30001")["sensor_type"],
                "Sensor ID:": "30001",
                "Numerical value:": device.info("30001")["value"],
            },
        },
        {
            "name": "State",
            "platform": "switch",
            "entity_category": EntityCategory.CONFIG,
            "device_class": BinarySensorDeviceClass.RUNNING,
            "value": lambda value: value not in STATES_OFF,
            "extra_state_attributes": lambda device: {
                "Device serial:": device.serial,
                "Sensor type:": device.info("30001")["sensor_type"],
                "Sensor ID:": "30001",
                "Numerical value:": device.info("30001")["value"],
            },
        },
    ],
    "30002": [
        {
            "id": "30002",
            "name": "Error",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "device_class": BinarySensorDeviceClass.PROBLEM,
            "value": lambda value: ERROR_NAMES[value],
        },
        {
            "id": "30002",
            "name": "Clear error",
            "platform": "button",
            "entity_category": EntityCategory.CONFIG,
            "device_class": ButtonDeviceClass.UPDATE,
            "press_action": lambda coordinator: coordinator.device.async_send_command(
                "unblock"
            ),
            "supported": lambda coordinator: coordinator.device.mode is False,
        },
    ],
    "30003": [
        {
            "id": "30003",
            "name": "Timer",
            "platform": "sensor",
        }
    ],
    "30004": [
        {
            "id": "30004",
            "name": "Ignition",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "30005": [
        {
            "id": "30005",
            "name": "Exhaust temperature",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "value": lambda value: round(value, 1),
            "platform": "sensor",
        }
    ],
    "30006": [
        {
            "id": "30006",
            "name": "Room temperature",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "30007": [
        {
            "id": "30007",
            "name": "Inputs",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "30008": [
        {
            "id": "30008",
            "name": "Combustion fan",
            "native_unit_of_measurement": REVOLUTIONS_PER_MINUTE,
            "state_class": SensorStateClass.MEASUREMENT,
            "platform": "sensor",
        }
    ],
    "30009": [
        {
            "id": "30009",
            "name": "Heating fan",
            "native_unit_of_measurement": REVOLUTIONS_PER_MINUTE,
            "state_class": SensorStateClass.MEASUREMENT,
            "platform": "sensor",
        }
    ],
    "30010": [
        {
            "id": "30010",
            "name": "UN 30010",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "30011": [
        {
            "id": "30011",
            "name": "Combustion power",
            "platform": "sensor",
        }
    ],
    "30012": [
        {
            "id": "30012",
            "name": "Puffer temperature",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "30015": [
        {
            "id": "30015",
            "name": "Combustion fan",
            "native_unit_of_measurement": "%",
            "state_class": SensorStateClass.MEASUREMENT,
            "platform": "sensor",
        }
    ],
    "30017": [
        {
            "id": "30017",
            "name": "Boiler water",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "30020": [
        {
            "id": "30020",
            "name": "Water pressure",
            "native_unit_of_measurement": UnitOfPressure.MBAR,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "30025": [
        {
            "id": "30025",
            "name": "Comb.FanRealSpeed",
            "native_unit_of_measurement": REVOLUTIONS_PER_MINUTE,
            "state_class": SensorStateClass.MEASUREMENT,
            "platform": "sensor",
        }
    ],
    "30026": [
        {
            "id": "30026",
            "name": "UN 30026",
            "platform": "sensor",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "30033": [
        {
            "id": "30033",
            "name": "Exhaust depression",
            "native_unit_of_measurement": UnitOfPressure.PA,
            "device_class": SensorDeviceClass.PRESSURE,
            "platform": "sensor",
        }
    ],
    "30040": [
        {
            "id": "30040",
            "name": "UN 30040",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "30044": [
        {
            "id": "30044",
            "name": "UN 30044",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "30084": [
        {
            "id": "30084",
            "name": "UN 30084",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "40007": [
        {
            "id": "40007",
            "name": "UN 40007",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20180": [
        {
            "id": "20180",
            "name": "Boiler target",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "entity_category": EntityCategory.CONFIG,
            "platform": "sensor",
        },
        {
            "id": "20180",
            "name": "Boiler target",
            "platform": "number",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "entity_category": EntityCategory.CONFIG,
            "native_min_value": 50,
            "native_max_value": 80,
            "native_step": 1,
            "mode": NumberMode("slider"),
        },
    ],
    "20199": [
        {
            "id": "20199",
            "name": "Boiler target",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "entity_category": EntityCategory.CONFIG,
            "platform": "sensor",
        }
    ],
    "20005": [
        {
            "id": "20005",
            "name": "Min boiler temperature",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "20006": [
        {
            "id": "20006",
            "name": "Max boiler temperature",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
            "platform": "sensor",
        }
    ],
    "20211": [
        {
            "id": "20211",
            "name": "UN 20211",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20225": [
        {
            "id": "20225",
            "name": "UN 20225",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20364": [
        {
            "id": "20364",
            "name": "Power Setting",
            "platform": "sensor",
            "entity_category": EntityCategory.CONFIG,
            "device_class": BinarySensorDeviceClass.RUNNING,
            "value": lambda value: POWER_NAMES[value],
            "extra_state_attributes": lambda device: {
                "Device serial:": device.serial,
                "Sensor type:": device.info("20364")["sensor_type"],
                "Sensor ID:": "20364",
                "Numerical value:": device.info("20364")["value"],
            },
        }
    ],
    "20381": [
        {
            "id": "20381",
            "name": "UN 20381",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20365": [
        {
            "id": "20365",
            "name": "UN 20365",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20366": [
        {
            "id": "20366",
            "name": "UN 20366",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20369": [
        {
            "id": "20369",
            "name": "UN 20369",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20374": [
        {
            "id": "20374",
            "name": "UN 20374",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20375": [
        {
            "id": "20375",
            "name": "UN 20375",
            "entity_category": EntityCategory.DIAGNOSTIC,
            "platform": "sensor",
        }
    ],
    "20575": [
        {
            "id": "20575",
            "name": "UN 20575",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "20493": [
        {
            "id": "20493",
            "name": "Room temperature set point",
            "platform": "sensor",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
        }
    ],
    "20570": [
        {
            "id": "20570",
            "name": "UN 20570",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "20801": [
        {
            "id": "20801",
            "name": "Heating power",
            "platform": "sensor",
            "entity_category": EntityCategory.CONFIG,
        }
    ],
    "20803": [
        {
            "id": "20803",
            "name": "UN 20803",
            "platform": "sensor",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ],
    "20813": [
        {
            "id": "20813",
            "name": "Power Setting",
            "platform": "sensor",
            "entity_category": EntityCategory.CONFIG,
            "device_class": BinarySensorDeviceClass.RUNNING,
            "value": lambda value: POWER_NAMES[value],
            "extra_state_attributes": lambda device: {
                "Device serial:": device.serial,
                "Sensor type:": device.info("20813")["sensor_type"],
                "Sensor ID:": "20364",
                "Numerical value:": device.info("20813")["value"],
            },
        }
    ],
    "21700": [
        {
            "id": "21700",
            "name": "Room thermostat",
            "platform": "sensor",
            "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
            "device_class": SensorDeviceClass.TEMPERATURE,
        }
    ],
    "40016": [
        {
            "id": "40016",
            "name": "Outputs",
            "platform": "sensor",
        }
    ],
    "50001": [
        {
            "id": "50001",
            "name": "Auger on",
            "platform": "sensor",
            "entity_category": EntityCategory.CONFIG,
            "device_class": BinarySensorDeviceClass.RUNNING,
            "extra_state_attributes": lambda device: {
                "Device serial:": device.serial,
                "Sensor type:": device.info("30001")["sensor_type"],
                "Sensor ID:": "30001",
                "Numerical value:": device.info("30001")["value"],
            },
        }
    ],
}
