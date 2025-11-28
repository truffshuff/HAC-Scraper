#!/usr/bin/env python3
"""
Dynamic Dashboard Generator for HAC Grades

This script generates a complete Lovelace dashboard YAML configuration
based on the entity metadata created by the HAC Grades integration.

Usage:
    python generate_dashboard.py [--metadata-file PATH] [--output PATH]
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


def get_course_icon(course_name: str) -> str:
    """Get an appropriate MDI icon for a course based on its name.

    Args:
        course_name: The display name of the course (e.g., "Spanish II", "Math 7")

    Returns:
        MDI icon string (e.g., "mdi:translate")
    """
    course_lower = course_name.lower()

    # Subject-based icon mapping
    icon_map = {
        # Languages
        "spanish": "mdi:translate",
        "french": "mdi:translate",
        "german": "mdi:translate",
        "chinese": "mdi:translate",
        "latin": "mdi:book-alphabet",
        "english": "mdi:book-alphabet",
        "esl": "mdi:book-alphabet",
        "language": "mdi:book-alphabet",
        "literature": "mdi:book-open-variant",
        "reading": "mdi:book-open-variant",

        # Math & Science
        "math": "mdi:calculator",
        "algebra": "mdi:math-compass",
        "geometry": "mdi:shape",
        "calculus": "mdi:function-variant",
        "statistics": "mdi:chart-bell-curve",
        "science": "mdi:flask",
        "biology": "mdi:leaf",
        "chemistry": "mdi:flask-outline",
        "physics": "mdi:atom",
        "earth": "mdi:earth",
        "astronomy": "mdi:telescope",

        # Social Studies
        "history": "mdi:book-clock",
        "geography": "mdi:map",
        "government": "mdi:bank",
        "civics": "mdi:gavel",
        "economics": "mdi:currency-usd",
        "social": "mdi:account-group",

        # Arts
        "art": "mdi:palette",
        "fine art": "mdi:palette",
        "drawing": "mdi:draw",
        "painting": "mdi:brush",
        "music": "mdi:music",
        "band": "mdi:music-note",
        "orchestra": "mdi:violin",
        "choir": "mdi:microphone-variant",
        "drama": "mdi:drama-masks",
        "theater": "mdi:drama-masks",
        "dance": "mdi:dance-ballroom",

        # Technology & Business
        "computer": "mdi:laptop",
        "programming": "mdi:code-braces",
        "coding": "mdi:code-tags",
        "technology": "mdi:chip",
        "engineering": "mdi:cog",
        "robotics": "mdi:robot",
        "business": "mdi:briefcase",
        "marketing": "mdi:chart-line",
        "accounting": "mdi:calculator-variant",
        "finance": "mdi:cash",
        "entrepreneurship": "mdi:lightbulb",
        "management": "mdi:office-building",

        # Physical Education & Health
        "pe": "mdi:basketball",
        "physical education": "mdi:run",
        "gym": "mdi:dumbbell",
        "health": "mdi:heart-pulse",
        "fitness": "mdi:arm-flex",
        "sports": "mdi:soccer",

        # Other
        "study": "mdi:book-open-page-variant",
        "advisory": "mdi:account-group",
        "homeroom": "mdi:home-account",
        "elective": "mdi:star-circle",
    }

    # Check for keyword matches
    for keyword, icon in icon_map.items():
        if keyword in course_lower:
            return icon

    # Default icon
    return "mdi:book-open-page-variant"


def create_gauge_card(entity: str, name: str, min_val: int = 0, max_val: int = 100) -> dict[str, Any]:
    """Create a gauge card configuration."""
    return {
        "type": "gauge",
        "entity": entity,
        "name": name,
        "min": min_val,
        "max": max_val,
        "severity": {
            "green": 90,
            "yellow": 70,
            "red": 0,
        },
    }


def create_stats_markdown(student_id: str, quarter: str, student_name: str = None) -> dict[str, Any]:
    """Create statistics markdown card."""
    display_name = student_name or f"Student {student_id}"
    quarter_upper = quarter.upper()

    content = f"""### {display_name}'s Grade Statistics

**Highest Grade:** {{{{ states('sensor.hac_student_{student_id}_highest_grade_{quarter}') }}}}

**Lowest Grade:** {{{{ states('sensor.hac_student_{student_id}_lowest_grade_{quarter}') }}}}

