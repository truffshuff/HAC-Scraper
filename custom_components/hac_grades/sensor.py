"""Sensor platform for HAC Grades."""
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_STUDENT_ID, CONF_QUARTER, DATA_COORDINATOR, DOMAIN
from .coordinator import HACDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _clean_course_name(course_name: str) -> str:
    """Clean course name by removing leading numbers and extra whitespace.

    Examples:
        "2 Spanish II" -> "Spanish II"
        "5 Science 7" -> "Science 7"
        "AR017C - 1 Art 7" -> "Art 7"
    """
    # Split on " - " to get the part after course code
    if " - " in course_name:
        course_name = course_name.split(" - ")[-1].strip()

    # Remove leading number and space (e.g., "2 Spanish II" -> "Spanish II")
    parts = course_name.split(None, 1)  # Split on first whitespace
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[1]

    return course_name


async def _write_entity_metadata(
    hass: HomeAssistant,
    student_id: str,
    all_quarters_data: dict[str, Any],
) -> None:
    """Write entity metadata to a JSON file for dashboard generation.

    Args:
        hass: Home Assistant instance
        student_id: The student ID
        all_quarters_data: Dictionary of all quarters data from coordinator
    """
    try:
        # Determine the metadata file path (in the integration's custom_components folder)
        # This keeps all HAC Grades files together
        integration_dir = Path(__file__).parent
        metadata_file = integration_dir / "hac_entity_registry.json"

        # Load existing metadata if it exists
        existing_metadata = {}
        if await hass.async_add_executor_job(metadata_file.exists):
            try:
                def _load_metadata():
                    with open(metadata_file, "r") as f:
                        return json.load(f)
                existing_metadata = await hass.async_add_executor_job(_load_metadata)
            except (json.JSONDecodeError, IOError) as err:
                _LOGGER.warning("Could not load existing metadata file: %s", err)

        # Build student metadata
        student_metadata = {
            "student_id": student_id,
            "quarters": {},
        }

        for quarter, quarter_data in all_quarters_data.items():
            courses = quarter_data.get("courses", [])

            course_list = []
            for course in courses:
                course_name = course.get("course", "")
                clean_name = _clean_course_name(course_name)

                # Apply same cleaning logic as entity creation
                clean_course_name = clean_name.lower().replace(" ", "_")
                clean_course_name = "".join(c for c in clean_course_name if c.isalnum() or c == "_")

                course_list.append({
                    "clean_name": clean_course_name,
                    "display_name": clean_name,
                    "original_name": course_name,
                    "course_index": course.get("course_index"),
                })

            student_metadata["quarters"][quarter] = {
                "course_count": len(courses),
                "courses": course_list,
            }

        # Update the metadata structure
        if "students" not in existing_metadata:
            existing_metadata["students"] = {}

        existing_metadata["students"][student_id] = student_metadata
        existing_metadata["last_updated"] = datetime.now().isoformat()

        # Write the metadata file (async)
        def _write_metadata():
            with open(metadata_file, "w") as f:
                json.dump(existing_metadata, f, indent=2)

        await hass.async_add_executor_job(_write_metadata)

        _LOGGER.info(
            "Wrote entity metadata to %s for student %s with %d quarters",
            metadata_file,
            student_id,
            len(student_metadata["quarters"])
        )

    except Exception as err:
        _LOGGER.error("Failed to write entity metadata: %s", err, exc_info=True)


def _format_missing_summary(data: dict[str, Any]) -> str:
    """Format missing assignments summary with counts."""
    courses = data.get("courses", [])

    # Calculate totals
    total_nhi = sum(c.get("not_hand_in", 0) for c in courses)
    total_nyg = sum(c.get("not_yet_graded", 0) for c in courses)
    total_tltc = sum(c.get("too_late_to_count", 0) for c in courses)
    total_sbf = sum(c.get("score_below_fifty", 0) for c in courses)

    return f"⚠️ {total_nhi} NHI, {total_nyg} NYG, ⏰ {total_tltc} TLTC, 📉 {total_sbf} SBF"


