# Dynamic Dashboard Generation for HAC Grades

This system automatically generates Lovelace dashboard YAML configurations based on the entities created by the HAC Grades Home Assistant integration.

## Prerequisites

### Required Custom Cards

The generated dashboards use these HACS frontend cards. Install them before importing the dashboard:

1. **Mushroom** (v5 or newer): course cards, stat tiles, and category bars
   - Repository: [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)
2. **Nodalia Cards**: circular GPA and course grade gauges
   - Repository: [danielmigueltejedor/nodalia-cards](https://github.com/danielmigueltejedor/nodalia-cards)
3. **flex-table-card**: the full assignment table on each course page
   - Repository: [custom-cards/flex-table-card](https://github.com/custom-cards/flex-table-card)
4. **ApexCharts Card**: the grade trend chart on each course page
   - Repository: [RomRider/apexcharts-card](https://github.com/RomRider/apexcharts-card)

Install via **HACS → Frontend** and search for each card by name. Without them, the dashboard shows "Custom element doesn't exist" errors for those cards.

Home Assistant 2026.2 or newer is recommended (heading button badges and the `trend-graph` / `bar-gauge` card features).

## Overview

The system consists of three components:

1. **Entity Metadata Writer** (in `sensor.py` and `binary_sensor.py`) - Automatically creates a metadata file when sensors are set up
2. **Metadata File** (`hac_entity_registry.json`) - JSON file containing information about all students, quarters, and courses
3. **Dashboard Generator** (`generate_dashboard.py`) - Python script that reads the metadata and generates a complete dashboard YAML

## How It Works

### 1. Automatic Metadata Generation

When the HAC Grades integration creates sensors, it automatically writes entity metadata to:
```
<home-assistant-config-dir>/custom_components/hac_grades/hac_entity_registry.json
```

This file contains:
- Student IDs
- Available quarters (Q1, Q2, Q3, Q4)
- Course information (clean names, display names, indices)
- Binary sensor types
- Last update timestamp

**No manual intervention needed** - the metadata file is created and updated automatically whenever the integration reloads or sensors are created.

### 2. Dashboard Generation

Run the `generate_dashboard.py` script to create a complete dashboard YAML:

```bash
# Basic usage (from Home Assistant config directory)
python3 generate_dashboard.py

# Specify custom paths
python3 generate_dashboard.py \
  --metadata-file /path/to/hac_entity_registry.json \
  --output /path/to/output.yaml

# Specify student display order
python3 generate_dashboard.py \
  --student-order "123456,789012"

# Specify student friendly names
python3 generate_dashboard.py \
  --student-names "123456:John,789012:Jane"

# Combine all options
python3 generate_dashboard.py \
  --metadata-file /path/to/hac_entity_registry.json \
  --output /path/to/output.yaml \
  --dashboard-path dashboard-grades \
  --student-order "789012,123456" \
  --student-names "789012:Jane,123456:John"
```

### 3. Using the Generated Dashboard

1. Copy the generated YAML content
2. In Home Assistant, go to Settings → Dashboards
3. Click the three dots → "Edit Dashboard"
4. Click the three dots again → "Raw configuration editor"
5. Paste the generated YAML
6. Save

## Generated Dashboard Structure

The dashboard includes:

### Now (default tab)
Opens on each student's current quarter, as reported by their **Current Quarter** sensor (the latest quarter with graded work). It shows the same sections as the quarter tabs below, with the quarter in each student's heading, and switches to the next quarter by itself once that quarter's first grade posts.

### Overview Pages (one tab per quarter)
Each quarter tab (**Q1**, **Q2**, ...) has one section per student with:
- **Heading** with the last-scraped time and a refresh button
- **GPA gauge** with highest/lowest grade, missing and not-graded counts beside it
- **Needs attention** table listing every missing, too-late, below-50, and not-yet-graded assignment across all courses (read from each course's assignment details, so nothing is truncated). Each table pads itself with blank rows to match the student with the most items, so side-by-side students stay aligned.
- **Course cards**, colored by grade (green ≥90, amber ≥80, orange ≥70, red below), with days since the last grade posted, a 3-week grade sparkline, and a red badge when the course has missing work. Tap a card to open the course page.
- **Trends** chart with one stepped line per course over the last 8 weeks, with 90%/80% guides and a shared 60–110% scale so side-by-side students are directly comparable

A quarter with no grades yet shows a "No grades posted yet" card instead of the gauge.

### Course Pages (hidden subviews)
One page per course per student per quarter. They are subviews, so they stay out of the tab bar, and their back arrow returns to the page you came from (Now or a quarter tab). Each includes:
- **Smart Icons**: picks an MDI icon from the course name (Spanish → translate, Hnr Chemistry → flask, Prin Acct Fin → calculator, and so on)
- **Summary**: the overall grade gauge on the left; on the right, Practice / Process / Product cards (weight, score, graded count, progress bar), the latest assignment, days since the last grade posted, highest/lowest score, and scored/pending counts. On a phone these stack under the gauge.
- **Trend chart** (full width): overall grade and category scores over the last 8 weeks, drawn as steps since grades only change when an assignment posts, with dashed 90%/80% guides. Each graded assignment is plotted as a dot in its category's color at the time its score was posted (found from the recorder history; anything already graded when the 8-week window starts falls back to its due date), so each dot lines up with the step it caused. Tap "Practice/Process/Product assignments" in the legend to hide or show that set of dots. The scale is capped at 110% so a single extra-credit score can't flatten the chart (hover still shows the real value). Gaps from restarts or failed scrapes are bridged with the last known value. Showing the full range needs the recorder to keep at least 8 weeks of history (`recorder: purge_keep_days: 56` or more; the default is 10).
- **Assignments table**: every assignment with due date, category, score, percentage, and status. Phones get a compact version (date, title, percentage, status icon).

## Updating the Dashboard When Courses Change

### Automatic Method (Recommended)
When courses change in HAC:
1. The integration will detect new courses during the next update
2. New sensors will be created automatically
3. The metadata file will be updated automatically
4. Run the dashboard generator script again
5. Update your dashboard in Home Assistant

### Manual Method
If you need to force a regeneration:
1. Reload the HAC Grades integration in Home Assistant
2. Wait for sensors to be created
3. Run `generate_dashboard.py`
4. Update your dashboard

### Removing Old Courses
Entities for courses that no longer exist (last year's classes, a dropped elective) stay in Home Assistant as "unavailable" forever. The integration's **Remove stale entities** action (`hac_grades.remove_stale_entities`) deletes them, along with any course devices left empty. Run it from **Developer tools → Actions**, or from the script:

```bash
# See what would be removed
./regenerate_dashboard.sh /config --remove-stale --dry-run

# Remove it, then regenerate the dashboard
./regenerate_dashboard.sh /config --remove-stale --student-names "123456:John,789012:Jane"
```

The script calls Home Assistant's API, so it needs the URL and a long-lived access token (your profile → **Security** → **Long-lived access tokens**): pass `--ha-url` and `--token`, or set `HA_URL` and `HA_TOKEN`. In a Home Assistant app (add-on) terminal it connects automatically.

A student is skipped unless all four quarters loaded the last time the integration started, because a quarter that failed to load would make its real entities look stale. If one is skipped, reload the integration and try again.

Everything after the path in `regenerate_dashboard.sh` is passed to `generate_dashboard.py`, so `--student-names`, `--student-order`, and `--dashboard-path` work there too.

## Automation (Optional)

You can create a Home Assistant automation to regenerate the dashboard automatically:

```yaml
automation:
  - alias: "Regenerate HAC Dashboard on Course Changes"
    trigger:
      - platform: state
        entity_id: sensor.hac_student_<ID>_all_quarters_summary
        attribute: total_courses
    action:
      - service: shell_command.generate_hac_dashboard
```

And add this to your `configuration.yaml`:

```yaml
shell_command:
  generate_hac_dashboard: >
    cd /config &&
    python3 generate_dashboard.py
    --metadata-file custom_components/hac_grades/hac_entity_registry.json
    --output dashboards/hac_grades_generated.yaml
    --student-order "123456,789012"
    --student-names "123456:John,789012:Jane"
```

## Customization

### Course Icons

The dashboard generator automatically selects appropriate icons based on course names. The icon picker includes mappings for:

**Languages**: Spanish, French, German, Chinese, Latin, English
**Math**: Algebra, Geometry, Calculus, Statistics
**Science**: Biology, Chemistry, Physics, Earth Science, Astronomy
**Social Studies**: History, Geography, Government, Economics
**Arts**: Art, Music, Band, Orchestra, Drama, Dance
**Technology**: Computer Science, Programming, Robotics, Engineering
**Business**: Marketing, Accounting, Finance, Entrepreneurship
**PE & Health**: Physical Education, Sports, Fitness

You can customize icon mappings by editing the `get_course_icon()` function in `generate_dashboard.py` (lines 25-119).

### Student Display Order

By default, students appear in the order they're found in the metadata file. To customize the display order, use the `--student-order` parameter:

```bash
python3 generate_dashboard.py --student-order "123456,789012"
```

**How it works:**
- Students will appear in the specified order in all dashboard sections:
  - GPA gauges and statistics on overview pages
  - Assignment alerts on overview pages
  - Course grade sections on overview pages
  - Individual course pages in the navigation
- If you list only some students, the remaining ones will be added at the end in their original order
- Student IDs that don't exist in the metadata will be ignored
- This setting must be specified each time you regenerate the dashboard

**Example:** To always show Student 789012 first, then Student 123456:
```bash
python3 generate_dashboard.py \
  --metadata-file custom_components/hac_grades/hac_entity_registry.json \
  --output dashboards/hac_grades.yaml \
  --student-order "789012,123456"
```

### Student Names

By default, students are labeled as "Student 123456", etc. You can customize student names in two ways:

**Method 1: Command-line parameter (Recommended)**

Use the `--student-names` parameter when generating the dashboard:

```bash
python3 generate_dashboard.py --student-names "123456:John,789012:Jane"
```

**How it works:**
- Format: `StudentID:Name,StudentID:Name,...`
- Names can contain spaces: `"123456:John Smith,789012:Jane Jones"`
- Only specify the students you want to rename
- Student IDs that don't exist in the metadata will be ignored
- This setting must be specified each time you regenerate the dashboard

**Example:**
```bash
python3 generate_dashboard.py \
  --metadata-file custom_components/hac_grades/hac_entity_registry.json \
  --output dashboards/hac_grades.yaml \
  --student-order "789012,123456" \
  --student-names "789012:Jane,123456:John"
```

**Method 2: Edit metadata file directly**

Alternatively, you can edit the metadata file and add a `"name"` field to each student:

```json
{
  "students": {
    "123456": {
      "name": "John",
      "student_id": "123456",
      ...
    }
  }
}
```

Then regenerate the dashboard. Note that manually edited names in the metadata file will be overwritten if you use the `--student-names` parameter.

### Card Customization
To customize the generated cards, edit `generate_dashboard.py` and modify the card creation functions:
- `create_student_section()` - Layout of each student's section on a quarter overview
- `create_course_tile()` - Course cards (colors, sparkline, badge)
- `create_attention_card()` - The "Needs attention" table
- `create_course_view()` - Course page layout
- `COURSE_ICONS` - Course name keyword → icon mapping

## Troubleshooting

### Metadata file not found
- Make sure the HAC Grades integration has been set up and has run at least once
- Check that sensors are being created in Home Assistant
- Look for `hac_entity_registry.json` in `custom_components/hac_grades/` directory

### Dashboard generation fails
- Ensure PyYAML is installed: `pip3 install pyyaml`
- Check that the metadata file is valid JSON
- Review the error messages in the console output

### Entities not showing in dashboard
- Verify sensor entity IDs match the generated YAML
- Check Home Assistant Developer Tools → States to see actual entity IDs
- The script uses the same naming conventions as the integration

### Regenerating after course changes
1. Reload the integration in Home Assistant
2. Wait 2-5 minutes for new sensors to be created
3. Run the generator script again
4. Update your dashboard

## File Locations

- **Integration code**: `custom_components/hac_grades/sensor.py`, `binary_sensor.py`
- **Metadata file**: `custom_components/hac_grades/hac_entity_registry.json` (auto-generated)
- **Generator script**: `generate_dashboard.py`
- **Sample metadata**: `sample_hac_entity_registry.json`

## Examples

### Generate with default settings
```bash
cd /path/to/homeassistant/config
python3 /path/to/generate_dashboard.py
```

### Generate from a specific location
```bash
python3 generate_dashboard.py \
  --metadata-file /config/custom_components/hac_grades/hac_entity_registry.json \
  --output /config/dashboards/hac_grades.yaml
```

### Test generation with sample data
```bash
python3 generate_dashboard.py \
  --metadata-file sample_hac_entity_registry.json \
  --output test_output.yaml
```

## Benefits

✅ **No manual dashboard editing** when courses change
✅ **Consistent formatting** across all course pages
✅ **Automatic entity discovery** - script knows about all created sensors
✅ **Multi-student support** - handles multiple students automatically
✅ **Multi-quarter support** - creates views for all available quarters
✅ **Easy customization** - modify Python functions instead of editing massive YAML files
✅ **Version control friendly** - generate from metadata, commit the generator script

## Future Enhancements

Possible improvements:
- Web interface for dashboard generation
- Template system for custom dashboard layouts
- Automatic dashboard updating via Home Assistant service
- Support for custom card types
- Integration with HACS for easier distribution
