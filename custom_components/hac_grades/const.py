"""Constants for the HAC Grades integration."""
from datetime import timedelta

DOMAIN = "hac_grades"

# Configuration
CONF_SCHOOL_URL = "school_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_STUDENT_ID = "student_id"
CONF_QUARTER = "quarter"
CONF_STUDENTS = "students"
CONF_BROWSERLESS_URL = "browserless_url"

# Defaults
DEFAULT_SCAN_INTERVAL = timedelta(hours=6)
DEFAULT_TIMEOUT = 60
DEFAULT_QUARTER = "Q2"  # Default to current quarter
DEFAULT_BROWSERLESS_URL = "http://homeassistant.local:3000/function"

# Quarter options
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

# Assignment status types
STATUS_SCORED = "Scored"
STATUS_NHI = "NHI"  # Not Handed In
STATUS_NYG = "NYG"  # Not Yet Graded
STATUS_TLTC = "TLTC"  # Too Late To Count
STATUS_SBF = "SBF"  # Score Below Fifty
STATUS_EXEMPT = "EXEMPT"

# Category weights (standard HAC weighting)
CATEGORY_WEIGHTS = {
    "PRACTICE": 0.20,
    "PROCESS": 0.30,
    "PRODUCT": 0.50
}

# Data keys
DATA_COORDINATOR = "coordinator"
DATA_UNDO_UPDATE_LISTENER = "undo_update_listener"