**Total Courses:** {{{{ states('sensor.hac_student_{student_id}_total_courses_{quarter}') }}}}

**Not Handed In:** {{{{ states('sensor.hac_student_{student_id}_total_not_handed_in_{quarter}') }}}}"""

    return {
        "type": "markdown",
        "content": content,
    }


def create_last_updated_card(student_id: str) -> dict[str, Any]:
    """Create last updated markdown card."""
    return {
        "type": "markdown",
        "content": f"""**Last Updated:**

{{{{ states('sensor.hac_student_{student_id}_last_scraped') }}}}""",
    }


def create_assignment_alerts_card(student_id: str, quarter: str, student_name: str = None) -> dict[str, Any]:
    """Create assignment alerts markdown card."""
    display_name = student_name or f"Student {student_id}"

    content = f"""{{{{states('sensor.hac_student_{student_id}_missing_assignments_summary_{quarter}')}}}}

**Missing Assignments:** <BR>{{{{ states('sensor.hac_student_{student_id}_missing_assignments_by_course_{quarter}') | replace('; ', '\\n') }}}}

**Missing Assignments Details:** <BR>{{{{ states('sensor.hac_student_{student_id}_missing_assignment_details_{quarter}') | replace('| ', '\\n')}}}}"""

    return {
        "type": "markdown",
        "content": content,
        "title": f"{display_name} Assignments of Interest",
        "grid_options": {
            "rows": "auto",
        },
    }


def create_course_grades_entities_card(
    student_id: str,
    courses: list[dict[str, Any]],
    quarter: str,
    dashboard_path: str = "dashboard-grades",
    student_name: str = None
) -> dict[str, Any]:
    """Create entities card listing all courses with navigation links."""
    entities = []

    for course in courses:
        course_clean = course["clean_name"]
        course_display = course["display_name"]
        icon = get_course_icon(course_display)

        # Create navigation path
        nav_path = f"/{dashboard_path}/{quarter}-{student_id}-{course_clean}"

        entities.append({
            "entity": f"sensor.{course_clean}_grade_{quarter}",
            "name": course_display,
            "icon": icon,
            "tap_action": {
                "action": "navigate",
                "navigation_path": nav_path,
            },
        })

    display_name = student_name or f"Student {student_id}"
    return {
        "type": "entities",
        "title": f"{display_name}'s Course Grades",
        "entities": entities,
    }


def create_overview_view(metadata: dict[str, Any], quarter: str, dashboard_path: str = "dashboard-grades", student_order: list[str] = None) -> dict[str, Any]:
    """Create the overview view for a specific quarter."""
    quarter_lower = quarter.lower()
    quarter_upper = quarter.upper()

    students = metadata.get("students", {})

    # Determine student iteration order
    if student_order:
        student_ids = [sid for sid in student_order if sid in students]
    else:
        student_ids = list(students.keys())

    # Build horizontal stack with all student gauges and stats
    gauge_cards = []
    alert_cards = []
    course_grade_cards = []

    for student_id in student_ids:
        student_data = students[student_id]
        if quarter not in student_data.get("quarters", {}):
            continue

        # Student name extraction (can be enhanced)
        student_name = student_data.get("name") or f"Student {student_id}"

        # Add gauge
        gauge_cards.append(create_gauge_card(
            f"sensor.hac_student_{student_id}_gpa_{quarter_lower}",
            f"{student_name}'s GPA"
        ))

        # Add stats
        gauge_cards.append(create_stats_markdown(student_id, quarter_lower, student_name))

    # Add last updated card (use first student)
    if student_ids:
        first_student_id = student_ids[0]
        gauge_cards.append(create_last_updated_card(first_student_id))

    # Build assignment alerts for each student
    for student_id in student_ids:
        student_data = students[student_id]
        if quarter not in student_data.get("quarters", {}):
            continue

        student_name = student_data.get("name") or f"Student {student_id}"
        alert_cards.append(create_assignment_alerts_card(student_id, quarter_lower, student_name))

    # Build course grade entities cards for each student
    for student_id in student_ids:
        student_data = students[student_id]
        quarter_data = student_data.get("quarters", {}).get(quarter, {})
        if not quarter_data:
            continue

        student_name = student_data.get("name") or f"Student {student_id}"
        courses = quarter_data.get("courses", [])

        # Add entities card with student name in title
        if courses:
            course_grade_cards.append(
                create_course_grades_entities_card(student_id, courses, quarter_lower, dashboard_path, student_name)
            )

    view = {
        "title": f"{quarter_upper} Overview",
        "path": f"{quarter_lower}-overview",
        "icon": f"mdi:numeric-{quarter[-1]}-box",
        "type": "sections",
        "max_columns": 4,
        "sections": [
            {
                "type": "grid",
                "cards": [
                    {
                        "type": "horizontal-stack",
                        "cards": gauge_cards,
                        "grid_options": {
                            "columns": "full",
                        },
                    }
                ],
                "column_span": 4,
            },
            {
                "type": "grid",
                "cards": [
                    {
                        "type": "heading",
                        "heading": "Assignment Alerts",
                    }
                ] + alert_cards,
                "column_span": 2,
            },
            {
                "type": "grid",
                "cards": course_grade_cards,
                "column_span": 2,
            },
        ],
    }

    return view


def create_course_gauge_section(student_id: str, course_clean: str, quarter: str) -> dict[str, Any]:
    """Create gauge section for a course dashboard."""
    return {
        "type": "grid",
        "cards": [
            {
                "type": "horizontal-stack",
                "cards": [
                    create_gauge_card(
                        f"sensor.{course_clean}_grade_{quarter}",
                        "Overall Grade"
                    ),
                ],
                "grid_options": {
                    "columns": "full",
                },
            },
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "conditional",
                        "conditions": [
                            {
                                "entity": f"sensor.{course_clean}_practice_category_score_{quarter}",
                                "state_not": "unknown"
                            }
                        ],
                        "card": create_gauge_card(
                            f"sensor.{course_clean}_practice_category_score_{quarter}",
                            "Practice"
                        ),
                    },
                    {
                        "type": "conditional",
                        "conditions": [
                            {
                                "entity": f"sensor.{course_clean}_process_category_score_{quarter}",
                                "state_not": "unknown"
                            }
                        ],
                        "card": create_gauge_card(
                            f"sensor.{course_clean}_process_category_score_{quarter}",
                            "Process"
                        ),
                    },
                    {
                        "type": "conditional",
                        "conditions": [
                            {
                                "entity": f"sensor.{course_clean}_product_category_score_{quarter}",
                                "state_not": "unknown"
                            }
                        ],
                        "card": create_gauge_card(
                            f"sensor.{course_clean}_product_category_score_{quarter}",
                            "Product"
                        ),
                    },
                ],
                "grid_options": {
                    "columns": "full",
                },
            },
            {
                "type": "horizontal-stack",
                "cards": create_category_stats_cards(course_clean, quarter),
                "grid_options": {
                    "columns": "full",
                    "rows": 3,
                },
            },
        ],
        "column_span": 4,
    }


def create_category_stats_cards(course_clean: str, quarter: str) -> list[dict[str, Any]]:
    """Create the three category statistics markdown cards.

    Note: Some courses may not have assignments in all 3 categories yet,
    so we need to check if the category exists by name (not index).
    """
    cards = []

    # Standard category order: Practice, Process, Product
    category_names = ["Practice", "Process", "Product"]
    entity_names = ["practice", "process", "product"]

    for expected_name, entity_name in zip(category_names, entity_names):
        # Use template strings to avoid f-string escaping issues
        # Find the category by name, not by index (since categories are sorted alphabetically)
        content = """{% set categories = state_attr('sensor.""" + course_clean + """_assignment_category_statistics_""" + quarter + """', 'categories') %}
{% set category = categories | selectattr('category', 'equalto', '""" + expected_name + """') | first if categories else none %}

