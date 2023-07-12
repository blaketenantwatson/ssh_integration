from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any
import logging
import paramiko
from typing import Final

import voluptuous as vol

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    ENTITY_ID_FORMAT,
    PLATFORM_SCHEMA,
    SwitchEntity,
)

from homeassistant.const import (
    CONF_COMMAND_OFF,
    CONF_COMMAND_ON,
    CONF_COMMAND_STATE,
    CONF_FRIENDLY_NAME,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    CONF_VALUE_TEMPLATE,
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
)

from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.template_entity import TemplateEntity

_LOGGER = logging.getLogger(__name__)

# DEFAULT VALUES
CONF_COMMAND_TIMEOUT = None
DEFAULT_TIMEOUT = 60
DEFAULT_SSH_PORT = 22
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
SCAN_INTERVAL = timedelta(seconds=30)
CONF_KEY: Final = "key"
DEFAULT_KEY = '/config/alcazar-switch'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_COMMAND_OFF, default="true"): cv.string,
        vol.Optional(CONF_COMMAND_ON, default="true"): cv.string,
        vol.Optional(CONF_COMMAND_STATE): cv.string,
        vol.Optional(CONF_FRIENDLY_NAME): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
        vol.Optional(CONF_COMMAND_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Required(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_SSH_PORT): cv.port,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_KEY, default=DEFAULT_KEY): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)#.extend()

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:

    """Set up the SSH Switch"""
    if switch_config := config:
        # Deprecated Yaml Issue Catch
        async_create_issue(
            hass,
            SWITCH_DOMAIN,
            "deprecated_yaml_switch",
            breaks_in_ha_version="2023.12.0",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_platform_yaml",
            translation_placeholders={"platform": SWITCH_DOMAIN}
        )
    if discovery_info:
        switch_config = discovery_info

    command_off: str = switch_config.get(CONF_COMMAND_OFF)
    command_on: str = switch_config.get(CONF_COMMAND_ON)
    command_state: str = switch_config.get(CONF_COMMAND_STATE)
    value_template: Template = switch_config.get(CONF_VALUE_TEMPLATE)
    if value_template:
        value_template.hass = hass
    command_timeout: int = switch_config.get(CONF_COMMAND_TIMEOUT)
    unique_id: str = switch_config.get(CONF_UNIQUE_ID)
    host: str = switch_config.get(CONF_HOST)
    port: int = switch_config.get(CONF_PORT)
    name: str = switch_config.get(CONF_NAME) or switch_config.get(CONF_FRIENDLY_NAME)
    username: str = switch_config.get(CONF_USERNAME)
    key: str = switch_config.get(CONF_KEY)
    scan_interval: timedelta = switch_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    password: str = switch_config.get(CONF_PASSWORD)

    data = SSHData(
        hass,
        command_on,
        command_off,
        command_state,
        command_timeout,
        host,
        username,
        key,
        port,
        password,
    )

    trigger_entity_config = {
        CONF_UNIQUE_ID: unique_id,
        CONF_NAME: Template(name, hass),
    }

    async_add_entities(
        [
            SSHSwitch(
                hass,
                trigger_entity_config,
                unique_id,
                command_on,
                command_off,
                command_state,
                value_template,
                command_timeout,
                scan_interval,
                data,
            )
        ]
    )