def _format_missing_by_course(data: dict[str, Any]) -> str:
    """Format missing assignments summary by course."""
    courses = data.get("courses", [])
    lines = []

    for course in courses:
        course_name = _clean_course_name(course.get("course", "Unknown"))
        nhi = course.get("not_hand_in", 0)
        nyg = course.get("not_yet_graded", 0)
        tltc = course.get("too_late_to_count", 0)
        sbf = course.get("score_below_fifty", 0)

        # Build line for this course if it has any issues
        parts = []
        if nhi > 0:
            parts.append(f"⚠️ {nhi} NHI")
        if nyg > 0:
            parts.append(f"{nyg} NYG")
        if tltc > 0:
            parts.append(f"⏰ {tltc} TLTC")
        if sbf > 0:
            parts.append(f"📉 {sbf} SBF")

        if parts:
            lines.append(f"{course_name}: {', '.join(parts)}")

    return "\n".join(lines) if lines else "No missing assignments"


def _format_missing_details(data: dict[str, Any]) -> str:
    """Format detailed list of all missing assignments.

    Prioritizes critical statuses (NHI, TLTC) over less urgent ones (NYG, SBF).
    Truncates to fit within 255 character limit if needed.
    Adds summary of cut off assignments by status type.
    """
    courses = data.get("courses", [])

    # Map status codes to emoji, labels, and priority (lower number = higher priority)
    status_map = {
        "NHI": ("⚠️", "NHI", 1),      # Highest priority
        "TLTC": ("⏰", "TLTC", 2),    # Second priority
        "NYG": ("", "NYG", 3),      # Third priority
        "SBF": ("📉", "SBF", 4)      # Lowest priority
    }

    # Collect all items with their priority and status
    all_items = []

    for course in courses:
        course_name = _clean_course_name(course.get("course", "Unknown"))
        assignments = course.get("assignments", [])

        for assignment in assignments:
            status = assignment.get("status", "")

            # Only include problematic statuses
            if status in status_map:
                emoji, label, priority = status_map[status]
                title = assignment.get("title", "Unknown Assignment")
                due_date = assignment.get("due_date", "No due date")

                # Truncate long titles
                max_title_len = 80
                if len(title) > max_title_len:
                    title = title[:max_title_len-3] + "..."

                # Truncate long course names
                max_course_len = 20
                if len(course_name) > max_course_len:
                    course_name_short = course_name[:max_course_len-3] + "..."
                else:
                    course_name_short = course_name

                item_text = f"{emoji} {label}: {course_name_short}: {title}: {due_date}"
                all_items.append((priority, item_text, status))

    if not all_items:
        return "No missing assignments"

    # Sort by priority (NHI and TLTC first, then SBF, then NYG)
    all_items.sort(key=lambda x: x[0])

    # Build the final string, truncating if it exceeds 255 chars
    max_length = 255
    items = []
    current_length = 0
    truncated_by_status = {}

    # First pass: add items and track what gets cut off
    for priority, item_text, status in all_items:
        # Calculate length including separator
        separator = " | " if items else ""
        new_length = current_length + len(separator) + len(item_text)

        if new_length > max_length:
            # Stop adding items if we'd exceed the limit
            # Track what got cut off by status
            truncated_by_status[status] = truncated_by_status.get(status, 0) + 1
        else:
            items.append(item_text)
            current_length = new_length

    # If we truncated items, we need to make sure summary fits
    if truncated_by_status:
        # Build summary: "and X more NHI, Y more NYG"
        summary_parts = []
        # Order by priority
        for status in ["NHI", "TLTC", "NYG", "SBF"]:
            count = truncated_by_status.get(status, 0)
            if count > 0:
                summary_parts.append(f"{count} more {status}")

        summary = " | " + " and ".join(summary_parts)

        # Check if we can fit the summary
        test_length = current_length + len(summary)

        # If summary doesn't fit, remove items from the end until it does
        while test_length > max_length and items:
            removed_item = items.pop()
            current_length -= len(removed_item)
            if items:  # Account for separator
                current_length -= len(" | ")

            # Find the status of the removed item and update counts
            for status in ["NHI", "TLTC", "NYG", "SBF"]:
                if f" {status}:" in removed_item:
                    truncated_by_status[status] = truncated_by_status.get(status, 0) + 1
                    break

            # Rebuild summary with updated counts
            summary_parts = []
            for status in ["NHI", "TLTC", "NYG", "SBF"]:
                count = truncated_by_status.get(status, 0)
                if count > 0:
                    summary_parts.append(f"{count} more {status}")

            summary = " | " + " and ".join(summary_parts)
            test_length = current_length + len(summary)

        # If we still can't fit it, try abbreviated version
        if test_length > max_length:
            total_truncated = sum(truncated_by_status.values())
            summary = f" | {total_truncated} more"
            test_length = current_length + len(summary)

            # Remove more items if needed
            while test_length > max_length and items:
                removed_item = items.pop()
                current_length -= len(removed_item)
                if items:
                    current_length -= len(" | ")
                total_truncated += 1
                summary = f" | {total_truncated} more"
                test_length = current_length + len(summary)

        result = " | ".join(items) + summary

        # Log warning if items were truncated
        _LOGGER.warning(
            "Missing assignment details truncated to %d chars (limit: %d). "
            "Included %d/%d items. Cut off by status: %s",
            len(result),
            max_length,
            len(items),
            len(all_items),
            truncated_by_status
        )

        return result

    return " | ".join(items)


