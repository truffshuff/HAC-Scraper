#!/usr/bin/env python3
"""
Dynamic Dashboard Generator for HAC Grades

This script generates a complete Lovelace dashboard YAML configuration
based on the entity metadata created by the HAC Grades integration.

Layout:
    - One "Qn" overview tab per quarter, with a section per student
      (GPA gauge, stat tiles, a "needs attention" table, and a card per course).
    - One hidden subview per student/course/quarter with a native back arrow,
      category breakdown, grade trend chart, and a full assignment table.

Required frontend cards (HACS):
    - Mushroom (v5+)          custom:mushroom-template-card
    - Nodalia Cards           custom:nodalia-circular-gauge-card
    - flex-table-card         custom:flex-table-card
    - apexcharts-card         custom:apexcharts-card

Usage:
    python generate_dashboard.py [--metadata-file PATH] [--output PATH]
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# Category weights as used by HAC (see custom_components/hac_grades/const.py)
CATEGORIES = [
    ("Practice", "practice", "mdi:pencil-outline", 20),
    ("Process", "process", "mdi:cog-outline", 30),
    ("Product", "product", "mdi:package-variant-closed", 50),
]

# Category line colors on the course trend chart; assignment dots reuse them
CATEGORY_COLORS = {"practice": "#FB8C00", "process": "#1E88E5", "product": "#43A047"}

# Course line colors on the student trend chart, assigned in this fixed order
# (validated categorical palette: blue, orange, aqua, yellow, magenta, green,
# violet, red). A ninth course reuses colors from the start.
COURSE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Trend chart time range: roughly one quarter. The recorder must keep at
# least this much history for the full range to show.
TREND_WEEKS = 8
TREND_SPAN = f"{TREND_WEEKS}w"

# Course card sparkline range: recent direction only
SPARKLINE_WEEKS = 3

# Longest assignment title shown in the "Needs attention" table
TITLE_MAX = 40

# Assignment status display: (emoji, label, sort priority)
STATUS_DISPLAY = {
    "NHI": ("🔴", "Missing", 1),
    "TLTC": ("⏰", "Too late", 2),
    "SBF": ("📉", "Below 50", 3),
    "NYG": ("⏳", "Not graded", 4),
}

# Ordered most-specific first; each keyword matches at the start of a word in
# the course name, so "art" matches "Art 8" but not "Lang Arts".
COURSE_ICONS = [
    # Languages
    ("spanish", "mdi:translate"),
    ("french", "mdi:translate"),
    ("german", "mdi:translate"),
    ("chinese", "mdi:translate"),
    ("latin", "mdi:book-alphabet"),
    ("lang", "mdi:book-alphabet"),
    ("english", "mdi:book-alphabet"),
    ("esl", "mdi:book-alphabet"),
    ("lit", "mdi:book-open-variant"),
    ("reading", "mdi:book-open-variant"),
    ("writ", "mdi:pencil"),
    # Math
    ("algebra", "mdi:math-compass"),
    ("geometry", "mdi:shape"),
    ("calc", "mdi:function-variant"),
    ("stat", "mdi:chart-bell-curve"),
    ("math", "mdi:calculator"),
    ("integ math", "mdi:calculator"),
    # Science
    ("bio", "mdi:leaf"),
    ("chem", "mdi:flask-outline"),
    ("physics", "mdi:atom"),
    ("earth", "mdi:earth"),
    ("astro", "mdi:telescope"),
    ("science", "mdi:flask"),
    # Social studies
    ("hist", "mdi:book-clock"),
    ("human geo", "mdi:map"),
    ("geo", "mdi:map"),
    ("gov", "mdi:bank"),
    ("civics", "mdi:gavel"),
    ("econ", "mdi:currency-usd"),
    ("psych", "mdi:head-cog-outline"),
    ("socio", "mdi:account-group"),
    ("social", "mdi:account-group"),
    # Arts
    ("fine art", "mdi:palette"),
    ("art", "mdi:palette"),
    ("drawing", "mdi:draw"),
    ("painting", "mdi:brush"),
    ("chorus", "mdi:microphone-variant"),
    ("choir", "mdi:microphone-variant"),
    ("band", "mdi:music-note"),
    ("orchestra", "mdi:violin"),
    ("music", "mdi:music"),
    ("drama", "mdi:drama-masks"),
    ("theat", "mdi:drama-masks"),
    ("dance", "mdi:dance-ballroom"),
    # Technology & business
    ("computer", "mdi:laptop"),
    ("program", "mdi:code-braces"),
    ("coding", "mdi:code-tags"),
    ("tech", "mdi:chip"),
    ("engineer", "mdi:cog"),
    ("robot", "mdi:robot"),
    ("acct", "mdi:calculator-variant"),
    ("account", "mdi:calculator-variant"),
    ("fin", "mdi:cash"),
    ("bus", "mdi:briefcase"),
    ("market", "mdi:chart-line"),
    ("entrepreneur", "mdi:lightbulb"),
    # PE & health
    ("phy ed", "mdi:run"),
    ("physical ed", "mdi:run"),
    ("fnd fit", "mdi:run"),
    ("fit", "mdi:arm-flex"),
    ("weight", "mdi:weight-lifter"),
    ("gym", "mdi:dumbbell"),
    ("sport", "mdi:soccer"),
    ("health", "mdi:heart-pulse"),
    # Other
    ("study", "mdi:book-open-page-variant"),
    ("advisory", "mdi:account-group"),
    ("homeroom", "mdi:home-account"),
    ("elective", "mdi:star-circle"),
]


def get_course_icon(course_name: str) -> str:
    """Get an appropriate MDI icon for a course based on its name.

    Args:
        course_name: The display name of the course (e.g., "Spanish II", "Math 7")

    Returns:
        MDI icon string (e.g., "mdi:translate")
    """
    course_lower = course_name.lower()
    for keyword, icon in COURSE_ICONS:
        if re.search(rf"\b{re.escape(keyword)}", course_lower):
            return icon
    return "mdi:book-open-page-variant"


# ---------------------------------------------------------------------------
# Jinja snippets shared by several cards
# ---------------------------------------------------------------------------


def _jinja_grade_color(entity: str) -> str:
    """Jinja expression rendering a color token for a percentage sensor."""
    return (
        f"{{% set g = states('{entity}') | float(-1) %}}"
        "{{ 'green' if g >= 90 else 'amber' if g >= 80 "
        "else 'orange' if g >= 70 else 'red' if g >= 0 else 'disabled' }}"
    )


def _jinja_percent(entity: str) -> str:
    """Jinja expression rendering a sensor value as "97.1%" (or a dash)."""
    return (
        f"{{% set v = states('{entity}') | float(none) %}}"
        "{{ '—' if v is none else '%.1f' | format(v) ~ '%' }}"
    )


def _no_data(entity: str) -> list[dict[str, Any]]:
    """Visibility condition: entity has no value yet."""
    return [{"condition": "state", "entity": entity, "state": ["unknown", "unavailable"]}]


def _has_data(entity: str) -> list[dict[str, Any]]:
    """Visibility condition: entity has a value."""
    return [{"condition": "state", "entity": entity, "state_not": ["unknown", "unavailable"]}]


# ---------------------------------------------------------------------------
# Entity ID helpers (must match the integration's entity naming)
# ---------------------------------------------------------------------------


def _student_entity(student_id: str, key: str, quarter: str) -> str:
    return f"sensor.hac_student_{student_id}_{key}_{quarter}"


def _course_entity(course_clean: str, key: str, quarter: str) -> str:
    return f"sensor.{course_clean}_{key}_{quarter}"


def _course_path(quarter: str, student_id: str, course_clean: str) -> str:
    return f"{quarter}-{student_id}-{course_clean}"


# ---------------------------------------------------------------------------
# Overview view
# ---------------------------------------------------------------------------


def create_stat_card(entity: str, label: str, icon: str, color: str, value: str) -> dict[str, Any]:
    """Create a compact stat tile (value as the primary line)."""
    return {
        "type": "custom:mushroom-template-card",
        "entity": entity,
        "primary": value,
        "secondary": label,
        "icon": icon,
        "color": color,
        "tap_action": {"action": "more-info"},
    }


def create_student_stats_grid(student_id: str, quarter: str) -> dict[str, Any]:
    """Create the column of headline stats shown beside the GPA gauge."""
    highest = _student_entity(student_id, "highest_grade", quarter)
    lowest = _student_entity(student_id, "lowest_grade", quarter)
    nhi = _student_entity(student_id, "total_not_handed_in", quarter)
    nyg = _student_entity(student_id, "total_not_yet_graded", quarter)

    return {
        "type": "grid",
        "columns": 1,
        "square": False,
        "cards": [
            create_stat_card(highest, "Highest", "mdi:trophy-outline",
                             _jinja_grade_color(highest), _jinja_percent(highest)),
            create_stat_card(lowest, "Lowest", "mdi:arrow-down-circle-outline",
                             _jinja_grade_color(lowest), _jinja_percent(lowest)),
            create_stat_card(
                nhi, "Missing",
                f"{{{{ 'mdi:file-alert-outline' if states('{nhi}') | int(0) > 0 else 'mdi:check-circle-outline' }}}}",
                f"{{{{ 'red' if states('{nhi}') | int(0) > 0 else 'green' }}}}",
                f"{{{{ states('{nhi}') | int(0) }}}}",
            ),
            create_stat_card(
                nyg, "Not graded", "mdi:timer-sand",
                f"{{{{ 'blue' if states('{nyg}') | int(0) > 0 else 'disabled' }}}}",
                f"{{{{ states('{nyg}') | int(0) }}}}",
            ),
        ],
        # Fixed height matching the gauge so the stat cards don't stretch
        "grid_options": {"columns": 12, "rows": 4},
        "visibility": _has_data(_student_entity(student_id, "gpa", quarter)),
    }


def create_attention_card(
    student_id: str,
    quarter: str,
    quarter_courses: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Create a markdown table of every missing / ungraded assignment.

    Reads each course's assignment_details attribute directly, so nothing is
    truncated (the summary sensors are capped at 255 characters). The table is
    padded with blank rows up to the longest list among all students this
    quarter, so side-by-side student sections stay the same height.

    Args:
        student_id: The student this card is for
        quarter: Lowercase quarter (e.g. "q1")
        quarter_courses: Every student's courses this quarter, keyed by student ID
    """
    students = ", ".join(
        f"{json.dumps(sid)}: ["
        + ", ".join(
            f"({json.dumps(c['display_name'])}, "
            f"{json.dumps(_course_entity(c['clean_name'], 'assignment_details', quarter))})"
            for c in courses
        )
        + "]"
        for sid, courses in quarter_courses.items()
    )
    labels = ", ".join(
        f'"{status}": ["{emoji}", "{label}", {prio}]'
        for status, (emoji, label, prio) in STATUS_DISPLAY.items()
    )

    # Titles are shortened so every row stays one line tall; the full title
    # is on the course page.
    content = (
        f"{{%- set students = {{{students}}} %}}\n"
        f"{{%- set labels = {{{labels}}} %}}\n"
        "{%- set ns = namespace(rows=[], most=1) %}\n"
        "{%- for sid, courses in students.items() %}\n"
        "{%- set cnt = namespace(n=0) %}\n"
        "{%- for name, sensor in courses %}\n"
        "{%- for a in (state_attr(sensor, 'assignments') or []) if a.status in labels %}\n"
        "{%- set cnt.n = cnt.n + 1 %}\n"
        f"{{%- if sid == {json.dumps(student_id)} %}}\n"
        "{%- set t = (a.title or '') | replace('|', '/') %}\n"
        "{%- set ns.rows = ns.rows + [{'p': labels[a.status][2], 's': a.status, 'c': name, "
        "'t': (t[:" + str(TITLE_MAX - 1) + "] ~ '…') if t | length > " + str(TITLE_MAX) + " else t, "
        "'d': (a.due_date or '')[:5]}] %}\n"
        "{%- endif %}\n"
        "{%- endfor %}\n"
        "{%- endfor %}\n"
        "{%- set ns.most = [ns.most, cnt.n] | max %}\n"
        "{%- endfor %}\n"
        "{%- set out = namespace(lines=['| Status | Course | Assignment | Due |', '|:--|:--|:--|--:|']) %}\n"
        "{%- for r in ns.rows | sort(attribute='p') %}\n"
        "{%- set out.lines = out.lines + ['| ' ~ labels[r.s][0] ~ ' ' ~ labels[r.s][1] ~ ' | ' ~ r.c ~ ' | ' ~ r.t ~ ' | ' ~ r.d ~ ' |'] %}\n"
        "{%- endfor %}\n"
        "{%- if not ns.rows %}\n"
        "{%- set out.lines = out.lines + ['| ✅ All caught up | | | |'] %}\n"
        "{%- endif %}\n"
        "{%- for i in range(ns.most - ([ns.rows | count, 1] | max)) %}\n"
        "{%- set out.lines = out.lines + ['| &nbsp; | | | |'] %}\n"
        "{%- endfor %}\n"
        "{{ out.lines | join('\\n') }}"
    )

    return {
        "type": "markdown",
        "content": content,
        "grid_options": {"columns": "full", "rows": "auto"},
    }


