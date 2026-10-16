import sqlite3
import re
import logging
import os
import asyncio
import calendar
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = -1003968149974
MAX_VIDEOS_PER_MONTH = 60

ADMIN_IDS = [ADMIN_GROUP_ID, 556767982]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "creators_bot.db")

def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            telegram_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            game_id TEXT UNIQUE,
            registered_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            video_url TEXT UNIQUE,
            views INTEGER DEFAULT 0,
            submission_month TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def is_allowed(telegram_id: int) -> bool:
    if telegram_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM whitelist WHERE telegram_id = ?", (telegram_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def clean_old_submissions():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    expiry_date = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM submissions WHERE created_at < ?", (expiry_date,))
    conn.commit()
    conn.close()

class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_update_game_id = State()
    waiting_for_video_url = State()
    waiting_for_views = State()

def calculate_rank(views, videos_count):
    if views >= 2000000 and videos_count >= 60:
        return "👑 إمبراطور (مكافأة 24,000 صدفة + تأهل لجائزة طماطم بلس)"
    elif views >= 1000000 and videos_count >= 20:
        return "💎 أيقونة (مكافأة 20,000 صدفة)"
    elif views >= 500000 and videos_count >= 20:
        return "🏆 أسطورة (مكافأة 16,000 صدفة)"
    elif views >= 100000 and videos_count >= 20:
        return "⚡ سلطان (مكافأة 13,000 صدفة)"
    elif views >= 50000 and videos_count >= 20:
        return "🔥 زعيم (مكافأة 9,000 صدفة)"
    elif views >= 15000 and videos_count >= 15:
        return "🎖 قائد (مكافأة 6,000 صدفة)"
    elif views >= 5000 and videos_count >= 12:
        return "⭐ فارس (مكافأة 3,500 صدفة)"
    elif views >= 1500 and videos_count >= 8:
        return "⚔️ محارب (مكافأة 2,000 صدفة)"
    elif views >= 150 and videos_count >= 5:
        return "🛡️ مجند (مكافأة 800 صدفة)"
    elif views >= 50 and videos_count >= 1:
        return "🌱 مبتدئ (مكافأة 200 صدفة)"
    else:
        return "📌 مرشح (لم يستوفِ الحد الأدنى من شروط الرتب)"

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="إرسال مقطع جديد")],
        [KeyboardButton(text="مقاطعي هذا الشهر"), KeyboardButton(text="حسابي المعرّف")],
        [KeyboardButton(text="تعديل المعرّف")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="إلغاء")]
    ],
    resize_keyboard=True
)

async def report_scheduler():
    last_monthly_report_month = ""
    while True:
        clean_old_submissions()
        now = datetime.now()
        current_month_str = now.strftime("%Y-%m")
        
        last_day_of_month = calendar.monthrange(now.year, now.month)[1]
        
        if now.day == last_day_of_month and now.hour == 23 and now.minute == 30:
            if last_monthly_report_month != current_month_str:
                if ADMIN_GROUP_ID != 0:
                    conn = sqlite3.connect(get_db_path())
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id
                        FROM users u
                        LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = ?
                        GROUP BY u.telegram_id
                    """, (current_month_str,))
                    creators = cursor.fetchall()
                    conn.close()
                    
                    if creators:
                        monthly_text = f"🏆 **التقرير الشهري الختامي لصناع المحتوى (شهر {current_month_str}):**\n\n"
                        for idx, c in enumerate(creators, 1):
                            v_count = c[1] or 0
                            v_views = c[2] or 0
                            telegram_id = c[3]
                            rank = calculate_rank(v_views, v_count)
                            monthly_text += f"{idx}. 🎮 Game ID: `{c[0]}` | 🆔 Telegram ID: `{telegram_id}`\n   📹 عدد المقاطع: **{v_count}**\n   👁 إجمالي المشاهدات: **{v_views:,}**\n   🎖 الرتبة المستحقة: {rank}\n\n"
                        try:
                            await bot.send_message(ADMIN_GROUP_ID, monthly_text, parse_mode="Markdown")
                            last_monthly_report_month = current_month_str
                        except Exception as e:
                            logging.error(f"Failed to send monthly report: {e}")

        if now.day == (last_day_of_month - 2) and now.hour == 12 and now.minute == 0:
            if ADMIN_GROUP_ID != 0:
                try:
                    await bot.send_message(ADMIN_GROUP_ID, "⚠️ تنبيه: بقي يومان على إغلاق استقبال المقاطع ونهاية الشهر.")
                except Exception as e:
                    logging.error(f"Error: {e}")

        if now.hour == 23 and now.minute == 59:
            if ADMIN_GROUP_ID != 0:
                today_date = now.strftime("%Y-%m-%d")
                conn = sqlite3.connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute("SELECT u.game_id, s.video_url, s.views, s.created_at, u.telegram_id FROM submissions s LEFT JOIN users u ON s.telegram_id = u.telegram_id WHERE DATE(s.created_at) = ?", (today_date,))
                rows = cursor.fetchall()
                conn.close()
                
                if rows:
                    report_text = f"📊 التقرير اليومي ({today_date}):\n\n"
                    for idx, row in enumerate(rows, 1):
                        report_text += f"{idx}. Game ID: {row[0] or 'غير معروف'} | Telegram ID: {row[4] or 'غير معروف'}\nالرابط: {row[1]}\nالمشاهدات: {row[2]:,}\n\n"
                    try:
                        await bot.send_message(ADMIN_GROUP_ID, report_text, disable_web_page_preview=True)
                    except Exception as e:
                        logging.error(f"Error: {e}")
                        
        await asyncio.sleep(60)

@dp.message(Command("report"))
async def send_immediate_report(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    current_month_str = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id
        FROM users u
        LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = ?
        GROUP BY u.telegram_id
    """, (current_month_str,))
    creators = cursor.fetchall()
    conn.close()
    
    if not creators:
        await message.answer(f"⚠️ لا توجد بيانات مسجلة لشهر {current_month_str} حتى الآن.")
        return
        
    report_text = f"⚡ **تقرير فوري لشهر {current_month_str}:**\n\n"
    for idx, c in enumerate(creators, 1):
        v_count = c[1] or 0
        v_views = c[2] or 0
        telegram_id = c[3]
        rank = calculate_rank() 
