"""Services for the SpielerPlus integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from . import const
from .api import SpielerplusError
from .models import Participation

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_PARTICIPATION = "set_participation"

_STATUS_MAP: dict[str, Participation] = {
    "zusage": Participation.ZUSAGE,
    "unsicher": Participation.UNSICHER,
    "absage": Participation.ABSAGE,
}

_SCHEMA = vol.Schema(
    {
        # Populated by HA from the service call's ``target``.
        vol.Optional("entity_id"): vol.Any(cv.entity_id, cv.entity_ids),
        vol.Required("event_id"): cv.string,
        vol.Required("status"): vol.In(list(_STATUS_MAP)),
        vol.Optional("event_type"): cv.string,
        vol.Optional("reason", default=""): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the ``spielerplus.set_participation`` service once."""
    if hass.services.has_service(const.DOMAIN, SERVICE_SET_PARTICIPATION):
        return

    async def _async_handle(call: ServiceCall) -> None:
        entity_ids = call.data.get("entity_id")
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        if not entity_ids:
            raise ServiceValidationError(
                "Es muss eine Entität eines SpielerPlus-Mitglieds angegeben werden"
            )

        registry = er.async_get(hass)
        status = _STATUS_MAP[call.data["status"]]
        event_id = call.data["event_id"]

        for entity_id in entity_ids:
            registry_entry = registry.async_get(entity_id)
            if (
                registry_entry is None
                or registry_entry.platform != const.DOMAIN
                or not registry_entry.unique_id
            ):
                raise ServiceValidationError(f"Unbekannte Entität: {entity_id}")

            parts = registry_entry.unique_id.split(":")
            if len(parts) < 2:
                raise ServiceValidationError(f"Ungültige Entität: {entity_id}")
            config_entry_id, member_id = parts[0], parts[1]

            runtime = hass.data.get(const.DOMAIN, {}).get(config_entry_id)
            if runtime is None:
                raise ServiceValidationError(
                    f"Kein laufender SpielerPlus-Eintrag für {entity_id}"
                )
            coordinator = runtime["coordinator"]
            client = runtime["client"]

            member_data = (coordinator.data or {}).get(member_id)
            if member_data is None:
                raise ServiceValidationError(f"Kein Mitglied zu {entity_id} gefunden")

            target = next(
                (event for event in member_data.events if event.event.id == event_id),
                None,
            )
            if target is None:
                raise ServiceValidationError(
                    f"Termin {event_id} ist nicht (mehr) in den kommenden Terminen"
                )
            if target.event.deadline_passed:
                raise ServiceValidationError(
                    f"Die Frist zum Zu-/Absagen für Termin {event_id} ist abgelaufen"
                )

            try:
                await client.async_set_participation(
                    member_id=member_id,
                    event_type=call.data.get("event_type") or target.event.type,
                    event_id=event_id,
                    status=status,
                    reason=call.data.get("reason", ""),
                )
            except SpielerplusError as err:
                raise HomeAssistantError(str(err)) from err

            await coordinator.async_request_refresh()

    hass.services.async_register(
        const.DOMAIN,
        SERVICE_SET_PARTICIPATION,
        _async_handle,
        schema=_SCHEMA,
        supports_response=SupportsResponse.NONE,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the service when the last entry is unloaded."""
    if hass.services.has_service(const.DOMAIN, SERVICE_SET_PARTICIPATION):
        hass.services.async_remove(const.DOMAIN, SERVICE_SET_PARTICIPATION)
