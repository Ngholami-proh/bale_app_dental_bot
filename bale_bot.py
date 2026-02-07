import sqlite3
from datetime import datetime, timedelta
from collections import Counter
import csv
import matplotlib.pyplot as plt
import time
import requests

# ----- توکن و URL API بله -----
BOT_TOKEN = "1214743869:HVosoVwMIVkUtkv3gXHENWnPbZWdxEwR7X4"
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"

# ----- اتصال دیتابیس -----
conn = sqlite3.connect("appointments.db")
cur = conn.cursor()

# ----- جدول نوبت‌ها -----
cur.execute('''CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    date TEXT,
    time TEXT,
    chat_id INTEGER,
    reminded INTEGER DEFAULT 0,
    followup_sent INTEGER DEFAULT 0
)''')
conn.commit()
# cur.execute("UPDATE appointments SET followup_waiting=0")
# conn.commit()
# ----- شناسه‌های مجاز منشی/دکتر -----
AUTHORIZED_USERS = [1984139551, 987654321]  # chat_id دکتر و منشی

# ----- ارسال پیام واقعی به بله -----
def send_message(chat_id, text):
    url = BASE_URL + "/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        print("❌ ارسال پیام به بله موفق نبود:", res.text)

# ----- ثبت نوبت توسط منشی -----
def add_appointment(name, date_, hour_, patient_chat_id, user_chat_id):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه ثبت نوبت را ندارید.")
        return
    cur.execute("SELECT * FROM appointments WHERE date=? AND time=?", (date_, hour_))
    if cur.fetchone():
        send_message(user_chat_id, "❌ این ساعت قبلاً رزرو شده است.")
        return
    cur.execute("INSERT INTO appointments (name, date, time, chat_id) VALUES (?, ?, ?, ?)",
                (name, date_, hour_, patient_chat_id))
    conn.commit()
    send_message(user_chat_id, f"نوبت {name} برای {date_} ساعت {hour_} ثبت شد ✅")
    send_message(patient_chat_id, f"سلام {name}، نوبت شما برای {date_} ساعت {hour_} ثبت شد ✅")

# ----- رزرو خودکار بیمار -----
ALL_HOURS = ["10:00","11:00","13:00","14:00","15:00","16:00"]

def get_free_hours(date_):
    cur.execute("SELECT time FROM appointments WHERE date=?", (date_,))
    taken = [r[0] for r in cur.fetchall()]
    return [h for h in ALL_HOURS if h not in taken]

def book_day(patient_chat_id, date_):
    free_hours = get_free_hours(date_)
    if not free_hours:
        send_message(patient_chat_id, "این روز هیچ ساعت خالی ندارد.")
        return
    send_message(patient_chat_id, f"ساعت‌های خالی برای {date_}:\n" + ", ".join(free_hours))

def book_time(patient_chat_id, date_, hour_):
    free_hours = get_free_hours(date_)
    if hour_ not in free_hours:
        send_message(patient_chat_id, "❌ این ساعت قبلاً رزرو شده یا موجود نیست.")
        return

    cur.execute(
        "INSERT INTO appointments (name, date, time, chat_id) VALUES (?, ?, ?, ?)",
        (f"Patient {patient_chat_id}", date_, hour_, patient_chat_id)
    )
    conn.commit()
    send_message(patient_chat_id, f"✅ نوبت شما برای {date_} ساعت {hour_} ثبت شد")



# ----- لغو نوبت توسط بیمار -----
def cancel_appointment(patient_chat_id):
    cur.execute("SELECT * FROM appointments WHERE chat_id=? ORDER BY date,time", (patient_chat_id,))
    rows = cur.fetchall()

    if not rows:
        send_message(patient_chat_id, "❌ شما هیچ نوبتی برای لغو ندارید.")
        return

    ap_id, name, date_, hour_, _, _, _ = rows[-1]

    cur.execute("DELETE FROM appointments WHERE id=?", (ap_id,))
    conn.commit()

    # پیام به بیمار
    send_message(patient_chat_id, f"نوبت شما برای {date_} ساعت {hour_} لغو شد ✅")

    # پیام به منشی‌ها
    for admin_id in AUTHORIZED_USERS:
        send_message(
            admin_id,
            f"📣 لغو نوبت\n"
            f"👤 بیمار: {name}\n"
            f"📅 تاریخ: {date_}\n"
            f"⏰ ساعت: {hour_}\n"
            f"🆔 chat_id: {patient_chat_id}"
        )
