#!/bin/bash
# Helper script to regenerate HAC Grades dashboard
#
# Usage: ./regenerate_dashboard.sh [config_dir|path/to/hac_entity_registry.json] [options]
#
# Any options after the path are passed to generate_dashboard.py, e.g.:
#   ./regenerate_dashboard.sh /config --student-names "100001:Alex,100002:Sam" --student-order 100001,100002
#   ./regenerate_dashboard.sh /config --remove-stale --dry-run
#
# --remove-stale also removes entities and course devices for courses that no
# longer exist (e.g. last year's classes). It calls Home Assistant's API, so
# it needs --ha-url and --token (or HA_URL and HA_TOKEN set). In a Home
# Assistant app (add-on) terminal it connects automatically.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The first argument is the config dir or metadata file, unless it's an option
if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
    ARG="$1"
    shift
else
    ARG="."
fi

# Accept either a config directory (containing custom_components/hac_grades/hac_entity_registry.json)
# or a direct path to a metadata JSON file.
if [ -f "$ARG" ]; then
    METADATA_FILE="$ARG"
    OUTPUT_FILE="$(dirname "$ARG")/hac_grades_dashboard_generated.yaml"
    CONFIG_DIR="$(dirname "$ARG")"
else
    CONFIG_DIR="$ARG"
    METADATA_FILE="$CONFIG_DIR/custom_components/hac_grades/hac_entity_registry.json"
    OUTPUT_FILE="$CONFIG_DIR/hac_grades_dashboard_generated.yaml"
fi

echo "========================================="
echo "HAC Grades Dashboard Generator"
echo "========================================="
echo ""
echo "Config Directory: $CONFIG_DIR"
echo "Metadata File: $METADATA_FILE"
echo "Output File: $OUTPUT_FILE"
if [ $# -gt 0 ]; then
    echo "Options: $*"
fi
echo ""

# Check if metadata file exists
if [ ! -f "$METADATA_FILE" ]; then
    echo "ERROR: Metadata file not found: $METADATA_FILE"
    echo ""
    echo "Make sure:"
    echo "  1. The HAC Grades integration is installed and running"
    echo "  2. Sensors have been created at least once"
    echo "  3. You're running this script from the correct directory"
    echo ""
    exit 1
fi

# Check if Python is available
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python not found"
    echo "Please install Python 3"
    exit 1
fi

if ! "$PYTHON_CMD" -c "import yaml" &> /dev/null; then
    echo "ERROR: The PyYAML package is missing"
    echo "Install it with: $PYTHON_CMD -m pip install pyyaml"
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
echo ""

# Run the generator (set -e exits here with its status if it fails)
echo "Generating dashboard..."
"$PYTHON_CMD" "$SCRIPT_DIR/generate_dashboard.py" \
    --metadata-file "$METADATA_FILE" \
    --output "$OUTPUT_FILE" \
    "$@"

echo ""
echo "========================================="
echo "SUCCESS!"
echo "========================================="
echo ""
echo "Dashboard generated: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "  1. Copy the contents of $OUTPUT_FILE"
echo "  2. In Home Assistant, go to Settings → Dashboards"
echo "  3. Select your dashboard and click Edit"
echo "  4. Click the three dots → Raw configuration editor"
echo "  5. Paste the generated YAML"
echo "  6. Save"
echo ""
