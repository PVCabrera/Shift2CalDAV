#!/usr/bin/env python
# ===== Standard Library =====
import configparser
import datetime
from datetime import date, datetime, timedelta
import os
import re
import sys
import time
import pytz

# ===== Third-Party Libraries =====
from google.auth.transport.requests import Request
from google.oauth2 import credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


config = configparser.ConfigParser()
config.read("credentials.cfg")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = config["secrets"]["calendar_id"]


def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = credentials.Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

service = get_calendar_service()

def parse_shift_label(label):
    """
    Parse the aria-label text from a shift element to extract shift info.
    """
    # Regex to capture:
    # 1) position: anything before ' shift from '
    # 2) start_time: time after ' shift from ' and before ' to '
    # 3) end_time: time after ' to ' and before ' at location '
    # 4) location: digits after ' at location ' and before ' on '
    pattern = r"^(.*?) shift from (\d{1,2}:\d{2}[AP]M) to (\d{1,2}:\d{2}[AP]M) at location (\d+) on .*$"
    match = re.match(pattern, label)
    if not match:
        raise ValueError(f"Could not parse shift label: {label}")

    position = match.group(1)
    start_time = match.group(2)
    end_time = match.group(3)
    location = match.group(4)

    return position, start_time, end_time, location




def process_shifts_new():
    schedule_container = WebDriverWait(browser, timeout).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'ul[aria-label="your weekly schedule"]')
        )
    )

    day_items = schedule_container.find_elements(
        By.CSS_SELECTOR, 'li[data-cy^="weeklySchedListItem"]'
    )

    for day_item in day_items:
        date_elem = day_item.find_element(
            By.CSS_SELECTOR, 'p[data-cy="nextSchedDisplaySegDateOnWeekly"]'
        )
        date_text = date_elem.text  # e.g., "Tuesday, August 5"

        # Parse the date string to "YYYY-MM-DD"
        date_obj = datetime.strptime(date_text, "%A, %B %d")
        # NOTE: This returns a date without year, add year manually (e.g., this year)
        date_obj = date_obj.replace(year=datetime.now().year)
        formatted_date = date_obj.strftime("%Y-%m-%d")

        shifts = day_item.find_elements(By.CSS_SELECTOR, 'a[aria-label*="shift"]')
        if not shifts:
            print(f"No shifts for {date_text}")
            continue

        for shift in shifts:
            shift_label = shift.get_attribute("aria-label")
            try:
                position, start_time, end_time, location = parse_shift_label(
                    shift_label
                )
            except ValueError as e:
                print(e)
                continue

            # Create Shift object (adapt constructor as you have it)
            shift_obj = Shift(
                day=date_text,
                date=formatted_date,
                position=position,
                start_time=start_time,
                end_time=end_time,
                location=location,
            )
            shift_obj.make_event()
            print(
                f"Created calendar event for {date_text} - {position} from {start_time} to {end_time} at location {location}"
            )


# ===== Classes and Functions =====


class Shift:
    def __init__(self, day, date, position, start_time, end_time, location=None):
        self.day = day
        self.date = date  # YYYY-MM-DD string
        self.position = position
        # Convert times to 24-hour format strings
        self.start_time = datetime.strptime(start_time, "%I:%M%p").strftime("%H:%M:%S")
        self.end_time = datetime.strptime(end_time, "%I:%M%p").strftime("%H:%M:%S")
        self.location = location  # Not used in event creation, but can be stored

    def make_event(self):
        tz = pytz.timezone("America/Chicago")
        
        start_dt = tz.localize(datetime.strptime(f"{self.date} {self.start_time}", "%Y-%m-%d %H:%M:%S"))
        end_dt = tz.localize(datetime.strptime(f"{self.date} {self.end_time}", "%Y-%m-%d %H:%M:%S"))

        event_body = {
            "summary": f"Work - {self.position}",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "America/Chicago",  # Adjust to your timezone
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "America/Chicago",
            },
        }

        # Search for existing "Work" events overlapping this shift to delete/update
        events_result = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=start_dt.isoformat(),
                timeMax=(start_dt + timedelta(days=1)).isoformat(),
                singleEvents=True,
            )
            .execute()
        )

        for e in events_result.get("items", []):
            if e.get("summary", "").startswith("Work"):
                service.events().delete(
                    calendarId=CALENDAR_ID, eventId=e["id"]
                ).execute()

        created_event = (
            service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
        )
        print(
            f"Created event for {self.date} - {self.position}: {created_event.get('htmlLink')}"
        )


