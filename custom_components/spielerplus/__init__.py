"""The SpielerPlus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from . import const
from .api import SpielerplusAuthError, SpielerplusClient, SpielerplusError
from .coordinator import SpielerplusCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SpielerPlus from a config entry."""
    session = async_create_clientsession(hass)
    client = SpielerplusClient(
        session,
        entry.data[const.CONF_EMAIL],
        entry.data[const.CONF_PASSWORD],
    )
    try:
        await client.async_login()
    except SpielerplusAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SpielerplusError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SpielerplusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await async_setup_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = hass.data[const.DOMAIN].pop(entry.entry_id, None)
    if data is not None:
        # The session was created for this entry; close it on unload so a
        # reload does not leak the connector until HA shuts down.
        await data["session"].close()
    if not hass.data[const.DOMAIN]:
        await async_unload_services(hass)
    return True
