import os
from datetime import datetime, date, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")


def get_service():
    """取得已授權的 Google Calendar service"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def create_family_calendar(name: str) -> str:
    """為家人建立專屬 Calendar，回傳 calendar_id"""
    service = get_service()
    calendar = service.calendars().insert(body={
        "summary": name,
        "timeZone": "Asia/Taipei",
    }).execute()
    return calendar["id"]


def add_event(calendar_id: str, title: str, start: datetime, end: datetime,
              description: str = "") -> str:
    """新增事件，回傳 event_id"""
    service = get_service()
    event = service.events().insert(
        calendarId=calendar_id,
        body={
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Taipei"},
            "end":   {"dateTime": end.isoformat(),   "timeZone": "Asia/Taipei"},
        }
    ).execute()
    return event["id"]


def get_events_for_week(calendar_id: str, week_start: date) -> list[dict]:
    """取得指定週的所有事件"""
    service = get_service()
    time_min = datetime.combine(week_start, datetime.min.time()).isoformat() + "Z"
    time_max = datetime.combine(week_start + timedelta(days=7), datetime.min.time()).isoformat() + "Z"

    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date"))
        end   = e["end"].get("dateTime",   e["end"].get("date"))
        events.append({
            "id":    e["id"],
            "title": e.get("summary", "（無標題）"),
            "start": start,
            "end":   end,
        })
    return events
