"""DataUpdateCoordinator for the SpielerPlus integration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import const
from .api import SpielerplusAuthError, SpielerplusClient, SpielerplusError
from .logic import resolve_events, upcoming
from .models import ResolvedEvent, SpMember

_LOGGER = logging.getLogger(__name__)

_LABEL_RE = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


@dataclass(slots=True)
class MemberData:
    """Everything the entities need for one member."""

    member: SpMember
    events: list[ResolvedEvent]


def member_from_label(member_id: str, label: str) -> SpMember:
    """Rebuild a member from its stored ``Name (Team)`` label."""
    match = _LABEL_RE.match(label)
    if match is not None:
        return SpMember(id=member_id, name=match.group(1), team=match.group(2))
    return SpMember(id=member_id, name=label, team="")


class SpielerplusCoordinator(DataUpdateCoordinator[dict[str, MemberData]]):
    """Poll the upcoming events of every configured member."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SpielerplusClient
    ) -> None:
        interval = timedelta(
            minutes=int(entry.options.get(const.CONF_SCAN_INTERVAL, 15))
        )
        super().__init__(
            hass,
            _LOGGER,
            name=const.DOMAIN,
            update_interval=interval,
            config_entry=entry,
        )
        self.client = client
        self.members: dict[str, SpMember] = {
            member_id: member_from_label(member_id, label)
            for member_id, label in entry.data.get(const.CONF_MEMBERS, {}).items()
        }

    async def _async_update_data(self) -> dict[str, MemberData]:
        now = dt_util.now()
        today = now.date()
        data: dict[str, MemberData] = {}

        for member_id, member in self.members.items():
            try:
                await self.client.async_select_member(member_id)
                events = await self.client.async_get_events()
            except SpielerplusAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except SpielerplusError as err:
                raise UpdateFailed(str(err)) from err

            data[member_id] = MemberData(
                member=member,
                events=upcoming(
                    resolve_events(events, today, dt_util.DEFAULT_TIME_ZONE), now
                ),
            )

        return data