#####################################
#####   CHROME  STUFF  UPDATED  #####
#####################################


config = configparser.ConfigParser()
config.read("credentials.cfg")

if config["options"]["headless"] == "yes":
    print("Headless mode enabled")
    options = webdriver.ChromeOptions()
    options.add_argument("-headless")
    browser = webdriver.Chrome(options=options)
else:
    browser = webdriver.Chrome()

browser.get(
    "https://logonservices.iam.target.com/v1/login/?application=wfm_tm_enablement_ui_prod_im&assurance=2&form=password&referrer=https%3A%2F%2Foauth.iam.target.com%2Fauth%2Foauth%2Fv2%2Fauthorize%3Fclient_id%3Dwfm_tm_enablement_ui_prod_im%26login%3Dtrue%26nonce%3Dsn3WamWQw2sHie2gO8ypP%26redirect_uri%3Dhttps%3A%2F%2Fmytime.target.com%26response_type%3Dtoken+id_token%26scope%3Dopenid+profile%26state%3D&tid=cdeae68b-267e-4749-b8b0-916d478f4251&type=teammember+partner"
)

timeout = 20

try:
    print("Waiting for login page to load...")
    WebDriverWait(browser, timeout).until(
        EC.presence_of_element_located((By.ID, "loginID"))
    )
except TimeoutException:
    print("Timed out waiting for login page to load or login failed?")
    browser.quit()
    exit(1)

print("Entering username and password...")
try:
    username = browser.find_element(By.ID, "loginID")
    password = browser.find_element(By.ID, "password")
    username.send_keys(config["secrets"]["employeeID"])
    username.send_keys(Keys.TAB)
    password.send_keys(config["secrets"]["password"])
except Exception as e:
    print(f"Error entering login credentials: {e}")
    browser.quit()
    exit(1)

try:
    loginbutton = browser.find_element(By.ID, "submit-button")
    loginbutton.submit()
except Exception as e:
    print(f"Error submitting login form: {e}")
    browser.quit()
    exit(1)
# try:
#     qna = browser.find_element(By.ID, "sec_qna")
#     qna.click()
#     login_attempt = browser.find_element(By.XPATH, "//*[@type='submit']")
#     login_attempt.submit()
# except Exception as e:
#     print(f"Error handling security question selection: {e}")
#     browser.quit()
#     exit(1)
try:
    # Wait a short time for the skip button to appear
    skip_button = WebDriverWait(browser, 3).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//a[contains(text(),'Skip') and @class[contains(.,'MuiLink-root')]]",
            )
        )
    )
    skip_button.click()
    print("Skip button clicked.")
except TimeoutException:
    print("Skip button not found, continuing...")

# check for in case of OTP prompt
try:
    print("Checking for 2FA method selection (SMS/Call)...")
    sms_button = WebDriverWait(browser, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()='SMS']]"))
    )
    print("2FA SMS button found, clicking it...")
    sms_button.click()
except TimeoutException:
    print("No 2FA method selection step needed.")

# Now handle OTP input
try:
    print("Waiting for OTP input field...")
    otp_input = WebDriverWait(browser, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel']"))
    )
    otp_code = input("Enter OTP code: ").strip()
    otp_input.send_keys(otp_code)

    otp_submit = WebDriverWait(browser, 5).until(
        EC.element_to_be_clickable((By.ID, "submit-button"))
    )
    otp_submit.click()

    # Confirm OTP success by checking for next page element
    # WebDriverWait(browser, 15).until(
    #     EC.presence_of_element_located((By.CLASS_NAME, "request_table_bordered"))
    # )
    # print("OTP verified, continuing...")

except TimeoutException:
    print("No OTP step detected, continuing...")
except Exception as e:
    print(f"Error handling OTP: {e}")
    browser.quit()
    exit(1)
# Wait for the page to load after login
try:
    print("Waiting for 'My Schedule' button...")
    schedule_btn = WebDriverWait(browser, timeout).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'a[data-cy="scheduleBtnBottomNav"]')
        )
    )
    schedule_btn.click()
    print("'My Schedule' button clicked, navigating to schedule page.")
    # Wait a bit for schedule page to load fully
    WebDriverWait(browser, timeout).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'ul[aria-label="your weekly schedule"]')
        )
    )

    # Now call your function to process shifts
    process_shifts_new()

except Exception as e:
    print(f"Failed to find or click 'My Schedule' button: {e}")
    browser.quit()
    exit(1)


browser.quit()