def create_course_tile(
    student_id: str,
    course: dict[str, Any],
    quarter: str,
    dashboard_path: str,
) -> dict[str, Any]:
    """Create a color-coded course card with a grade sparkline."""
    course_clean = course["clean_name"]
    grade = _course_entity(course_clean, "grade", quarter)
    details = _course_entity(course_clean, "assignment_details", quarter)

    secondary = (
        _jinja_percent(grade)
        + f"{{% set d = state_attr('{grade}', 'days_since_update') %}}"
        "{% if d is not none %} · updated "
        "{{ 'today' if d == 0 else '1 day ago' if d == 1 else d ~ ' days ago' }}{% endif %}"
    )
    flagged = (
        f"(state_attr('{details}', 'assignments') or []) "
        "| selectattr('status', 'in', ['NHI', 'TLTC', 'SBF']) | list | count"
    )

    return {
        "type": "custom:mushroom-template-card",
        "entity": grade,
        "primary": course["display_name"],
        "secondary": secondary,
        "icon": get_course_icon(course["display_name"]),
        "color": _jinja_grade_color(grade),
        "badge_icon": f"{{{{ 'mdi:exclamation-thick' if {flagged} > 0 else '' }}}}",
        "badge_color": "red",
        "features": [{"type": "trend-graph", "hours_to_show": SPARKLINE_WEEKS * 7 * 24}],
        "features_position": "bottom",
        "tap_action": {
            "action": "navigate",
            "navigation_path": f"/{dashboard_path}/{_course_path(quarter, student_id, course_clean)}",
        },
        "hold_action": {"action": "more-info"},
        "grid_options": {"columns": 12},
    }


