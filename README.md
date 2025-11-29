<div align="center">
  <img src="brands/hac_grades/logo.png" alt="HAC Grades Logo" width="200"/>

  # HAC Grades - Home Assistant Custom Integration

  [![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
  ![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)
  ![License](https://img.shields.io/badge/license-MIT-green.svg)

  **A Home Assistant custom integration that fetches student grades from Home Access Center (HAC) and creates dynamic sensors for monitoring academic performance.**
</div>

---

## ✨ Features

- 🔐 **Secure Configuration** - Credentials stored securely via Home Assistant config flow
- 📊 **Dynamic Entity Creation** - Automatically creates sensors for all courses
- 🎯 **Comprehensive Metrics** - Track grades, missing assignments, category scores, and more
- 🔔 **Binary Sensors** - Alert when assignments are missing or grades fall below thresholds
- 🔄 **Automatic Updates** - Configurable polling interval (default: every 6 hours)
- 👥 **Multi-Student Support** - Add multiple accounts for different students
- 📈 **Rich Data** - Assignment details, category breakdowns, GPA calculations

## 📋 Prerequisites

### Required: Browserless Chrome

This integration **requires** a Browserless Chrome instance to scrape grade data from HAC websites (HAC sites use JavaScript that require browser automation).

**Option 1: Home Assistant Add-on (Easiest)**

Install the Browserless Chrome add-on:

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Search for "**Browserless**" or "**Chrome**"
3. Install a compatible browserless add-on
4. Configure:
   - Port: `3000` (default)
   - Token: Optional (leave blank for local use)
5. Click **Start** and enable **Start on boot**

**Option 2: Docker**

Run browserless via Docker on your network:
```bash
docker run -d -p 3000:3000 --name browserless browserless/chrome
```

**Important**: The browserless URL can be configured during integration setup (defaults to `http://homeassistant.local:3000/function`).

### Optional: Custom Dashboard Cards

For enhanced dashboards, install these HACS frontend cards:

- **[ApexCharts Card](https://github.com/RomRider/apexcharts-card)** - Grade trend visualizations
- **[Auto-entities](https://github.com/thomasloven/lovelace-auto-entities)** - Dynamic course lists
- **[Bar Card](https://github.com/custom-cards/bar-card)** - Grade percentage displays

Install via: **HACS** → **Frontend** → Search for card name

## 📦 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/truffshuff/HAC-Scraper`
6. Select category: "Integration"
7. Click "Add"
8. Search for "HAC Grades" and install
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/hac_grades` directory to your Home Assistant's `custom_components` folder
2. Restart Home Assistant
3. Add the integration via the UI

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **HAC Grades**
4. Enter your configuration:
   - **Student ID**: The student's unique ID from HAC (will be validated)
   - **School HAC URL**: Your school's Home Access Center URL (e.g., `https://hac.hcps.org`)
   - **Username**: Your HAC username
   - **Password**: Your HAC password
   - **Browserless URL** (optional): URL to your browserless instance (defaults to `http://homeassistant.local:3000/function`)

## 🎯 Entities Created

### 📊 Overall Sensors

For each configured student/quarter combination, the integration creates:

- `sensor.student_[id]_[quarter]_gpa` - Overall GPA-like average across all courses
- `sensor.student_[id]_[quarter]_course_count` - Total number of courses
- `sensor.student_[id]_[quarter]_max_grade` - Highest grade among all courses
- `sensor.student_[id]_[quarter]_min_grade` - Lowest grade among all courses
- `sensor.student_[id]_[quarter]_total_nhi` - Total NHI (Not Handed In) assignments
- `sensor.student_[id]_[quarter]_total_nyg` - Total NYG (Not Yet Graded) assignments
- `sensor.student_[id]_[quarter]_course_list` - Comma-separated list of course names
- `binary_sensor.student_[id]_[quarter]_any_missing_assignments` - Alert when any assignments need attention

**Example**: If you configure student ID "12345" for Q2, you'll get entities like:
- `sensor.student_12345_q2_gpa`
- `sensor.student_12345_q2_max_grade`
- `binary_sensor.student_12345_q2_any_missing_assignments`

### 📚 Per-Course Sensors

For each course, the integration creates:

- `sensor.student_[id]_[quarter]_[course]_grade` - Overall course grade percentage
- `sensor.student_[id]_[quarter]_[course]_practice_score` - Practice category percentage
- `sensor.student_[id]_[quarter]_[course]_process_score` - Process category percentage
- `sensor.student_[id]_[quarter]_[course]_product_score` - Product category percentage
- `sensor.student_[id]_[quarter]_[course]_total_assignments` - Total number of assignments
- `sensor.student_[id]_[quarter]_[course]_assignments_scored` - Number of graded assignments
- `sensor.student_[id]_[quarter]_[course]_assignments_pending` - Number of pending assignments
- `sensor.student_[id]_[quarter]_[course]_not_hand_in` - Count of NHI assignments
- `sensor.student_[id]_[quarter]_[course]_assignment_details` - Detailed assignment data (attributes)
- `binary_sensor.student_[id]_[quarter]_[course]_has_missing_assignments` - Alert for missing assignments
- `binary_sensor.student_[id]_[quarter]_[course]_grade_below_threshold` - Alert when grade < 90%

**Example**: For student 12345's Q2 Biology class, you'll get entities like:
- `sensor.student_12345_q2_biology_grade`
- `sensor.student_12345_q2_biology_practice_score`
- `binary_sensor.student_12345_q2_biology_has_missing_assignments`

## 📱 Example Dashboard

Here's a basic Lovelace dashboard example:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Academic Overview
    entities:
      - entity: sensor.hac_student_gpa
        name: Overall GPA
      - entity: sensor.hac_student_highest_grade
        name: Best Grade
      - entity: sensor.hac_student_lowest_grade
        name: Needs Attention
      - entity: binary_sensor.hac_student_missing_assignments_alert
        name: Missing Work

  - type: custom:auto-entities
    card:
      type: entities
      title: Course Grades
    filter:
      include:
        - entity_id: "sensor.*_grade"
          options:
            type: custom:bar-card
    sort:
      method: state
      reverse: true

  - type: conditional
    conditions:
      - entity: binary_sensor.hac_student_missing_assignments_alert
        state: "on"
    card:
      type: markdown
      content: |
        ## ⚠️ Missing Assignments

        **Total NHI:** {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'total_nhi') }}
        **Total NYG:** {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'total_nyg') }}
        **Total TLTC:** {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'total_tltc') }}
        **Total SBF:** {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'total_sbf') }}
