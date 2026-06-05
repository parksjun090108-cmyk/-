import datetime as dt
import hashlib
import json
import os
import re
import secrets
from html import escape

import requests
import streamlit as st

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


NEIS_BASE_URL = "https://open.neis.go.kr/hub"
SCHOOL_NAME = "\uae40\ud3ec\uace0\ub4f1\ud559\uad50"
DATA_FILE = os.path.join(os.path.dirname(__file__), "users.json")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")

if load_dotenv:
    load_dotenv(ENV_FILE, override=True)
    load_dotenv(override=False)


def get_env_value(name):
    value = os.getenv(name, "").strip()
    if value:
        return value
    if not os.path.exists(ENV_FILE):
        return ""
    with open(ENV_FILE, "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")
    return ""


OPENAI_MODEL = get_env_value("OPENAI_MODEL") or "gpt-4.1-nano"


def load_db():
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(db, file, ensure_ascii=False, indent=2)


def password_hash(password, salt):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return digest.hex()


def create_user(student_id, password):
    student_id = student_id.strip()
    if not student_id:
        return False, "\ud559\ubc88\uc744 \uc785\ub825\ud558\uc138\uc694."
    if not student_id.isdigit():
        return False, "\ud559\ubc88\uc740 \uc22b\uc790\ub9cc \uc785\ub825\ud558\uc138\uc694."
    if len(password) < 4:
        return False, "\ube44\ubc00\ubc88\ud638\ub294 4\uc790 \uc774\uc0c1\uc73c\ub85c \ub9cc\ub4dc\uc138\uc694."

    db = load_db()
    if student_id in db["users"]:
        return False, "\uc774\ubbf8 \ub4f1\ub85d\ub41c \ud559\ubc88\uc785\ub2c8\ub2e4."

    salt = secrets.token_hex(16)
    db["users"][student_id] = {
        "salt": salt,
        "password_hash": password_hash(password, salt),
        "events": {},
    }
    save_db(db)
    return True, "\ud68c\uc6d0\uac00\uc785\uc774 \uc644\ub8cc\ub410\uc2b5\ub2c8\ub2e4."


def verify_user(student_id, password):
    student_id = student_id.strip()
    db = load_db()
    user = db["users"].get(student_id)
    if not user:
        return False
    return secrets.compare_digest(user["password_hash"], password_hash(password, user["salt"]))


def add_personal_event(student_id, selected_date, title):
    title = title.strip()
    if not title:
        return

    db = load_db()
    date_key = selected_date.strftime("%Y-%m-%d")
    user = db["users"].setdefault(student_id, {"events": {}})
    user.setdefault("events", {}).setdefault(date_key, []).append({"title": title})
    save_db(db)


def delete_personal_event(student_id, selected_date, index):
    db = load_db()
    date_key = selected_date.strftime("%Y-%m-%d")
    events = db["users"].get(student_id, {}).get("events", {}).get(date_key, [])
    if 0 <= index < len(events):
        events.pop(index)
        save_db(db)


def clear_personal_events(student_id, selected_date):
    db = load_db()
    date_key = selected_date.strftime("%Y-%m-%d")
    events = db["users"].get(student_id, {}).get("events", {})
    if date_key in events:
        events[date_key] = []
        save_db(db)


def delete_personal_event_by_text(student_id, selected_date, text):
    db = load_db()
    date_key = selected_date.strftime("%Y-%m-%d")
    events = db["users"].get(student_id, {}).get("events", {}).get(date_key, [])
    for index, event in enumerate(events):
        if text in event.get("title", ""):
            events.pop(index)
            save_db(db)
            return True
    return False


def get_personal_events(student_id, selected_date):
    db = load_db()
    date_key = selected_date.strftime("%Y-%m-%d")
    return db["users"].get(student_id, {}).get("events", {}).get(date_key, [])


def get_month_personal_events(student_id, selected_date):
    if not student_id:
        return {}
    start, end = month_bounds(selected_date)
    db = load_db()
    events = db["users"].get(student_id, {}).get("events", {})
    month_events = {}
    for date_key, items in events.items():
        try:
            event_date = dt.date.fromisoformat(date_key)
        except ValueError:
            continue
        if start <= event_date <= end:
            month_events[date_key] = items
    return month_events