{% if category %}
**{{ category.category }}**

- Count: {{ category.count }} assignments

- Average Score: {{ category.avg_percentage }}%

- Scored: {{ category.scored }} | Pending: {{ category.pending }}

- Points: {{ category.earned_points }}/{{ category.total_points }}


{% else %}

**""" + expected_name + """**

*No assignments yet*

{% endif %}"""

        # Wrap each stats card in a conditional to match the gauge visibility
        cards.append({
            "type": "conditional",
            "conditions": [
                {
                    "entity": f"sensor.{course_clean}_{entity_name}_category_score_{quarter}",
                    "state_not": "unknown"
                }
            ],
            "card": {
                "type": "markdown",
                "content": content,
            }
        })

    return cards


def create_extended_entities_section(course_clean: str, quarter: str) -> dict[str, Any]:
    """Create the extended entities section with 4 entity cards."""
    return {
        "type": "grid",
        "cards": [
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "entities",
                        "entities": [
                            {
                                "entity": f"sensor.{course_clean}_grade_{quarter}",
                                "name": "Overall Grade",
                                "icon": "mdi:school",
                            },
                            {"type": "divider"},
                            {
                                "entity": f"sensor.{course_clean}_highest_assignment_score_{quarter}",
                                "name": "Highest Score",
                            },
                            {
                                "entity": f"sensor.{course_clean}_lowest_assignment_score_{quarter}",
                                "name": "Lowest Score",
                            },
                        ],
                    },
                    {
                        "type": "entities",
                        "entities": [
                            {
                                "entity": f"sensor.{course_clean}_process_category_score_{quarter}",
                                "name": "Process Average",
                                "icon": "mdi:cog",
                            },
                            {
                                "entity": f"sensor.{course_clean}_product_category_score_{quarter}",
                                "name": "Product Average",
                                "icon": "mdi:package-variant",
                            },
                            {
                                "entity": f"sensor.{course_clean}_practice_category_score_{quarter}",
                                "name": "Practice Average",
                                "icon": "mdi:pencil",
                            },
                        ],
                    },
                    {
                        "type": "entities",
                        "entities": [
                            {
                                "entity": f"sensor.{course_clean}_total_points_earned_{quarter}",
                                "name": "Points Earned",
                            },
                            {
                                "entity": f"sensor.{course_clean}_total_points_possible_{quarter}",
                                "name": "Points Possible",
                            },
                        ],
                    },
                    {
                        "type": "entities",
                        "entities": [
                            {
                                "entity": f"sensor.{course_clean}_total_assignments_{quarter}",
                                "name": "Total Assignments",
                            },
                            {
                                "entity": f"sensor.{course_clean}_assignments_scored_{quarter}",
                                "name": "Scored",
                            },
                            {
                                "entity": f"sensor.{course_clean}_assignments_pending_{quarter}",
                                "name": "Pending",
                            },
                        ],
                    },
                ],
                "grid_options": {
                    "columns": "full",
                },
            }
        ],
        "column_span": 4,
    }


def create_latest_assignment_section(course_clean: str, quarter: str) -> dict[str, Any]:
    """Create the latest assignment section."""
    content = """## Latest Assignment