def create_student_section(
    student_id: str,
    student_name: str,
    quarter: str,
    quarter_courses: dict[str, list[dict[str, Any]]],
    dashboard_path: str,
    show_quarter: bool = False,
) -> dict[str, Any]:
    """Create one student's section on a quarter overview.

    Args:
        student_id: The student this section is for
        student_name: Display name for the heading
        quarter: Lowercase quarter (e.g. "q1")
        quarter_courses: Every student's courses this quarter, keyed by student ID
        dashboard_path: The base path for the dashboard (for navigation links)
        show_quarter: Append the quarter to the heading (used on the Now view)
    """
    gpa = _student_entity(student_id, "gpa", quarter)
    courses = quarter_courses[student_id]

    cards: list[dict[str, Any]] = [
        {
            "type": "heading",
            "heading": f"{student_name} · {quarter.upper()}" if show_quarter else student_name,
            "heading_style": "title",
            "icon": "mdi:account-school",
            "badges": [
                {
                    "type": "entity",
                    "entity": f"sensor.hac_student_{student_id}_last_scraped",
                    "show_state": True,
                    "show_icon": True,
                },
                {
                    "type": "button",
                    "icon": "mdi:refresh",
                    "tap_action": {
                        "action": "perform-action",
                        "perform_action": "button.press",
                        "target": {"entity_id": f"button.hac_student_{student_id}_force_refresh"},
                    },
                },
            ],
        },
        {
            "type": "custom:mushroom-template-card",
            "primary": "No grades posted yet",
            "secondary": f"{quarter.upper()} hasn't started or has no scored work",
            "icon": "mdi:calendar-clock",
            "color": "disabled",
            "grid_options": {"columns": "full"},
            "visibility": _no_data(gpa),
        },
        {
            "type": "custom:nodalia-circular-gauge-card",
            "entity": gpa,
            "name": "Average",
            "min": 0,
            "max": 100,
            "unit": "%",
            "grid_options": {"columns": 12, "rows": 4},
            "visibility": _has_data(gpa),
        },
        create_student_stats_grid(student_id, quarter),
        {"type": "heading", "heading": "Needs attention", "heading_style": "subtitle", "icon": "mdi:alert-outline"},
        create_attention_card(student_id, quarter, quarter_courses),
        {
            "type": "heading",
            "heading": f"Courses · {SPARKLINE_WEEKS}-week trend",
            "heading_style": "subtitle",
            "icon": "mdi:bookshelf",
        },
    ]
    cards.extend(create_course_tile(student_id, c, quarter, dashboard_path) for c in courses)
    cards.extend(create_student_trend_card(courses, quarter, gpa))

    return {"type": "grid", "column_span": 2, "cards": cards}