def _format_days_since_update(data: dict[str, Any]) -> str:
    """Format days since update for each course."""
    courses = data.get("courses", [])
    lines = []

    for course in courses:
        course_name = _clean_course_name(course.get("course", "Unknown"))
        days = course.get("days_since_update")

        if days is not None:
            lines.append(f"{course_name}: {days} days")
        else:
            lines.append(f"{course_name}: Unknown")

    return "\n".join(lines) if lines else "No course data available"


@dataclass
class HACGradesSensorEntityDescription(SensorEntityDescription):
    """Describes HAC Grades sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


# Overall/Summary sensors
OVERALL_SENSORS = [
    HACGradesSensorEntityDescription(
        key="gpa",
        name="GPA",
        icon="mdi:school",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda data: data.get("overall_summary", {}).get("gpa_like_average"),
    ),
    HACGradesSensorEntityDescription(
        key="course_count",
        name="Total Courses",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("overall_summary", {}).get("course_count"),
    ),
    HACGradesSensorEntityDescription(
        key="max_grade",
        name="Highest Grade",
        icon="mdi:trophy",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda data: max(
            (c.get("hac_overall_percentage") or 0 for c in data.get("courses", [])),
            default=None,
        ),
    ),
    HACGradesSensorEntityDescription(
        key="min_grade",
        name="Lowest Grade",
        icon="mdi:alert",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda data: min(
            (c.get("hac_overall_percentage") or 100 for c in data.get("courses", []) if c.get("hac_overall_percentage")),
            default=None,
        ),
    ),
    HACGradesSensorEntityDescription(
        key="total_nhi",
        name="Total Not Handed In",
        icon="mdi:file-alert",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(c.get("not_hand_in", 0) for c in data.get("courses", [])),
    ),
    HACGradesSensorEntityDescription(
        key="total_nyg",
        name="Total Not Yet Graded",
        icon="mdi:file-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(c.get("not_yet_graded", 0) for c in data.get("courses", [])),
    ),
    HACGradesSensorEntityDescription(
        key="total_tltc",
        name="Total Too Late To Count",
        icon="mdi:clock-alert",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(c.get("too_late_to_count", 0) for c in data.get("courses", [])),
    ),
    HACGradesSensorEntityDescription(
        key="total_sbf",
        name="Total Score Below Fifty",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(c.get("score_below_fifty", 0) for c in data.get("courses", [])),
    ),
    HACGradesSensorEntityDescription(
        key="missing_summary",
        name="Missing Assignments Summary",
        icon="mdi:alert-box",
        value_fn=lambda data: _format_missing_summary(data),
    ),
    HACGradesSensorEntityDescription(
        key="missing_by_course",
        name="Missing Assignments by Course",
        icon="mdi:format-list-checks",
        value_fn=lambda data: _format_missing_by_course(data),
    ),
    HACGradesSensorEntityDescription(
        key="missing_details",
        name="Missing Assignment Details",
        icon="mdi:clipboard-text",
        value_fn=lambda data: _format_missing_details(data),
    ),
    HACGradesSensorEntityDescription(
        key="courses_updated_last_3_days",
        name="Courses Updated in Last 3 Days",
        icon="mdi:update",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len([
            c for c in data.get("courses", [])
            if c.get("days_since_update") is not None and c.get("days_since_update") <= 3
        ]),
    ),
    HACGradesSensorEntityDescription(
        key="days_since_update_by_course",
        name="Days Since Update by Course",
        icon="mdi:calendar-clock",
        value_fn=lambda data: _format_days_since_update(data),
    ),
    HACGradesSensorEntityDescription(
        key="course_list",
        name="Course List",
        icon="mdi:format-list-bulleted",
        value_fn=lambda data: ", ".join(
            c.get("course", "").split(" - ")[-1].strip()
            for c in data.get("courses", [])
        ),
    ),
]

# Per-course sensor descriptions
COURSE_SENSORS = [
    HACGradesSensorEntityDescription(
        key="grade",
        name="Grade",
        icon="mdi:certificate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: course.get("overall_percentage"),
        attributes_fn=lambda course: {
            "course_name": _clean_course_name(course.get("course", "Unknown")),
            "hac_grade": course.get("hac_overall_percentage"),
            "points_earned": course.get("hac_points_earned"),
            "points_possible": course.get("hac_points_possible"),
            "last_updated": course.get("hac_last_updated"),
            "days_since_update": course.get("days_since_update"),
        },
    ),
    HACGradesSensorEntityDescription(
        key="practice_score",
        name="Practice Category Score",
        icon="mdi:pencil",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: course.get("category_breakdown", {}).get("PRACTICE", {}).get("percentage"),
        attributes_fn=lambda course: course.get("category_breakdown", {}).get("PRACTICE", {}),
    ),
    HACGradesSensorEntityDescription(
        key="process_score",
        name="Process Category Score",
        icon="mdi:cog",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: course.get("category_breakdown", {}).get("PROCESS", {}).get("percentage"),
        attributes_fn=lambda course: course.get("category_breakdown", {}).get("PROCESS", {}),
    ),
    HACGradesSensorEntityDescription(
        key="product_score",
        name="Product Category Score",
        icon="mdi:package-variant",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: course.get("category_breakdown", {}).get("PRODUCT", {}).get("percentage"),
        attributes_fn=lambda course: course.get("category_breakdown", {}).get("PRODUCT", {}),
    ),
    HACGradesSensorEntityDescription(
        key="total_assignments",
        name="Total Assignments",
        icon="mdi:file-document-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: course.get("total_assignments"),
    ),
    HACGradesSensorEntityDescription(
        key="assignments_scored",
        name="Assignments Scored",
        icon="mdi:file-check",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: len([
            a for a in course.get("assignments", [])
            if a.get("status") == "Scored"
        ]),
    ),
    HACGradesSensorEntityDescription(
        key="assignments_pending",
        name="Assignments Pending",
        icon="mdi:file-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: len([
            a for a in course.get("assignments", [])
            if a.get("status") != "Scored"
        ]),
    ),
    HACGradesSensorEntityDescription(
        key="not_hand_in",
        name="Not Handed In",
        icon="mdi:file-alert",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: course.get("not_hand_in"),
        attributes_fn=lambda course: {
            "assignments": [
                {
                    "title": a["title"],
                    "due_date": a["due_date"],
                    "category": a["category"],
                }
                for a in course.get("assignments", [])
                if a.get("status") == "NHI"
            ]
        },
    ),
    HACGradesSensorEntityDescription(
        key="assignment_details",
        name="Assignment Details",
        icon="mdi:clipboard-list",
        value_fn=lambda course: course.get("total_assignments"),
        attributes_fn=lambda course: {
            "assignments": [
                {
                    "title": a["title"],
                    "due_date": a["due_date"],
                    "category": a["category"],
                    "score": a["score"],
                    "total_points": a["total_points"],
                    "percentage": a["percentage"],
                    "status": a["status"],
                }
                for a in course.get("assignments", [])
            ]
        },
    ),
    HACGradesSensorEntityDescription(
        key="assignment_category_statistics",
        name="Assignment Category Statistics",
        icon="mdi:chart-box",
        value_fn=lambda course: len(course.get("assignments", [])),
        attributes_fn=lambda course: {
            "categories": [
                {
                    "category": cat_name,
                    "count": len([a for a in course.get("assignments", []) if a.get("category") == cat_name]),
                    "scored": len([a for a in course.get("assignments", []) if a.get("category") == cat_name and a.get("status") == "Scored"]),
                    "pending": len([a for a in course.get("assignments", []) if a.get("category") == cat_name and a.get("status") != "Scored"]),
                    "avg_percentage": round(
                        sum(a.get("percentage", 0) or 0 for a in course.get("assignments", []) if a.get("category") == cat_name and a.get("status") == "Scored") /
                        len([a for a in course.get("assignments", []) if a.get("category") == cat_name and a.get("status") == "Scored"]) if len([a for a in course.get("assignments", []) if a.get("category") == cat_name and a.get("status") == "Scored"]) > 0 else 0,
                        1
                    ),
                    "earned_points": sum((a.get("score") or 0) for a in course.get("assignments", []) if a.get("category") == cat_name),
                    "total_points": sum((a.get("total_points") or 0) for a in course.get("assignments", []) if a.get("category") == cat_name),
                }
                for cat_name in sorted(set(a.get("category", "Unknown") for a in course.get("assignments", [])))
            ]
        },
    ),
    HACGradesSensorEntityDescription(
        key="highest_assignment_score",
        name="Highest Assignment Score",
        icon="mdi:trophy",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: max(
            (a.get("percentage") for a in course.get("assignments", []) if a.get("status") == "Scored" and a.get("percentage") is not None),
            default=None,
        ),
    ),
    HACGradesSensorEntityDescription(
        key="lowest_assignment_score",
        name="Lowest Assignment Score",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda course: min(
            (a.get("percentage") for a in course.get("assignments", []) if a.get("status") == "Scored" and a.get("percentage") is not None),
            default=None,
        ),
    ),
    HACGradesSensorEntityDescription(
        key="total_points_earned",
        name="Total Points Earned",
        icon="mdi:star",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: course.get("hac_points_earned"),
    ),
    HACGradesSensorEntityDescription(
        key="total_points_possible",
        name="Total Points Possible",
        icon="mdi:star-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda course: course.get("hac_points_possible"),
    ),
    HACGradesSensorEntityDescription(
        key="recent_assignments",
        name="Recent Assignments",
        icon="mdi:clock-outline",
        value_fn=lambda course: len(course.get("assignments", [])),
        attributes_fn=lambda course: {
            "latest_assignment": course.get("assignments", [{}])[0].get("title", "No assignments") if course.get("assignments") else "No assignments",
            "latest_score": course.get("assignments", [{}])[0].get("percentage") if course.get("assignments") and course.get("assignments")[0].get("status") == "Scored" else None,
            "assignments_list": [
                {
                    "title": a.get("title", "Unknown"),
                    "due_date": a.get("due_date", "No date"),
                    "percentage": a.get("percentage") or 0,
                }
                for a in course.get("assignments", [])
                if a.get("status") == "Scored"
            ]
        },
    ),
]


class HACLastScrapedSensor(CoordinatorEntity[HACDataUpdateCoordinator], SensorEntity):
    """Sensor that shows when data was last scraped."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        student_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._student_id = student_id
        self._attr_unique_id = f"{entry.entry_id}_last_scraped"
        self._attr_suggested_object_id = f"student_{student_id}_last_scraped"
        self._attr_name = "Last Scraped"
        self._attr_icon = "mdi:clock-check"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HAC - Student {student_id}",
            manufacturer="Home Access Center",
            model="Grade Portal",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the last scraped timestamp."""
        if not self.coordinator.data:
            return None

        last_updated = self.coordinator.data.get("last_updated")
        if not last_updated:
            return None

        try:
            # If it's already a datetime object, use it directly
            if isinstance(last_updated, datetime):
                # Ensure it has timezone info (should always be UTC from hac_client)
                if last_updated.tzinfo is None:
                    _LOGGER.warning("Last updated datetime is missing timezone, adding UTC")
                    return dt_util.as_utc(last_updated)
                return last_updated

            # If it's a string, parse it
            parsed_dt = dt_util.parse_datetime(str(last_updated))
            if parsed_dt is None:
                # Fallback to fromisoformat
                parsed_dt = datetime.fromisoformat(str(last_updated))

            # Ensure timezone info (defensive programming)
            if parsed_dt and parsed_dt.tzinfo is None:
                _LOGGER.warning("Parsed datetime is missing timezone, adding UTC: %s", parsed_dt)
                return dt_util.as_utc(parsed_dt)

            return parsed_dt
        except (ValueError, TypeError) as err:
            _LOGGER.error("Error parsing last_updated timestamp '%s': %s", last_updated, err)
            return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Only available if we have coordinator data with a valid timestamp
        if not super().available or not self.coordinator.data:
            return False

        last_updated = self.coordinator.data.get("last_updated")
        if not last_updated:
            return False

        # If it's a datetime, ensure it has timezone info
        if isinstance(last_updated, datetime):
            return last_updated.tzinfo is not None

        # If it's a string, we'll parse it in native_value
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}

        all_quarters = self.coordinator.data.get("all_quarters", {})
        return {
            "student_id": self._student_id,
            "quarters_scraped": list(all_quarters.keys()),
        }


class HACMultiQuarterSummarySensor(CoordinatorEntity[HACDataUpdateCoordinator], SensorEntity):
    """Sensor that summarizes data across all quarters."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        student_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._student_id = student_id
        self._attr_unique_id = f"{entry.entry_id}_all_quarters_summary"
        self._attr_suggested_object_id = f"student_{student_id}_all_quarters_summary"
        self._attr_name = "All Quarters Summary"
        self._attr_icon = "mdi:calendar-multiple"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HAC - Student {student_id}",
            manufacturer="Home Access Center",
            model="Grade Portal",
        )

    @property
    def native_value(self) -> Any:
        """Return the number of quarters with data."""
        if not self.coordinator.data:
            return 0

        all_quarters = self.coordinator.data.get("all_quarters", {})
        quarters_with_data = [q for q, data in all_quarters.items() if data.get("courses")]
        return len(quarters_with_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed multi-quarter statistics."""
        if not self.coordinator.data:
            return {}

        all_quarters = self.coordinator.data.get("all_quarters", {})

        # Collect statistics across all quarters
        quarters_summary = {}
        all_courses_count = 0
        all_grades = []
        total_nhi = 0
        total_nyg = 0

        for quarter, quarter_data in all_quarters.items():
            courses = quarter_data.get("courses", [])
            if not courses:
                quarters_summary[quarter] = {
                    "course_count": 0,
                    "gpa": None,
                    "status": "No data"
                }
                continue

            overall_summary = quarter_data.get("overall_summary", {})
            gpa = overall_summary.get("gpa_like_average")
            course_count = overall_summary.get("course_count", 0)

            quarters_summary[quarter] = {
                "course_count": course_count,
                "gpa": gpa,
                "highest_grade": max((c.get("hac_overall_percentage") or 0 for c in courses), default=None),
                "lowest_grade": min((c.get("hac_overall_percentage") or 100 for c in courses if c.get("hac_overall_percentage")), default=None),
                "not_handed_in": sum(c.get("not_hand_in", 0) for c in courses),
                "not_yet_graded": sum(c.get("not_yet_graded", 0) for c in courses),
                "status": "Active"
            }

            # Accumulate totals
            all_courses_count += course_count
            if gpa is not None:
                all_grades.append(gpa)
            total_nhi += quarters_summary[quarter]["not_handed_in"]
            total_nyg += quarters_summary[quarter]["not_yet_graded"]

        # Calculate overall GPA across all quarters
        overall_gpa = round(sum(all_grades) / len(all_grades), 2) if all_grades else None

        return {
            "student_id": self._student_id,
            "quarters_with_data": len([q for q, s in quarters_summary.items() if s["course_count"] > 0]),
            "total_courses": all_courses_count,
            "overall_gpa": overall_gpa,
            "total_not_handed_in": total_nhi,
            "total_not_yet_graded": total_nyg,
            "quarters": quarters_summary,
            "last_updated": self.coordinator.data.get("last_updated"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HAC Grades sensors."""
    coordinator: HACDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    # Get student ID for entity IDs
    student_id = entry.data[CONF_STUDENT_ID]

    _LOGGER.debug("Setting up sensors for student %s", student_id)
    _LOGGER.debug("Coordinator data available: %s", coordinator.data is not None)

    async def _create_entities_when_ready() -> None:
        """Wait for data and create entities in the background."""
        # Wait for data to be available before creating sensors
        if not coordinator.data:
            _LOGGER.info("Waiting for initial data fetch to complete (this may take up to 4 minutes)...")
            # Wait up to 4 minutes for the data to become available
            for i in range(48):  # 48 * 5 seconds = 4 minutes
                await asyncio.sleep(5)
                if coordinator.data:
                    _LOGGER.info("Data became available after %d seconds", (i + 1) * 5)
                    break

            if not coordinator.data:
                _LOGGER.error(
                    "Coordinator data still not available after waiting 4 minutes. "
                    "Cannot create sensors. Try reloading the integration."
                )
                return

        # Now create all sensors based on available data
        entities: list[SensorEntity] = []

        all_quarters_data = coordinator.data.get("all_quarters", {})
        quarters_available = list(all_quarters_data.keys())

        _LOGGER.info("Creating sensors for %d quarters: %s", len(quarters_available), quarters_available)

        # Add last scraped sensor (shows when all quarters were last fetched)
        last_scraped_sensor = HACLastScrapedSensor(
            coordinator,
            entry,
            student_id,
        )
        entities.append(last_scraped_sensor)
        _LOGGER.info("Created Last Scraped sensor with unique_id: %s", last_scraped_sensor.unique_id)

        # Add multi-quarter summary sensor
        entities.append(
            HACMultiQuarterSummarySensor(
                coordinator,
                entry,
                student_id,
            )
        )

        # Create sensors for each quarter that has data
        for quarter in quarters_available:
            quarter_lower = quarter.lower()

            # Add overall sensors for this quarter
            for description in OVERALL_SENSORS:
                entities.append(
                    HACOverallSensor(
                        coordinator,
                        entry,
                        description,
                        student_id,
                        quarter_lower,
                    )
                )

            # Add per-course sensors for this quarter
            quarter_data = all_quarters_data.get(quarter, {})
            courses = quarter_data.get("courses", [])

            _LOGGER.debug("Creating sensors for %d courses in %s", len(courses), quarter)

            for course in courses:
                course_index = course.get("course_index")
                course_name = _clean_course_name(course.get("course", f"Course {course_index}"))

                for description in COURSE_SENSORS:
                    entities.append(
                        HACCourseSensor(
                            coordinator,
                            entry,
                            description,
                            course_index,
                            course_name,
                            student_id,
                            quarter_lower,
                        )
                    )

        _LOGGER.info("Adding %d total entities", len(entities))
        async_add_entities(entities)
        _LOGGER.info("Successfully set up HAC Grades sensors")

        # Write entity metadata for dashboard generation (async)
        await _write_entity_metadata(hass, student_id, all_quarters_data)

    # Schedule entity creation in the background (non-blocking)
    hass.async_create_task(_create_entities_when_ready())

    _LOGGER.info("Sensor platform setup initiated (entities will be created in background)")


class HACOverallSensor(CoordinatorEntity[HACDataUpdateCoordinator], SensorEntity):
    """Representation of an overall HAC sensor."""

    entity_description: HACGradesSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HACGradesSensorEntityDescription,
        student_id: str,
        quarter: str,
    ) -> None:
        """Initialize the sensor."""
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
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.entity_description.value_fn:
            # Special handling for "last_updated" sensor - use top-level data
            if self.entity_description.key == "last_updated":
                return self.entity_description.value_fn(self.coordinator.data or {})
            return self.entity_description.value_fn(self._quarter_data)
        return None

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


