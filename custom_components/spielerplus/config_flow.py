"""Config and options flow for the SpielerPlus integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import const, logic
from .api import SpielerplusAuthError, SpielerplusClient, SpielerplusError
from .models import SpMember

_LOGGER = logging.getLogger(__name__)

_SCAN_INTERVALS = ["5", "10", "15", "30", "60"]


def _credentials_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(const.CONF_EMAIL): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL)
            ),
            vol.Required(const.CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


class SpielerplusConfigFlow(ConfigFlow, domain=const.DOMAIN):
    """Two-step flow: credentials, then member selection."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._members: list[SpMember] = []

    async def _async_verify(self, email: str, password: str) -> str | None:
        """Log in and return an error key, or ``None`` on success."""
        session = async_create_clientsession(self.hass)
        client = SpielerplusClient(session, email, password)
        try:
            await client.async_login()
            self._members = await client.async_get_members()
        except SpielerplusAuthError:
            return "invalid_auth"
        except SpielerplusError:
            return "cannot_connect"
        if not self._members:
            return "no_members"
        return None

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Ask for the account credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[const.CONF_EMAIL]
            password = user_input[const.CONF_PASSWORD]
            error = await self._async_verify(email, password)
            if error is None:
                self._email = email
                self._password = password
                return await self.async_step_members()
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=_credentials_schema(), errors=errors
        )

    async def async_step_members(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which members to track."""
        if user_input is not None:
            labels = logic.member_options(self._members)
            selected = {
                member_id: labels[member_id]
                for member_id in user_input[const.CONF_MEMBERS]
            }
            return self.async_create_entry(
                title=f"SpielerPlus ({self._email})",
                data={
                    const.CONF_EMAIL: self._email,
                    const.CONF_PASSWORD: self._password,
                    const.CONF_MEMBERS: selected,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(const.CONF_MEMBERS): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=member.id, label=member.label)
                            for member in self._members
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="members", data_schema=schema)

    async def async_step_reauth(
        self, entry_data: dict
    ) -> ConfigFlowResult:
        """Start the reauth flow with the stored email."""
        self._email = entry_data.get(const.CONF_EMAIL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh password after authentication failed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[const.CONF_PASSWORD]
            error = await self._async_verify(self._email or "", password)
            if error is None:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={const.CONF_PASSWORD: password},
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(const.CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "SpielerplusOptionsFlow":
        """Return the options flow."""
        return SpielerplusOptionsFlow()


class SpielerplusOptionsFlow(OptionsFlow):
    """Only the polling interval is configurable."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = str(self.config_entry.options.get(const.CONF_SCAN_INTERVAL, 15))
        schema = vol.Schema(
            {
                vol.Required(const.CONF_SCAN_INTERVAL, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=_SCAN_INTERVALS, mode=SelectSelectorMode.DROPDOWN
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
