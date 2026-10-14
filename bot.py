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
ADMIN_ID = 0  # استبدلها بمعرف التيليجرام الخاص بك إن أردت

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

# ================= إعداد قاعدة البيانات =================
def init_db():
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            game_id TEXT,
            registered_at TEXT
        )
    """)
    
    # تحديث الجدول ليشمل حقل المشاهدات (views)
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
    waiting_for_views = State() # حالة جديدة بانتظار إدخال المشاهدات

# ================= أمر البداية /start =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    conn = sqlite3.connect("creators_bot.db")
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
    else:
        await message.answer("أهلاً بك في بوت برنامج صناع المحتوى! 🚀\nيرجى إرسال **معرّف اللاعب (Game ID)** الخاص بك داخل اللعبة للبدء:")
        await state.set_state(Form.waiting_for_game_id)

# ================= حفظ معرف اللعبة =================
@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, ?)",
                   (telegram_id, game_id, now))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(
        f"✅ تم ربط حسابك بنجاح بمعرّف اللعبة: `{game_id}`",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

# ================= زر إرسال مقطع جديد =================
@dp.message(F.text == "📤 إرسال مقطع جديد")
async def start_submission(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE telegram_id = ? AND submission_month = ?",
        (telegram_id, current_month)
    )
    count = cursor.fetchone()[0]
    conn.close()
    
    if count >= MAX_VIDEOS_PER_MONTH:
        await message.answer(f"⚠️ وصلت للحد الأقصى المسموح به لهذا الشهر وهو ({MAX_VIDEOS_PER_MONTH}) مقاطع.")
        return

    await message.answer(f"يرجى إرسال رابط المقطع الآن (TikTok / YouTube / Instagram).\nالمتبقي لك هذا الشهر: {MAX_VIDEOS_PER_MONTH - count} مقاطع.")
    await state.set_state(Form.waiting_for_video_url)

# ================= استقبال رابط الفيديو ثم طلب المشاهدات =================
URL_PATTERN = r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|youtube\.com|youtu\.be|instagram\.com)/.+)"

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if not re.match(URL_PATTERN, text):
        await message.answer("❌ الرابط غير صالح! أرسل رابط صحيح من (TikTok, YouTube, Instagram).")
        return

    if datetime.now().day > 28:
        await state.clear()
        await message.answer("⏳ عذراً، تم إغلاق استقبال المقاطع لهذا الشهر (يتم الإغلاق يوم 28).")
        return

    # حفظ الرابط مؤقتاً في الذاكرة والانتقال لطلب المشاهدات
    await state.update_data(video_url=text)
    await message.answer("📊 ممتاز! الآن أرسل **عدد المشاهدات** الحالية للمقطع (أرقام فقط، مثال: 1500):")
    await state.set_state(Form.waiting_for_views)

# ================= استقبال عدد المشاهدات وحفظ المقطع نهائياً =================
@dp.message(Form.waiting_for_views)
async def process_video_views(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if not text.isdigit():
        await message.answer("❌ يرجى إرسال أرقام صحيحة فقط لعدد المشاهدات (مثال: 500):")
        return

    views = int(text)
    data = await state.get_data()
    video_url = data.get("video_url")
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO submissions (telegram_id, video_url, views, submission_month, created_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, video_url, views, current_month, now)
        )
        conn.commit()
        await message.answer(f"🎉 تم تسجيل مقطعك وعدد المشاهدات ({views}) بنجاح!", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الرابط تم تسجيله مسبقاً في النظام!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

# ================= استعراض المقاطع والبيانات الشخصية =================
@dp.message(F.text == "📊 مقاطعي هذا الشهر")
async def show_my_submissions(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?",
        (telegram_id, current_month)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("لم تقم بإرسال أي مقاطع هذا الشهر حتى الآن.", reply_markup=main_keyboard)
        return

    res = f"🎬 **مقاطعك المسجلة لشهر {current_month}:**\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\n👁 المشاهدات: **{row[1]}**\n🗓 {row[2]}\n\n"
    
    await message.answer(res, disable_web_page_preview=True, parse_mode="Markdown", reply_markup=main_keyboard)

@dp.message(F.text == "👤 حسابي المعرّف")
async def show_my_account(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(f"معرّف اللعبة المسجل بحسابك هو: `{user[0]}`", parse_mode="Markdown", reply_markup=main_keyboard)
    else:
        await message.answer("غير مسجل لدينا، يرجى إرسال /start للتسجيل.", reply_markup=main_keyboard)

# ================= تشغيل البوت =================
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