# ----- تغییر ساعت توسط بیمار -----
def reschedule_time(patient_chat_id, date_, new_time):
    cur.execute("SELECT * FROM appointments WHERE chat_id=? ORDER BY date,time DESC", (patient_chat_id,))
    row = cur.fetchone()
    if not row:
        send_message(patient_chat_id, "❌ هیچ نوبتی برای تغییر ساعت وجود ندارد.")
        return

    ap_id, name, old_date, old_time, _, _, _ = row
    free_hours = get_free_hours(date_)
    if new_time not in free_hours:
        send_message(patient_chat_id, "❌ این ساعت قبلاً پر است.")
        return

    # بروزرسانی نوبت
    cur.execute("UPDATE appointments SET date=?, time=? WHERE id=?", (date_, new_time, ap_id))
    conn.commit()
    send_message(patient_chat_id, f"✅ نوبت شما از {old_date} ساعت {old_time} به {date_} ساعت {new_time} تغییر یافت")
def reschedule_appointment(patient_chat_id, date_):
    # گرفتن آخرین نوبت بیمار
    cur.execute("SELECT * FROM appointments WHERE chat_id=? ORDER BY date,time DESC", (patient_chat_id,))
    row = cur.fetchone()
    if not row:
        send_message(patient_chat_id, "❌ هیچ نوبتی برای تغییر وجود ندارد.")
        return

    # نمایش ساعت‌های آزاد آن روز
    free_hours = get_free_hours(date_)
    if not free_hours:
        send_message(patient_chat_id, "❌ این روز هیچ ساعت خالی ندارد.")
        return

    send_message(patient_chat_id, f"ساعت‌های خالی برای {date_}:\n" + ", ".join(free_hours))
# کنسل و تغییر ساعت توسط منشی
def admin_cancel(user_chat_id, name, date_, hour_):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه ندارید.")
        return

    cur.execute(
        "SELECT * FROM appointments WHERE name=? AND date=? AND time=?",
        (name, date_, hour_)
    )
    row = cur.fetchone()

    if not row:
        send_message(user_chat_id, "❌ چنین نوبتی پیدا نشد.")
        return

    ap_id, name, date_, hour_, chat_id, _, _ = row

    cur.execute("DELETE FROM appointments WHERE id=?", (ap_id,))
    conn.commit()

    send_message(user_chat_id, f"نوبت {name} در {date_} ساعت {hour_} لغو شد ✅")
    send_message(chat_id, f"📣 نوبت شما لغو شد\n📅 {date_}\n⏰ {hour_}")
def admin_reschedule(user_chat_id, name, date_, old_time, new_time):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه ندارید.")
        return

    cur.execute(
        "SELECT * FROM appointments WHERE name=? AND date=? AND time=?",
        (name, date_, old_time)
    )
    row = cur.fetchone()

    if not row:
        send_message(user_chat_id, "❌ نوبت پیدا نشد.")
        return

    ap_id, name, date_, old_time, chat_id, _, _ = row

    if new_time not in get_free_hours(date_):
        send_message(user_chat_id, "❌ ساعت جدید پر است.")
        return

    cur.execute("UPDATE appointments SET time=? WHERE id=?", (new_time, ap_id))
    conn.commit()

    send_message(user_chat_id, f"نوبت {name} تغییر کرد ✅")
    send_message(chat_id, f"🔄 نوبت شما تغییر کرد\n📅 {date_}\n⏰ {old_time} ➝ {new_time}")