def strip_calendar_words(message):
    text = message.strip()
    text = re.sub(r"(20\d{2})[-./\ub144 ]\s*(\d{1,2})[-./\uc6d4 ]\s*(\d{1,2})", " ", text)
    text = re.sub(r"(\d{1,2})[-./\uc6d4 ]\s*(\d{1,2})", " ", text)
    for word in [
        "\uc624\ub298",
        "\ub0b4\uc77c",
        "\uc5b4\uc81c",
        "\uae08\uc77c",
        "\uc77c\uc815",
        "\uce98\ub9b0\ub354",
        "\ucd94\uac00",
        "\ub4f1\ub85d",
        "\uc800\uc7a5",
        "\ub123\uc5b4",
        "\ub123\uc5b4\uc918",
        "\uc0ad\uc81c",
        "\uc9c0\uc6cc",
        "\uc9c0\uc6cc\uc918",
        "\ubcf4\uc5ec\uc918",
        "\ubcf4\uc5ec",
        "\ud655\uc778",
        "\ud574\uc918",
        "\ud574\uc8fc\uc138\uc694",
    ]:
        text = text.replace(word, " ")
    return re.sub(r"\s+", " ", text).strip()


def is_personal_calendar_command(message):
    action_words = ["\ucd94\uac00", "\ub4f1\ub85d", "\uc800\uc7a5", "\ub123\uc5b4", "\uc0ad\uc81c", "\uc9c0\uc6cc", "\ub0b4 \uc77c\uc815", "\uac1c\uc778 \uc77c\uc815"]
    return any(word in message for word in action_words)


def handle_personal_calendar_command(message, student_id):
    if not is_personal_calendar_command(message):
        return None
    if not student_id:
        return "\ub85c\uadf8\uc778\ud558\uba74 \uac1c\uc778 \uce98\ub9b0\ub354 \uc77c\uc815\uc744 \uc870\uc728\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."

    start_date, _ = parse_period(message)
    title = strip_calendar_words(message)

    if any(word in message for word in ["\ucd94\uac00", "\ub4f1\ub85d", "\uc800\uc7a5", "\ub123\uc5b4"]):
        if not title:
            return "\ucd94\uac00\ud560 \uc77c\uc815 \ub0b4\uc6a9\uc744 \uac19\uc774 \uc785\ub825\ud558\uc138\uc694."
        add_personal_event(student_id, start_date, title)
        return f"{start_date.strftime('%Y-%m-%d')} \uc77c\uc815\uc73c\ub85c `{escape(title)}`\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4."

    if any(word in message for word in ["\uc0ad\uc81c", "\uc9c0\uc6cc"]):
        if title:
            deleted = delete_personal_event_by_text(student_id, start_date, title)
            if deleted:
                return f"{start_date.strftime('%Y-%m-%d')} \uc77c\uc815 \uc911 `{escape(title)}`\uc744 \uc0ad\uc81c\ud588\uc2b5\ub2c8\ub2e4."
            return f"{start_date.strftime('%Y-%m-%d')}\uc5d0 `{escape(title)}` \uc77c\uc815\uc744 \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."
        clear_personal_events(student_id, start_date)
        return f"{start_date.strftime('%Y-%m-%d')} \uac1c\uc778 \uc77c\uc815\uc744 \ubaa8\ub450 \uc0ad\uc81c\ud588\uc2b5\ub2c8\ub2e4."

    events = get_personal_events(student_id, start_date)
    return format_personal_events(events, start_date)


