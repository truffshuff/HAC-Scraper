# HAC Grades Integration - Usage Guide

## Configuring Update Interval

The integration automatically fetches grades from HAC at a configurable interval.

### How to Change Update Interval

1. Go to **Settings** → **Devices & Services**
2. Find **HAC Grades** integration
3. Click the **Configure** button (gear icon) on any student entry
4. Adjust the **Update interval (hours)** slider (1-24 hours)
5. Click **Submit**

The integration will automatically reload with the new interval.

### Default Interval

- **Default**: 6 hours
- **Range**: 1-24 hours

### Important Notes

- Each student configuration has a random startup delay of 0-2 minutes to prevent overwhelming browserless
- This delay helps when you have multiple students configured
- The delay only applies at integration startup and during automatic updates

## Force Refresh Button

Each student configuration has a **Force Refresh** button entity that triggers an immediate grade fetch for all quarters.

### How to Use Force Refresh

1. Go to **Settings** → **Devices & Services**
2. Find **HAC Grades** integration
3. Click on a student device
4. Find the **Force Refresh** button entity
5. Click **Press** to trigger an immediate update

Alternatively, you can:
- Add the button to your dashboard
- Use it in automations
- Call the `button.press` service

### Example Automation

```yaml
automation:
  - alias: "Refresh Student Grades Every Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.student_12345_q2_force_refresh
```

**Note**: The Force Refresh button fetches data for all configured quarters, not just the current one.

## Understanding the Update Process

### What Happens During an Update

1. **Random Delay**: 0-120 seconds (0-2 minutes) to stagger requests
2. **Login**: Uses browserless Chrome to authenticate
3. **Fetch Q2**: Cached from initial login (fastest)
4. **Fetch Q1**: Separate browserless session with quarter selection
5. **Fetch Q3**: Separate browserless session (may be empty if quarter hasn't started)
6. **Fetch Q4**: Separate browserless session (may be empty if quarter hasn't started)

### Performance Considerations

- Each quarter fetch requires a full login + navigation sequence
- Q2 is optimized (cached from initial login)
- Q1, Q3, Q4 each require ~30-60 seconds
- **Total time per student**: ~2-4 minutes
- **With multiple students**: Staggered by 0-2 minutes each

### Browserless Load

With 2 students configured:
- **Worst case**: 8 browserless sessions (2 students × 4 quarters)
- **Best case**: 6 sessions (2 students × 3 quarters, with Q2 cached)
- **Duration**: Spread over 0-4 minutes due to random delays

## Sensors Created

For each student, the integration creates sensors for each quarter:

### Overall Sensors (per quarter)
- `sensor.student_{id}_{quarter}_gpa` - GPA-like average across all courses
- `sensor.student_{id}_{quarter}_course_count` - Number of courses

### Course Sensors (per quarter, per course)
- `sensor.student_{id}_{quarter}_{course}_grade` - Course grade percentage
- Binary sensors for alerts (missing assignments, low grades, etc.)

### Example Entities

For student 148613 in Q2:
- `sensor.student_148613_q2_gpa`
- `sensor.student_148613_q2_course_count`
- `sensor.student_148613_q2_biology_grade`
- `sensor.student_148613_q2_english_grade`
- etc.

## Best Practices

### Recommended Update Interval

- **6 hours** (default): Good balance between freshness and server load
- **12 hours**: Twice daily updates (morning and evening)
- **24 hours**: Once daily (minimal load)
- **1-3 hours**: For active monitoring during grading periods

### When to Use Force Refresh

- After known grade postings (e.g., end of week)
- Before parent-teacher conferences
- When checking if a specific assignment has been graded
- After submitting late work

### Multiple Students

When configuring multiple students:
- Each student gets their own random delay
- Updates are automatically staggered
- Force refresh can be triggered independently per student
- Consider setting a longer scan interval (12-24 hours) and using force refresh for on-demand updates

## Troubleshooting

### Updates Taking Too Long

- Check browserless Chrome logs
- Verify network connectivity to HAC
- Consider increasing scan interval to reduce load

### Timeouts

- Browserless sessions have 90-second timeout
- Navigation steps have 45-second timeout
- Check browserless resource limits

### Missing Quarters

- Q3 and Q4 may be empty early in the school year
- This is normal and not an error
- Sensors will show 0 courses for empty quarters
