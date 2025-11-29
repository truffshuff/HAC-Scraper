"""HAC (Home Access Center) client for scraping grade data."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    CATEGORY_WEIGHTS,
    STATUS_EXEMPT,
    STATUS_NHI,
    STATUS_NYG,
    STATUS_SBF,
    STATUS_SCORED,
    STATUS_TLTC,
)

_LOGGER = logging.getLogger(__name__)


class HACClient:
    """Client to interact with Home Access Center."""

    def __init__(
        self,
        school_url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        student_id: str | None = None,
        quarter: str = "Q2",
        browserless_url: str = "http://homeassistant.local:3000/function",
    ) -> None:
        """Initialize the HAC client."""
        self.school_url = school_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = session
        self.student_id = student_id
        self.quarter = quarter
        self.browserless_url = browserless_url
        self._cookies = None
        self._detected_student_id = None
        self._initial_html = None  # HTML from initial browserless login
        self._initial_quarter = None  # Which quarter the initial HTML represents

    async def _check_browserless_ready(self) -> bool:
        """Check if browserless is ready to accept requests."""
        try:
            # Try to hit the browserless health endpoint or root
            health_url = self.browserless_url.replace("/function", "/")
            async with self.session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                return response.status in [200, 404]  # 404 is ok, means server is up
        except Exception:
            return False

    async def login(self) -> bool:
        """Login to HAC using browserless Chrome and extract cookies."""
        # Retry configuration for browserless connection
        # Extended retry schedule to handle slow browserless startup during system boot
        max_retries = 12
        retry_delays = [5, 10, 15, 20, 30, 45, 60, 90, 120, 150, 180, 240]  # Faster initial retries

        for attempt in range(max_retries):
            try:
                # Check if browserless is ready before attempting login (skip on first attempt to be fast)
                if attempt > 0:
                    if not await self._check_browserless_ready():
                        retry_delay = retry_delays[attempt] if attempt < len(retry_delays) else 240
                        _LOGGER.info(
                            "Browserless not ready yet (attempt %d/%d). "
                            "Waiting %d seconds before next check...",
                            attempt + 1, max_retries, retry_delay
                        )
                        await asyncio.sleep(retry_delay)
                        continue

                # Add a small random delay to stagger requests when multiple students
                # are configured (prevents overwhelming browserless)
                # Only apply stagger delay on first attempt, and keep it very short
                if attempt == 0:
                    import random
                    delay = random.uniform(0, 5)  # Very short stagger to reduce blocking
                    _LOGGER.debug("Waiting %.1f seconds before login to stagger requests", delay)
                    await asyncio.sleep(delay)

                login_url = f"{self.school_url}/HomeAccess/Account/LogOn"

                # Use browserless Chrome to perform the login

                # JavaScript function to run in the browser
                # Escape special characters in credentials for JavaScript
                escaped_username = self.username.replace("'", "\\'").replace('"', '\\"')
                escaped_password = self.password.replace("'", "\\'").replace('"', '\\"')

                browser_script = f"""