def get_openai_client():
    if OpenAI is None:
        return None
    api_key = get_env_value("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def neis_get(endpoint, **params):
    query = {
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000,
        **params,
    }
    response = requests.get(f"{NEIS_BASE_URL}/{endpoint}", params=query, timeout=10)
    response.raise_for_status()
    data = response.json()

    if "RESULT" in data:
        code = data["RESULT"].get("CODE", "")
        message = data["RESULT"].get("MESSAGE", "NEIS API error")
        if code == "INFO-200":
            return []
        raise RuntimeError(message)

    return data.get(endpoint, [{}, {"row": []}])[1].get("row", [])


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def get_school():
    rows = neis_get("schoolInfo", SCHUL_NM=SCHOOL_NAME)
    for row in rows:
        if row.get("SCHUL_NM") == SCHOOL_NAME:
            return {
                "name": row.get("SCHUL_NM", SCHOOL_NAME),
                "office_code": row.get("ATPT_OFCDC_SC_CODE", ""),
                "school_code": row.get("SD_SCHUL_CODE", ""),
                "address": row.get("ORG_RDNMA", ""),
            }
    raise RuntimeError("\uae40\ud3ec\uace0\ub4f1\ud559\uad50 \ud559\uad50 \uc815\ubcf4\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.")


@st.cache_data(ttl=10 * 60, show_spinner=False)
def get_meals(office_code, school_code, start_date, end_date):
    rows = neis_get(
        "mealServiceDietInfo",
        ATPT_OFCDC_SC_CODE=office_code,
        SD_SCHUL_CODE=school_code,
        MLSV_FROM_YMD=start_date.strftime("%Y%m%d"),
        MLSV_TO_YMD=end_date.strftime("%Y%m%d"),
    )
    by_key = {
        (row.get("MLSV_YMD", ""), row.get("MMEAL_SC_CODE", ""), row.get("MMEAL_SC_NM", "")): row
        for row in rows
    }
    for meal_code in ["2", "3"]:
        for row in neis_get(
            "mealServiceDietInfo",
            ATPT_OFCDC_SC_CODE=office_code,
            SD_SCHUL_CODE=school_code,
            MLSV_FROM_YMD=start_date.strftime("%Y%m%d"),
            MLSV_TO_YMD=end_date.strftime("%Y%m%d"),
            MMEAL_SC_CODE=meal_code,
        ):
            by_key[(row.get("MLSV_YMD", ""), row.get("MMEAL_SC_CODE", ""), row.get("MMEAL_SC_NM", ""))] = row
    return sorted(by_key.values(), key=lambda row: (row.get("MLSV_YMD", ""), row.get("MMEAL_SC_CODE", "")))


@st.cache_data(ttl=10 * 60, show_spinner=False)
def get_schedules(office_code, school_code, start_date, end_date):
    return neis_get(
        "SchoolSchedule",
        ATPT_OFCDC_SC_CODE=office_code,
        SD_SCHUL_CODE=school_code,
        AA_FROM_YMD=start_date.strftime("%Y%m%d"),
        AA_TO_YMD=end_date.strftime("%Y%m%d"),
    )


def parse_period(message):
    today = dt.date.today()
    text = message.strip()

    if any(word in text for word in ["\uc774\ubc88\ub2ec", "\uc774\ubc88 \ub2ec"]):
        start = today.replace(day=1)
        end = dt.date(today.year, 12, 31) if today.month == 12 else today.replace(month=today.month + 1, day=1) - dt.timedelta(days=1)
        return start, end

    if any(word in text for word in ["\uc774\ubc88\uc8fc", "\uc774\ubc88 \uc8fc", "\uc8fc\uac04", "\uc77c\uc8fc\uc77c"]):
        return today, today + dt.timedelta(days=6)
    if any(word in text for word in ["\ub2e4\uc74c\uc8fc", "\ub2e4\uc74c \uc8fc"]):
        next_monday = today + dt.timedelta(days=(7 - today.weekday()))
        return next_monday, next_monday + dt.timedelta(days=6)
    if any(word in text for word in ["\uc624\ub298", "\uae08\uc77c"]):
        return today, today
    if "\ub0b4\uc77c" in text:
        target = today + dt.timedelta(days=1)
        return target, target
    if "\uc5b4\uc81c" in text:
        target = today - dt.timedelta(days=1)
        return target, target

    match = re.search(r"(20\d{2})[-./\ub144 ]\s*(\d{1,2})[-./\uc6d4 ]\s*(\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        target = dt.date(year, month, day)
        return target, target

    match = re.search(r"(\d{1,2})[-./\uc6d4 ]\s*(\d{1,2})", text)
    if match:
        month, day = map(int, match.groups())
        target = dt.date(today.year, month, day)
        return target, target

    return today, today


def is_schedule_question(message):
    keywords = ["\ud559\uc0ac", "\uc77c\uc815", "\ud589\uc0ac", "\uc2dc\ud5d8", "\ubc29\ud559", "\uac1c\ud559", "\uccb4\ud5d8", "\ub300\ud68c"]
    return any(keyword in message for keyword in keywords)


def clean_menu(raw_menu):
    menu = raw_menu.replace("<br/>", "\n").replace("<br>", "\n")
    return [line.strip() for line in menu.split("\n") if line.strip()]


def format_date(yyyymmdd):
    if len(yyyymmdd) != 8:
        return yyyymmdd
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def empty_message(kind, start_date, end_date):
    if start_date == end_date:
        return f"{start_date.strftime('%Y-%m-%d')} {kind} \uc815\ubcf4\uac00 \uc5c6\uc2b5\ub2c8\ub2e4."
    return f"{start_date.strftime('%Y-%m-%d')}\ubd80\ud130 {end_date.strftime('%Y-%m-%d')}\uae4c\uc9c0 {kind} \uc815\ubcf4\uac00 \uc5c6\uc2b5\ub2c8\ub2e4."


def format_meals(rows, start_date, end_date):
    if not rows:
        return empty_message("\uae09\uc2dd", start_date, end_date)

    cards = []
    for row in rows:
        menu_html = "\n".join(f"<li>{escape(item)}</li>" for item in clean_menu(row.get("DDISH_NM", "")))
        calories = row.get("CAL_INFO", "")
        calories_html = f'<span class="calories">{escape(calories)}</span>' if calories else ""
        cards.append(
            f"""
            <section class="info-card">
                <div class="meta">
                    <strong>{escape(format_date(row.get("MLSV_YMD", "")))}</strong>
                    <span>{escape(row.get("MMEAL_SC_NM", "\uae09\uc2dd"))}</span>
                    {calories_html}
                </div>
                <ul>{menu_html}</ul>
            </section>
            """
        )
    return "\n".join(cards)


def filter_meals_by_question(rows, message):
    if any(word in message for word in ["\uc11d\uc2dd", "\uc800\ub141"]):
        return [row for row in rows if row.get("MMEAL_SC_NM") == "\uc11d\uc2dd" or row.get("MMEAL_SC_CODE") == "3"]
    if any(word in message for word in ["\uc810\uc2ec", "\uc911\uc2dd"]):
        return [row for row in rows if row.get("MMEAL_SC_NM") == "\uc911\uc2dd" or row.get("MMEAL_SC_CODE") == "2"]
    return rows


def format_schedules(rows, start_date, end_date):
    if not rows:
        return empty_message("\ud559\uc0ac\uc77c\uc815", start_date, end_date)

    cards = []
    for row in rows:
        event = row.get("EVENT_NM", "\ud559\uc0ac\uc77c\uc815")
        content = row.get("EVENT_CNTNT", "")
        grades = [
            grade
            for key, grade in [
                ("ONE_GRADE_EVENT_YN", "1\ud559\ub144"),
                ("TW_GRADE_EVENT_YN", "2\ud559\ub144"),
                ("THREE_GRADE_EVENT_YN", "3\ud559\ub144"),
            ]
            if row.get(key) == "Y"
        ]
        grade_text = ", ".join(grades) if grades else "\uc804\uccb4"
        content_html = f"<p>{escape(content)}</p>" if content else ""
        cards.append(
            f"""
            <section class="info-card">
                <div class="meta">
                    <strong>{escape(format_date(row.get("AA_YMD", "")))}</strong>
                    <span>{escape(event)}</span>
                    <span class="grade">{escape(grade_text)}</span>
                </div>
                {content_html}
            </section>
            """
        )
    return "\n".join(cards)


def is_important_schedule(row):
    text = f"{row.get('EVENT_NM', '')} {row.get('EVENT_CNTNT', '')}"
    keywords = ["\uc2dc\ud5d8", "\uace0\uc0ac", "\ud3c9\uac00", "\ubc29\ud559", "\uac1c\ud559", "\ud734\uc5c5", "\uc218\ub2a5"]
    return any(keyword in text for keyword in keywords)


def month_bounds(selected_date):
    start = selected_date.replace(day=1)
    if selected_date.month == 12:
        end = dt.date(selected_date.year, 12, 31)
    else:
        end = selected_date.replace(month=selected_date.month + 1, day=1) - dt.timedelta(days=1)
    return start, end


def format_month_calendar(selected_date, rows, personal_by_date=None):
    personal_by_date = personal_by_date or {}
    start, end = month_bounds(selected_date)
    by_date = {}
    for row in rows:
        date_text = row.get("AA_YMD", "")
        if len(date_text) == 8:
            key = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:]}"
            by_date.setdefault(key, []).append(row)

    leading_blank = start.weekday()
    total_days = end.day
    cells = ["<td></td>"] * leading_blank

    for day in range(1, total_days + 1):
        current = start.replace(day=day)
        key = current.strftime("%Y-%m-%d")
        events = by_date.get(key, [])
        important = [row for row in events if is_important_schedule(row)]
        personal_events = personal_by_date.get(key, [])
        selected_class = " selected-day" if current == selected_date else ""
        important_class = " important-day" if important or personal_events else ""
        school_labels = "".join(f'<span class="school-event">{escape(row.get("EVENT_NM", ""))}</span>' for row in important[:2])
        personal_labels = "".join(f'<span class="personal-event">{escape(item.get("title", ""))}</span>' for item in personal_events[:3])
        cells.append(
            f"""
            <td class="calendar-day{selected_class}{important_class}">
                <div class="day-num">{day}</div>
                <div class="day-events">{school_labels}{personal_labels}</div>
            </td>
            """
        )

    while len(cells) % 7 != 0:
        cells.append("<td></td>")

    rows_html = []
    for index in range(0, len(cells), 7):
        rows_html.append(f"<tr>{''.join(cells[index:index + 7])}</tr>")

    return f"""
    <div class="calendar-wrap">
        <div class="calendar-title">{selected_date.year}\ub144 {selected_date.month}\uc6d4</div>
        <table class="month-calendar">
            <thead>
                <tr><th>\uc6d4</th><th>\ud654</th><th>\uc218</th><th>\ubaa9</th><th>\uae08</th><th>\ud1a0</th><th>\uc77c</th></tr>
            </thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </div>
    """


