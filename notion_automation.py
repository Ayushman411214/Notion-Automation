import requests
import matplotlib.pyplot as plt
import pandas as pd
import yagmail
import gspread
import os
from datetime import date ,timedelta,datetime,time
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv


load_dotenv()
# ================= CONFIG =================

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
TIME_BLOCK_DB = os.getenv("TIME_BLOCK_DB") 

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
DAILY_SHEET = os.getenv("DAILY_SHEET")

SERVICE_ACCOUNT_FILE = "service_account.json"


SENDER_EMAIL=os.getenv("SENDER_EMAIL")
APP_PASSWORD=os.getenv("APP_PASSWORD")
RECEIVER_EMAIL=os.getenv("RECEVIER_EMAIL")

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


today = date.today()
yesterday = today - timedelta(days=1)
day_name = today.strftime("%A")
date = today.isoformat()

def query_db(db_id,payload=None):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    results=[]
    payload=payload or {}
    while True:
        res = requests.post(url,headers=HEADERS,json=payload,timeout=15).json()
        # res = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        # res.raise_for_status()
        # data = res.json()
        if "results" not in res:
            print("❌ Notion API error response:")
            print(res)
            exit()
        
        results.extend(res["results"])
        if not res.get("has_more"):
            break
        payload["start_cursor"]=res["next_cursor"]
    return results

def get_today_data(day,pages):
    tag_count = defaultdict(float)
    chk = day[:3]
    for page in pages:
        props = page["properties"]

        # worked blocks
        if props.get(chk, {}).get("checkbox"):
            tag_obj = props.get(day, {}).get("select")
            tag = tag_obj["name"] if tag_obj else "Uncategorized"
            tag_count[tag] += 0.5

        # free / unused blocks
        else:
            tag_count["Free / Unused"] += 0.5
    # sorted_tag = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
    return tag_count

def update_page(page_id, properties):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    requests.patch(url, headers=HEADERS, json={"properties": properties})

def get_sheets():
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
        ws.append_row(["Day"])

    return ws

def get_headers(ws):
    headers = ws.row_values(1)
    if not headers:
        headers = ["Day"]
        ws.append_row(headers)
    return headers

def ensure_tag_columns(ws, headers, tags):
    updated = False
    for tag in tags:
        if tag not in headers:
            headers.append(tag)
            updated = True
    if updated:
        ws.update("A1", [headers])
    return headers

def get_or_create_day_row(ws, day):
    days = ws.col_values(1)
    if day in days:
        return days.index(day) + 1
    ws.append_row([day])
    return len(days) + 1

def push_daily_matrix(ws, day, tag_data):
    headers = get_headers(ws)
    headers = ensure_tag_columns(ws, headers, tag_data.keys())
    row = get_or_create_day_row(ws, day)

    updates = []
    for tag, hours in tag_data.items():
        col = headers.index(tag) + 1
        cell = gspread.utils.rowcol_to_a1(row, col)
        updates.append({
            "range": cell,
            "values": [[hours]]
        })

    ws.batch_update(updates)

def create_vertical_bar_chart(
    data,
    bg_color="#E9F5DB",
    max_color="#1f6f6f",
    min_color="#9fc8c8",
    normal_color="#54a1a1",
    label_rotation=50
):
    # ---- clean + sort ----
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

    # ---- plot ----
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    bars = ax.bar(labels, values, width=0.5, color=colors, edgecolor="none")
    # ax.grid(False)

    # ---- value labels ----
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
    # ---- labels & title ----
    free = data.get("Free / Unused", 0)
    ax.set_title(f"Today Time Utilization : {total_time - free} hrs",pad=15,fontsize=14)
   
    ax.set_ylabel("Hours",fontsize=8)
    ax.set_xlabel("Activity",fontsize=8)
    
    ax.set_xticklabels(labels, rotation=label_rotation, ha="right",fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", linestyle="-", alpha=0.2)


    # ---- save ----
    os.makedirs("charts", exist_ok=True)
    png = f"charts/{date}.png"
    pdf = f"charts/{date}.pdf"

    plt.tight_layout()
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.savefig(pdf, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()

    print(f"📊 Vertical bar chart saved → {png}")
    print(f"📄 PDF saved → {pdf}")

def send_single_file_via_email(
    sender_email: str,
    app_password: str,
    receiver_email: str,
    folder_path: str,
    file_name: str,
    subject_prefix="Daily Report"
):
    file_path = os.path.join(folder_path, file_name)

    try:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"❌ File not found: {file_path}")

        body = f"""
Hello,
This is your automated daily report for {yesterday}.

Attached File:
- {file_name}

Regards,
🤖
"""

        yag = yagmail.SMTP(sender_email, app_password)

        yag.send(
            to=receiver_email,
            subject=f"{subject_prefix} | {yesterday}",
            contents=body,
            attachments=[file_path]   # ✔ list is safer
        )

        print(f"✅ Email sent successfully with file: {file_name}")

    except FileNotFoundError as e:
        print(e)
        return   # ❗ VERY IMPORTANT

    except Exception as e:
        print("❌ Email sending failed:", e)
        return

def reset_table(today, pages):
    now = datetime.now()
    reset_time = time(3, 0)  # ⏰ 03:00 AM

    print("Today date => ",now)
    week_start_str = pages[0]["properties"]["Week Start"]["date"]["start"]
    week_start = datetime.fromisoformat(week_start_str).date()

    next_week_start = week_start + timedelta(days=7)
    print("next errk reset date => ",next_week_start)

 
    if (
        today >= next_week_start
        and now.time() >= reset_time
        and not reset_done
    ):
        print("♻️ Weekly reset started...")

        new_week_start = next_week_start.isoformat()

        for page in pages:
            reset_props = {
                "Week Start": {"date": {"start": new_week_start}},
               
            }

            for chk, sel in DAYS.items():
                reset_props[chk] = {"checkbox": False}
                reset_props[sel] = {"select": None}

            update_page(page["id"], reset_props)
         

        print("✅ Weekly reset completed (one-time)")

    else:
        print(
            f"⏳ No reset | "
            f"Today={today} | "
            f"ResetOn={next_week_start} | "
            f"Time={now.strftime('%H:%M')} | "
            # f"Done={reset_done}"
        )
#  =============== Main ===============   
def main():
    print("📡 Fetching Notion data...")
    pages=query_db(TIME_BLOCK_DB)

    print(f"📅 Processing: {day_name}")
    day_data=get_today_data(day_name,pages)
    print("📊 Data: ✅")


    print("✉️ Send Dialy Data to Sheet")
    ws = get_sheets()
    push_daily_matrix(ws, date, day_data)
    create_vertical_bar_chart(day_data)

    print(" 📩 Sending Email")
    send_single_file_via_email(
        sender_email=SENDER_EMAIL,
        app_password=APP_PASSWORD,
        receiver_email=RECEIVER_EMAIL,
        folder_path="charts",
        file_name=f"{yesterday}.pdf"
    )
    reset_table(today,pages)


if __name__ == "__main__":
    main()