# تغییر نوبت در 2 وز متفاوت 
def admin_move(user_chat_id, name, old_date, old_time, new_date, new_time):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه ندارید.")
        return

    # نوبت قبلی
    cur.execute(
        "SELECT * FROM appointments WHERE name=? AND date=? AND time=?",
        (name, old_date, old_time)
    )
    row = cur.fetchone()

    if not row:
        send_message(user_chat_id, "❌ نوبت قبلی پیدا نشد.")
        return

    ap_id, name, old_date, old_time, chat_id, _, _ = row

    # بررسی تایم جدید
    cur.execute(
        "SELECT 1 FROM appointments WHERE date=? AND time=?",
        (new_date, new_time)
    )
    if cur.fetchone():
        send_message(user_chat_id, "❌ زمان جدید پر است.")
        return

    # انتقال
    cur.execute(
        "UPDATE appointments SET date=?, time=? WHERE id=?",
        (new_date, new_time, ap_id)
    )
    conn.commit()

    # پیام‌ها
    send_message(user_chat_id, f"نوبت {name} منتقل شد ✅")

    send_message(
        chat_id,
        f"🔁 تغییر نوبت\n"
        f"📅 از {old_date} ⏰ {old_time}\n"
        f"➡ به {new_date} ⏰ {new_time}"
    )    
# ----- گزارش برای دکتر/منشی -----
def report(chat_id, period):
    if chat_id not in AUTHORIZED_USERS:
        send_message(chat_id, "❌ شما اجازه استفاده از گزارش را ندارید.")
        return
    now = datetime.now()
    start_date = now - timedelta(days=7 if period=="weekly" else 30)
    cur.execute("SELECT name, date, time FROM appointments")
    rows = cur.fetchall()
    filtered = [r for r in rows if datetime.strptime(r[1], "%Y-%m-%d") >= start_date]

    total = len(filtered)
    msg = f"📊 گزارش {period}:\nتعداد نوبت‌ها: {total}\n"
    days_count = Counter(r[1] for r in filtered)
    if days_count:
        msg += "روزهای شلوغ:\n" + "\n".join(f"{d}: {c} نوبت" for d,c in days_count.most_common(3))
    send_message(chat_id, msg)

# ----- لیست بیماران برای منشی/دکتر -----
def list_patients(user_chat_id):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه مشاهده بیماران را ندارید.")
        return
    cur.execute("SELECT name, chat_id FROM appointments GROUP BY chat_id, name")
    rows = cur.fetchall()
    if not rows:
        send_message(user_chat_id, "❌ هیچ بیمار ثبت شده‌ای وجود ندارد.")
        return
    msg = "📋 لیست بیماران و chat_id:\n"
    for name, chat_id in rows:
        msg += f"{name} : {chat_id}\n"
    send_message(user_chat_id, msg)

# ----- یادآوری و پیگیری خودکار -----
def auto_reminders():
    now = datetime.now()
    # یادآوری قبل نوبت
    cur.execute("SELECT id, name, date, time, chat_id, reminded FROM appointments WHERE reminded=0")
    for ap_id, name, date_, hour_, chat_id, reminded in cur.fetchall():
        ap_datetime = datetime.strptime(f"{date_} {hour_}", "%Y-%m-%d %H:%M")
        if now >= ap_datetime - timedelta(hours=1) and now < ap_datetime:
            send_message(chat_id, f"سلام {name}، نوبت شما در یک ساعت دیگر ({hour_}) است ⏰")
            cur.execute("UPDATE appointments SET reminded=1 WHERE id=?", (ap_id,))
            conn.commit()
    # پیگیری بعد نوبت
    # پیگیری بعد نوبت
    cur.execute("SELECT id, name, date, time, chat_id, followup_sent FROM appointments WHERE followup_sent=0")
    for ap_id, name, date_, hour_, chat_id, followup_sent in cur.fetchall():
        ap_datetime = datetime.strptime(f"{date_} {hour_}", "%Y-%m-%d %H:%M")
        if now >= ap_datetime + timedelta(hours=1):
            send_message(chat_id, f"سلام {name}، وضعیت دندان شما بعد از درمان چطور است؟ 🙂")
            cur.execute("UPDATE appointments SET followup_sent=1, followup_waiting=1 WHERE id=?", (ap_id,))
            conn.commit()
            
#دریافت اسامی بیماران روز             
def today_schedule(user_chat_id):
    if user_chat_id not in AUTHORIZED_USERS:
        send_message(user_chat_id, "❌ شما اجازه مشاهده برنامه امروز را ندارید.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT name, time, chat_id FROM appointments WHERE date=? ORDER BY time", (today,))
    rows = cur.fetchall()

    if not rows:
        send_message(user_chat_id, "📋 امروز هیچ نوبتی ثبت نشده است.")
        return

    msg = f"📅 برنامه امروز ({today}):\n"
    for name, time_, chat_id in rows:
        msg += f"⏰ {time_} - {name} (chat_id: {chat_id})\n"

    send_message(user_chat_id, msg)