def format_important_month_list(rows):
    important_rows = [row for row in rows if is_important_schedule(row)]
    if not important_rows:
        return '<section class="info-card"><div class="meta"><strong>\uc774\ubc88 \ub2ec \uc8fc\uc694 \uc77c\uc815</strong></div><p>\ud45c\uc2dc\ud560 \uc2dc\ud5d8/\ubc29\ud559 \uc77c\uc815\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.</p></section>'

    items = []
    for row in important_rows:
        items.append(f"<li><strong>{escape(format_date(row.get('AA_YMD', '')))}</strong> {escape(row.get('EVENT_NM', ''))}</li>")
    return (
        '<section class="info-card">'
        '<div class="meta"><strong>\uc774\ubc88 \ub2ec \uc8fc\uc694 \uc77c\uc815</strong></div>'
        f"<ul>{''.join(items)}</ul>"
        "</section>"
    )


def format_personal_events(events, selected_date):
    if not events:
        return f"{selected_date.strftime('%Y-%m-%d')} \uac1c\uc778 \uc77c\uc815\uc774 \uc5c6\uc2b5\ub2c8\ub2e4."

    items = "\n".join(f"<li>{escape(event['title'])}</li>" for event in events)
    return (
        '<section class="info-card personal-card">'
        '<div class="meta"><strong>\uac1c\uc778 \uc77c\uc815</strong></div>'
        f"<ul>{items}</ul>"
        "</section>"
    )


