import logging
import voluptuous as vol
from datetime import timedelta
import json
import asyncio
import paramiko
from typing import Final

from homeassistant.components.sensor import (
    CONF_STATE_CLASS,
    DEVICE_CLASSES_SCHEMA,
    DOMAIN as SENSOR_DOMAIN,
    PLATFORM_SCHEMA,
    STATE_CLASSES_SCHEMA,
    SensorEntity,
    SensorStateClass
)

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_UNIQUE_ID,
    CONF_USERNAME,
    CONF_VALUE_TEMPLATE,
    CONF_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
    CONF_NAME,
    CONF_COMMAND,
    CONF_DEVICE_CLASS,
    CONF_SCAN_INTERVAL
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template_entity import (
    TEMPLATE_SENSOR_BASE_SCHEMA,
    TemplateSensor
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.template import Template
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

_LOGGER = logging.getLogger(__name__)

# DEFAULT VALUES
DEFAULT_NAME = 'SSH'
DEFAULT_SSH_PORT = 22
DEFAULT_KEY = '/config/alcazar-switch'
DEFAULT_USERNAME = 'cumulus'
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
CONF_COMMAND_TIMEOUT = 30

CONF_KEY: Final = "key"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_SSH_PORT): cv.port,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_KEY, default=DEFAULT_KEY): cv.string,
        vol.Optional(CONF_COMMAND): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
).extend(TEMPLATE_SENSOR_BASE_SCHEMA.schema)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:

    """Set up the SSH Sensor"""
    if sensor_config := config:
        # Deprecated Yaml Issue Catch
        async_create_issue(
            hass,
            SENSOR_DOMAIN,
            "deprecated_yaml_sensor",
            breaks_in_ha_version="2023.12.0",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_platform_yaml",
            translation_placeholders={"platform": SENSOR_DOMAIN}
        )
    if discovery_info:
        sensor_config = discovery_info
    
    name: str = sensor_config[CONF_NAME]
    command: str = sensor_config[CONF_COMMAND]
    unit: str | None = sensor_config.get(CONF_UNIT_OF_MEASUREMENT)
    value_template: Template | None = sensor_config.get(CONF_VALUE_TEMPLATE)
    if value_template:
        value_template.hass = hass
    command_timeout: int = CONF_COMMAND_TIMEOUT
    unique_id: str | None = sensor_config.get(CONF_UNIQUE_ID)
    scan_interval: timedelta = sensor_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    state_class: SensorStateClass | None = sensor_config.get(CONF_STATE_CLASS)
    host: str = sensor_config.get(CONF_HOST)
    username: str = sensor_config.get(CONF_USERNAME)
    key: str = sensor_config.get(CONF_KEY)

    data = SSHData(hass,
        command,
        command_timeout,
        host,
        username,
        key)

    trigger_entity_config = {
        CONF_UNIQUE_ID: unique_id,
        CONF_NAME: name,
        CONF_DEVICE_CLASS: sensor_config.get(CONF_DEVICE_CLASS),
    }

    async_add_entities(
        [
            SSHSensor(
                hass,
                unique_id,
                data,
                trigger_entity_config,
                unit,
                state_class,
                value_template,
                scan_interval,
            )
        ]
    )


class SSHSensor(TemplateSensor):
    """SSH Sensor Class"""
    _attr_should_poll = True

    def __init__(
        self,
        hass,
        unique_id,
        data,
        config: ConfigType,
        unit_of_measurement: str | None,
        state_class: SensorStateClass | None,
        value_template: Template | None,
        scan_interval: timedelta,
    ) -> None:
        """Initialize the sensor"""
        super().__init__(hass, config=config, unique_id=unique_id, fallback_name=DEFAULT_NAME)
        self.data = data
        self._attr_extra_state_attributes = {}
        self._attr_native_value = None
        self._value_template = value_template
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_state_class = state_class
        self._scan_interval = scan_interval
        self._process_updates: asyncio.Lock | None = None
        self._run_updates: bool = True

    @property
    def native_value(self):
        return self.data.value

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass"""
        await super().async_added_to_hass()
        await self._update_entity_state()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._update_entity_state,
                self._scan_interval,
                name=f"SSH Sensor - {self.name}",
                cancel_on_shutdown=True,
            ),
        )

    async def _update_entity_state(self, *args) -> None:
        """Update the state of the entity"""
        if self._run_updates:
            asyncio.create_task(asyncio.to_thread(self.async_update))
            await self.hass.async_add_executor_job(self.data.update)
            value = self.data.value
            self.async_write_ha_state()
        else:
            return
            _LOGGER.warning("Updates Blocked")

    async def async_update(self) -> None:
        await self.hass.async_add_executor_job(self.data.update)
        value = self.data.value

        if self._value_template:
            self._attr_native_value = (
                self._value_template.async_render_with_possible_json_value(
                    value,
                    None,
                )
            )
        else: # No template provided
            self._attr_native_value = value

        self.async_write_ha_state()

class SSHData:
    def __init__(
        self, 
        hass: HomeAssistant,
        command: str,
        command_timeout: int,
        host: str,
        username: str,
        key: str
    ) -> None:
        """Initialize the data object"""
        self.value: str | None = None
        self.hass = hass
        self.command = command
        self.timeout = command_timeout
        self._host = host
        self._connected = False
        self._key = key
        self._ssh = None
        self._username = username

        # Create ssh private key
        try:
            self._ssh_key = paramiko.Ed25519Key.from_private_key_file(self._key)
        except FileNotFoundError as err:
            _LOGGER.error("SSH Key Not Found...")

    def _connect(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(self._host, username=self._username, pkey=self._ssh_key)
            self._ssh = client
            self._connected = True
        except Exception as err:
            _LOGGER.error(f"Failed to Connect SSH Error: {str(err)}")

    def _disconnect(self):
        """Disconnect the SSH connection"""
        try:
            self._ssh.logout()
        except Exception:
            pass
        finally:
            self._ssh = None
            self._connected = False

    def update(self) -> None:
        """Get the latest data with the specified command"""
        try:
            if not self._connected:
                self._connect()

            # NOTE: There are some cases where we still haven't connected at this point
            #       Because the scan interval is small, it will just fail to fetch once, and catch on the next cycle
            stdin, stdout, stderr = self._ssh.exec_command(self.command, self.timeout)
            
            for line in stdout:
                value = line.strip('\n')

            self.value = value
        except Exception as err:
            _LOGGER.error(f"Failed to Update SSH Error: {str(err)}")
        