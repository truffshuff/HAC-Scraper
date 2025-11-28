# Dynamic Dashboard Generation for HAC Grades

This system automatically generates Lovelace dashboard YAML configurations based on the entities created by the HAC Grades Home Assistant integration.

## Prerequisites

### Required Custom Cards

The generated dashboards use custom Lovelace cards. Install these via HACS before using the dashboards:

1. **ApexCharts Card** (Required)
   - Used for grade trend visualizations
   - Install: HACS → Frontend → Search "ApexCharts Card"
   - Repository: [RomRider/apexcharts-card](https://github.com/RomRider/apexcharts-card)

2. **Auto-entities** (Optional but recommended)
   - Used for dynamic course lists
   - Install: HACS → Frontend → Search "Auto-entities"
   - Repository: [thomasloven/lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities)

3. **Bar Card** (Optional but recommended)
   - Used for grade percentage displays
   - Install: HACS → Frontend → Search "Bar Card"
   - Repository: [custom-cards/bar-card](https://github.com/custom-cards/bar-card)

**Without these cards**, the dashboard will show errors for those card types. ApexCharts is especially important as it's used for the grade trends section on each course page.

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
  --student-order "148613,170512"

# Specify student friendly names
python3 generate_dashboard.py \
  --student-names "148613:Owen,170512:Emma"

# Combine all options
python3 generate_dashboard.py \
  --metadata-file /path/to/hac_entity_registry.json \
  --output /path/to/output.yaml \
  --dashboard-path dashboard-grades \
  --student-order "170512,148613" \
  --student-names "170512:Emma,148613:Owen"
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

### Overview Pages (per quarter)
- **Q1 Overview**, **Q2 Overview**, etc.
- Student GPA gauges for all students
- Grade statistics for each student
- Missing assignment alerts
- Last updated timestamp

### Individual Course Pages
One page per course per student per quarter, including:
- **Smart Icons**: Automatically selects appropriate MDI icons based on course name
  - Math courses → calculator icon
  - Science → flask icon
  - Spanish/French → translate icon
  - Art → palette icon
  - And many more!
- **Gauges**: Overall grade, Practice, Process, Product scores
- **Category Statistics**: Breakdown by assignment category
- **Extended Entities**: Detailed grade information
- **Latest Assignments**: Recent assignments with scores
- **Assignment Details**: Complete assignment list with filtering
- **Grade Trends Chart**: ApexCharts visualization of category scores over time

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
    --student-order "148613,170512"
    --student-names "148613:Owen,170512:Emma"
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
python3 generate_dashboard.py --student-order "148613,170512"
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

**Example:** To always show Student 170512 first, then Student 148613:
```bash
python3 generate_dashboard.py \
  --metadata-file custom_components/hac_grades/hac_entity_registry.json \
  --output dashboards/hac_grades.yaml \
  --student-order "170512,148613"
```

### Student Names

By default, students are labeled as "Student 148613", etc. You can customize student names in two ways:

**Method 1: Command-line parameter (Recommended)**

Use the `--student-names` parameter when generating the dashboard:

```bash
python3 generate_dashboard.py --student-names "148613:Owen,170512:Emma"
```

**How it works:**
- Format: `StudentID:Name,StudentID:Name,...`
- Names can contain spaces: `"148613:Owen Smith,170512:Emma Jones"`
- Only specify the students you want to rename
- Student IDs that don't exist in the metadata will be ignored
- This setting must be specified each time you regenerate the dashboard

**Example:**
```bash
python3 generate_dashboard.py \
  --metadata-file custom_components/hac_grades/hac_entity_registry.json \
  --output dashboards/hac_grades.yaml \
  --student-order "170512,148613" \
  --student-names "170512:Emma,148613:Owen"
```

**Method 2: Edit metadata file directly**

Alternatively, you can edit the metadata file and add a `"name"` field to each student:

```json
{
  "students": {
    "148613": {
      "name": "Owen",
      "student_id": "148613",
      ...
    }
  }
}
```

Then regenerate the dashboard. Note that manually edited names in the metadata file will be overwritten if you use the `--student-names` parameter.

### Card Customization
To customize the generated cards, edit `generate_dashboard.py` and modify the card creation functions:
- `create_gauge_card()` - Gauge appearance
- `create_stats_markdown()` - Statistics display
- `create_course_gauge_section()` - Course page layout
- etc.

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