def today_event_notice(student_id):
    if not student_id:
        return None
    today = dt.date.today()
    events = get_personal_events(student_id, today)
    if not events:
        return None
    titles = ", ".join(event["title"] for event in events)
    return f"\uc624\ub298 \uac1c\uc778 \uc77c\uc815\uc774 \uc788\uc2b5\ub2c8\ub2e4: {escape(titles)}"


def answer_question(message):
    school = get_school()
    start_date, end_date = parse_period(message)

    if "\ud559\uad50" in message and "\ucf54\ub4dc" in message:
        return (
            f"<p><b>{escape(school['name'])}</b></p>"
            f"<p>\uad50\uc721\uccad \ucf54\ub4dc: <code>{escape(school['office_code'])}</code><br>"
            f"\ud559\uad50 \ucf54\ub4dc: <code>{escape(school['school_code'])}</code><br>"
            f"{escape(school['address'])}</p>"
        )

    if is_schedule_question(message):
        schedules = get_schedules(school["office_code"], school["school_code"], start_date, end_date)
        return format_schedules(schedules, start_date, end_date)

    meals = filter_meals_by_question(get_meals(school["office_code"], school["school_code"], start_date, end_date), message)
    return format_meals(meals, start_date, end_date)


def is_school_data_question(message):
    keywords = [
        "\uae09\uc2dd",
        "\uc2dd\ub2e8",
        "\uc810\uc2ec",
        "\uc11d\uc2dd",
        "\ud559\uc0ac",
        "\uc77c\uc815",
        "\ud589\uc0ac",
        "\uc2dc\ud5d8",
        "\ubc29\ud559",
        "\uac1c\ud559",
        "\ud559\uad50 \ucf54\ub4dc",
    ]
    return any(keyword in message for keyword in keywords)


