#!/bin/bash
# Helper script to regenerate HAC Grades dashboard
# Usage: ./regenerate_dashboard.sh [config_dir]

set -e

# Default to current directory if not specified
CONFIG_DIR="${1:-.}"

# Metadata file is in the integration's custom_components folder
METADATA_FILE="$CONFIG_DIR/custom_components/hac_grades/hac_entity_registry.json"
OUTPUT_FILE="$CONFIG_DIR/hac_grades_dashboard_generated.yaml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "HAC Grades Dashboard Generator"
echo "========================================="
echo ""
echo "Config Directory: $CONFIG_DIR"
echo "Metadata File: $METADATA_FILE"
echo "Output File: $OUTPUT_FILE"
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

echo "Using Python: $PYTHON_CMD"
echo ""

# Run the generator
echo "Generating dashboard..."
"$PYTHON_CMD" "$SCRIPT_DIR/generate_dashboard.py" \
    --metadata-file "$METADATA_FILE" \
    --output "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
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
else
    echo ""
    echo "ERROR: Dashboard generation failed"
    exit 1
fi