```

## 📝 Assignment Status Codes

- **Scored** - Assignment has been graded
- **NHI** - Not Handed In
- **NYG** - Not Yet Graded (submitted but not graded)
- **TLTC** - Too Late To Count
- **SBF** - Score Below Fifty
- **EXEMPT** - Excused/Exempt assignment

## ⚖️ Category Weighting

The integration calculates grades using standard HAC category weights:

- **Practice**: 20%
- **Process**: 30%
- **Product**: 50%

## 🤖 Automation Examples

### Notify on New Missing Assignment

```yaml
automation:
  - alias: "Alert on Missing Assignment"
    trigger:
      - platform: state
        entity_id: binary_sensor.hac_student_missing_assignments_alert
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Missing Assignments"
          message: >
            {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'message') }}
```

### Weekly Grade Report

```yaml
automation:
  - alias: "Weekly Grade Report"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: time
        weekday:
          - fri
    action:
      - service: notify.family
        data:
          title: "📚 Weekly Grade Report"
          message: |
            Overall GPA: {{ states('sensor.hac_student_gpa') }}%
            Courses: {{ states('sensor.hac_student_course_count') }}
            Missing Work: {{ state_attr('binary_sensor.hac_student_missing_assignments_alert', 'message') }}
```

### Grade Below Threshold Alert

```yaml
automation:
  - alias: "Low Grade Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.biology_grade_below_threshold
        to: "on"
    action:
      - service: notify.parents
        data:
          title: "📉 Grade Alert"
          message: >
            Biology grade has fallen to {{ states('sensor.biology_grade') }}%