def is_allowed_chat_question(message):
    keywords = [
        "\uae40\ud3ec\uace0",
        "\ud559\uad50",
        "\ud559\uc0dd",
        "\ubc18",
        "\ud559\ubc88",
        "\ub2f4\uc784",
        "\uc218\uc5c5",
        "\uc219\uc81c",
        "\uacf5\ubd80",
        "\uc9c4\ub85c",
        "\ub300\ud559",
        "\ub3d9\uc544\ub9ac",
        "\uc218\ud589\ud3c9\uac00",
        "\uacfc\uc81c",
        "\uae09\uc2dd",
        "\uc2dd\ub2e8",
        "\ud559\uc0ac",
        "\uc77c\uc815",
        "\ud589\uc0ac",
        "\uc2dc\ud5d8",
        "\ubc29\ud559",
        "\uac1c\ud559",
        "\uce98\ub9b0\ub354",
        "\uac1c\uc778 \uc77c\uc815",
        "\uc0dd\uae30\ubd80",
        "\uc138\ud2b9",
        "\uba74\uc811",
        "\uc790\uc18c\uc11c",
        "\ud0d0\uad6c",
        "\ubc1c\ud45c",
        "\ud544\uae30",
        "\uc694\uc57d",
        "\uc815\ub9ac",
        "\uacc4\ud68d",
        "\uc2dc\uac04\ud45c",
        "\ub3c4\uc640",
        "\ub3c4\uc6c0",
        "\uc5b4\ub5bb\uac8c",
    ]
    return any(keyword in message for keyword in keywords)


def answer_general_chat(message):
    if OpenAI is None:
        return "`openai` \ud328\ud0a4\uc9c0\uac00 \uc124\uce58\ub418\uc5b4 \uc788\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4. `python -m pip install openai python-dotenv`\ub97c \uc2e4\ud589\ud558\uc138\uc694."
    if not get_env_value("OPENAI_API_KEY"):
        return "\ud658\uacbd\ubcc0\uc218 `OPENAI_API_KEY`\uac00 \uc124\uc815\ub418\uc5b4 \uc788\uc9c0 \uc54a\uc544\uc11c \uc77c\ubc18 \ucc57\ubd07 \ub2f5\ubcc0\uc744 \ub9cc\ub4e4 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4."
    client = get_openai_client()

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            max_output_tokens=220,
            input=[
                {
                    "role": "system",
                    "content": "\ub108\ub294 \uae40\ud3ec\uace0 \ucc57\ubd07\uc774\ub2e4. \ud559\uc0dd\uc774 \uc9e7\uac8c \ubb3c\uc5b4\ubcf4\uba74 \uc790\uc5f0\uc2a4\ub7fd\uace0 \uc2e4\uc6a9\uc801\uc73c\ub85c \ub300\ub2f5\ud574\ub77c. \uae09\uc2dd, \ud559\uc0ac\uc77c\uc815, \uc2dc\ud5d8, \ubc29\ud559 \uad00\ub828 \uc0ac\uc2e4\uc740 \uc560\ud50c\ub9ac\ucf00\uc774\uc158\uc758 NEIS \uc870\ud68c \uacb0\uacfc\ub97c \uc6b0\uc120\ud574\uc57c \ud558\uba70, \uc54c\uc9c0 \ubabb\ud558\ub294 \ud559\uad50 \uc815\ubcf4\ub294 \uc9c0\uc5b4\ub0b4\uc9c0 \ub9c8\ub77c.",
                },
                {"role": "user", "content": message},
            ],
        )
        text = getattr(response, "output_text", "").strip()
        if not text:
            return "\ub2f5\ubcc0\uc744 \ub9cc\ub4e4\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."
        return escape(text).replace("\n", "<br>")
    except Exception as exc:
        return f"OpenAI \ud638\ucd9c \uc624\ub958: {escape(str(exc))}"


def answer_with_openai_context(message, base_answer):
    client = get_openai_client()
    if client is None:
        return base_answer

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            max_output_tokens=160,
            input=[
                {
                    "role": "system",
                    "content": "\uae40\ud3ec\uace0 \ucc57\ubd07\uc785\ub2c8\ub2e4. \uc81c\uacf5\ub41c NEIS \uc870\ud68c \uacb0\uacfc\ub97c \ubc14\ud0d5\uc73c\ub85c \uc9e7\uace0 \uc790\uc5f0\uc2a4\ub7fd\uac8c \ub2f5\ud558\uc138\uc694. \uc5c6\ub294 \uc77c\uc815\uc774\ub098 \uae09\uc2dd\uc744 \uc9c0\uc5b4\ub0b4\uc9c0 \ub9c8\uc138\uc694.",
                },
                {
                    "role": "user",
                    "content": f"\uc9c8\ubb38: {message}\n\nNEIS \uc870\ud68c \uacb0\uacfc HTML:\n{base_answer}",
                },
            ],
        )
        text = getattr(response, "output_text", "").strip()
        if not text:
            return base_answer
        return f"<p>{escape(text)}</p>{base_answer}"
    except Exception:
        return base_answer


st.set_page_config(page_title="\uae40\ud3ec\uace0 \ucc57\ubd07", page_icon="G", layout="centered")

