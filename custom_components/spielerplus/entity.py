"""Shared base entity for the SpielerPlus platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .coordinator import MemberData, SpielerplusCoordinator
from .models import ResolvedEvent


class SpielerplusEntity(CoordinatorEntity[SpielerplusCoordinator]):
    """Base class: one device per member, shared lookup helpers."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SpielerplusCoordinator,
        entry: ConfigEntry,
        member_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._member_id = member_id
        member = coordinator.members[member_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(const.DOMAIN, f"{entry.entry_id}:{member_id}")},
            name=f"SpielerPlus {member.name}",
            manufacturer="SpielerPlus",
            model=member.team or None,
        )

    @property
    def member_data(self) -> MemberData | None:
        """Coordinator data for this member, if available."""
        return (self.coordinator.data or {}).get(self._member_id)

    @property
    def events(self) -> list[ResolvedEvent]:
        """Upcoming events of this member, if available."""
        data = self.member_data
        return data.events if data is not None else []
