# ================== IMPORTS ==================
import os
import requests
import matplotlib
matplotlib.use("Agg")  # 🔥 REQUIRED for GitHub Actions / server

import matplotlib.pyplot as plt
import gspread
import yagmail

from collections import defaultdict
from datetime import datetime, timedelta, timezone, time
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# ================== LOAD ENV ==================
load_dotenv()

# ================== CONFIG ==================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
TIME_BLOCK_DB = os.getenv("TIME_BLOCK_DB")

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
DAILY_SHEET = os.getenv("DAILY_SHEET")

SERVICE_ACCOUNT_FILE = "service_account.json"

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")  # ✅ FIXED TYPO

# ================== TIME (SINGLE SOURCE OF TRUTH) ==================
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)

RUN_DATE = NOW.date().isoformat()                 # today (logs only)
DATA_DATE = (NOW - timedelta(days=1)).date().isoformat()  # 🔥 yesterday (chart + email)

DAY_NAME = (NOW - timedelta(days=1)).strftime("%A")

print(f"📅 Run Date : {RUN_DATE}")
print(f"📊 Data Date: {DATA_DATE}")
print(f"📅 Day Name : {DAY_NAME}")

# ================== NOTION CONFIG ==================
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

DAYS = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday"
}

# ================== NOTION HELPERS ==================
def query_db(db_id, payload=None):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    results = []
    payload = payload or {}

    while True:
        res = requests.post(url, headers=HEADERS, json=payload, timeout=15).json()
        if "results" not in res:
            raise RuntimeError(f"❌ Notion API error: {res}")

        results.extend(res["results"])
        if not res.get("has_more"):
            break

        payload["start_cursor"] = res["next_cursor"]

    return results

def get_day_data(day, pages):
    tag_count = defaultdict(float)
    chk = day[:3]

    for page in pages:
        props = page["properties"]

        if props.get(chk, {}).get("checkbox"):
            tag_obj = props.get(day, {}).get("select")
            tag = tag_obj["name"] if tag_obj else "Uncategorized"
            tag_count[tag] += 0.5
        else:
            tag_count["Free / Unused"] += 0.5

    return tag_count

# ================== GOOGLE SHEETS ==================
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        SERVICE_ACCOUNT_FILE, scope
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet(DAILY_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=DAILY_SHEET, rows=1000, cols=30)
        ws.append_row(["Date"])

    return ws

def push_daily_matrix(ws, date_str, tag_data):
    headers = ws.row_values(1)
    if not headers:
        headers = ["Date"]
        ws.append_row(headers)

    for tag in tag_data:
        if tag not in headers:
            headers.append(tag)

    ws.update("A1", [headers])

    dates = ws.col_values(1)
    if date_str in dates:
        row = dates.index(date_str) + 1
    else:
        ws.append_row([date_str])
        row = len(dates) + 1

    updates = []
    for tag, val in tag_data.items():
        col = headers.index(tag) + 1
        updates.append({
            "range": gspread.utils.rowcol_to_a1(row, col),
            "values": [[val]]
        })

    ws.batch_update(updates)

# ================== CHART ==================
def create_vertical_bar_chart(data):
    max_color="#1f6f6f"
    min_color="#9fc8c8"
    normal_color="#54a1a1"
    
    data = {k: v for k, v in data.items() if v > 0}
    data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True))

    labels = list(data.keys())
    values = list(data.values())


    
   
    max_val = max(values)
    min_val = min(values)

    # ---- assign colors dynamically ----
    colors = []
    for v in values:
        if v == max_val:
            colors.append(max_color)
        elif v == min_val:
            colors.append(min_color)
        else:
            colors.append(normal_color)

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#E9F5DB")
    ax.set_facecolor("#E9F5DB")
    bars = ax.bar(labels, values,width=0.4,color=colors,edgecolor="none")

    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 4,
            height + 0.1,
            f"{height:.1f}h",
            ha="center",
            va="bottom",
            fontsize=8
        )
    total_time = sum(data.values())
    free = data.get("Free / Unused", 0)
    ax.set_title(f"Today Time Utilization : {total_time - free} hrs",pad=15,fontsize=14)
    
    ax.set_ylabel("Hours",fontsize=8)
    ax.set_xlabel("Activity",fontsize=8)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right",fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    os.makedirs("charts", exist_ok=True)
    ax.grid(axis="y", linestyle="-", alpha=0.2)

    png = f"charts/{DATA_DATE}.png"
    pdf = f"charts/{DATA_DATE}.pdf"

    plt.tight_layout()
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.savefig(pdf, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

    assert os.path.exists(pdf), f"❌ Chart not created: {pdf}"

    print(f"📊 Chart saved → {png}")
    print(f"📄 PDF saved → {pdf}")

# ================== EMAIL ==================
def send_single_file_via_email():
    file_path = f"charts/{DATA_DATE}.pdf"

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"❌ File not found: {file_path}")

    yag = yagmail.SMTP(SENDER_EMAIL, APP_PASSWORD)

    body = f"""
Hello,

This is your automated daily report.

📅 Date: {DATA_DATE}, {DAY_NAME}

Regards,
🤖 Automation
"""

    yag.send(
        to=RECEIVER_EMAIL,
        subject=f"Daily Report | {DATA_DATE}",
        contents=body,
        attachments=[file_path]
    )

    print("✅ Email sent successfully")

# ================== WEEK RESET ==================
def reset_table(today_date, pages):
    now = datetime.now(IST)
    reset_time = time(3, 0)  # 03:00 AM IST

    week_start_str = pages[0]["properties"]["Week Start"]["date"]["start"]
    week_start = datetime.fromisoformat(week_start_str).date()
    next_week_start = week_start + timedelta(days=7)

    if today_date >= next_week_start and now.time() >= reset_time:
        print("♻️ Weekly reset started")

        for page in pages:
            props = {
                "Week Start": {"date": {"start": next_week_start.isoformat()}}
            }
            for chk, sel in DAYS.items():
                props[chk] = {"checkbox": False}
                props[sel] = {"select": None}

            requests.patch(
                f"https://api.notion.com/v1/pages/{page['id']}",
                headers=HEADERS,
                json={"properties": props}
            )

        print("✅ Weekly reset completed")
    else:
        print(f"⏳ No reset | Today={today_date} | ResetOn={next_week_start}")

# ================== MAIN ==================
def main():
    print("📡 Fetching Notion data...")
    pages = query_db(TIME_BLOCK_DB)

    print(f"📅 Processing data for: {DAY_NAME}")
    day_data = get_day_data(DAY_NAME, pages)

    print("✉️ Sending data to Google Sheet")
    ws = get_sheet()
    push_daily_matrix(ws, DATA_DATE, day_data)

    create_vertical_bar_chart(day_data)

    print("📩 Sending Email")
    send_single_file_via_email()

    reset_table(NOW.date(), pages)

# ================== RUN ==================
if __name__ == "__main__":
    main()