st.markdown(
    """
    <style>
    :root {
        --ink: #17212b;
        --muted: #667085;
        --line: #d8dee6;
        --panel: #ffffff;
        --accent: #116a5c;
        --warn: #c94f2d;
    }
    .stApp {
        background: linear-gradient(180deg, #eef3f7 0%, #fbfcfd 42%, #ffffff 100%);
        color: var(--ink);
    }
    .block-container {
        max-width: 920px;
        padding-top: 34px;
    }
    h1 {
        letter-spacing: 0;
        color: var(--ink);
    }
    .hero {
        border-bottom: 1px solid var(--line);
        padding-bottom: 18px;
        margin-bottom: 18px;
    }
    .hero p {
        color: var(--muted);
        margin: 6px 0 0;
    }
    .answer {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 16px;
        margin-top: 12px;
        box-shadow: 0 8px 22px rgba(22, 33, 43, 0.05);
    }
    .auth-shell {
        max-width: 430px;
        margin: 28px auto 0;
    }
    .auth-switch {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-bottom: 12px;
    }
    .info-card {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 14px 15px;
        margin: 10px 0;
        background: #fff;
    }
    .personal-card {
        border-color: #9cc9bd;
        background: #f4fbf8;
    }
    .meta {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 8px;
    }
    .meta strong {
        color: var(--accent);
    }
    .calories {
        margin-left: auto;
        color: var(--warn);
        font-weight: 700;
        font-size: 0.92rem;
    }
    .grade {
        border: 1px solid #bed7cf;
        background: #eef8f5;
        color: #0e5a4d;
        border-radius: 999px;
        padding: 1px 8px;
        font-size: 0.78rem;
    }
    .calendar-wrap {
        background: #fff;
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
        margin: 8px 0 20px;
        box-shadow: 0 8px 22px rgba(22, 33, 43, 0.05);
    }
    .calendar-title {
        font-weight: 800;
        color: var(--ink);
        margin-bottom: 14px;
        font-size: 1.15rem;
    }
    .month-calendar {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
    }
    .month-calendar th {
        color: var(--muted);
        font-size: 0.84rem;
        padding: 6px;
        border-bottom: 1px solid var(--line);
    }
    .month-calendar td {
        height: 118px;
        vertical-align: top;
        border: 1px solid #edf0f4;
        padding: 8px;
        background: #fff;
    }
    .calendar-day.important-day {
        background: #fff7ed;
        border-color: #f2b489;
    }
    .calendar-day.selected-day {
        outline: 2px solid var(--accent);
        outline-offset: -2px;
    }
    .day-num {
        font-weight: 800;
        color: var(--ink);
        margin-bottom: 4px;
    }
    .day-events {
        display: grid;
        gap: 3px;
    }
    .day-events span {
        display: block;
        font-size: 0.76rem;
        line-height: 1.25;
        word-break: keep-all;
        overflow-wrap: anywhere;
        border-radius: 5px;
        padding: 2px 5px;
    }
    .school-event {
        color: #9b321d;
        background: #fff4ef;
    }
    .personal-event {
        color: #0e5a4d;
        background: #eef8f5;
    }
    ul {
        margin: 0;
        padding-left: 20px;
        line-height: 1.8;
    }
    .stTextInput input, .stButton button {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "student_id" not in st.session_state:
    st.session_state.student_id = None

st.markdown(
    """
    <div class="hero">
        <h1>\uae40\ud3ec\uace0 \ucc57\ubd07</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.student_id:
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    switch_col1, switch_col2 = st.columns(2)
    with switch_col1:
        if st.button("\ub85c\uadf8\uc778", use_container_width=True):
            st.session_state.auth_mode = "login"
            st.rerun()
    with switch_col2:
        if st.button("\ud68c\uc6d0\uac00\uc785", use_container_width=True):
            st.session_state.auth_mode = "signup"
            st.rerun()

    if st.session_state.auth_mode == "login":
        st.markdown("<h2>\ub85c\uadf8\uc778</h2>", unsafe_allow_html=True)
        with st.form("main_login_form"):
            login_id = st.text_input("\ud559\ubc88", key="main_login_id")
            login_password = st.text_input("\ube44\ubc00\ubc88\ud638", type="password", key="main_login_password")
            if st.form_submit_button("\ub85c\uadf8\uc778", use_container_width=True):
                if verify_user(login_id, login_password):
                    st.session_state.student_id = login_id.strip()
                    st.rerun()
                else:
                    st.error("\ud559\ubc88 \ub610\ub294 \ube44\ubc00\ubc88\ud638\uac00 \ub2e4\ub985\ub2c8\ub2e4.")

    if st.session_state.auth_mode == "signup":
        st.markdown("<h2>\ud68c\uc6d0\uac00\uc785</h2>", unsafe_allow_html=True)
        with st.form("main_signup_form"):
            signup_id = st.text_input("\ud559\ubc88", key="main_signup_id")
            signup_password = st.text_input("\ube44\ubc00\ubc88\ud638", type="password", key="main_signup_password")
            signup_password_confirm = st.text_input("\ube44\ubc00\ubc88\ud638 \ud655\uc778", type="password", key="main_signup_password_confirm")
            if st.form_submit_button("\ud68c\uc6d0\uac00\uc785", use_container_width=True):
                if signup_password != signup_password_confirm:
                    st.error("\ube44\ubc00\ubc88\ud638\uac00 \uc11c\ub85c \ub2e4\ub985\ub2c8\ub2e4.")
                else:
                    ok, message = create_user(signup_id, signup_password)
                    if ok:
                        st.success(message)
                    else:
                        st.error(message)

    st.stop()

with st.sidebar:
    st.subheader("\ub85c\uadf8\uc778")
    st.caption(f"{st.session_state.student_id}")
    if st.button("\ub85c\uadf8\uc544\uc6c3", use_container_width=True):
        st.session_state.student_id = None
        st.rerun()

    st.divider()
    selected_date = st.date_input("\uce98\ub9b0\ub354", value=dt.date.today())

    if "show_delete_panel" not in st.session_state:
        st.session_state.show_delete_panel = False
    if st.button("\uc77c\uc815 \uc0ad\uc81c \uad00\ub9ac", use_container_width=True):
        st.session_state.show_delete_panel = not st.session_state.show_delete_panel
        st.rerun()

    if st.session_state.show_delete_panel:
        personal_events = get_personal_events(st.session_state.student_id, selected_date)
        if personal_events:
            labels = [event["title"] for event in personal_events]
            selected_label = st.selectbox("\uc0ad\uc81c\ud560 \uc77c\uc815", labels)
            if st.button("\uc120\ud0dd \uc77c\uc815 \uc0ad\uc81c", use_container_width=True):
                delete_personal_event(st.session_state.student_id, selected_date, labels.index(selected_label))
                st.rerun()
        else:
            st.caption("\uc120\ud0dd\ud55c \ub0a0\uc9dc\uc5d0 \uc0ad\uc81c\ud560 \uc77c\uc815\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.")

school_for_calendar = get_school()
month_start, month_end = month_bounds(selected_date)
month_rows = get_schedules(
    school_for_calendar["office_code"],
    school_for_calendar["school_code"],
    month_start,
    month_end,
)
personal_by_date = get_month_personal_events(st.session_state.student_id, selected_date)
st.markdown(format_month_calendar(selected_date, month_rows, personal_by_date), unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "\ubb34\uc5c7\uc744 \ud655\uc778\ud560\uae4c\uc694?"}]