class SSHSwitch(TemplateEntity, SwitchEntity):
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        object_id: str,
        command_on: str,
        command_off: str,
        command_state: str | None,
        value_template: Template | None,
        command_timeout: int,
        scan_interval: timedelta,
        data: SSHData,
    ) -> None:
        super().__init__(hass, config=config, fallback_name=None, unique_id=object_id)
        self.hass: HomeAssistant = hass
        self.entity_id = ENTITY_ID_FORMAT.format(object_id)
        self._attr_is_on = True
        self._command_on = command_on
        self._command_off = command_off
        self._command_state = command_state
        self._value_template = value_template
        self._timeout = command_timeout
        self._scan_interval = scan_interval
        self._process_updates: asyncio.Lock | None = None
        self._run_updates: bool = True
        self.data = data
        
    async def async_added_to_hass(self) -> None:
        """Called when entity about to be added to hass"""
        await super().async_added_to_hass()
        if self._command_state:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass,
                    self._update_entity_state,
                    self._scan_interval,
                    name=f"SSH Switch - {self.name}",
                    cancel_on_shutdown=True,
                ),
            )

    async def _update_entity_state(self, *args) -> None:
        """Update the state of the entity"""
        if self._run_updates:
            await self.hass.async_add_executor_job(self.data.update)
            value = self.data.value

            if self._value_template:
                self._attr_native_value = (
                    self._value_template.async_render_with_possible_json_value(
                        value,
                        None
                    )
                )
            else: # No template provided
                self._attr_native_value = value

            self.async_write_ha_state()

        else:
            return
    
    async def async_update(self) -> None:
        await self._update_entity_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on"""
        await self.hass.async_add_executor_job(self.data.turn_on)

        self._attr_is_on = True

        if self._value_template:
            self._attr_native_value = (
                self._value_template.async_render_with_possible_json_value(
                    self.data.value,
                    None
                )
            )
        else: # No template provided
            self._attr_native_value = self.data.value

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.data.turn_off)

        self._attr_is_on = False

        if self._value_template:
            self._attr_native_value = (
                self._value_template.async_render_with_possible_json_value(
                    self.data.value,
                    None
                )
            )
        else: # No template provided
            self._attr_native_value = self.data.value

        self.async_write_ha_state()


class SSHData:
    def __init__(
        self,
        hass: HomeAssistant,
        command_on: str,
        command_off: str,
        command_state: str,
        command_timeout: int,
        host: str,
        username: str,
        key: str,
        port: int,
        password: str,
    ) -> None:
        self.value: str | None = None
        self.hass: HomeAssistant = hass
        self._command_on: str = command_on
        self._command_off: str = command_off
        self._command_state: str = command_state
        self._host: str = host
        self._key: str = key
        self._port: int = port
        self._ssh = None
        self._username: str = username
        self._timeout = command_timeout
        self._switch_state = True
        self._connected = False
        self._password = password

        if not self._password: # Using private key instead of password
            try:
                self._ssh_key = paramiko.Ed25519Key.from_private_key_file(self._key)
            except FileNotFoundError as err:
                _LOGGER.error("SSH Key Not Found")
        
    def _connect(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self._password: # Using provided password
                client.connect(self._host, port=self._port, username=self._username, password=self._password)
            else: # Using private key
                client.connect(self._host, port=self._port, username=self._username, pkey=self._ssh_key)
            self._ssh = client
            self._connected = True
        except Exception as err:
            _LOGGER.error(f"Generic SSH Error: {str(err)}")

    def _disconnect(self):
        try:
            self._ssh.logout()
        except Exception:
            pass
        finally:
            self._ssh = None
            self._connected = False

    def update(self) -> None:
        """Run the specified command to update the data"""
        try:
            if not self._connected:
                self._connect()

            _, stdout, _ = self._ssh.exec_command(self._command_state, self._timeout)

            self.value = stdout.read().decode()
        except Exception as err:
            _LOGGER.error(f"Generic SSH Error: {str(err)}")

    def turn_on(self) -> None:
        """Run the specified payload on command"""
        try:
            if not self._connected:
                self._connect()

            _, _, _ = self._ssh.exec_command(self._command_on, self._timeout)

            self._switch_state = False

        except Exception as err:
            _LOGGER.error(f"Generic SSH Error: {str(err)}")

    def turn_off(self) -> None:
        """Run the specified payload off command"""
        try:
            if not self._connected:
                self._connect()

            _, _, _ = self._ssh.exec_command(self._command_off, self._timeout)

            self._switch_state = True

        except Exception as err:
            _LOGGER.error(f"Generic SSH Error: {str(err)}")