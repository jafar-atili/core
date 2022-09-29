"""Support for SwitchBee cover."""

from __future__ import annotations

from typing import Any, cast

from switchbee.api import SwitchBeeError, SwitchBeeTokenError
from switchbee.const import SomfyCommand
from switchbee.device import SwitchBeeShutter, SwitchBeeSomfy

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SwitchBeeCoordinator
from .entity import SwitchBeeDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SwitchBee switch."""
    coordinator: SwitchBeeCoordinator = hass.data[DOMAIN][entry.entry_id]
    switchbee_covers_tuple: list[tuple[Any, Any]] = []

    for device in coordinator.data.values():
        if isinstance(device, SwitchBeeShutter):
            switchbee_covers_tuple.append((device, SwitchBeeCoverEntity))
        elif isinstance(device, SwitchBeeSomfy):
            switchbee_covers_tuple.append((device, SwitchBeeSomfyEntity))

    async_add_entities(
        device_class(device, coordinator)
        for device, device_class in switchbee_covers_tuple
    )


class SwitchBeeSomfyEntity(SwitchBeeDeviceEntity[SwitchBeeSomfy], CoverEntity):
    """Representation of a SwitchBee Somfy cover."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.CLOSE | CoverEntityFeature.OPEN | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        device: SwitchBeeSomfy,
        coordinator: SwitchBeeCoordinator,
    ) -> None:
        """Initialize the SwitchBee cover."""
        super().__init__(device, coordinator)
        self._attr_current_cover_position = 0
        self._attr_is_closed = True

    async def _fire_somfy_command(self, command: str) -> None:
        """Async function to fire Somfy device command."""
        try:
            await self.coordinator.api.set_state(self._device.id, command)
        except (SwitchBeeError, SwitchBeeTokenError) as exp:
            raise HomeAssistantError(
                f"Failed to fire {command} for {self.name}, {str(exp)}"
            ) from exp

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        return await self._fire_somfy_command(SomfyCommand.UP)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        return await self._fire_somfy_command(SomfyCommand.DOWN)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop a moving cover."""
        return await self._fire_somfy_command(SomfyCommand.MY)


class SwitchBeeCoverEntity(SwitchBeeDeviceEntity[SwitchBeeShutter], CoverEntity):
    """Representation of a SwitchBee cover."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.CLOSE
        | CoverEntityFeature.OPEN
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        device: SwitchBeeShutter,
        coordinator: SwitchBeeCoordinator,
    ) -> None:
        """Initialize the SwitchBee cover."""
        super().__init__(device, coordinator)
        self._attr_current_cover_position = 0
        self._attr_is_closed = True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    def _update_from_coordinator(self) -> None:
        """Update the entity attributes from the coordinator data."""

        coordinator_device = cast(
            SwitchBeeShutter, self.coordinator.data[self._device.id]
        )

        if coordinator_device.position == -1:
            self._check_if_became_offline()
            return

        # check if the device was offline (now online) and bring it back
        self._check_if_became_online()

        self._attr_current_cover_position = coordinator_device.position

        if self._attr_current_cover_position == 0:
            self._attr_is_closed = True
        else:
            self._attr_is_closed = False
        super()._handle_coordinator_update()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._attr_current_cover_position == 100:
            return

        await self.async_set_cover_position(position=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self._attr_current_cover_position == 0:
            return

        await self.async_set_cover_position(position=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop a moving cover."""
        # to stop the shutter, we just interrupt it with any state during operation
        await self.async_set_cover_position(
            position=self._attr_current_cover_position, force=True
        )

        # fetch data from the Central Unit to get the new position
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Async function to set position to cover."""
        if (
            self._attr_current_cover_position == kwargs[ATTR_POSITION]
            and "force" not in kwargs
        ):
            return
        try:
            await self.coordinator.api.set_state(self._device.id, kwargs[ATTR_POSITION])
        except (SwitchBeeError, SwitchBeeTokenError) as exp:
            raise HomeAssistantError(
                f"Failed to set {self._attr_name} position to {str(kwargs[ATTR_POSITION])}, error: {str(exp)}"
            ) from exp
        else:
            cast(
                SwitchBeeShutter, self.coordinator.data[self._device.id]
            ).position = kwargs[ATTR_POSITION]
            self.coordinator.async_set_updated_data(self.coordinator.data)
            self.async_write_ha_state()
