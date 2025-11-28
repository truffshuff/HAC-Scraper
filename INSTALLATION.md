# Installation Guide

## Prerequisites

### Required

- **Home Assistant 2024.1.0 or newer**
- **Active Home Access Center (HAC) account**
- **Browserless Chrome** - Required for scraping HAC websites
  - Install as Home Assistant add-on or via Docker
  - See [Prerequisites in README](README.md#prerequisites) for detailed setup
  - Default expects browserless at `192.168.1.236:3000`
- **HACS** (recommended for easiest installation)

### Optional (For Enhanced Dashboards)

- **ApexCharts Card** - Grade trend visualizations
- **Auto-entities Card** - Dynamic course lists
- **Bar Card** - Grade percentage displays

Install optional cards via: **HACS** → **Frontend** → Search for card name

## Method 1: HACS Installation (Recommended)

### Step 1: Add Custom Repository

1. Open Home Assistant
2. Navigate to **HACS** in the sidebar
3. Click on **Integrations**
4. Click the **⋮** (three dots) in the top right corner
5. Select **Custom repositories**
6. Add the following:
   - **Repository**: `https://github.com/dustinhouseman/HAC-Scraper`
   - **Category**: `Integration`
7. Click **Add**

### Step 2: Install Integration

1. In HACS Integrations, search for "**HAC Grades**"
2. Click on the integration
3. Click **Download**
4. Restart Home Assistant

### Step 3: Configure Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for "**HAC Grades**"
4. Fill in the configuration form:

   ```
   Student ID: 12345 (your student's ID from HAC)
   Quarter: Q2 (select Q1, Q2, Q3, or Q4)
   School HAC URL: https://hac.hcps.org (or your school's URL)
   Username: your.username
   Password: your_password
   ```

5. Click **Submit**
6. Wait for initial data fetch (may take 30-60 seconds)

**Note**: The integration will validate that the provided Student ID matches the ID in HAC.

## Method 2: Manual Installation

### Step 1: Download Files

1. Download the latest release from GitHub
2. Extract the ZIP file

### Step 2: Copy Files

1. Copy the `custom_components/hac_grades` folder to your Home Assistant's `config/custom_components/` directory

   Your directory structure should look like:
   ```
   config/
   ├── custom_components/
   │   └── hac_grades/
   │       ├── __init__.py
   │       ├── binary_sensor.py
   │       ├── config_flow.py
   │       ├── const.py
   │       ├── coordinator.py
   │       ├── hac_client.py
   │       ├── manifest.json
   │       ├── sensor.py
   │       └── strings.json
   ```

### Step 3: Restart Home Assistant

1. Go to **Settings** → **System** → **Restart**
2. Wait for Home Assistant to restart

### Step 4: Add Integration

Follow Step 3 from Method 1 above.

## Adding Multiple Students

To monitor multiple students:

1. Complete the installation steps above for the first student
2. Go to **Settings** → **Devices & Services**
3. Click **+ ADD INTEGRATION** again
4. Search for "**HAC Grades**"
5. Enter the credentials for the second student
6. Repeat for each additional student

Each student will have their own device with separate entities.

## Verifying Installation

After installation and configuration:

1. Go to **Settings** → **Devices & Services**
2. Find "**HAC Grades**" in your integrations
3. Click on it to see the device
4. You should see entities like:
   - `sensor.student_[id]_[quarter]_gpa`
   - `sensor.student_[id]_[quarter]_course_count`
   - Multiple course-specific sensors (e.g., `sensor.student_12345_q2_biology_grade`)
   - Binary sensors for alerts
   - Force refresh button entity

## Configuring Options

After installation, you can adjust settings:

1. Go to **Settings** → **Devices & Services**
2. Find "**HAC Grades**"
3. Click **Configure** (or the three dots → **Configure**)
4. Adjust **Update Interval** (1-24 hours)
5. Click **Submit**

## Troubleshooting

### Integration Not Found

- Ensure you copied files to the correct directory
- Restart Home Assistant
- Clear browser cache

### Login Fails

- Double-check credentials
- Verify school URL is correct (should start with `https://`)
- Ensure HAC account is active and not locked
- Try logging in directly to HAC website to verify credentials

### No Data/Entities

- Check **Settings** → **System** → **Logs** for errors
- Ensure student has active courses
- Wait for initial data fetch (can take 1-2 minutes)
- Try manual refresh from integration page

### Entities Show "Unavailable"

- Check internet connection
- Verify HAC website is accessible
- Check if credentials are still valid
- **Verify browserless is running** (Settings → Add-ons → Browserless)
- Check browserless logs for errors
- Review Home Assistant logs for specific errors

### Browserless Issues

**Connection Failed**
- Verify browserless add-on is running and started
- Check the port (default: 3000) matches integration code
- If using Docker, ensure it's accessible from Home Assistant
- Update `hac_client.py` line 63 if using different IP/port

**Timeout Errors**
- Browserless may be overwhelmed if multiple students configured
- Increase browserless resource limits in add-on configuration
- Consider spreading out update times

## Uninstallation

1. Go to **Settings** → **Devices & Services**
2. Find "**HAC Grades**"
3. Click the three dots → **Delete**
4. Confirm deletion
5. (Optional) Remove the `custom_components/hac_grades` folder
6. Restart Home Assistant

## Getting Help

If you encounter issues:

1. Check the [README.md](README.md) for common issues
2. Review Home Assistant logs
3. Open an issue on GitHub with:
   - Home Assistant version
   - Integration version
   - Error logs (redact personal info)
   - Steps to reproduce
