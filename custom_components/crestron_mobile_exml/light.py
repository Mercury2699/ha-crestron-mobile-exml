"""Light platform for Crestron Mobile EXML integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import CrestronExmlHub
from .const import (
    CONF_COMPANION_DOWN,
    CONF_COMPANION_TOGGLE,
    CONF_COMPANION_UP,
    CONF_DOWN_JOIN,
    CONF_LIGHTS,
    CONF_LINKED_OFF,
    CONF_RAMP_TIME,
    CONF_TOGGLE_JOIN,
    CONF_UNIQUE_ID,
    CONF_UP_JOIN,
    DEFAULT_RAMP_TIME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

LOOP_STEP = 0.05       # Control loop sampling period in seconds
TOLERANCE = 4          # ~1.5% brightness deadband
CEILING_EXTRA = 0.4    # Extra hold time to hit 100% ceiling
OFF_GUARD_TIME = 3.5   # Guard against double-toggle while hardware fades out


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Crestron lights platform."""
    domain_data = hass.data[DOMAIN]
    hub: CrestronExmlHub = domain_data["hub"]
    lights_config: list[dict[str, Any]] = domain_data[CONF_LIGHTS]

    entities = [CrestronExmlLight(hub, cfg) for cfg in lights_config]
    async_add_entities(entities)


class CrestronExmlLight(LightEntity):
    """Representation of a Crestron switched or dimmed lighting load."""

    _attr_should_poll = False

    def __init__(self, hub: CrestronExmlHub, cfg: dict[str, Any]) -> None:
        self._hub = hub
        self._name = cfg[CONF_NAME]
        self._toggle_join = cfg[CONF_TOGGLE_JOIN]
        self._up_join = cfg.get(CONF_UP_JOIN)
        self._down_join = cfg.get(CONF_DOWN_JOIN)
        self._ramp_time = float(cfg.get(CONF_RAMP_TIME, DEFAULT_RAMP_TIME))

        self._companion_toggle_joins: list[int] = cfg.get(CONF_COMPANION_TOGGLE, [])
        self._companion_up_joins: list[int] = cfg.get(CONF_COMPANION_UP, [])
        self._companion_down_joins: list[int] = cfg.get(CONF_COMPANION_DOWN, [])
        self._linked_off_joins: list[int] = cfg.get(CONF_LINKED_OFF, [])

        uid = cfg.get(CONF_UNIQUE_ID) or f"crestron_light_{self._toggle_join}"
        self._attr_unique_id = uid
        self._attr_name = self._name

        # If dim up/down joins are provided, enable brightness control
        if self._up_join and self._down_join:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._ramp_rate = 255.0 / self._ramp_time
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._ramp_rate = 0.0

        self._est: float = 0.0
        self._target: int | None = None
        self._held_dir: int = 0
        self._worker: asyncio.Task | None = None
        self._off_guard_until: float = 0.0

    async def async_added_to_hass(self) -> None:
        """Register listeners upon addition to Home Assistant."""
        self._hub.register_listener(self._handle_update)
        self._est = 255.0 if self._fb_on() else 0.0

    def _fb_on(self) -> bool:
        if self._hub.digital_state.get(self._toggle_join, False):
            return True
        return any(self._hub.digital_state.get(j, False) for j in self._companion_toggle_joins)

    @callback
    def _handle_update(self) -> None:
        if self._worker is None:
            if self._fb_on():
                if self._est <= 0:
                    self._est = 255.0
            else:
                self._est = 0.0
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        if self._off_guard_until and self._now() < self._off_guard_until:
            return False
        return self._fb_on()

    @property
    def brightness(self) -> int | None:
        if not self.is_on:
            return None
        if self._worker is not None and self._target is not None:
            return self._target
        return max(1, min(255, int(round(self._est))))

    def _now(self) -> float:
        return asyncio.get_running_loop().time()

    async def _press(self, direction: int) -> None:
        if not self._up_join or not self._down_join:
            return
        joins = (
            [self._up_join, *self._companion_up_joins]
            if direction > 0
            else [self._down_join, *self._companion_down_joins]
        )
        for j in joins:
            await self._hub.set_digital(j, True)
        self._held_dir = direction

    async def _release(self) -> None:
        if self._held_dir == 0 or not self._up_join or not self._down_join:
            return
        joins = (
            [self._up_join, *self._companion_up_joins]
            if self._held_dir > 0
            else [self._down_join, *self._companion_down_joins]
        )
        self._held_dir = 0
        for j in joins:
            await self._hub.set_digital(j, False)

    async def _stop_worker(self) -> None:
        task = self._worker
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker = None
        await self._release()

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._ramp_loop())

    async def _ramp_loop(self) -> None:
        """Hold raise/lower signals until the estimated level reaches target."""
        try:
            last = self._now()
            extra_until: float | None = None
            while True:
                target = self._target
                if target is None:
                    break
                diff = target - self._est
                want = 1 if diff > 0 else -1

                reached = abs(diff) <= TOLERANCE or (
                    self._held_dir != 0 and want != self._held_dir and abs(diff) <= TOLERANCE * 2
                )
                if reached:
                    if target >= 250 and self._held_dir > 0:
                        if extra_until is None:
                            extra_until = self._now() + CEILING_EXTRA
                        if self._now() < extra_until:
                            await asyncio.sleep(LOOP_STEP)
                            continue
                    break
                extra_until = None

                if want != self._held_dir:
                    await self._release()
                    await self._press(want)
                    last = self._now()

                await asyncio.sleep(LOOP_STEP)
                now = self._now()
                self._est = max(0.0, min(255.0, self._est + want * self._ramp_rate * (now - last)))
                last = now
        finally:
            await self._release()
            if self._target is not None:
                self._est = float(self._target)
            _LOGGER.debug("%s: ramp complete, estimated level=%.0f", self.name, self._est)
            self._target = None
            self._worker = None
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on or adjust brightness."""
        target = kwargs.get(ATTR_BRIGHTNESS)
        while self._off_guard_until and self._now() < self._off_guard_until and self._fb_on():
            await asyncio.sleep(0.1)
        self._off_guard_until = 0.0

        # Simple ON or switch-only load
        if target is None or not (self._up_join and self._down_join):
            if self._worker is not None:
                await self._stop_worker()
            if not self._fb_on():
                _LOGGER.debug("%s: pulse toggle ON", self.name)
                await self._hub.pulse_digital(self._toggle_join)
                self._est = 255.0
            self.async_write_ha_state()
            return

        target = max(1, min(255, int(target)))
        if not self._fb_on() and self._worker is None:
            self._est = 0.0

        _LOGGER.debug("%s: request dimming to %d (current est=%.0f)", self.name, target, self._est)
        self._target = target
        self._ensure_worker()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._stop_worker()
        self._target = None

        now = self._now()
        if now < self._off_guard_until:
            _LOGGER.debug("%s: turn_off ignored (fade-out in progress)", self.name)
            return

        pulsed = False
        if self._hub.digital_state.get(self._toggle_join, False):
            await self._hub.pulse_digital(self._toggle_join)
            pulsed = True
        for j in self._companion_toggle_joins:
            if self._hub.digital_state.get(j, False):
                await self._hub.pulse_digital(j)
                pulsed = True

        for j in self._linked_off_joins:
            if self._hub.digital_state.get(j, False):
                await self._hub.pulse_digital(j)

        if pulsed:
            _LOGGER.debug("%s: pulse toggle OFF", self.name)
            self._off_guard_until = now + OFF_GUARD_TIME
        self._est = 0.0
        self.async_write_ha_state()
