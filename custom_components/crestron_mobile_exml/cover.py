"""Cover platform for Crestron Mobile EXML integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import CrestronExmlHub
from .const import (
    CONF_ANALOG_JOIN,
    CONF_CLOSE_JOIN,
    CONF_COVERS,
    CONF_OPEN_JOIN,
    CONF_STOP_JOIN,
    CONF_UNIQUE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Crestron covers platform."""
    domain_data = hass.data[DOMAIN]
    hub: CrestronExmlHub = domain_data["hub"]
    covers_config: list[dict[str, Any]] = domain_data[CONF_COVERS]

    entities = [CrestronExmlCover(hub, cfg) for cfg in covers_config]
    async_add_entities(entities)


class CrestronExmlCover(CoverEntity):
    """Representation of a Crestron motorized shade, drape, or blind."""

    _attr_device_class = CoverDeviceClass.SHADE
    _attr_should_poll = False

    def __init__(self, hub: CrestronExmlHub, cfg: dict[str, Any]) -> None:
        self._hub = hub
        self._name = cfg[CONF_NAME]
        self._analog_join = cfg[CONF_ANALOG_JOIN]
        self._open_join = cfg.get(CONF_OPEN_JOIN)
        self._close_join = cfg.get(CONF_CLOSE_JOIN)
        self._stop_join = cfg.get(CONF_STOP_JOIN)

        uid = cfg.get(CONF_UNIQUE_ID) or f"crestron_cover_{self._analog_join}"
        self._attr_unique_id = uid
        self._attr_name = self._name

        features = CoverEntityFeature.SET_POSITION
        if self._open_join:
            features |= CoverEntityFeature.OPEN
        if self._close_join:
            features |= CoverEntityFeature.CLOSE
        if self._stop_join:
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    async def async_added_to_hass(self) -> None:
        """Register listener for Crestron state updates."""
        self._hub.register_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=fully open)."""
        raw = self._hub.analog_state.get(self._analog_join)
        if raw is None:
            return None
        # Crestron scales 0 to 65535
        return int(round((raw / 65535.0) * 100.0))

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the shade."""
        if self._open_join:
            await self._hub.pulse_digital(self._open_join)
        else:
            await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the shade."""
        if self._close_join:
            await self._hub.pulse_digital(self._close_join)
        else:
            await self.async_set_cover_position(position=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop moving the shade."""
        if self._stop_join:
            await self._hub.pulse_digital(self._stop_join)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Set cover position (0-100%)."""
        position = kwargs.get("position", 0)
        # Convert 0-100% to 0-65535
        raw_val = int(round((position / 100.0) * 65535.0))
        raw_val = max(0, min(65535, raw_val))
        await self._hub.set_analog(self._analog_join, raw_val)