**{{ state_attr('sensor.""" + course_clean + """_recent_assignments_""" + quarter + """', 'latest_assignment') }}**

Score: {{ state_attr('sensor.""" + course_clean + """_recent_assignments_""" + quarter + """', 'latest_score') }}%


---


### All Assignments (Most Recent First)

{% set assignments = state_attr('sensor.""" + course_clean + """_recent_assignments_""" + quarter + """', 'assignments_list') %}

{% if assignments %}
  {% for assignment in assignments[:5] %}
**{{ assignment.title }}** - {{ assignment.percentage }}% ({{ assignment.due_date }})
  {% endfor %}
{% if assignments | length > 5 %}


*...and {{ assignments | length - 5 }} more assignments*

{% endif %}

{% else %}

*No assignments found*

{% endif %}"""

    return {
        "type": "grid",
        "cards": [
            {
                "type": "markdown",
                "content": content,
            }
        ],
    }


def create_recent_assignments_section(course_clean: str, quarter: str) -> dict[str, Any]:
    """Create the recent assignments detailed section."""
    content = """## Recent Assignments {% set assignments = state_attr('sensor.""" + course_clean + """_assignment_details_""" + quarter + """', 'assignments') %} {% if assignments %}
  {% for assignment in assignments %}
**{{ assignment.title }}** - Due: {{ assignment.due_date }} - Score: {{ assignment.score }}/{{ assignment.total_points }} ({{ assignment.percentage }}%) - Category: {{ assignment.category }} - Status: {{ assignment.status }}
  {% endfor %}
{% else %} *Loading assignment details...* {% endif %}"""

    return {
        "type": "grid",
        "cards": [
            {
                "type": "markdown",
                "content": content,
                "card_mod": {
                    "style": """ha-markdown {
  column-count: 2;
  column-gap: 20px;
}""",
                },
                "grid_options": {
                    "columns": 24,
                    "rows": "auto",
                },
            }
        ],
        "column_span": 2,
    }


def create_grade_trends_section(course_clean: str, quarter: str) -> dict[str, Any]:
    """Create the grade trends ApexCharts section."""
    return {
        "type": "grid",
        "cards": [
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "custom:apexcharts-card",
                        "graph_span": "15d",
                        "span": {
                            "start": "day",
                            "offset": "-10d",
                        },
                        "header": {
                            "show": True,
                            "title": "Grade Trends",
                            "show_states": True,
                            "colorize_states": True,
                        },
                        "now": {
                            "show": True,
                            "label": "Now",
                        },
                        "series": [
                            {
                                "entity": f"sensor.{course_clean}_process_category_score_{quarter}",
                                "name": "Process",
                                "stroke_width": 3,
                                "curve": "smooth",
                                "color": "#1E88E5",
                                "show": {
                                    "legend_value": False,
                                },
                            },
                            {
                                "entity": f"sensor.{course_clean}_product_category_score_{quarter}",
                                "name": "Product",
                                "stroke_width": 3,
                                "curve": "smooth",
                                "color": "#43A047",
                                "show": {
                                    "legend_value": False,
                                },
                            },
                            {
                                "entity": f"sensor.{course_clean}_practice_category_score_{quarter}",
                                "name": "Practice",
                                "stroke_width": 3,
                                "curve": "smooth",
                                "color": "#FB8C00",
                                "show": {
                                    "legend_value": False,
                                },
                            },
                        ],
                    }
                ],
                "grid_options": {
                    "columns": "full",
                },
            }
        ],
        "column_span": 4,
    }


def create_course_view(
    student_id: str,
    course: dict[str, Any],
    quarter: str,
    dashboard_path: str = "dashboard-grades",
) -> dict[str, Any]:
    """Create a view for a specific course."""
    course_clean = course["clean_name"]
    course_display = course["display_name"]
    quarter_lower = quarter.lower()
    quarter_upper = quarter.upper()

    # Create path-safe version
    path = f"{quarter_lower}-{student_id}-{course_clean}"

    # Get appropriate icon for this course
    icon = get_course_icon(course_display)

    # Create heading and back button section
    header_section = {
        "type": "grid",
        "cards": [
            {
                "type": "heading",
                "heading": f"{course_display} - Quarter {quarter[-1]}",
            },
            {
                "type": "button",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": f"/{dashboard_path}/{quarter_lower}-overview",
                },
                "name": f"Return to {quarter_upper} Overview",
                "icon": "mdi:arrow-left",
            },
        ],
        "column_span": 4,
    }

    view = {
        "title": f"{student_id} - {course_display} ({quarter_upper})",
        "path": path,
        "type": "sections",
        "max_columns": 4,
        "sections": [
            header_section,
            create_course_gauge_section(student_id, course_clean, quarter_lower),
            create_extended_entities_section(course_clean, quarter_lower),
            create_latest_assignment_section(course_clean, quarter_lower),
            create_recent_assignments_section(course_clean, quarter_lower),
            create_grade_trends_section(course_clean, quarter_lower),
        ],
        "visible": [],
        "cards": [],
    }

    return view


def generate_dashboard(metadata: dict[str, Any], dashboard_path: str = "dashboard-grades", student_order: list[str] = None) -> dict[str, Any]:
    """Generate complete dashboard configuration from metadata.

    Args:
        metadata: The entity metadata dictionary
        dashboard_path: The base path for the dashboard (for navigation links)
        student_order: Optional list of student IDs to specify display order

    Returns:
        Complete dashboard YAML structure
    """
    _LOGGER.info("Generating dashboard from metadata...")

    students = metadata.get("students", {})

    if not students:
        _LOGGER.warning("No students found in metadata")
        return {"views": []}

    # Order students if order is specified
    if student_order:
        # Filter to only include students that exist in metadata
        ordered_student_ids = [sid for sid in student_order if sid in students]
        # Add any remaining students not in the order list
        remaining_students = [sid for sid in students.keys() if sid not in ordered_student_ids]
        all_student_ids = ordered_student_ids + remaining_students
        _LOGGER.info("Ordered students: %s", all_student_ids)
    else:
        all_student_ids = list(students.keys())

    # Collect all quarters across all students
    all_quarters = set()
    for student_data in students.values():
        all_quarters.update(student_data.get("quarters", {}).keys())

    _LOGGER.info("Found %d quarters: %s", len(all_quarters), sorted(all_quarters))

    views = []

    # Create overview views for each quarter
    for quarter in sorted(all_quarters):
        overview_view = create_overview_view(metadata, quarter, dashboard_path, all_student_ids)
        views.append(overview_view)
        _LOGGER.info("Created overview view for %s", quarter)

    # Create individual course views using ordered student list
    for student_id in all_student_ids:
        student_data = students[student_id]
        for quarter, quarter_data in student_data.get("quarters", {}).items():
            courses = quarter_data.get("courses", [])

            for course in courses:
                course_view = create_course_view(student_id, course, quarter, dashboard_path)
                views.append(course_view)
                _LOGGER.info(
                    "Created course view for %s - %s (%s)",
                    student_id,
                    course["display_name"],
                    quarter
                )

    dashboard = {
        "views": views,
    }

    _LOGGER.info("Generated dashboard with %d total views", len(views))

    return dashboard


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate HAC Grades dashboard from entity metadata"
    )
    parser.add_argument(
        "--metadata-file",
        type=Path,
        help="Path to hac_entity_registry.json (default: ./hac_entity_registry.json)",
        default=Path("hac_entity_registry.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output YAML file path (default: ./Grades_Dashboard_Generated.yaml)",
        default=Path("Grades_Dashboard_Generated.yaml"),
    )
    parser.add_argument(
        "--dashboard-path",
        type=str,
        help="Dashboard path for navigation links (default: dashboard-grades)",
        default="dashboard-grades",
    )
    parser.add_argument(
        "--student-order",
        type=str,
        help="Comma-separated list of student IDs to specify display order (e.g., '148613,170512')",
        default=None,
    )
    parser.add_argument(
        "--student-names",
        type=str,
        help="Comma-separated list of student names in format 'ID:Name' (e.g., '148613:Owen,170512:Emma')",
        default=None,
    )

    args = parser.parse_args()

    # Load metadata
    if not args.metadata_file.exists():
        _LOGGER.error("Metadata file not found: %s", args.metadata_file)
        _LOGGER.error(
            "Make sure the HAC Grades integration has run and created the metadata file"
        )
        return 1

    _LOGGER.info("Loading metadata from %s", args.metadata_file)

    try:
        with open(args.metadata_file, "r") as f:
            metadata = json.load(f)
    except (json.JSONDecodeError, IOError) as err:
        _LOGGER.error("Failed to load metadata: %s", err)
        return 1

    # Parse student order if provided
    student_order = None
    if args.student_order:
        student_order = [sid.strip() for sid in args.student_order.split(",")]
        _LOGGER.info("Using student order: %s", student_order)

    # Parse and apply student names if provided
    if args.student_names:
        student_names = {}
        for mapping in args.student_names.split(","):
            mapping = mapping.strip()
            if ":" in mapping:
                student_id, name = mapping.split(":", 1)
                student_names[student_id.strip()] = name.strip()

        # Apply names to metadata
        for student_id, name in student_names.items():
            if student_id in metadata.get("students", {}):
                metadata["students"][student_id]["name"] = name
                _LOGGER.info("Set name for student %s: %s", student_id, name)
            else:
                _LOGGER.warning("Student ID %s not found in metadata, skipping name assignment", student_id)

    # Generate dashboard
    dashboard = generate_dashboard(metadata, args.dashboard_path, student_order)

    # Write output
    _LOGGER.info("Writing dashboard to %s", args.output)

    try:
        with open(args.output, "w") as f:
            yaml.dump(
                dashboard,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=1000,
            )
    except IOError as err:
        _LOGGER.error("Failed to write output: %s", err)
        return 1

    _LOGGER.info("Dashboard generation complete!")
    _LOGGER.info("Generated: %s", args.output.absolute())

    # Print summary
    print("\n" + "="*60)
    print("Dashboard Generation Summary")
    print("="*60)
    print(f"Metadata file: {args.metadata_file}")
    print(f"Output file: {args.output}")
    print(f"Total views: {len(dashboard['views'])}")
    print(f"Last metadata update: {metadata.get('last_updated', 'Unknown')}")
    print("="*60 + "\n")

    return 0


if __name__ == "__main__":
    exit(main())
