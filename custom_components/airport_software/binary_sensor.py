"""Binary sensor platform for airport-software."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_FREE_REST_OF_DAY, DOMAIN
from .coordinator import AirportSoftwareCoordinator


def _device_info(tail_number: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, tail_number)},
        name=tail_number,
        manufacturer="airport-software DS GmbH",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AirportSoftwareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[BinarySensorEntity] = [
        AirportSoftwareInUseBinarySensor(coordinator, tail_number)
        for tail_number in coordinator.data
    ]
    if entry.data[CONF_ENABLE_FREE_REST_OF_DAY]:
        entities.extend(
            AirportSoftwareFreeRestOfDayBinarySensor(coordinator, tail_number)
            for tail_number in coordinator.data
        )
    async_add_entities(entities)


class AirportSoftwareInUseBinarySensor(
    CoordinatorEntity[AirportSoftwareCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "in_use"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_in_use"
        self._attr_device_info = _device_info(tail_number)

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.in_use if status else None


class AirportSoftwareFreeRestOfDayBinarySensor(
    CoordinatorEntity[AirportSoftwareCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "free_rest_of_day"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_free_rest_of_day"
        self._attr_device_info = _device_info(tail_number)

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.free_rest_of_day if status else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        status = self.coordinator.data.get(self._tail_number)
        if not status:
            return {}
        return {"available_from": status.available_from_today}
