"""Sensor platform for the SpielerPlus integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import const, logic
from .coordinator import SpielerplusCoordinator
from .entity import SpielerplusEntity
from .models import ResolvedEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the next-training and next-event sensors per member."""
    coordinator: SpielerplusCoordinator = hass.data[const.DOMAIN][entry.entry_id][
        "coordinator"
    ]
    entities: list[SpielerplusNextEventSensor] = []
    for member_id in coordinator.members:
        entities.append(SpielerplusNextEventSensor(coordinator, entry, member_id, "training"))
        entities.append(SpielerplusNextEventSensor(coordinator, entry, member_id, None))
    async_add_entities(entities)


class SpielerplusNextEventSensor(SpielerplusEntity, SensorEntity):
    """Start of the next event, optionally restricted to trainings."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: SpielerplusCoordinator,
        entry: ConfigEntry,
        member_id: str,
        event_type: str | None,
    ) -> None:
        super().__init__(coordinator, entry, member_id)
        self._event_type = event_type
        suffix = "naechstes_training" if event_type == "training" else "naechster_termin"
        self._attr_unique_id = f"{entry.entry_id}:{member_id}:sensor:{suffix}"
        self._attr_name = (
            "Nächstes Training" if event_type == "training" else "Nächster Termin"
        )

    @property
    def _next_event(self) -> ResolvedEvent | None:
        return logic.next_event(self.events, dt_util.now(), type_=self._event_type)

    @property
    def native_value(self) -> datetime | None:
        event = self._next_event
        return event.start if event is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        _, attributes = logic.sensor_state(self._next_event, self.events)
        return attributes
