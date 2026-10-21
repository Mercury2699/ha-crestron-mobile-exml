"""Crestron Mobile EXML Home Assistant Integration.

Connects to Crestron 2-Series, 3-Series, and 4-Series control processors
via the standard Crestron Mobile (EXML) protocol on port 41790.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ANALOG_JOIN,
    CONF_CLOSE_JOIN,
    CONF_COMPANION_DOWN,
    CONF_COMPANION_TOGGLE,
    CONF_COMPANION_UP,
    CONF_COVERS,
    CONF_DOWN_JOIN,
    CONF_HOST,
    CONF_LIGHTS,
    CONF_LINKED_OFF,
    CONF_OPEN_JOIN,
    CONF_PASSCODE,
    CONF_PORT,
    CONF_RAMP_TIME,
    CONF_STOP_JOIN,
    CONF_TOGGLE_JOIN,
    CONF_UNIQUE_ID,
    CONF_UP_JOIN,
    DEFAULT_PORT,
    DEFAULT_RAMP_TIME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

BOOL_RE = re.compile(r'<bool\s+id="(\d+)"\s+value="(true|false)"', re.IGNORECASE)
I32_RE = re.compile(r'<i32\s+id="(\d+)"[^>]*>(-?\d+)</i32>', re.IGNORECASE)

LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TOGGLE_JOIN): cv.positive_int,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_UP_JOIN): cv.positive_int,
        vol.Optional(CONF_DOWN_JOIN): cv.positive_int,
        vol.Optional(CONF_RAMP_TIME, default=DEFAULT_RAMP_TIME): vol.Coerce(float),
        vol.Optional(CONF_COMPANION_TOGGLE, default=[]): vol.All(cv.ensure_list, [cv.positive_int]),
        vol.Optional(CONF_COMPANION_UP, default=[]): vol.All(cv.ensure_list, [cv.positive_int]),
        vol.Optional(CONF_COMPANION_DOWN, default=[]): vol.All(cv.ensure_list, [cv.positive_int]),
        vol.Optional(CONF_LINKED_OFF, default=[]): vol.All(cv.ensure_list, [cv.positive_int]),
    }
)

COVER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ANALOG_JOIN): cv.positive_int,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_OPEN_JOIN): cv.positive_int,
        vol.Optional(CONF_CLOSE_JOIN): cv.positive_int,
        vol.Optional(CONF_STOP_JOIN): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_PASSCODE, default="1234"): cv.string,
                vol.Optional(CONF_LIGHTS, default=[]): vol.All(cv.ensure_list, [LIGHT_SCHEMA]),
                vol.Optional(CONF_COVERS, default=[]): vol.All(cv.ensure_list, [COVER_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class CrestronExmlHub:
    """Manages the persistent TCP connection to the Crestron EXML port."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, passcode: str) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.passcode = passcode
        self.digital_state: dict[int, bool] = {}
        self.analog_state: dict[int, int] = {}
        self._listeners: list[Callable[[], None]] = []
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stopping = False

    def register_listener(self, cb: Callable[[], None]) -> None:
        """Register a callback for join state updates."""
        self._listeners.append(cb)

    def _notify_listeners(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception as err:
                _LOGGER.error("Error in Crestron state listener: %s", err)

    async def start(self) -> None:
        """Start the background connection worker."""
        self._stopping = False
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Gracefully disconnect and stop the worker."""
        self._stopping = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            if self._writer:
                self._writer.close()
                await self._writer.wait_closed()
                self._writer = None

    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                _LOGGER.info("Connecting to Crestron processor at %s:%s", self.host, self.port)
                reader, writer = await asyncio.open_connection(self.host, self.port)
                self._writer = writer

                # Read initial banner
                await asyncio.wait_for(reader.read(4096), timeout=5.0)

                # Send connectRequest with passcode
                auth_xml = (
                    f'<cresnet><control><comm><connectRequest>'
                    f'<passcode>{self.passcode}</passcode>'
                    f'<mode><status>01</status></mode>'
                    f'</connectRequest></comm></control></cresnet>'
                )
                writer.write(auth_xml.encode("utf-8"))
                await writer.drain()
                await asyncio.wait_for(reader.read(4096), timeout=5.0)

                # Request full state snapshot
                upd_xml = '<cresnet><data><updateCommand><updateRequest></updateRequest></updateCommand></data></cresnet>'
                writer.write(upd_xml.encode("utf-8"))
                await writer.drain()

                _LOGGER.info("Successfully authenticated to Crestron processor at %s", self.host)

                while not self._stopping:
                    try:
                        data = await asyncio.wait_for(reader.read(4096), timeout=25.0)
                        if not data:
                            raise ConnectionResetError("EOF received from Crestron processor")
                        text = data.decode("utf-8", errors="ignore")
                        self._process_incoming(text)
                    except asyncio.TimeoutError:
                        # Send heartbeat ping
                        hb = '<cresnet><control><comm><heartbeatRequest/></comm></control></cresnet>'
                        writer.write(hb.encode("utf-8"))
                        await writer.drain()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.warning("Crestron connection interrupted (%s), retrying in 5s...", err)
                async with self._lock:
                    self._writer = None
                await asyncio.sleep(5.0)

    def _process_incoming(self, text: str) -> None:
        changed = False
        if "<clearAll" in text:
            self.digital_state.clear()
            changed = True

        for match in BOOL_RE.finditer(text):
            jid = int(match.group(1))
            val = match.group(2).lower() == "true"
            if self.digital_state.get(jid) != val:
                self.digital_state[jid] = val
                changed = True

        for match in I32_RE.finditer(text):
            jid = int(match.group(1))
            val = int(match.group(2))
            if self.analog_state.get(jid) != val:
                self.analog_state[jid] = val
                changed = True

        if changed:
            self._notify_listeners()

    async def set_digital(self, join_id: int, value: bool) -> None:
        """Assert or de-assert a digital join signal."""
        async with self._lock:
            if not self._writer:
                return
            val_str = "true" if value else "false"
            msg = f'<cresnet><data><bool id="{join_id}" value="{val_str}"/></data></cresnet>'
            self._writer.write(msg.encode("utf-8"))
            await self._writer.drain()

    async def pulse_digital(self, join_id: int, duration: float = 0.15) -> None:
        """Pulse a digital join signal (momentary button press)."""
        await self.set_digital(join_id, True)
        await asyncio.sleep(duration)
        await self.set_digital(join_id, False)

    async def set_analog(self, join_id: int, value: int) -> None:
        """Set a 16-bit analog join value (0-65535)."""
        async with self._lock:
            if not self._writer:
                return
            val = max(0, min(65535, int(value)))
            msg = f'<cresnet><data><i32 id="{join_id}" value="{val}">{val}</i32></data></cresnet>'
            self._writer.write(msg.encode("utf-8"))
            await self._writer.drain()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Crestron Mobile EXML integration from YAML."""
    conf = config.get(DOMAIN)
    if not conf:
        return True

    host = conf[CONF_HOST]
    port = conf[CONF_PORT]
    passcode = str(conf[CONF_PASSCODE])

    hub = CrestronExmlHub(hass, host, port, passcode)
    hass.data[DOMAIN] = {
        "hub": hub,
        CONF_LIGHTS: conf.get(CONF_LIGHTS, []),
        CONF_COVERS: conf.get(CONF_COVERS, []),
    }
    await hub.start()

    if conf.get(CONF_LIGHTS):
        hass.async_create_task(async_load_platform(hass, "light", DOMAIN, {}, config))
    if conf.get(CONF_COVERS):
        hass.async_create_task(async_load_platform(hass, "cover", DOMAIN, {}, config))

    return True