class HACCourseSensor(CoordinatorEntity[HACDataUpdateCoordinator], SensorEntity):
    """Representation of a per-course HAC sensor."""

    entity_description: HACGradesSensorEntityDescription
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: HACDataUpdateCoordinator,
        entry: ConfigEntry,
        description: HACGradesSensorEntityDescription,
        course_index: int,
        course_name: str,
        student_id: str,
        quarter: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._course_index = course_index
        self._course_name = course_name
        self._student_id = student_id
        self._quarter = quarter

        # Create a clean course name for entity_id (remove course codes, lowercase, underscores)
        # Remove special characters and normalize
        clean_course_name = course_name.split(" - ")[-1].strip()
        # Remove leading digit and space if present (e.g., "2 Spanish II" -> "Spanish II")
        parts = clean_course_name.split(None, 1)
        if len(parts) >= 2 and parts[0].isdigit():
            clean_course_name = parts[1]

        # Convert to lowercase and replace spaces with underscores
        clean_course_name = clean_course_name.lower().replace(" ", "_")
        # Remove special characters
        clean_course_name = "".join(c for c in clean_course_name if c.isalnum() or c == "_")

        # Store clean name for lookups
        self._clean_course_name = clean_course_name

        # Use clean course name in unique_id instead of course_index to ensure consistency
        self._attr_unique_id = f"{entry.entry_id}_{quarter}_{clean_course_name}_{description.key}"

        # Debug logging to see what's being generated
        _LOGGER.debug(
            "Creating entity: student_id=%s, course_name=%s, clean_course_name=%s, key=%s, quarter=%s",
            student_id, course_name, clean_course_name, description.key, quarter
        )

        # With has_entity_name=False, we control the full entity name
        # Include course name in the entity name for clarity in dashboards
        self._attr_name = f"{clean_course_name.replace('_', ' ').title()} {description.name} ({quarter.upper()})"

        # Use suggested_object_id to control entity_id format: coursename_key_quarter
        self._attr_suggested_object_id = f"{clean_course_name}_{description.key}_{quarter}"

        _LOGGER.debug(
            "Entity configuration: name='%s', suggested_object_id='%s', course_name='%s', quarter='%s'",
            self._attr_name, self._attr_suggested_object_id, course_name, quarter
        )

        # One device per course (all quarters share same device)
        # Use course name instead of course_index since index can vary between quarters
        device_name = f"{course_name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_course_{clean_course_name}")},
            name=device_name,
            manufacturer="Home Access Center",
            model="Course",
            via_device=(DOMAIN, entry.entry_id),
        )

        _LOGGER.debug("Device name set to: '%s'", device_name)

    @property
    def _course_data(self) -> dict[str, Any] | None:
        """Get the course data from coordinator.

        Match by clean course name instead of course_index since index can vary between quarters.
        """
        if not self.coordinator.data:
            return None

        # Get data from all_quarters for this specific quarter
        all_quarters = self.coordinator.data.get("all_quarters", {})
        quarter_data = all_quarters.get(self._quarter.upper(), {})
        courses = quarter_data.get("courses", [])

        # Match by cleaned course name instead of course_index
        for course in courses:
            course_name = _clean_course_name(course.get("course", ""))
            # Apply same cleaning logic as in __init__
            clean_name = course_name.lower().replace(" ", "_")
            clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")

            if clean_name == self._clean_course_name:
                return course

        # Fallback to index-based lookup if name matching fails (for backwards compatibility)
        _LOGGER.warning(
            "Could not find course by name '%s' in quarter %s, falling back to index %d",
            self._clean_course_name, self._quarter.upper(), self._course_index
        )
        for course in courses:
            if course.get("course_index") == self._course_index:
                return course

        return None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        course_data = self._course_data
        if not course_data:
            return None

        if self.entity_description.value_fn:
            return self.entity_description.value_fn(course_data)
        return None

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
