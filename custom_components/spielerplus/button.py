"""Button platform for the SpielerPlus integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import const, logic
from .api import SpielerplusClient
from .coordinator import SpielerplusCoordinator
from .entity import SpielerplusEntity
from .models import Participation, ResolvedEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the accept/decline buttons per member."""
    data = hass.data[const.DOMAIN][entry.entry_id]
    coordinator: SpielerplusCoordinator = data["coordinator"]
    client: SpielerplusClient = data["client"]

    entities: list[SpielerplusParticipationButton] = []
    for member_id in coordinator.members:
        entities.append(
            SpielerplusParticipationButton(
                coordinator, client, entry, member_id, Participation.ZUSAGE
            )
        )
        entities.append(
            SpielerplusParticipationButton(
                coordinator, client, entry, member_id, Participation.ABSAGE
            )
        )
    async_add_entities(entities)


class SpielerplusParticipationButton(SpielerplusEntity, ButtonEntity):
    """Confirm or decline attendance for the next upcoming event."""

    def __init__(
        self,
        coordinator: SpielerplusCoordinator,
        client: SpielerplusClient,
        entry: ConfigEntry,
        member_id: str,
        status: Participation,
    ) -> None:
        super().__init__(coordinator, entry, member_id)
        self._client = client
        self._status = status
        accept = status is Participation.ZUSAGE
        self._attr_unique_id = (
            f"{entry.entry_id}:{member_id}:button:{'zusagen' if accept else 'absagen'}"
        )
        self._attr_name = "Zusagen" if accept else "Absagen"
        self._attr_icon = "mdi:check-circle-outline" if accept else "mdi:close-circle-outline"

    @property
    def _target_event(self) -> ResolvedEvent | None:
        return logic.next_event(self.events, dt_util.now())

    @property
    def available(self) -> bool:
        event = self._target_event
        return (
            super().available
            and event is not None
            and not event.event.deadline_passed
        )

    async def async_press(self) -> None:
        event = self._target_event
        if event is None:
            raise HomeAssistantError("Es gibt keinen kommenden Termin zum Zu-/Absagen")
        if event.event.deadline_passed:
            raise HomeAssistantError(
                "Die Frist zum Zu-/Absagen für diesen Termin ist abgelaufen"
            )
        await self._client.async_set_participation(
            member_id=self._member_id,
            event_type=event.event.type,
            event_id=event.event.id,
            status=self._status,
        )
        await self.coordinator.async_request_refresh()
