# Quick Start Guide - Dynamic HAC Dashboard

## TL;DR

Your dashboards can now be automatically generated when courses change!

## What Changed?

✅ HAC Grades integration now automatically creates a metadata file
✅ New script generates complete dashboard YAML from that metadata
✅ No more manual editing of 621KB YAML files!

## Prerequisites

Before generating dashboards:

1. **Install Custom Cards** (via HACS → Frontend):
   - **ApexCharts Card** (Required) - Grade trend visualizations
   - **Auto-entities** (Recommended) - Dynamic course lists
   - **Bar Card** (Recommended) - Grade percentage displays

2. **Verify Integration Setup**:
   - Browserless Chrome running (default: `http://homeassistant.local:3000/function`)
   - HAC Grades integration configured
   - Sensors created successfully

See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions.

## First Time Setup

### 1. Ensure Integration is Running

The modified files are already in place:
- [custom_components/hac_grades/sensor.py](custom_components/hac_grades/sensor.py)
- [custom_components/hac_grades/binary_sensor.py](custom_components/hac_grades/binary_sensor.py)

If you're using the integration elsewhere, you need to reload it for the changes to take effect.

### 2. Verify Metadata File Creation

After the integration runs (or after reloading it):
1. Check your integration directory: `custom_components/hac_grades/`
2. Look for `hac_entity_registry.json`
3. This file is automatically created/updated by the integration

### 3. Generate Your First Dashboard

```bash
# Navigate to your Home Assistant config directory
cd /path/to/homeassistant/config

# Run the generator (adjust path as needed)
python3 /path/to/generate_dashboard.py

# Or use the helper script
/path/to/regenerate_dashboard.sh
```

### 4. Apply to Home Assistant

1. Open the generated file: `hac_grades_dashboard_generated.yaml`
2. Copy all contents
3. In Home Assistant: Settings → Dashboards → Your Dashboard → Edit
4. Click three dots → "Raw configuration editor"
5. Paste the YAML
6. Click Save

Done! 🎉

## When Courses Change

### Quick Version
```bash
# 1. Reload HAC Grades integration in Home Assistant UI
# 2. Wait 2-5 minutes for new sensors
# 3. Run regeneration:
./regenerate_dashboard.sh

# 4. Copy output to Home Assistant dashboard
```

### Detailed Version

**Step 1: Reload Integration**
- Go to Settings → Devices & Services
- Find "HAC Grades"
- Click three dots → Reload

**Step 2: Wait for Sensors**
- The integration needs to fetch new data
- New sensors will be created automatically
- Metadata file updates automatically
- Usually takes 2-5 minutes

**Step 3: Regenerate Dashboard**
```bash
cd /path/to/homeassistant/config
python3 /path/to/generate_dashboard.py
# OR
/path/to/regenerate_dashboard.sh
```

**Step 4: Update Home Assistant**
- Copy the generated YAML
- Paste into your dashboard's raw configuration editor
- Save

## Files You'll Use

### Scripts
- [generate_dashboard.py](generate_dashboard.py) - Main generator
- [regenerate_dashboard.sh](regenerate_dashboard.sh) - Helper script

### Documentation
- [DASHBOARD_GENERATION.md](DASHBOARD_GENERATION.md) - Complete documentation
- This file - Quick start

### Automatically Created
- `hac_entity_registry.json` - Created by integration in `custom_components/hac_grades/`
- `hac_grades_dashboard_generated.yaml` - Created by generator script

## Common Commands

### Test with sample data
```bash
python3 generate_dashboard.py \
  --metadata-file sample_hac_entity_registry.json \
  --output test.yaml
```

### Generate for specific location
```bash
python3 generate_dashboard.py \
  --metadata-file /config/hac_entity_registry.json \
  --output /config/dashboards/hac.yaml
```

### Use helper script
```bash
# From anywhere, specify config directory
./regenerate_dashboard.sh /path/to/homeassistant/config

# From config directory
./regenerate_dashboard.sh
```

## Troubleshooting

### "Metadata file not found"
- Make sure HAC Grades integration has run at least once
- Check Settings → Devices & Services → HAC Grades
- Try reloading the integration

### "No module named yaml"
```bash
pip3 install pyyaml
# OR use the venv
./venv/bin/python generate_dashboard.py
```

### "Entities not found in Home Assistant"
- Verify sensors are created: Developer Tools → States
- Search for `sensor.hac_student_` or `sensor.<course_name>`
- If missing, reload the integration

### Dashboard looks wrong
- Check entity IDs match between generated YAML and Home Assistant
- Verify all custom cards are installed (e.g., ApexCharts)
- Check Home Assistant logs for errors

## What Gets Generated?

### For 2 students, 2 quarters, 2 courses each:
- **2 Quarter Overview pages** (Q1, Q2)
  - All student GPAs
  - Grade statistics
  - Missing assignments

- **8 Course Detail pages** (one per student/quarter/course)
  - Grade gauges
  - Category breakdowns
  - Assignment details
  - Trend charts

### Total: 10 dashboard views

## Advanced: Automation (Optional)

Create a button in Home Assistant to regenerate:

```yaml
# configuration.yaml
shell_command:
  regenerate_hac_dashboard: >
    cd /config &&
    python3 /config/scripts/generate_dashboard.py

# dashboard button
type: button
name: Regenerate HAC Dashboard
tap_action:
  action: call-service
  service: shell_command.regenerate_hac_dashboard
```

## Need Help?

1. Read [DASHBOARD_GENERATION.md](DASHBOARD_GENERATION.md) for detailed documentation
2. Check the [README.md](README.md) for general integration information
3. Visit the [GitHub Issues](https://github.com/dustinhouseman/HAC-Scraper/issues) for support

## Summary

**Before:**
- Manual YAML editing
- 621KB file to maintain
- Error-prone when courses change

**After:**
- Run one script
- Automatic entity discovery
- Dashboard updates in < 1 minute

---

**Questions? Issues? Check the full documentation in DASHBOARD_GENERATION.md**
