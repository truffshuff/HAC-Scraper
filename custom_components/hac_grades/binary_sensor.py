"""Binary sensor platform for HAC Grades."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STUDENT_ID, CONF_QUARTER, DATA_COORDINATOR, DOMAIN
from .coordinator import HACDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def _update_entity_metadata_with_binary_sensors(
    hass: HomeAssistant,
    student_id: str,
) -> None:
    """Update entity metadata with binary sensor information.

    Args:
        hass: Home Assistant instance
        student_id: The student ID
    """
    try:
        # Determine the metadata file path (in the integration's custom_components folder)
        # This keeps all HAC Grades files together
        integration_dir = Path(__file__).parent
        metadata_file = integration_dir / "hac_entity_registry.json"

        # Load existing metadata (async)
        if not await hass.async_add_executor_job(metadata_file.exists):
            _LOGGER.debug(
                "Metadata file does not exist yet, binary sensor info will be "
                "added when sensors create it"
            )
            return

        def _load_metadata():
            with open(metadata_file, "r") as f:
                return json.load(f)

        metadata = await hass.async_add_executor_job(_load_metadata)

        # Update student metadata with binary sensor info
        if "students" in metadata and student_id in metadata["students"]:
            metadata["students"][student_id]["has_binary_sensors"] = True
            metadata["students"][student_id]["binary_sensor_types"] = [
                desc.key for desc in OVERALL_BINARY_SENSORS + COURSE_BINARY_SENSORS
            ]
            metadata["last_updated"] = datetime.now().isoformat()

            # Write back (async)
            def _write_metadata():
                with open(metadata_file, "w") as f:
                    json.dump(metadata, f, indent=2)

            await hass.async_add_executor_job(_write_metadata)

            _LOGGER.info("Updated metadata with binary sensor info for student %s", student_id)

    except Exception as err:
        _LOGGER.error("Failed to update metadata with binary sensors: %s", err, exc_info=True)


@dataclass
class HACGradesBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes HAC Grades binary sensor entity."""

    is_on_fn: Callable[[dict[str, Any]], bool] | None = None
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


# Overall binary sensors
OVERALL_BINARY_SENSORS = []