export default async ({{ page }}) => {{
    try {{
        // Navigate to login page
        await page.goto('{login_url}', {{
            waitUntil: 'networkidle2',
            timeout: 45000
        }});

        // Wait a moment for page to be ready
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Type credentials
        await page.type('input[name="LogOnDetails.UserName"]', '{escaped_username}');
        await page.type('input[name="LogOnDetails.Password"]', '{escaped_password}');

        // Submit login
        await Promise.all([
            page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 45000 }}),
            page.click('button#login')
        ]);

        // Wait for page to settle
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Navigate to student picker page to select the correct student
        const response = await page.goto('{self.school_url}/HomeAccess/Frame/StudentPicker', {{
            waitUntil: 'networkidle2',
            timeout: 30000
        }}).catch(() => null);

        if (response && response.ok()) {{
            // We're on the student picker page - check if we have the student selector
            const hasStudentInput = await page.$('input[name="studentId"][value="{self.student_id}"]');

            if (hasStudentInput) {{
                // Click the radio button for this student
                await page.click('input[name="studentId"][value="{self.student_id}"]');

                // Submit the form to switch students
                await Promise.all([
                    page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 30000 }}),
                    page.evaluate(() => {{
                        const form = document.querySelector('form');
                        if (form) form.submit();
                    }})
                ]);

                // Wait for the switch to complete
                await new Promise(resolve => setTimeout(resolve, 2000));
            }}
        }}

        // Now navigate to the assignments page
        await page.goto('{self.school_url}/HomeAccess/Content/Student/Assignments.aspx', {{
            waitUntil: 'networkidle2',
            timeout: 45000
        }});

        // Wait for grades to load - this is critical!
        await page.waitForSelector('span[id*="lblOverallAverage"]', {{ timeout: 10000 }});

        // Get the HTML content after everything has loaded
        const html = await page.content();
        const url = page.url();
        const cookies = await page.cookies();

        // Get selected student ID for verification from the banner
        // Navigate to Classwork page to read the banner (Assignments.aspx doesn't have it)
        let selectedStudentId = null;
        try {{
            await page.goto('{self.school_url}/HomeAccess/Classes/Classwork', {{
                waitUntil: 'networkidle2',
                timeout: 15000
            }});
            const banner = await page.$('.sg-banner');
            if (banner) {{
                selectedStudentId = await page.$eval('.sg-banner', el => el.getAttribute('data-student-id'));
            }}
        }} catch (e) {{
            // If we can't get to classwork page, that's okay
        }}

        return {{ url, cookies, html, selectedStudentId }};
    }} catch (error) {{
        return {{ error: error.message }};
    }}
}};
"""

                _LOGGER.debug("Sending browserless request to: %s (attempt %d/%d)",
                             self.browserless_url, attempt + 1, max_retries)

                # Execute the browser script via browserless /function endpoint
                # Allow up to 90 seconds for the full login + navigation sequence
                async with self.session.post(
                    self.browserless_url,
                    data=browser_script,
                    headers={"Content-Type": "application/javascript"},
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as response:
                    if response.status != 200:
                        _LOGGER.error("Browserless request failed with status: %s", response.status)
                        return False

                    result = await response.json()

                    if "error" in result:
                        _LOGGER.error("Browser automation error: %s", result["error"])
                        return False

                    final_url = result.get("url", "")
                    cookies = result.get("cookies", [])
                    initial_html = result.get("html", "")
                    selected_student_id = result.get("selectedStudentId")

                    _LOGGER.debug("Browser login completed, final URL: %s", final_url)
                    _LOGGER.debug("Received %d cookies", len(cookies))
                    _LOGGER.debug("Received HTML content: %d characters", len(initial_html))
                    _LOGGER.info("Login for student ID: %s (requested) / %s (selected)",
                                self.student_id, selected_student_id)

                    # Check if we landed on an error page
                    if "/Error" in final_url:
                        _LOGGER.error("Login failed - redirected to error page: %s", final_url)
                        return False

                    # Check if we're still on the login page
                    if "/LogOn" in final_url:
                        _LOGGER.error("Login failed - still on login page (invalid credentials)")
                        return False

                    # Success if we reached any authenticated page (not login/error)
                    # The assignments page navigation in the script should have succeeded
                    _LOGGER.info("Login successful, landed on: %s", final_url)

                    # Import cookies into our aiohttp session
                    # Create a simple cookie dict for the session
                    for cookie in cookies:
                        self.session.cookie_jar.update_cookies(
                            {cookie["name"]: cookie["value"]},
                            response.url
                        )

                    self._cookies = self.session.cookie_jar
                    # Store the initial HTML and detect which quarter it represents
                    self._initial_html = initial_html
                    self._initial_quarter = self._detect_quarter_from_html(initial_html)

                    # Store the detected student ID from the browser script
                    if selected_student_id:
                        self._detected_student_id = selected_student_id
                        _LOGGER.info("Detected student ID from banner: %s", selected_student_id)

                    _LOGGER.info(
                        "Successfully logged in to HAC using browserless (cookies: %d, initial quarter: %s)",
                        len(cookies),
                        self._initial_quarter or "unknown"
                    )
                    return True

            except aiohttp.ClientConnectorError as err:
                # Connection error - browserless might not be ready yet
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    _LOGGER.warning(
                        "Cannot connect to browserless (attempt %d/%d): %s. "
                        "Retrying in %d seconds...",
                        attempt + 1, max_retries, err, retry_delay
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    _LOGGER.error(
                        "Failed to connect to browserless after %d attempts: %s",
                        max_retries, err
                    )
                    return False

            except asyncio.TimeoutError as err:
                # Timeout error - might also be a browserless startup issue
                if attempt < max_retries - 1:
                    retry_delay = retry_delays[attempt]
                    _LOGGER.warning(
                        "Browserless request timed out (attempt %d/%d). "
                        "Retrying in %d seconds...",
                        attempt + 1, max_retries, retry_delay
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    _LOGGER.error(
                        "Browserless request timed out after %d attempts",
                        max_retries
                    )
                    return False

            except Exception as err:
                # Other errors should not be retried (e.g., invalid credentials)
                _LOGGER.error("Error during browserless login: %s", err, exc_info=True)
                return False

        # If we exhausted all retries without success
        return False

    async def _fetch_quarter_with_browserless(self, quarter: str) -> str | None:
        """Fetch a specific quarter's HTML using browserless to change the dropdown."""
        try:
            # Map quarter to dropdown value (format: {quarter_num}-{year})
            # We'll use 2026 as the year since that's what appears in the HTML
            quarter_num = quarter[1]  # Extract number from "Q1", "Q2", etc.
            quarter_value = f"{quarter_num}-2026"

            # Escape credentials
            escaped_username = self.username.replace("'", "\\'").replace('"', '\\"')
            escaped_password = self.password.replace("'", "\\'").replace('"', '\\"')

            browser_script = f"""
export default async ({{ page }}) => {{
    try {{
        // Login
        await page.goto('{self.school_url}/HomeAccess/Account/LogOn', {{
            waitUntil: 'networkidle2',
            timeout: 45000
        }});

        await new Promise(resolve => setTimeout(resolve, 1000));

        await page.type('input[name="LogOnDetails.UserName"]', '{escaped_username}');
        await page.type('input[name="LogOnDetails.Password"]', '{escaped_password}');

        await Promise.all([
            page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 45000 }}),
            page.click('button#login')
        ]);

        await new Promise(resolve => setTimeout(resolve, 2000));

        // Navigate to student picker page to select the correct student
        const response = await page.goto('{self.school_url}/HomeAccess/Frame/StudentPicker', {{
            waitUntil: 'networkidle2',
            timeout: 30000
        }}).catch(() => null);

        if (response && response.ok()) {{
            // We're on the student picker page - check if we have the student selector
            const hasStudentInput = await page.$('input[name="studentId"][value="{self.student_id}"]');

            if (hasStudentInput) {{
                // Click the radio button for this student
                await page.click('input[name="studentId"][value="{self.student_id}"]');

                // Submit the form to switch students
                await Promise.all([
                    page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 30000 }}),
                    page.evaluate(() => {{
                        const form = document.querySelector('form');
                        if (form) form.submit();
                    }})
                ]);

                // Wait for the switch to complete
                await new Promise(resolve => setTimeout(resolve, 2000));
            }}
        }}

        // Navigate to assignments page
        await page.goto('{self.school_url}/HomeAccess/Content/Student/Assignments.aspx', {{
            waitUntil: 'networkidle2',
            timeout: 45000
        }});

        // Wait for the dropdown to be available
        await page.waitForSelector('#plnMain_ddlReportCardRuns', {{ timeout: 15000 }});

        // Select the quarter from the dropdown
        await page.select('#plnMain_ddlReportCardRuns', '{quarter_value}');

        // Click the refresh button to load the quarter data
        await Promise.all([
            page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 45000 }}),
            page.click('#plnMain_btnRefreshView')
        ]);

        // Wait a bit for the page to settle after refresh
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Try to wait for grades to load, but don't fail if the quarter has no data
        // Some quarters (like Q3/Q4 in current school year) may not have assignments yet
        try {{
            await page.waitForSelector('span[id*="lblOverallAverage"]', {{ timeout: 5000 }});
        }} catch (e) {{
            // Quarter might have no data - that's okay, we'll return empty courses
        }}

        // Get the HTML content
        const html = await page.content();
        return {{ html }};
    }} catch (error) {{
        return {{ error: error.message }};
    }}
}};
"""

            # Allow up to 90 seconds for the full login + quarter selection sequence
            async with self.session.post(
                self.browserless_url,
                data=browser_script,
                headers={"Content-Type": "application/javascript"},
                timeout=aiohttp.ClientTimeout(total=90)
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Browserless request failed for %s: %s", quarter, response.status)
                    return None

                result = await response.json()

                if "error" in result:
                    _LOGGER.error("Browser automation error for %s: %s", quarter, result["error"])
                    return None

                html = result.get("html", "")
                _LOGGER.debug("Fetched %d characters of HTML for %s", len(html), quarter)
                return html

        except Exception as err:
            _LOGGER.error("Error fetching %s with browserless: %s", quarter, err)
            return None

    def _extract_student_id(self, soup: BeautifulSoup) -> str | None:
        """Extract student ID from the HAC page."""
        try:
            import re

            # Look for student ID in the page - it's typically in a hidden field or data attribute
            # Common patterns in HAC:

            # 1. Data attribute on banner div (most reliable - this is in the parent frame)
            banner = soup.find("div", {"class": "sg-banner"})
            if banner and banner.get("data-student-id"):
                student_id = banner.get("data-student-id")
                _LOGGER.debug("Found student ID from banner: %s", student_id)
                return student_id

            # 3. Hidden input field with student ID
            student_id_input = soup.find("input", {"id": lambda x: x and "studentid" in x.lower()})
            if student_id_input and student_id_input.get("value"):
                return student_id_input.get("value")

            # 4. In the page URL or form action
            forms = soup.find_all("form")
            for form in forms:
                action = form.get("action", "")
                if "studentid=" in action.lower():
                    match = re.search(r"studentid=(\d+)", action, re.IGNORECASE)
                    if match:
                        return match.group(1)

            # 5. In JavaScript variables
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string:
                    match = re.search(r"studentId[\"']?\s*[:=]\s*[\"']?(\d+)", script.string, re.IGNORECASE)
                    if match:
                        return match.group(1)

            _LOGGER.warning("Could not extract student ID from page")
            return None

        except Exception as err:
            _LOGGER.error("Error extracting student ID: %s", err)
            return None

    def _detect_quarter_from_html(self, html: str) -> str | None:
        """Detect which quarter the HTML represents by checking the dropdown selection."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Look for the quarter dropdown (Report Card Runs dropdown)
            dropdown = soup.find("select", {"id": "plnMain_ddlReportCardRuns"})
            if not dropdown:
                _LOGGER.warning("Could not find quarter dropdown to detect initial quarter")
                return None

            # Find the selected option
            selected_option = dropdown.find("option", {"selected": True})
            if selected_option and selected_option.get("value"):
                # The value format is like "1-2026" for Q1, "2-2026" for Q2, etc.
                quarter_value = selected_option.get("value")
                quarter_num = quarter_value.split("-")[0]
                detected_quarter = f"Q{quarter_num}"
                _LOGGER.debug("Detected initial quarter from dropdown: %s", detected_quarter)
                return detected_quarter

            _LOGGER.warning("Could not detect selected quarter from dropdown")
            return None

        except Exception as err:
            _LOGGER.error("Error detecting quarter from HTML: %s", err)
            return None

    def _extract_all_courses_from_html(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Extract complete course list from assignments page HTML.

        This gets ALL courses including those without assignments yet.
        Each course is in an AssignmentClass div, even if it has no assignments.
        """
        try:
            courses = []

            # Find all course divs - each course is wrapped in a div with class "AssignmentClass"
            assignment_class_divs = soup.find_all("div", {"class": "AssignmentClass"})

            for idx, course_div in enumerate(assignment_class_divs):
                # Within each AssignmentClass div, find the course name link
                course_link = course_div.find("a", {"class": "sg-header-heading"})

                if course_link:
                    course_text = course_link.text.strip()
                    if course_text:  # Make sure it's not empty
                        courses.append({
                            "course": course_text,
                            "course_index": idx,
                        })
                        _LOGGER.debug("Found course %d: %s", idx, course_text)

            _LOGGER.info("Found %d total courses from AssignmentClass divs", len(courses))
            return courses

        except Exception as err:
            _LOGGER.error("Error extracting all courses from HTML: %s", err, exc_info=True)
            return []

    async def _fetch_schedule(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch course schedule organized by marking period/quarter."""
        try:
            # The schedule page uses an iframe that loads /HomeAccess/Content/Student/Classes.aspx
            # We need to fetch the iframe content directly
            schedule_url = f"{self.school_url}/HomeAccess/Content/Student/Classes.aspx"

            async with self.session.get(schedule_url) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch schedule iframe: %s", response.status)
                    return {}

                html = await response.text()
                _LOGGER.debug("Fetched schedule iframe: %d characters", len(html))
                soup = BeautifulSoup(html, "lxml")

                # Parse schedule by marking period
                schedule_by_quarter = {
                    "Q1": [],
                    "Q2": [],
                    "Q3": [],
                    "Q4": [],
                }

                # Find the schedule table - try multiple selector strategies
                schedule_table = soup.find("table", {"class": "sg-asp-table"})

                if not schedule_table:
                    # Try finding by id pattern
                    schedule_table = soup.find("table", {"id": lambda x: x and "schedule" in x.lower()})

                if not schedule_table:
                    # Try finding any table with schedule data
                    schedule_table = soup.find("table", {"class": lambda x: x and "table" in str(x).lower()})

                if not schedule_table:
                    _LOGGER.warning("Could not find schedule table in HTML")
                    # Log available table classes for debugging
                    all_tables = soup.find_all("table")
                    _LOGGER.debug("Found %d tables in schedule page", len(all_tables))
                    for idx, table in enumerate(all_tables[:3]):  # Log first 3 tables
                        _LOGGER.debug("Table %d classes: %s, id: %s", idx, table.get("class"), table.get("id"))
                    return {}

                _LOGGER.debug("Found schedule table: class=%s, id=%s",
                             schedule_table.get("class"), schedule_table.get("id"))

                rows = schedule_table.find_all("tr", class_=lambda x: x and "data-row" in str(x).lower())
                if not rows:
                    # Try without class filter
                    rows = schedule_table.find_all("tr")
                    # Skip header row(s)
                    rows = [r for r in rows if r.find("th") is None]

                _LOGGER.debug("Found %d schedule rows", len(rows))

                for row_idx, row in enumerate(rows):
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        _LOGGER.debug("Row %d has %d cells", row_idx, len(cells))

                        # Try to parse based on cell count and content
                        # Common formats:
                        # - Course Code | Course Name | Periods | ... | Marking Period
                        # - Course Name | Period | Teacher | Room | Marking Period

                        # Extract text from all cells
                        cell_texts = [cell.text.strip() for cell in cells]
                        _LOGGER.debug("Row %d cells: %s", row_idx, cell_texts[:6] if len(cell_texts) > 6 else cell_texts)

                        # Try to identify course code/name and marking period
                        # Marking period is usually in the last 1-3 columns
                        marking_period = ""
                        for cell_text in cell_texts[-3:]:  # Check last 3 columns
                            if any(q in cell_text for q in ["Q1", "Q2", "Q3", "Q4", "All", "Year", "MP"]):
                                marking_period = cell_text
                                break

                        if not marking_period:
                            _LOGGER.debug("Row %d: Could not identify marking period, skipping", row_idx)
                            continue

                        # First two non-empty cells are usually course code and course name
                        non_empty_cells = [c for c in cell_texts if c]
                        if len(non_empty_cells) >= 2:
                            course_code = non_empty_cells[0]
                            course_name = non_empty_cells[1]

                            # Build course info
                            course_info = {
                                "course": f"{course_code} - {course_name}",
                                "course_code": course_code,
                                "course_name": course_name,
                            }

                            # Map marking period to quarters
                            # Marking periods can be: "Q1", "Q2", "Q3", "Q4", or combined like "Q1-Q2" or "All Year"
                            if "Q1" in marking_period or "MP1" in marking_period or "All" in marking_period or "Year" in marking_period:
                                if course_info not in schedule_by_quarter["Q1"]:
                                    schedule_by_quarter["Q1"].append(course_info)
                            if "Q2" in marking_period or "MP2" in marking_period or "All" in marking_period or "Year" in marking_period:
                                if course_info not in schedule_by_quarter["Q2"]:
                                    schedule_by_quarter["Q2"].append(course_info)
                            if "Q3" in marking_period or "MP3" in marking_period or "All" in marking_period or "Year" in marking_period:
                                if course_info not in schedule_by_quarter["Q3"]:
                                    schedule_by_quarter["Q3"].append(course_info)
                            if "Q4" in marking_period or "MP4" in marking_period or "All" in marking_period or "Year" in marking_period:
                                if course_info not in schedule_by_quarter["Q4"]:
                                    schedule_by_quarter["Q4"].append(course_info)

                _LOGGER.info(
                    "Parsed schedule: Q1=%d courses, Q2=%d courses, Q3=%d courses, Q4=%d courses",
                    len(schedule_by_quarter["Q1"]),
                    len(schedule_by_quarter["Q2"]),
                    len(schedule_by_quarter["Q3"]),
                    len(schedule_by_quarter["Q4"]),
                )

                return schedule_by_quarter

        except Exception as err:
            _LOGGER.error("Error fetching schedule: %s", err, exc_info=True)
            return {}

    async def fetch_grades(self) -> dict[str, Any]:
        """Fetch grade data for all quarters from HAC."""
        try:
            if not self._cookies:
                if not await self.login():
                    return {"error": "Login failed"}

            # Fetch data for all quarters
            quarters_data = {}
            quarters = ["Q1", "Q2", "Q3", "Q4"]

            for quarter in quarters:
                _LOGGER.debug("Fetching grades for quarter: %s", quarter)
                quarter_data = await self._fetch_quarter_grades(quarter)

                if "error" not in quarter_data:
                    quarters_data[quarter] = quarter_data
                else:
                    _LOGGER.warning("Failed to fetch %s: %s", quarter, quarter_data["error"])

            # Q3 and Q4 data should already have courses detected from AssignmentClass divs
            # The _fetch_quarter_grades method extracts all AssignmentClass divs even if they have no assignments
            # So we don't need to infer courses from Q1/Q2 - they're already detected!
            # Just log what we found
            for quarter in quarters:
                if quarters_data.get(quarter):
                    course_count = len(quarters_data[quarter].get("courses", []))
                    _LOGGER.info("%s has %d courses", quarter, course_count)

            if not quarters_data:
                return {"error": "No quarter data could be fetched"}

            return {
                "quarters": quarters_data,
                "last_updated": datetime.now(timezone.utc),
                "student_id": self._detected_student_id or self.student_id,
            }

        except Exception as err:
            _LOGGER.error("Error fetching grades: %s", err)
            return {"error": str(err)}

    def _create_placeholder_quarter(self, template_courses: list[dict]) -> dict[str, Any]:
        """Create a placeholder quarter structure based on template courses."""
        return {
            "overall_summary": {
                "course_count": len(template_courses),
                "gpa_like_average": None,
                "weighted_gpa_like_average": None,
                "latest_update_date": None,
                "days_since_latest_update": None,
            },
            "courses": [
                {
                    "course": course["course"],
                    "course_index": course["course_index"],
                    "total_assignments": 0,
                    "not_hand_in": 0,
                    "not_yet_graded": 0,
                    "too_late_to_count": 0,
                    "score_below_fifty": 0,
                    "overall_percentage": None,
                    "hac_overall_percentage": None,
                    "hac_points_earned": None,
                    "hac_points_possible": None,
                    "assignments": [],
                    "category_breakdown": {},
                    "hac_category_breakdown": [],
                    "hac_last_updated": None,
                    "days_since_update": None,
                }
                for course in template_courses
            ],
        }

    async def _fetch_quarter_grades(self, quarter: str) -> dict[str, Any]:
        """Fetch grade data for a specific quarter."""
        try:
            html = None

            # Check if we have the initial HTML from login and if it matches the requested quarter
            if quarter == self._initial_quarter and self._initial_html:
                _LOGGER.debug("Using cached HTML from login for %s", quarter)
                html = self._initial_html
            else:
                # For other quarters, we need to use browserless to change the dropdown
                # The quarter dropdown requires JavaScript to change and post back
                html = await self._fetch_quarter_with_browserless(quarter)
                if not html:
                    return {"error": f"Failed to fetch HTML for {quarter}"}

            # Parse the HTML
            soup = BeautifulSoup(html, "lxml")

            # Extract and validate student ID (only if we don't have it yet)
            if not self._detected_student_id:
                detected_id = self._extract_student_id(soup)
                if detected_id:
                    self._detected_student_id = detected_id
                    if self.student_id and self.student_id != detected_id:
                        _LOGGER.error(
                            "Student ID mismatch! Expected: %s, Found: %s",
                            self.student_id,
                            detected_id
                        )
                        return {"error": f"Student ID mismatch. Expected {self.student_id}, found {detected_id}"}
                    _LOGGER.info("Validated student ID from HTML: %s", detected_id)
                else:
                    # Only warn if we don't have student ID from login either
                    _LOGGER.debug("Could not extract student ID from HTML (may be normal for Assignments page)")

            # First, get the COMPLETE course list from AssignmentClass divs
            # These divs exist for ALL courses, even those without assignments yet
            all_courses_info = self._extract_all_courses_from_html(soup)

            # Extract courses with assignments from the assignments table
            courses_with_grades = []
            for i in range(8):  # HAC typically shows up to 8 courses
                course_data = self._parse_course(soup, i)
                if course_data:
                    courses_with_grades.append(course_data)

            _LOGGER.info("Extracted %d courses with grades for quarter %s", len(courses_with_grades), quarter)

            # Merge: Start with all courses from AssignmentClass divs, then overlay grade data where available
            courses = []
            courses_with_grades_dict = {c["course"]: c for c in courses_with_grades}

            for course_info in all_courses_info:
                course_name = course_info["course"]

                if course_name in courses_with_grades_dict:
                    # This course has grade data - use it
                    courses.append(courses_with_grades_dict[course_name])
                else:
                    # This course exists but has no assignments yet - create placeholder
                    _LOGGER.debug("Course %s exists but has no assignments yet", course_name)
                    courses.append({
                        "course": course_name,
                        "course_index": course_info["course_index"],
                        "total_assignments": 0,
                        "not_hand_in": 0,
                        "not_yet_graded": 0,
                        "too_late_to_count": 0,
                        "score_below_fifty": 0,
                        "overall_percentage": None,
                        "hac_overall_percentage": None,
                        "hac_points_earned": None,
                        "hac_points_possible": None,
                        "assignments": [],
                        "category_breakdown": {},
                        "hac_category_breakdown": [],
                        "hac_last_updated": None,
                        "days_since_update": None,
                    })

            _LOGGER.info("Final course count for %s: %d (including courses without assignments)", quarter, len(courses))

            # Calculate overall summary
            overall_summary = self._calculate_overall_summary(courses)

            return {
                "overall_summary": overall_summary,
                "courses": courses,
            }

        except Exception as err:
            _LOGGER.error("Error fetching quarter %s grades: %s", quarter, err)
            return {"error": str(err)}

    def _parse_course(self, soup: BeautifulSoup, course_index: int) -> dict[str, Any] | None:
        """Parse a single course from the HAC page."""
        try:
            # Find the assignments table for this course
            table_id = f"plnMain_rptAssigmnetsByCourse_dgCourseAssignments_{course_index}"
            assignments_table = soup.find("table", {"id": table_id})

            if not assignments_table:
                if course_index == 0:
                    # Only log for first course to avoid spam
                    _LOGGER.debug("No assignments table found with ID: %s", table_id)
                return None

            _LOGGER.debug("Found assignments table for course index %d", course_index)

            # Get course name
            course_name_selector = f"#plnMain_pnlFullPage > div:nth-child({course_index + 4}) > div.sg-header.sg-header-square > a"
            course_name_elem = soup.select_one(course_name_selector)
            course_name = course_name_elem.text.strip() if course_name_elem else f"Course {course_index + 1}"

            # Parse assignments
            assignments = []
            rows = assignments_table.find_all("tr", class_="sg-asp-table-data-row")

            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 6:
                    assignment = self._parse_assignment(cells)
                    if assignment:
                        assignments.append(assignment)

            # Calculate category breakdown
            category_stats = self._calculate_category_stats(assignments)

            # Calculate overall percentage using weighted categories
            overall_percentage = self._calculate_weighted_percentage(category_stats)

            # Get HAC's official numbers
            hac_overall = self._get_hac_overall(soup, course_index)
            hac_points_earned = self._get_hac_points(soup, course_index, "earned")
            hac_points_possible = self._get_hac_points(soup, course_index, "possible")

            # Get last updated date
            last_updated_info = self._get_last_updated(soup, course_index)

            # Get HAC category breakdown
            hac_category_breakdown = self._parse_hac_categories(soup, course_index)

            return {
                "course": course_name,
                "course_index": course_index,
                "total_assignments": len(assignments),
                "not_hand_in": sum(1 for a in assignments if a["status"] == STATUS_NHI),
                "not_yet_graded": sum(1 for a in assignments if a["status"] == STATUS_NYG),
                "too_late_to_count": sum(1 for a in assignments if a["status"] == STATUS_TLTC),
                "score_below_fifty": sum(1 for a in assignments if a["status"] == STATUS_SBF),
                "overall_percentage": overall_percentage,
                "hac_overall_percentage": hac_overall,
                "hac_points_earned": hac_points_earned,
                "hac_points_possible": hac_points_possible,
                "assignments": assignments,
                "category_breakdown": category_stats,
                "hac_category_breakdown": hac_category_breakdown,
                "hac_last_updated": last_updated_info.get("date"),
                "days_since_update": last_updated_info.get("days"),
            }

        except Exception as err:
            _LOGGER.warning("Error parsing course %s: %s", course_index, err)
            return None

    def _parse_assignment(self, cells: list) -> dict[str, Any] | None:
        """Parse a single assignment row."""
        try:
            due_date = cells[0].text.strip()
            assigned_date = cells[1].text.strip()

            title_link = cells[2].find("a")
            title = title_link.text.strip() if title_link else ""

            if not title:
                return None

            category = cells[3].text.strip()
            raw_score = cells[4].text.strip()
            total_points_str = cells[5].text.strip()

            # Parse score and status
            score = None
            status = None

            if "NHI" in raw_score.upper():
                score = 0
                status = STATUS_NHI
            elif "TLTC" in raw_score.upper():
                score = 0
                status = STATUS_TLTC
            elif "X" in raw_score.upper():
                score = None
                status = STATUS_EXEMPT
            elif "SBF" in raw_score.upper():
                # SBF might have actual score in a different column
                score = float(cells[7].text.strip()) if len(cells) > 7 else 0
                status = STATUS_SBF
            elif "NYG" in raw_score.upper() or raw_score == "":
                score = None
                status = STATUS_NYG
            else:
                try:
                    score = float(raw_score)
                    status = STATUS_SCORED
                except ValueError:
                    score = None
                    status = STATUS_NYG

            # Parse total points, handling "N/A" case
            total_points = None
            if total_points_str and total_points_str.upper() != "N/A":
                try:
                    total_points = float(total_points_str)
                except ValueError:
                    _LOGGER.debug("Could not parse total points: %s", total_points_str)
                    total_points = None

            percentage = None
            if score is not None and total_points:
                percentage = round((score / total_points) * 100, 2)

            return {
                "title": title,
                "due_date": due_date,
                "assigned_date": assigned_date,
                "category": category,
                "raw_score": raw_score,
                "score": score,
                "total_points": total_points,
                "status": status,
                "percentage": percentage,
            }

        except Exception as err:
            _LOGGER.warning("Error parsing assignment: %s", err)
            return None

    def _calculate_category_stats(self, assignments: list[dict]) -> dict[str, dict]:
        """Calculate statistics for each category."""
        category_stats = {
            "PRACTICE": {"earned": 0, "possible": 0},
            "PROCESS": {"earned": 0, "possible": 0},
            "PRODUCT": {"earned": 0, "possible": 0},
        }

        for assignment in assignments:
            cat = assignment["category"].upper()
            if cat in category_stats:
                if assignment["status"] in [STATUS_SCORED, STATUS_NHI, STATUS_SBF, STATUS_TLTC]:
                    if assignment["score"] is not None:
                        category_stats[cat]["earned"] += assignment["score"]
                    if assignment["total_points"]:
                        category_stats[cat]["possible"] += assignment["total_points"]

        # Calculate percentages
        for cat, stats in category_stats.items():
            if stats["possible"] > 0:
                stats["percentage"] = round((stats["earned"] / stats["possible"]) * 100, 2)
            else:
                stats["percentage"] = None

        return category_stats

    def _calculate_weighted_percentage(self, category_stats: dict) -> float | None:
        """Calculate overall percentage using weighted categories."""
        overall_percentage = 0
        total_weight = 0

        for cat, stats in category_stats.items():
            if stats["possible"] > 0:
                cat_percent = stats["earned"] / stats["possible"]
                overall_percentage += cat_percent * CATEGORY_WEIGHTS[cat]
                total_weight += CATEGORY_WEIGHTS[cat]

        if total_weight > 0:
            return round((overall_percentage / total_weight) * 100, 2)
        return None

    def _get_hac_overall(self, soup: BeautifulSoup, course_index: int) -> float | None:
        """Get HAC's official overall percentage."""
        try:
            span_id = f"plnMain_rptAssigmnetsByCourse_lblOverallAverage_{course_index}"
            span = soup.find("span", {"id": span_id})
            if span:
                val = float(span.text.strip())
                return round(val, 2)
        except Exception:
            pass
        return None

    def _get_hac_points(self, soup: BeautifulSoup, course_index: int, point_type: str) -> str | None:
        """Get HAC's points earned or possible."""
        try:
            if point_type == "earned":
                span_id = f"plnMain_rptAssigmnetsByCourse_lblStuPoints_{course_index}"
            else:
                span_id = f"plnMain_rptAssigmnetsByCourse_lblMaxPoints_{course_index}"

            span = soup.find("span", {"id": span_id})
            if span:
                return span.text.strip()
        except Exception:
            pass
        return None

    def _get_last_updated(self, soup: BeautifulSoup, course_index: int) -> dict[str, Any]:
        """Get the last updated date for a course."""
        try:
            span_id = f"plnMain_rptAssigmnetsByCourse_lblLastUpdDate_{course_index}"
            span = soup.find("span", {"id": span_id})

            if span:
                text = span.text.strip()
                # Extract date from "Last Updated: MM/DD/YYYY" (may have trailing parenthesis)
                if "Last Updated:" in text:
                    date_str = text.split("Last Updated:")[1].strip()
                    # Remove any trailing characters like parentheses
                    import re
                    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_str)
                    if date_match:
                        date_str = date_match.group(1)
                        last_updated = datetime.strptime(date_str, "%m/%d/%Y")
                        days_since = (datetime.now() - last_updated).days

                        return {
                            "date": last_updated.strftime("%Y-%m-%d"),
                            "days": days_since,
                        }
        except Exception as err:
            _LOGGER.debug("Error parsing last updated: %s", err)

        return {"date": None, "days": None}

    def _parse_hac_categories(self, soup: BeautifulSoup, course_index: int) -> list[dict]:
        """Parse HAC's official category breakdown."""
        categories = []
        try:
            table_id = f"plnMain_rptAssigmnetsByCourse_dgCourseCategories_{course_index}"
            table = soup.find("table", {"id": table_id})

            if table:
                rows = table.find_all("tr", class_="sg-asp-table-data-row")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 5:
                        categories.append({
                            "category": cells[0].text.strip(),
                            "points_earned": cells[1].text.strip(),
                            "points_possible": cells[2].text.strip(),
                            "percentage": cells[3].text.strip(),
                            "weight": cells[4].text.strip(),
                            "weighted_average": cells[5].text.strip() if len(cells) > 5 else None,
                        })
        except Exception as err:
            _LOGGER.debug("Error parsing HAC categories: %s", err)

        return categories

    def _calculate_overall_summary(self, courses: list[dict]) -> dict[str, Any]:
        """Calculate overall summary across all courses."""
        if not courses:
            return {
                "course_count": 0,
                "gpa_like_average": None,
                "weighted_gpa_like_average": None,
                "latest_update_date": None,
                "days_since_latest_update": None,
            }

        grade_sum = 0
        grade_count = 0
        weighted_sum = 0
        weighted_possible = 0
        most_recent_update = None

        for course in courses:
            if course["overall_percentage"] is not None:
                grade_sum += course["overall_percentage"]
                grade_count += 1

                if course["hac_points_possible"]:
                    try:
                        possible = float(course["hac_points_possible"])
                        earned_pct = course["overall_percentage"]
                        weighted_sum += earned_pct * possible
                        weighted_possible += possible
                    except ValueError:
                        pass

            if course["hac_last_updated"]:
                try:
                    upd_date = datetime.strptime(course["hac_last_updated"], "%Y-%m-%d")
                    if not most_recent_update or upd_date > most_recent_update:
                        most_recent_update = upd_date
                except ValueError:
                    pass

        gpa_like_average = round(grade_sum / grade_count, 2) if grade_count > 0 else None
        weighted_gpa = round(weighted_sum / weighted_possible, 2) if weighted_possible > 0 else None

        days_since_latest = None
        latest_date_str = None
        if most_recent_update:
            days_since_latest = (datetime.now() - most_recent_update).days
            latest_date_str = most_recent_update.strftime("%Y-%m-%d")

        return {
            "course_count": len(courses),
            "gpa_like_average": gpa_like_average,
            "weighted_gpa_like_average": weighted_gpa,
            "latest_update_date": latest_date_str,
            "days_since_latest_update": days_since_latest,
        }