#start
def start_message(patient_chat_id):
    msg = (
        "🦷 سلام! به مطب خوش آمدید.\n\n"
        "شما می‌توانید از دستورات زیر استفاده کنید:\n\n"
        "📌 رزرو نوبت: /booktime YYYY-MM-DD HH:MM\n"
        "📌 لغو نوبت: /cancel\n"
        "📌 تغییر ساعت یا تاریخ نوبت: /reschedule YYYY-MM-DD HH:MM\n"
        "📌 مشاهده سوالات متداول: /faq\n\n"
        "مثال:\n"
        "/booktime 2026-02-07 10:00 → رزرو نوبت\n"
        "/reschedule 2026-02-08 14:00 → تغییر نوبت شما\n"
        "/cancel → لغو نوبت شما\n"
        "/faq → مشاهده سوالات پر تکرار"
    )
    send_message(patient_chat_id, msg)

#FAQ
FAQ = {
    "ساعات کاری": "🕒 مطب از ساعت ۱۰ تا ۱۶ پذیرش دارد.",
    "مراحل درمان ریشه": "🦷 مراحل درمان ریشه شامل معاینه، بی‌حسی، تمیز کردن کانال، و پر کردن کانال می‌باشد.",
    "لغو نوبت": "❌ برای لغو نوبت، دستور /cancel را بفرستید یا با منشی هماهنگ کنید.",
    "رزرو نوبت": "📌 برای رزرو نوبت، دستور /booktime YYYY-MM-DD HH:MM را بفرستید."
}
def faq_message(patient_chat_id):
    msg = "💡 سوالات پر تکرار:\n"
    for key in FAQ.keys():
        msg += f"- {key}\n"
    msg += "\nلطفاً نام سوال را تایپ کنید تا پاسخ داده شود."
    send_message(patient_chat_id, msg)

# ----- دریافت پیام‌های چت و پردازش دستورات -----
def get_updates(offset=None):
    url = BASE_URL + "/getUpdates"
    params = {}
    if offset:
        params["offset"] = offset
    res = requests.get(url, params=params).json()
    return res["result"]