# Per-course binary sensors
COURSE_BINARY_SENSORS = [
    HACGradesBinarySensorEntityDescription(
        key="has_missing_assignments",
        name="Has Missing Assignments",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:file-alert",
        is_on_fn=lambda course: (
            course.get("not_hand_in", 0) > 0
            or course.get("not_yet_graded", 0) > 0
            or course.get("too_late_to_count", 0) > 0
            or course.get("score_below_fifty", 0) > 0
        ),
        attributes_fn=lambda course: {
            "not_hand_in": course.get("not_hand_in", 0),
            "not_yet_graded": course.get("not_yet_graded", 0),
            "too_late_to_count": course.get("too_late_to_count", 0),
            "score_below_fifty": course.get("score_below_fifty", 0),
            "missing_details": [
                {
                    "title": a["title"],
                    "due_date": a["due_date"],
                    "status": a["status"],
                    "category": a["category"],
                }
                for a in course.get("assignments", [])
                if a.get("status") in ["NHI", "NYG", "TLTC", "SBF"]
            ],
        },
    ),
    HACGradesBinarySensorEntityDescription(
        key="grade_below_threshold",
        name="Grade Below 90%",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        is_on_fn=lambda course: (
            course.get("hac_overall_percentage") is not None
            and course.get("hac_overall_percentage") < 90
        ),
        attributes_fn=lambda course: {
            "current_grade": course.get("hac_overall_percentage"),
            "threshold": 90,
        },
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HAC Grades binary sensors."""
    coordinator: HACDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[BinarySensorEntity] = []

    # Get student ID for entity IDs
    student_id = entry.data[CONF_STUDENT_ID]
    configured_quarter = entry.data.get(CONF_QUARTER, "q2").lower()

    # Get all available quarters from the coordinator data
    all_quarters_data = coordinator.data.get("all_quarters", {}) if coordinator.data else {}

    # If no all_quarters data yet (first load), just use configured quarter
    quarters_to_create = list(all_quarters_data.keys()) if all_quarters_data else [configured_quarter.upper()]

    # Create binary sensors for each quarter that has data
    for quarter in quarters_to_create:
        quarter_lower = quarter.lower()

        # Add overall binary sensors for this quarter
        for description in OVERALL_BINARY_SENSORS:
            entities.append(
                HACOverallBinarySensor(
                    coordinator,
                    entry,
                    description,
                    student_id,
                    quarter_lower,
                )
            )

        # Add per-course binary sensors for this quarter
        quarter_data = all_quarters_data.get(quarter, {})
        courses = quarter_data.get("courses", [])

        for course in courses:
            course_index = course.get("course_index")
            course_name = course.get("course", f"Course {course_index}")

            for description in COURSE_BINARY_SENSORS:
                entities.append(
                    HACCourseBinarySensor(
                        coordinator,
                        entry,
                        description,
                        course_index,
                        course_name,
                        student_id,
                        quarter_lower,
                    )
                )

    async_add_entities(entities)

    # Update metadata with binary sensor information (async)
    await _update_entity_metadata_with_binary_sensors(hass, student_id)


class HACOverallBinarySensor(CoordinatorEntity[HACDataUpdateCoordinator], BinarySensorEntity):
    """Representation of an overall HAC binary sensor."""

    entity_description: HACGradesBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HACGradesBinarySensorEntityDescription,
        student_id: str,
        quarter: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._student_id = student_id
        self._quarter = quarter
        # Include quarter in unique_id to avoid collisions when creating multiple quarter sensors
        self._attr_unique_id = f"{entry.entry_id}_{quarter}_{description.key}"
        # Use student ID and quarter in the suggested object_id for entity_id
        self._attr_suggested_object_id = f"student_{student_id}_{quarter}_{description.key}"
        # Add quarter to the friendly name
        self._attr_name = f"{description.name} ({quarter.upper()})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HAC - Student {student_id}",
            manufacturer="Home Access Center",
            model="Grade Portal",
        )

    @property
    def _quarter_data(self) -> dict[str, Any]:
        """Get the data for this sensor's quarter."""
        if not self.coordinator.data:
            return {}

        # Get data from all_quarters
        all_quarters = self.coordinator.data.get("all_quarters", {})
        quarter_data = all_quarters.get(self._quarter.upper(), {})

        return quarter_data

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.entity_description.is_on_fn:
            return self.entity_description.is_on_fn(self._quarter_data)
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        attrs = {
            "quarter": self._quarter.upper(),
            "student_id": self._student_id,
        }
        if self.entity_description.attributes_fn:
            custom_attrs = self.entity_description.attributes_fn(self._quarter_data)
            if custom_attrs:
                attrs.update(custom_attrs)
        return attrs


class HACCourseBinarySensor(CoordinatorEntity[HACDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a per-course HAC binary sensor."""

    entity_description: HACGradesBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HACGradesBinarySensorEntityDescription,
        course_index: int,
        course_name: str,
        student_id: str,
        quarter: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._course_index = course_index
        self._course_name = course_name
        self._student_id = student_id
        self._quarter = quarter
        # Include quarter in unique_id to avoid collisions when creating multiple quarter sensors
        self._attr_unique_id = f"{entry.entry_id}_{quarter}_course_{course_index}_{description.key}"

        # Create a clean course name for entity_id (remove course codes, lowercase, underscores)
        clean_course_name = course_name.split(" - ")[-1].strip().lower()
        clean_course_name = clean_course_name.replace(" ", "_").replace("(", "").replace(")", "")
        # Use student ID + quarter + course name in the suggested object_id for entity_id
        self._attr_suggested_object_id = f"student_{student_id}_{quarter}_{clean_course_name}_{description.key}"

        # Add quarter to the friendly name
        self._attr_name = f"{description.name} ({quarter.upper()})"

        # Create device for this course
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{quarter}_course_{course_index}")},
            name=f"{course_name} ({quarter.upper()})",
            manufacturer="Home Access Center",
            model="Course",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def _course_data(self) -> dict[str, Any] | None:
        """Get the course data from coordinator."""
        if not self.coordinator.data:
            return None

        # Get data from all_quarters for this specific quarter
        all_quarters = self.coordinator.data.get("all_quarters", {})
        quarter_data = all_quarters.get(self._quarter.upper(), {})
        courses = quarter_data.get("courses", [])

        for course in courses:
            if course.get("course_index") == self._course_index:
                return course

        return None

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        course_data = self._course_data
        if not course_data:
            return False

        if self.entity_description.is_on_fn:
            return self.entity_description.is_on_fn(course_data)
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        course_data = self._course_data
        if not course_data:
            return None

        if self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(course_data)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._course_data is not None
