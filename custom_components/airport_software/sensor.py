"""Sensor platform for airport-software."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_QUALIFICATION_STATUS, CONF_ENABLE_TOWER_DUTY, DOMAIN
from .coordinator import AirportSoftwareCoordinator, QualificationCoordinator, TowerDutyCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: AirportSoftwareCoordinator = entry_data["coordinator"]

    entities: list[SensorEntity] = []
    for tail_number in coordinator.data:
        entities.append(AirportSoftwareConditionSensor(coordinator, tail_number))
        entities.append(AirportSoftwareRemainingHoursSensor(coordinator, tail_number))

    if entry.data[CONF_ENABLE_TOWER_DUTY]:
        entities.append(TowerDutyNowSensor(entry_data["tower_duty_coordinator"], entry.entry_id))

    if entry.data[CONF_ENABLE_QUALIFICATION_STATUS]:
        entities.append(
            NextExpiringQualificationSensor(
                entry_data["qualification_coordinator"], entry.entry_id
            )
        )

    async_add_entities(entities)


def _device_info(tail_number: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, tail_number)},
        name=tail_number,
        manufacturer="airport-software DS GmbH",
    )


class AirportSoftwareConditionSensor(
    CoordinatorEntity[AirportSoftwareCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "condition"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_condition"
        self._attr_device_info = _device_info(tail_number)

    @property
    def native_value(self) -> str | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.condition if status else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        status = self.coordinator.data.get(self._tail_number)
        if not status:
            return {}
        return {"open_info_count": status.open_info_count, "remarks": status.remarks}


class AirportSoftwareRemainingHoursSensor(
    CoordinatorEntity[AirportSoftwareCoordinator], SensorEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "remaining_hours"
    _attr_native_unit_of_measurement = "h"

    def __init__(self, coordinator: AirportSoftwareCoordinator, tail_number: str) -> None:
        super().__init__(coordinator)
        self._tail_number = tail_number
        self._attr_unique_id = f"{tail_number}_remaining_hours"
        self._attr_device_info = _device_info(tail_number)

    @property
    def native_value(self) -> float | None:
        status = self.coordinator.data.get(self._tail_number)
        return status.remaining_hours if status else None


class TowerDutyNowSensor(CoordinatorEntity[TowerDutyCoordinator], SensorEntity):
    """Who's currently on Flugleitung (tower) duty. Club-wide, not per-aircraft."""

    _attr_has_entity_name = True
    _attr_translation_key = "tower_duty_now"

    def __init__(self, coordinator: TowerDutyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_tower_duty_now"

    @property
    def available(self) -> bool:
        """Keep showing the last known value through a transient failed poll.

        Only unavailable before the first-ever successful fetch — after
        that, a failed update (e.g. a parse hiccup) leaves coordinator.data
        untouched, so we keep displaying it rather than going blank.
        """
        return self.coordinator.data is not None

    @property
    def native_value(self) -> str | None:
        duty = self.coordinator.data
        if duty is None:
            return None
        return duty.on_duty if duty.on_duty else "none"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        duty = self.coordinator.data
        return {"note": duty.note} if duty else {}


class NextExpiringQualificationSensor(
    CoordinatorEntity[QualificationCoordinator], SensorEntity
):
    """Days remaining until the soonest-expiring license/qualification item."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_expiring_qualification"
    _attr_native_unit_of_measurement = "d"

    def __init__(self, coordinator: QualificationCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_next_expiring_qualification"

    @property
    def available(self) -> bool:
        """Keep showing the last known value through a transient failed poll.

        Only unavailable before the first-ever successful fetch — after
        that, a failed update (e.g. a parse hiccup) leaves coordinator.data
        untouched, so we keep displaying it rather than going blank.
        """
        return self.coordinator.data is not None

    @property
    def native_value(self) -> int | None:
        qualification = self.coordinator.data
        return qualification.days_remaining if qualification else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        qualification = self.coordinator.data
        if not qualification:
            return {}
        return {
            "label": qualification.label,
            "subcode": qualification.subcode,
            "end_date": qualification.end_date,
            "severity": qualification.severity,
        }