def process_updates():
    last_update_id = None
    
    while True:
        updates = get_updates(last_update_id)
        for update in updates:
            last_update_id = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            # ---- بررسی پاسخ بیمار به followup ----
            cur.execute("SELECT id, followup_waiting FROM appointments WHERE chat_id=? ORDER BY date DESC, time DESC LIMIT 1", (chat_id,))
            row = cur.fetchone()
            if row and row[1] == 1:
                ap_id = row[0]
                # ارسال پیام به تمام منشی‌ها / دکتر
                for staff_id in AUTHORIZED_USERS:
                    send_message(staff_id, f"پیام بیمار {chat_id}:\n{text}")
                # اطلاع به بیمار
                send_message(chat_id, "✅ پیام شما برای منشی ارسال شد.")
                # بروزرسانی دیتابیس
                cur.execute("UPDATE appointments SET followup_waiting=0 WHERE id=?", (ap_id,))
                conn.commit()
            if text.startswith("/add"):
                parts = text.split()
                if len(parts) == 4:
                    name, date_, hour_ = parts[1], parts[2], parts[3]
                    add_appointment(name, date_, hour_, chat_id, chat_id)
            elif text.startswith("/booktime"):
                try:
                    parts = text.split()  # جدا کردن دستور و پارامترها
                    if len(parts) != 3:  # باید سه قسمت باشه: /booktime YYYY-MM-DD HH:MM
                        send_message(chat_id, "❌ فرمت اشتباه است. مثال صحیح:\n/booktime 2026-02-06 10:00")
                    else:
                        date_ = parts[1]
                        hour_ = parts[2]
                        book_time(chat_id, date_, hour_)  # اجرای تابع ثبت نوبت
                except Exception as e:
                    send_message(chat_id, f"خطا: {e}")
            
            elif text.startswith("/book"):
                try:
                    parts = text.split()
                    if len(parts) != 2:
                        send_message(chat_id, "❌ فرمت اشتباه است. مثال صحیح:\n/book 2026-02-06")
                    else:
                        date_ = parts[1]
                        book_day(chat_id, date_)
                except Exception as e:
                    send_message(chat_id, f"خطا: {e}")


            
            elif text.startswith("/cancel"):
                cancel_appointment(chat_id)
            elif text.startswith("/rescheduletime"):
                try:
                    parts = text.split()
                    if len(parts) != 3:
                        send_message(chat_id, "❌ فرمت اشتباه است. مثال صحیح:\n/rescheduletime 2026-02-06 10:00")
                    else:
                        date_ = parts[1]
                        new_time = parts[2]
                        reschedule_time(chat_id, date_, new_time)
                except Exception as e:
                    send_message(chat_id, f"خطا: {e}")
            elif text.startswith("/reschedule"):
                try:
                    parts = text.split()
                    if len(parts) != 2:
                        send_message(chat_id, "❌ فرمت اشتباه است. مثال صحیح:\n/reschedule 2026-02-06")
                    else:
                        date_ = parts[1]
                        reschedule_appointment(chat_id, date_)
                except Exception as e:
                    send_message(chat_id, f"خطا: {e}")        
            elif text.startswith("/report"):
                parts = text.split()
                period = parts[1] if len(parts)>1 else "weekly"
                report(chat_id, period)

            elif text.startswith("/patientsday"):
                if chat_id not in AUTHORIZED_USERS:
                    send_message(chat_id, "❌ فقط دکتر یا منشی دسترسی دارند.")
                    return

                parts = text.split()
                if len(parts) != 2:
                    send_message(chat_id, "فرمت درست:\n/patientsday YYYY-MM-DD")
                    return

                date_ = parts[1]

                cur.execute(
                    "SELECT name, time FROM appointments WHERE date=? ORDER BY time",
                    (date_,)
                )
                rows = cur.fetchall()

                if not rows:
                    send_message(chat_id, f"هیچ نوبتی برای {date_} ثبت نشده ❌")
                else:
                    msg = f"📋 نوبت‌های روز {date_}:\n\n"
                    for name, time_ in rows:
                        msg += f"⏰ {time_} — {name}\n"

                    send_message(chat_id, msg)    
            elif text.startswith("/patients"):
                list_patients(chat_id)
            elif text.startswith("/myid"):
                send_message(chat_id, f"Chat ID شما: {chat_id}")

            elif text.startswith("/admin_reschedule"):
                _, name, date_, old_time, new_time = text.split()
                admin_reschedule(chat_id, name, date_, old_time, new_time)
            elif text.startswith("/admin_reschedule"):
                _, name, date_, old_time, new_time = text.split()
                admin_reschedule(chat_id, name, date_, old_time, new_time)
                
            elif text.startswith("/admin_move"):
                _, name, old_date, old_time, new_date, new_time = text.split()
                admin_move(chat_id, name, old_date, old_time, new_date, new_time)                
            elif text.startswith("/admin_move"):
                _, name, old_date, old_time, new_date, new_time = text.split()
                admin_move(chat_id, name, old_date, old_time, new_date, new_time)   

            elif text.startswith("/start"):
                start_message(chat_id)
            elif text.startswith("/today"):
                today_schedule(chat_id)
            elif text.startswith("/faq"):
                faq_message(chat_id)
            elif text in FAQ:
                send_message(chat_id, FAQ[text])
            
            elif text.startswith("/message"):
                if chat_id not in AUTHORIZED_USERS:
                    send_message(chat_id, "❌ شما اجازه ارسال پیام ندارید.")
                else:
                    try:
                        parts = text.split(maxsplit=2)
                        if len(parts) < 3:
                            send_message(chat_id, "❌ فرمت اشتباه. مثال:\n/message 1984139551 سلام! حالتان چطور است؟")
                        else:
                            patient_chat_id = int(parts[1])
                            msg = parts[2]
                            send_message(patient_chat_id, f"پیام منشی:\n{msg}")
                            send_message(chat_id, "✅ پیام شما ارسال شد.")
                    except Exception as e:
                        send_message(chat_id, f"خطا: {e}")                                       
        auto_reminders()
        time.sleep(5)

# ----- اجرای بات -----
if __name__ == "__main__":
    print("🤖 بات دندان پزشکی در حال اجراست...")
    process_updates()

