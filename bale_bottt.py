import requests
import time
import sqlite3
from datetime import datetime, timedelta
from collections import Counter
from datetime import timedelta
import csv
import matplotlib.pyplot as plt

TOKEN = "1214743869:HVosoVwMIVkUtkv3gXHENWnPbZWdxEwR7X4"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# --- DB ---
conn = sqlite3.connect("clinic.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    date TEXT,
    time TEXT,
    chat_id TEXT,
    reminded INTEGER DEFAULT 0
)
""")
conn.commit()

# --- Helper ---
def get_updates(offset=None):
    url = BASE_URL + "/getUpdates"
    params = {"timeout": 30, "offset": offset}
    return requests.get(url, params=params).json()

def send_message(chat_id, text):
    url = BASE_URL + "/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, json=data)

offset = None
print("Bot is running with reminders...")

while True:
    updates = get_updates(offset)

    # --- دریافت پیام‌ها ---
    if "result" in updates:
        for item in updates["result"]:
            offset = item["update_id"] + 1
            msg = item.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")

            if not chat_id:
                continue

            # --- /start ---
            if text == "/start":
                send_message(chat_id, "سلام 👋\nبه دستیار هوشمند مطب خوش آمدید.")

            # --- /today ---
            elif text == "/today":
                cur.execute("SELECT name, date, time FROM appointments")
                rows = cur.fetchall()
                if not rows:
                    send_message(chat_id, "امروز نوبتی نداریم.")
                else:
                    t = "نوبت‌ها:\n\n"
                    for r in rows:
                        t += f"{r[0]} - {r[1]} - {r[2]}\n"
                    send_message(chat_id, t)

            # --- /add ---
            elif text.startswith("/add"):
                try:
                    parts = text.split()
                    if len(parts) < 4:
                        raise ValueError
                    name = " ".join(parts[1:-2])
                    date = parts[-2]
                    hour = parts[-1]
                    cur.execute(
                        "INSERT INTO appointments (name, date, time, chat_id) VALUES (?,?,?,?)",
                        (name, date, hour, chat_id)
                    )
                    conn.commit()
                    send_message(chat_id, f"نوبت ثبت شد ✅\n{name}\n📅 {date}\n⏰ {hour}")
                except:
                    send_message(chat_id, "فرمت درست نیست ❌\nمثال:\n/add Ali 2026-02-06 16:00")

            # --- /cancel ---
            elif text.startswith("/cancel"):
                try:
                    parts = text.split()
                    if len(parts) < 2:
                        raise ValueError
                    name = " ".join(parts[1:])
                    cur.execute("SELECT * FROM appointments WHERE name=?", (name,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("DELETE FROM appointments WHERE name=?", (name,))
                        conn.commit()
                        send_message(chat_id, f"نوبت {name} با موفقیت کنسل شد ✅")
                    else:
                        send_message(chat_id, f"نوبتی با نام {name} پیدا نشد ❌")
                except:
                    send_message(chat_id, "فرمت درست نیست ❌\nمثال:\n/cancel Ali")

            # --- /reschedule ---
            elif text.startswith("/reschedule"):
                try:
                    parts = text.split()
                    if len(parts) < 4:
                        raise ValueError
                    name = " ".join(parts[1:-2])
                    new_date = parts[-2]
                    new_hour = parts[-1]
                    cur.execute("SELECT * FROM appointments WHERE name=?", (name,))
                    row = cur.fetchone()
                    if row:
                        cur.execute("UPDATE appointments SET date=?, time=?, reminded=0 WHERE name=?", (new_date, new_hour, name))
                        conn.commit()
                        send_message(chat_id, f"نوبت {name} با موفقیت تغییر یافت ✅\n📅 {new_date}\n⏰ {new_hour}")
                    else:
                        send_message(chat_id, f"نوبتی با نام {name} پیدا نشد ❌")
                except:
                    send_message(chat_id, "فرمت درست نیست ❌\nمثال:\n/reschedule Ali 2026-02-07 14:00")

            
            #report
            elif text.startswith("/report"):
                try:
                    parts = text.split()
                    if len(parts) != 2 or parts[1] not in ["weekly", "monthly"]:
                        raise ValueError
                    period = parts[1]

                    now = datetime.now()
                    if period == "weekly":
                        start_date = now - timedelta(days=7)
                    else:  # monthly
                        start_date = now - timedelta(days=30)

                    cur.execute("SELECT name, date, time FROM appointments")
                    rows = cur.fetchall()

                    # فیلتر بر اساس دوره
                    filtered = [r for r in rows if datetime.strptime(r[1], "%Y-%m-%d") >= start_date]

                    # --- آماده‌سازی متن پیام ---
                    total = len(filtered)
                    msg = f"📊 گزارش {period}:\n\nتعداد نوبت‌ها: {total}\n"

                    # روزهای شلوغ
                    days_count = Counter(r[1] for r in filtered)
                    if days_count:
                        msg += "روزهای شلوغ:\n"
                        for day, count in days_count.most_common(3):
                            msg += f"{day}: {count} نوبت\n"

                    # بیماران تکراری
                    patient_count = Counter(r[0] for r in filtered)
                    repeated = [p for p, c in patient_count.items() if c > 1]
                    if repeated:
                        msg += "\nبیماران تکراری:\n" + ", ".join(repeated)

                    # میانگین نوبت‌ها در هر ساعت
                    hour_count = Counter(r[2] for r in filtered)
                    if hour_count:
                        msg += "\nمیانگین نوبت‌ها در هر ساعت:\n"
                        for hour, count in sorted(hour_count.items()):
                            msg += f"{hour}: {count} نوبت\n"

                    # --- CSV ---
                    csv_file = f"{period}_report.csv"
                    with open(csv_file, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["نام", "تاریخ", "ساعت"])
                        for r in filtered:
                            writer.writerow(r)

                    # --- نمودار ---
                    chart_file = f"{period}_chart.png"
                    if days_count:
                        plt.figure(figsize=(8,4))
                        plt.bar(days_count.keys(), days_count.values(), color='skyblue')
                        plt.title(f"روزهای شلوغ - گزارش {period}")
                        plt.xlabel("تاریخ")
                        plt.ylabel("تعداد نوبت")
                        plt.xticks(rotation=45)
                        plt.tight_layout()
                        plt.savefig(chart_file)
                        plt.close()

                    # --- ارسال پیام خلاصه ---
                    send_message(chat_id, msg)

                    # --- ارسال لینک فایل‌ها ---
                    base_url = "http://example.com/reports"  # ← اینو لینک سرورت یا جایی که فایل‌ها آپلود می‌کنه بذار
                    send_message(chat_id, f"دانلود CSV: {base_url}/{csv_file}")
                    if days_count:
                        send_message(chat_id, f"دانلود نمودار: {base_url}/{chart_file}")

                except Exception as e:
                    send_message(chat_id, f"خطا در ایجاد گزارش ❌\n{e}")




    # --- یادآوری خودکار ---
    now = datetime.now()
    cur.execute("SELECT id, name, date, time, chat_id, reminded FROM appointments WHERE reminded=0")
    rows = cur.fetchall()
    for r in rows:
        ap_id, name, date_, hour_, chat_id, reminded = r
        ap_datetime = datetime.strptime(f"{date_} {hour_}", "%Y-%m-%d %H:%M")
        if 0 < (ap_datetime - now).total_seconds() < 3600:  # یک ساعت قبل
            send_message(chat_id, f"یادآوری ⏰\n{name}\nنوبت شما تا یک ساعت دیگر است.")
            cur.execute("UPDATE appointments SET reminded=1 WHERE id=?", (ap_id,))
            conn.commit()

    # بعد از ارسال نوبت و یادآوری نوبت
    now = datetime.now()
    cur.execute("SELECT id, name, date, time, chat_id, followup_sent FROM appointments WHERE followup_sent=0")
    rows = cur.fetchall()
    for r in rows:
        ap_id, name, date_, hour_, chat_id, followup_sent = r
        ap_datetime = datetime.strptime(f"{date_} {hour_}", "%Y-%m-%d %H:%M")
        if now > ap_datetime + timedelta(minutes=60):  # یک ساعت بعد از نوبت
            send_message(chat_id, f"سلام {name}، وضعیت دندون شما بعد از درمان چطوره؟ 🙂")
            cur.execute("UPDATE appointments SET followup_sent=1 WHERE id=?", (ap_id,))
            conn.commit()
    time.sleep(1)

