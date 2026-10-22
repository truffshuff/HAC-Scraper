# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Missing Sensors After a Failed Scrape**: If the configured quarter failed to load at startup (e.g. browserless dropped the connection), the quarters that did load were discarded and none of that student's quarter or course sensors were created until the next restart; they showed as "unavailable". The other quarters are now kept, and sensors for any quarter or course that appears on a later refresh are added then.

## [0.4.2] - 2026-10-11

### Fixed

- **HACS Validation**: `hacs.json` no longer has the `category` and `domain` keys HACS rejects, and the validation workflow is restored (now on `actions/checkout@v5`). Brand images were removed from this repository; they're provided separately, so the workflow skips the `brands` check.

## [0.4.1] - 2026-10-11

### Added

- **Remove Stale Entities Action**: `hac_grades.remove_stale_entities` removes entities and course devices for courses that no longer exist (e.g. last year's classes), with a `dry_run` option. Students whose quarters didn't all load at startup are skipped so a failed scrape can't delete real entities. `regenerate_dashboard.sh --remove-stale [--dry-run]` calls it through the Home Assistant API.

### Fixed

- **Dashboard Entity IDs**: The metadata file now records each student's actual refresh button, Last Scraped, and Current Quarter entity IDs, and the generator uses them, so dashboards work when those IDs differ from the defaults (e.g. `button.force_refresh_2`).
- **Refresh Button Naming**: New installs get `button.hac_student_<id>_force_refresh` instead of `button.force_refresh`, `button.force_refresh_2`, and so on. Existing button IDs are unchanged.
- **regenerate_dashboard.sh**: Options after the path (such as `--student-names` and `--student-order`) are now passed to the generator, and a missing PyYAML package is reported clearly.

## [0.4.0] - 2026-10-11

### Added

- **Current Quarter Sensor**: `sensor.hac_student_<id>_current_quarter` reports the latest quarter with graded work. The quarter HAC selects by default is available as the `hac_selected_quarter` attribute.
- **Now Dashboard View**: The generated dashboard opens on a "Now" tab that shows each student's current quarter.

### Changed

- **Dashboard Redesign**: The generated dashboard now uses Mushroom, Nodalia, and flex-table cards. Quarter tabs show a GPA gauge, stat tiles, an untruncated "Needs attention" table (padded so side-by-side students stay aligned), a per-student trend chart with one line per course, and color-coded course cards with 3-week grade sparklines. Course pages are hidden subviews with a back arrow: the grade gauge with category progress bars and at-a-glance stats beside it, a full-width stepped trend chart (8 weeks, 90%/80% guides, no gaps across restarts, a dot per graded assignment placed when its score was posted, toggleable from the legend), and an assignment table with a compact phone layout.
- **Course Icons**: Icons now match on word starts and cover HAC abbreviations (e.g. "Int Lang Arts" no longer gets the art icon; "Prin Acct Fin", "Hnr Chemistry", and "Weight Train" get specific icons).

### Fixed

- **Device Registry Deprecation**: Course devices now link to the student device with `via_device_id` instead of the deprecated `via_device` identifier tuple (stops working in Home Assistant 2027.8).

## [0.3.1] - 2025-11-29

### Fixed

- **Async Initialization**: Fixed improper use of `async_config_entry_first_refresh()` which caused deprecation warning. Entity creation now properly waits for coordinator data using polling mechanism that runs in background task.
- **JSON Metadata Corruption**: Fixed race condition where sensor.py and binary_sensor.py were writing to the same metadata file simultaneously, causing JSON corruption. Added error recovery (auto-delete corrupted file) and 2-second delay between writes to prevent conflicts.
- **Optimized Retry Timing**: Faster initial retry attempts (5s, 10s, 15s) with exponential backoff for later attempts. Reduced stagger delay from 30s to 5s to minimize startup time while still preventing overwhelming browserless with simultaneous requests.

## [0.3.0] - 2025-11-29

### Fixed

- **Browserless Connection Retry**: Added exponential backoff retry logic (12 attempts with delays up to 5 minutes) to handle cases where browserless service is not ready during Home Assistant startup or reboot. This fixes the issue where the integration would fail to start properly when HA reboots before browserless is fully initialized. The integration will now automatically retry connection attempts for up to ~20 minutes and wait for browserless to become available instead of requiring manual reload.
- **Browserless Health Check**: Added health check before attempting login to avoid unnecessary timeout errors when browserless is not yet ready.
- **Sensor Platform Timeout**: Increased sensor platform initialization timeout from 4 minutes to 15 minutes to accommodate very slow browserless startup times on some systems. This prevents the "Coordinator data still not available" error that occurred when browserless took longer than expected to start.
- **Reduced Stagger Delay**: Reduced initial random delay from 2 minutes to 30 seconds to speed up login when browserless is ready.

## [0.2.0] - 2025-01-28

### Breaking Changes

- **Entity IDs changed**: Entities now use student ID and quarter instead of student name
  - Old format: `sensor.john_gpa`
  - New format: `sensor.student_12345_q2_gpa`
- Configuration now requires **Student ID** instead of Student Name

### Added

- **Quarter Selection**: Choose which quarter/marking period to track (Q1, Q2, Q3, Q4)
- **Student ID Validation**: Integration validates that the provided student ID matches what's in HAC
- **Multi-Quarter Support**: Track multiple quarters for the same student
- **Dynamic Dashboard Generation**: Automatic Lovelace dashboard creation from entity metadata
- **Force Refresh Button**: Manual grade update trigger for each student
- **Enhanced Sensors**: Total TLTC, Total SBF, missing assignment details, course update tracking
- **Assignment Status Tracking**: NHI, NYG, TLTC, SBF status codes with emoji indicators

### Changed

- Entity ID format now includes student ID and quarter for uniqueness
- Configuration flow updated to use student ID instead of name
- HAC client validates student ID from HTML response

### Technical Details

- HAC client accepts and validates student ID from HTML
- Added quarter parameter support (uses MarkingPeriod query param)
- Coordinator updated to pass student ID and quarter
- All sensors and binary sensors use student_id + quarter in entity_id
- Async file I/O operations to prevent blocking event loop
- Metadata file auto-generation for dashboard system

## [0.1.0] - 2024-12-01

### Added
- Home Assistant custom integration for HAC grades
- Automatic course discovery
- Dynamic entity creation
- Overall and per-course sensors
- Binary sensors for alerts
- Category score tracking (Practice, Process, Product)
- Assignment details with status tracking
- Missing assignment detection