notice_key = f"today_notice_{st.session_state.student_id}_{dt.date.today().isoformat()}"
if st.session_state.student_id and not st.session_state.get(notice_key):
    notice = today_event_notice(st.session_state.student_id)
    if notice:
        st.session_state.messages.append({"role": "assistant", "content": notice})
    st.session_state[notice_key] = True

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message["content"].lstrip().startswith("<"):
            st.markdown(f'<div class="answer">{message["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

question = st.chat_input("\uc9c8\ubb38 \uc785\ub825")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            calendar_answer = handle_personal_calendar_command(question, st.session_state.student_id)
            if calendar_answer is not None:
                answer = calendar_answer
            elif is_school_data_question(question):
                base_answer = answer_question(question)
                answer = base_answer
            elif not is_allowed_chat_question(question):
                answer = "\uae40\ud3ec\uace0, \ud559\uad50\uc0dd\ud65c, \uae09\uc2dd, \ud559\uc0ac\uc77c\uc815, \uac1c\uc778 \uc77c\uc815\uacfc \uad00\ub828\ub41c \uc9c8\ubb38\ub9cc \ub2f5\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
            else:
                answer = answer_general_chat(question)
            st.markdown(f'<div class="answer">{answer}</div>', unsafe_allow_html=True)
        except Exception as exc:
            answer = f"\uac00\uc838\uc624\ub294 \uc911 \uc624\ub958\uac00 \ub0ac\uc2b5\ub2c8\ub2e4: {exc}"
            st.error(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
