import sqlite3
import re
import logging
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ================= إعدادات البوت =================
TOKEN = "8502001864:AAG9DfNx1s_U3tSpMXaUVsTF2WGAhIklLjk"
ADMIN_GROUP_ID = -1003968149974
MAX_VIDEOS_PER_MONTH = 60

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= مسار ثابت لقاعدة البيانات =================
def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")

def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # جدول المستخدمين: محفوظ بشكل دائم للأبد
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            game_id TEXT UNIQUE,
            registered_at TEXT
        )
    """)
    
    # جدول المقاطع: يتم تخزينها وتنظيف القديم منها تلقائياً
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

# ================= دالة تنظيف المقاطع الأقدم من 33 يوماً =================
def clean_old_submissions():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    expiry_date = (datetime.now() - timedelta(days=33)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM submissions WHERE created_at < ?", (expiry_date,))
    conn.commit()
    conn.close()

class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_video_url = State()
    waiting_for_views = State()

# ================= دالة حساب الرتب بناءً على دليل البرنامج =================
def calculate_rank(views, videos_count):
    if views >= 2000000 and videos_count >= 60:
        return "👑 إمبراطور (مكافأة 24,000 صدفة + تأهل لجائزة طماطم بلس)"
