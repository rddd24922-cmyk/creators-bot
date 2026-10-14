import sqlite3
import re
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ================= إعدادات البوت =================
TOKEN = "8502001864:AAG9DfNx1s_U3tSpMXaUVsTF2WGAhIklLjk"  # التوكن الخاص بك
ADMIN_GROUP_ID = -1003968149974  # معرف مجموعة المشرفين الخاصة بك

MAX_VIDEOS_PER_MONTH = 5      # الحد الأقصى للمقاطع المسموح بها لكل صانع شهرياً

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= لوحة الأزرار (Keyboards) =================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 إرسال مقطع جديد")],
        [KeyboardButton(text="📊 مقاطعي هذا الشهر"), KeyboardButton(text="👤 حسابي المعرّف")]
    ],
    resize_keyboard=True
)

# ================= إعداد قاعدة البيانات الدائمة =================
def init_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            game_id TEXT,
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

# ================= الحالات (FSM) =================
class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_video_url = State()
    waiting_for_views = State()

# ================= أمر معرف المجموعة /myid =================
@dp.message(Command("myid"))
async def get_group_id(message: types.Message):
    chat_id = message.chat.id
    chat_title = message.chat.title or "خاص"
    await message.answer(
        f"📌 **معلومات المحادثة الحالية:**\n\n"
        f"🏷 اسم المحادثة: {chat_title}\n"
        f"🆔 معرف المحادثة (Chat ID): `{chat_id}`",
        parse_mode="Markdown"
    )

# ================= أمر البداية /start =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(
            f"أهلاً بك مجدداً! 🎬\nمعرّفك المسجل لدينا: `{user[0]}`\nاختر من القائمة أدناه ما تريد القيام به:",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
    else
