"""DataUpdateCoordinator for airport-software."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AirportSoftwareClient, InvalidAuth
from .const import DOMAIN, POLL_INTERVAL_SECONDS
from .models import AircraftStatus

_LOGGER = logging.getLogger(__name__)


class AirportSoftwareCoordinator(DataUpdateCoordinator[dict[str, AircraftStatus]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        client: AirportSoftwareClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.config_entry = entry
        self._client = client

    async def _async_update_data(self) -> dict[str, AircraftStatus]:
        try:
            statuses = await self._client.async_get_status()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "airport-software rejected the configured credentials"
            ) from err
        except Exception as err:  # network or parse errors: retry next interval
            raise UpdateFailed(f"error communicating with airport-software: {err}") from err
        return {status.tail_number: status for status in statuses}
