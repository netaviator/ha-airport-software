"""The airport-software integration."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import AirportSoftwareClient
from .const import (
    CONF_BASE_URL,
    CONF_ENABLE_FREE_REST_OF_DAY,
    CONF_ENABLE_QUALIFICATION_STATUS,
    CONF_ENABLE_TOWER_DUTY,
    CONF_FREE_REST_OF_DAY_CUTOFF,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from .coordinator import AirportSoftwareCoordinator, QualificationCoordinator, TowerDutyCoordinator

PLATFORMS = ["binary_sensor", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # A dedicated session (not HA's shared one) so this integration's
    # authenticated cookies never mix with other integrations' requests
    # to the same or other hosts. All coordinators below share this one
    # client/session — they're one login, not three.
    session = aiohttp.ClientSession()
    client = AirportSoftwareClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        enable_free_rest_of_day=entry.data[CONF_ENABLE_FREE_REST_OF_DAY],
        free_rest_of_day_cutoff=entry.data[CONF_FREE_REST_OF_DAY_CUTOFF],
    )
    coordinator = AirportSoftwareCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    # Both of these are optional, "fun" side features (not per-aircraft
    # data): a failure fetching them on startup shouldn't block the whole
    # integration (including aircraft data) from loading, so a transient
    # ConfigEntryNotReady here is logged and left to resolve on the next
    # normal poll rather than re-raised.
    tower_duty_coordinator: TowerDutyCoordinator | None = None
    if entry.data[CONF_ENABLE_TOWER_DUTY]:
        tower_duty_coordinator = TowerDutyCoordinator(hass, entry, client)
        try:
            await tower_duty_coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.warning(
                "Could not fetch tower duty data during setup; will retry on next poll"
            )

    qualification_coordinator: QualificationCoordinator | None = None
    if entry.data[CONF_ENABLE_QUALIFICATION_STATUS]:
        qualification_coordinator = QualificationCoordinator(hass, entry, client)
        try:
            await qualification_coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.warning(
                "Could not fetch qualification status during setup; will retry on next poll"
            )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
        "tower_duty_coordinator": tower_duty_coordinator,
        "qualification_coordinator": qualification_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["session"].close()
    return unload_ok