def _quarter_courses(
    students: dict[str, Any],
    student_ids: list[str],
    quarter: str,
) -> dict[str, list[dict[str, Any]]]:
    """Map each student with courses this quarter to their course list."""
    result = {}
    for student_id in student_ids:
        courses = students[student_id].get("quarters", {}).get(quarter, {}).get("courses", [])
        if courses:
            result[student_id] = courses
    return result


def _student_name(students: dict[str, Any], student_id: str) -> str:
    return students[student_id].get("name") or f"Student {student_id}"


def create_overview_view(
    metadata: dict[str, Any],
    quarter: str,
    dashboard_path: str = "dashboard-grades",
    student_order: list[str] | None = None,
) -> dict[str, Any]:
    """Create the overview view for a specific quarter."""
    quarter_lower = quarter.lower()
    students = metadata.get("students", {})
    student_ids = [sid for sid in (student_order or students) if sid in students]
    quarter_courses = _quarter_courses(students, student_ids, quarter)

    return {
        "title": quarter.upper(),
        "path": f"{quarter_lower}-overview",
        "icon": f"mdi:numeric-{quarter[-1]}-box-outline",
        "type": "sections",
        "max_columns": 4,
        "sections": [
            create_student_section(
                sid, _student_name(students, sid), quarter_lower, quarter_courses, dashboard_path
            )
            for sid in quarter_courses
        ],
    }


