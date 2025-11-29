# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