```

## ⚙️ Configuration Options

After installation, you can configure:

- **Update Interval** - How often to poll HAC (1-24 hours, default: 6 hours)
- **Force Refresh** - Manually trigger grade updates via button entity

## 👨‍👩‍👧‍👦 Multiple Students and Quarters

The integration supports tracking multiple students and multiple quarters:

### Multiple Students (Same HAC Login)
1. Add Student 1 Q2: Student ID = "12345", Quarter = "Q2", Username = "parent.username"
2. Add Student 2 Q2: Student ID = "67890", Quarter = "Q2", Username = "parent.username"

Each student gets unique entity IDs based on their student ID.

### Multiple Quarters (Same Student)
1. Add Student Q1: Student ID = "12345", Quarter = "Q1", Username = "parent.username"
2. Add Student Q2: Student ID = "12345", Quarter = "Q2", Username = "parent.username"
3. Add Student Q3: Student ID = "12345", Quarter = "Q3", Username = "parent.username"

This lets you track historical quarters or compare current vs previous quarters.

### Example Entity IDs:
- Student 12345, Q2: `sensor.student_12345_q2_gpa`
- Student 12345, Q1: `sensor.student_12345_q1_gpa`
- Student 67890, Q2: `sensor.student_67890_q2_gpa`

## 🚀 Advanced Features

### Dynamic Dashboard Generation

This integration includes a powerful dashboard generation system that automatically creates beautiful Lovelace dashboards based on your students' courses. See [DASHBOARD_GENERATION.md](DASHBOARD_GENERATION.md) for details.

### Force Refresh

Each student configuration includes a Force Refresh button entity for on-demand grade updates. See [USAGE.md](USAGE.md) for more information.

## 📖 Documentation

- [Installation Guide](INSTALLATION.md) - Detailed installation instructions
- [Usage Guide](USAGE.md) - How to use the integration
- [Dashboard Generation](DASHBOARD_GENERATION.md) - Automatic dashboard creation
- [Quick Start](QUICKSTART.md) - Get started quickly with dashboards
- [Changelog](CHANGELOG.md) - Version history

## 🔧 Troubleshooting

### Common Issues

**Login Failed**
- Verify your credentials are correct
- Ensure the school URL is correct and accessible
- Check that your HAC account is active

**No Entities Created**
- Check the Home Assistant logs for errors
- Ensure you have courses showing in HAC
- Verify the student ID matches exactly

**Entities Not Updating**
- Check the update interval in integration options
- Manually trigger an update via the Force Refresh button
- Verify HAC is accessible and not under maintenance

**Integration Fails After Reboot**
- The integration now automatically retries connection to browserless with exponential backoff
- It will wait up to ~20 minutes for browserless to become available
- **IMPORTANT**: Ensure browserless is configured to "Start on boot" if using HA add-on
- If browserless takes longer than 5 minutes to start, check its logs for errors
- Verify port 3000 is accessible and not blocked by firewall
- After browserless becomes available, the integration will automatically connect - no manual reload needed

For more detailed troubleshooting, see [INSTALLATION.md](INSTALLATION.md).

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 💬 Support

If you encounter issues:

1. Check the [documentation](README.md)
2. Search existing [GitHub issues](https://github.com/truffshuff/HAC-Scraper/issues)
3. Create a new issue with:
   - Home Assistant version
   - Integration version
   - Error logs (redact personal information)
   - Steps to reproduce

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Created by TruffShuff

Inspired by the need to monitor children's academic progress efficiently through Home Assistant.

## ⚠️ Disclaimer

This integration is not affiliated with or endorsed by Home Access Center or any school district. Use at your own risk. Always verify grade information directly with your school's official HAC portal.