def create_now_view(
    metadata: dict[str, Any],
    quarters: list[str],
    dashboard_path: str = "dashboard-grades",
    student_order: list[str] | None = None,
) -> dict[str, Any]:
    """Create the default view showing each student's current quarter.

    Contains every quarter's student sections; each is only visible while the
    student's Current Quarter sensor reports that quarter.
    """
    students = metadata.get("students", {})
    student_ids = [sid for sid in (student_order or students) if sid in students]

    sections = []
    for student_id in student_ids:
        current = f"sensor.hac_student_{student_id}_current_quarter"
        sections.append({
            "type": "grid",
            "column_span": 2,
            "cards": [
                {
                    "type": "custom:mushroom-template-card",
                    "primary": _student_name(students, student_id),
                    "secondary": "Waiting for grades to determine the current quarter",
                    "icon": "mdi:calendar-question",
                    "color": "disabled",
                },
            ],
            "visibility": _no_data(current),
        })

    for quarter in quarters:
        quarter_courses = _quarter_courses(students, student_ids, quarter)
        for student_id in quarter_courses:
            section = create_student_section(
                student_id,
                _student_name(students, student_id),
                quarter.lower(),
                quarter_courses,
                dashboard_path,
                show_quarter=True,
            )
            section["visibility"] = [{
                "condition": "state",
                "entity": f"sensor.hac_student_{student_id}_current_quarter",
                "state": quarter.upper(),
            }]
            sections.append(section)

    return {
        "title": "Now",
        "path": "now",
        "icon": "mdi:calendar-today",
        "type": "sections",
        "max_columns": 4,
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Course subview
# ---------------------------------------------------------------------------


def create_category_card(course_clean: str, quarter: str, label: str, key: str, icon: str, weight: int) -> dict[str, Any]:
    """Create a category score card with a progress bar."""
    entity = _course_entity(course_clean, f"{key}_category_score", quarter)
    stats = _course_entity(course_clean, "assignment_category_statistics", quarter)

    secondary = (
        _jinja_percent(entity)
        + f"{{% set c = (state_attr('{stats}', 'categories') or []) "
        f"| selectattr('category', 'eq', '{label}') | list | first | default(none) %}}"
        "{% if c %} · {{ c.scored }}/{{ c.count }} graded{% endif %}"
    )

    return {
        "type": "custom:mushroom-template-card",
        "entity": entity,
        "primary": f"{label} ({weight}%)",
        "secondary": secondary,
        "icon": icon,
        "color": _jinja_grade_color(entity),
        "features": [{"type": "bar-gauge", "min": 0, "max": 100}],
        "features_position": "inline",
        "tap_action": {"action": "more-info"},
        "grid_options": {"columns": 12},
        "visibility": _has_data(entity),
    }


def create_course_summary_section(student_name: str, course: dict[str, Any], quarter: str) -> dict[str, Any]:
    """Create the top section of a course view.

    The gauge spans 7 grid rows on the left half; the cards after it (3
    category bars, latest assignment, last grade posted, and 2 rows of score
    tiles = 7 rows) fill the right half beside it. On a phone the section is
    one column wide, so everything stacks under the gauge.
    """
    course_clean = course["clean_name"]
    grade = _course_entity(course_clean, "grade", quarter)

    cards: list[dict[str, Any]] = [
        {
            "type": "heading",
            "heading": course["display_name"],
            "heading_style": "title",
            "icon": get_course_icon(course["display_name"]),
        },
        {
            "type": "heading",
            "heading": f"{student_name} · Quarter {quarter[-1]}",
            "heading_style": "subtitle",
        },
        {
            "type": "custom:nodalia-circular-gauge-card",
            "entity": grade,
            "name": "Overall",
            "min": 0,
            "max": 100,
            "unit": "%",
            "grid_options": {"columns": 12, "rows": 7},
        },
    ]
    cards.extend(create_category_card(course_clean, quarter, *cat) for cat in CATEGORIES)
    cards.extend(create_course_glance_cards(course_clean, quarter))

    return {"type": "grid", "column_span": 2, "cards": cards}


def create_course_glance_cards(course_clean: str, quarter: str) -> list[dict[str, Any]]:
    """Create the latest-assignment, last-posted, and score tile cards."""
    grade = _course_entity(course_clean, "grade", quarter)
    recent = _course_entity(course_clean, "recent_assignments", quarter)

    def tile(key: str, name: str, icon: str, color: str) -> dict[str, Any]:
        return {
            "type": "tile",
            "entity": _course_entity(course_clean, key, quarter),
            "name": name,
            "icon": icon,
            "color": color,
            "grid_options": {"columns": 6},
        }

    return [
        {
            "type": "custom:mushroom-template-card",
            "entity": recent,
            "primary": f"{{{{ state_attr('{recent}', 'latest_assignment') }}}}",
            "secondary": (
                f"{{% set s = state_attr('{recent}', 'latest_score') %}}"
                "Latest · {{ '—' if s is none else '%.1f' | format(s) ~ '%' }}"
            ),
            "icon": "mdi:clock-outline",
            "color": "blue",
            "multiline_secondary": True,
            "grid_options": {"columns": 12},
        },
        {
            "type": "custom:mushroom-template-card",
            "entity": grade,
            "primary": (
                f"{{% set d = state_attr('{grade}', 'days_since_update') %}}"
                "{{ 'Unknown' if d is none else 'Today' if d == 0 else '1 day ago' if d == 1 else d ~ ' days ago' }}"
            ),
            "secondary": "Last grade posted",
            "icon": "mdi:calendar-check-outline",
            "color": (
                f"{{% set d = state_attr('{grade}', 'days_since_update') %}}"
                "{{ 'disabled' if d is none else 'green' if d <= 7 else 'amber' if d <= 14 else 'red' }}"
            ),
            "grid_options": {"columns": 12},
        },
        tile("highest_assignment_score", "Highest", "mdi:trophy-outline", "green"),
        tile("lowest_assignment_score", "Lowest", "mdi:arrow-down-circle-outline", "orange"),
        tile("assignments_scored", "Scored", "mdi:file-check-outline", "blue"),
        tile("assignments_pending", "Pending", "mdi:file-clock-outline", "amber"),
    ]


def _trend_threshold(y: int) -> dict[str, Any]:
    """ApexCharts annotation drawing a dashed guide line at a grade cutoff."""
    return {
        "y": y,
        "borderColor": "var(--secondary-text-color)",
        "strokeDashArray": 4,
        "opacity": 0.5,
        # Label on the left, away from the current values at the right edge
        "label": {
            "text": f"{y}%",
            "position": "left",
            "textAnchor": "start",
            "borderWidth": 0,
            "style": {"background": "transparent", "color": "var(--secondary-text-color)"},
        },
    }


def _trend_yaxis(soft_min: int, ticks: int) -> dict[str, Any]:
    """Y axis for grade charts: 10-point ticks from soft_min up to a hard 110%.

    The hard cap keeps one extra-credit spike (e.g. 150% on a single early
    assignment) from flattening every other line; values above it still show
    in the tooltip. The minimum is soft, so a lower grade extends the axis.
    """
    return {"min": f"~{soft_min}", "max": 110, "decimals": 0, "apex_config": {"tickAmount": ticks}}


def _trend_line(entity: str, name: str, color: str, width: int) -> dict[str, Any]:
    """ApexCharts series for a grade sensor drawn as a stepped line."""
    return {
        "entity": entity,
        "name": name,
        "color": color,
        "stroke_width": width,
        # Grades change in steps when an assignment posts; don't interpolate
        "curve": "stepline",
        "extend_to": "now",
        # Bridge restarts and failed scrapes instead of breaking the line
        "fill_raw": "last",
        "show": {"legend_value": False},
    }


# Plots each graded assignment in a category at the time its score was
# posted. HAC only reports due dates, so the posted time is recovered from the
# recorder: the first stored version of the assignment list where the score is
# present. Assignments already graded at the start of the chart window (or if
# the history lookup fails) fall back to their due date.
_DOTS_JS = """return (async () => {
  const id = entity.entity_id;
  const key = (a) => a.title + '|' + a.due_date;
  const due = (a) => { const [m, d, y] = a.due_date.split('/'); return new Date(+y, +m - 1, +d, 12).getTime(); };
  const posted = {};
  try {
    const res = await hass.callWS({
      type: 'history/history_during_period',
      start_time: new Date(start).toISOString(),
      end_time: new Date(end).toISOString(),
      entity_ids: [id],
      minimal_response: false,
      no_attributes: false,
      significant_changes_only: false,
    });
    let first = true;
    for (const row of res[id] || []) {
      const list = row.a && row.a.assignments;
      if (!list) continue;
      for (const a of list) {
        if (a.percentage != null && !(key(a) in posted)) posted[key(a)] = first ? null : (row.lu || row.lc) * 1000;
      }
      first = false;
    }
  } catch (err) {}
  return (entity.attributes.assignments || [])
    .filter(a => a.category === '__CATEGORY__' && a.percentage != null && a.due_date)
    .map(a => [posted[key(a)] || due(a), Number(a.percentage)])
    .sort((p, q) => p[0] - q[0]);
})();
"""


def _assignment_dots(course_clean: str, quarter: str, category: str, color: str) -> dict[str, Any]:
    """ApexCharts series plotting each graded assignment in a category when it was posted.

    Shown in the legend so each category's dots can be toggled by tapping it.
    """
    return {
        "entity": _course_entity(course_clean, "assignment_details", quarter),
        "name": f"{category} assignments",
        "color": color,
        "stroke_width": 0,
        "show": {"legend_value": False},
        "data_generator": _DOTS_JS.replace("__CATEGORY__", category),
    }


def create_grade_trend_cards(course_clean: str, quarter: str) -> list[dict[str, Any]]:
    """Create the course trend heading and chart.

    Lines show the overall grade and each category score; dots show every
    graded assignment at its due date, colored by category.
    """
    lines = [_trend_line(_course_entity(course_clean, "grade", quarter), "Overall", "#7E57C2", 4)]
    lines += [
        {**_trend_line(_course_entity(course_clean, f"{key}_category_score", quarter), label,
                       CATEGORY_COLORS[key], 2), "opacity": 0.7}
        for label, key, _icon, _weight in CATEGORIES
    ]
    dots = [
        _assignment_dots(course_clean, quarter, label, CATEGORY_COLORS[key])
        for label, key, _icon, _weight in CATEGORIES
    ]

    return [
        {"type": "heading", "heading": f"Trend · last {TREND_WEEKS} weeks", "heading_style": "title", "icon": "mdi:chart-line"},
        {
            "type": "custom:apexcharts-card",
            "graph_span": TREND_SPAN,
            "header": {"show": False},
            "yaxis": [_trend_yaxis(50, 6)],
            "apex_config": {
                "chart": {"height": 300},
                "legend": {"show": True, "position": "bottom"},
                # Marker sizes per series: none on the lines, dots for assignments
                "markers": {
                    "size": [0] * len(lines) + [5] * len(dots),
                    "strokeWidth": 0,
                    "hover": {"sizeOffset": 2},
                },
                "annotations": {"yaxis": [_trend_threshold(90), _trend_threshold(80)]},
            },
            "series": lines + dots,
            "grid_options": {"columns": "full", "rows": "auto"},
        },
    ]


def create_student_trend_card(courses: list[dict[str, Any]], quarter: str, gpa: str) -> list[dict[str, Any]]:
    """Create a chart with one grade line per course for a student's quarter."""
    return [
        {
            "type": "heading",
            "heading": f"Trends · last {TREND_WEEKS} weeks",
            "heading_style": "subtitle",
            "icon": "mdi:chart-line",
            "visibility": _has_data(gpa),
        },
        {
            "type": "custom:apexcharts-card",
            "graph_span": TREND_SPAN,
            "header": {"show": False},
            "yaxis": [_trend_yaxis(60, 5)],
            "apex_config": {
                "chart": {"height": 300},
                "legend": {"show": True, "position": "bottom"},
                "annotations": {"yaxis": [_trend_threshold(90), _trend_threshold(80)]},
            },
            "series": [
                _trend_line(
                    _course_entity(c["clean_name"], "grade", quarter),
                    c["display_name"],
                    COURSE_COLORS[i % len(COURSE_COLORS)],
                    2,
                )
                for i, c in enumerate(courses)
            ],
            "grid_options": {"columns": "full", "rows": "auto"},
            "visibility": _has_data(gpa),
        },
    ]


def create_assignments_section(course_clean: str, quarter: str) -> dict[str, Any]:
    """Create the assignment table section.

    Phones get a compact table (due date, title, percent, status icon) since
    the full seven-column table doesn't fit at that width.
    """
    details = _course_entity(course_clean, "assignment_details", quarter)
    status_js = "({" + ", ".join(
        [f"'{s}': '{e} {l}'" for s, (e, l, _p) in STATUS_DISPLAY.items()]
        + ["'Scored': '✓ Scored'", "'EXEMPT': 'Exempt'"]
    ) + "})[x] || x"
    status_icon_js = "({" + ", ".join(
        [f"'{s}': '{e}'" for s, (e, _l, _p) in STATUS_DISPLAY.items()]
        + ["'Scored': '✓'", "'EXEMPT': 'Exempt'"]
    ) + "})[x] || x"
    percent_js = "x === null || x === undefined ? '—' : Number(x).toFixed(1) + '%'"
    phone = "(max-width: 767px)"

    return {
        "type": "grid",
        "column_span": 2,
        "cards": [
            {"type": "heading", "heading": "Assignments", "heading_style": "title", "icon": "mdi:format-list-checks"},
            {
                "type": "custom:flex-table-card",
                "entities": {"include": details},
                "columns": [
                    {"name": "Due", "data": "assignments.due_date"},
                    {"name": "Assignment", "data": "assignments.title"},
                    {"name": "Category", "data": "assignments.category"},
                    {
                        "name": "Score",
                        "data": "assignments.score",
                        "align": "right",
                        "modify": "x === null || x === undefined ? '—' : x",
                    },
                    {"name": "Out of", "data": "assignments.total_points", "align": "right"},
                    {"name": "%", "data": "assignments.percentage", "align": "right", "modify": percent_js},
                    {"name": "Status", "data": "assignments.status", "modify": status_js},
                ],
                "grid_options": {"columns": "full", "rows": "auto"},
                "visibility": [{"condition": "screen", "media_query": "(min-width: 768px)"}],
            },
            {
                "type": "custom:flex-table-card",
                "entities": {"include": details},
                "columns": [
                    {"name": "Due", "data": "assignments.due_date", "modify": "x ? x.slice(0, 5) : ''"},
                    {"name": "Assignment", "data": "assignments.title"},
                    {"name": "%", "data": "assignments.percentage", "align": "right", "modify": percent_js},
                    {"name": "", "data": "assignments.status", "align": "center", "modify": status_icon_js},
                ],
                "grid_options": {"columns": "full", "rows": "auto"},
                "visibility": [{"condition": "screen", "media_query": phone}],
            },
        ],
    }


def create_course_view(
    student_id: str,
    course: dict[str, Any],
    quarter: str,
    dashboard_path: str = "dashboard-grades",
    student_name: str | None = None,
) -> dict[str, Any]:
    """Create a drill-down subview for a specific course."""
    course_clean = course["clean_name"]
    quarter_lower = quarter.lower()
    student_name = student_name or f"Student {student_id}"

    return {
        "title": f"{student_name} · {course['display_name']} ({quarter.upper()})",
        "path": _course_path(quarter_lower, student_id, course_clean),
        "icon": get_course_icon(course["display_name"]),
        "type": "sections",
        # No back_path: the back arrow returns to the previous page, which may
        # be the Now view or a quarter tab
        "subview": True,
        "max_columns": 2,
        "sections": [
            create_course_summary_section(student_name, course, quarter_lower),
            {"type": "grid", "column_span": 2, "cards": create_grade_trend_cards(course_clean, quarter_lower)},
            create_assignments_section(course_clean, quarter_lower),
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def generate_dashboard(
    metadata: dict[str, Any],
    dashboard_path: str = "dashboard-grades",
    student_order: list[str] | None = None,
) -> dict[str, Any]:
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

    # Students in the requested order first, then any not listed
    ordered = [sid for sid in (student_order or []) if sid in students]
    all_student_ids = ordered + [sid for sid in students if sid not in ordered]
    _LOGGER.info("Student order: %s", all_student_ids)

    all_quarters = sorted({q for s in students.values() for q in s.get("quarters", {})})
    _LOGGER.info("Found %d quarters: %s", len(all_quarters), all_quarters)

    views = [create_now_view(metadata, all_quarters, dashboard_path, all_student_ids)]
    views += [create_overview_view(metadata, q, dashboard_path, all_student_ids) for q in all_quarters]

    for student_id in all_student_ids:
        student_data = students[student_id]
        student_name = student_data.get("name")
        for quarter in sorted(student_data.get("quarters", {})):
            for course in student_data["quarters"][quarter].get("courses", []):
                views.append(create_course_view(student_id, course, quarter, dashboard_path, student_name))

    _LOGGER.info("Generated dashboard with %d total views", len(views))

    return {"views": views}


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
        help="Comma-separated list of student IDs to specify display order (e.g., '100001,100002')",
        default=None,
    )
    parser.add_argument(
        "--student-names",
        type=str,
        help="Comma-separated list of student names in format 'ID:Name' (e.g., '100001:Alex,100002:Sam')",
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
