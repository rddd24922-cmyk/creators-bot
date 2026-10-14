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
# قراءة التوكن ومعرف الأدمن من إعدادات المنصة أماناً، أو يمكنك وضعها مباشرة هنا
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")  
ADMIN_ID = int(os.getenv("ADMIN_ID", 123456789))          

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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            video_url TEXT UNIQUE,
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

# ================= أمر البداية /start =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
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

# ================= استقبال واستحواذ رابط الفيديو =================
URL_PATTERN = r"(https?://(?:www\.)?(tiktok\.com|youtube\.com|youtu\.be|instagram\.com)/.+)"

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    text = message.text.strip()
    
    if not re.match(URL_PATTERN, text):
        await message.answer("❌ الرابط غير صالح! أرسل رابط صحيح من (TikTok, YouTube, Instagram).")
        return

    if datetime.now().day > 28:
        await state.clear()
        await message.answer("⏳ عذراً، تم إغلاق استقبال المقاطع لهذا الشهر (يتم الإغلاق يوم 28).")
        return

    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO submissions (telegram_id, video_url, submission_month, created_at) VALUES (?, ?, ?, ?)",
            (telegram_id, text, current_month, now)
        )
        conn.commit()
        await message.answer("🎉 تم تسجيل وتوثيق مقطعك بنجاح!", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الرابط تم تسجيله مسبقاً في النظام!")
    finally:
        conn.close()

# ================= استعراض المقاطع والبيانات الشخصية =================
@dp.message(F.text == "📊 مقاطعي هذا الشهر")
async def show_my_submissions(message: types.Message):
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT video_url, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?",
        (telegram_id, current_month)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("لم تقم بإرسال أي مقاطع هذا الشهر حتى الآن.")
        return

    res = f"🎬 **مقاطعك المسجلة لشهر {current_month}:**\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\n🗓 {row[1]}\n\n"
    
    await message.answer(res, disable_web_page_preview=True, parse_mode="Markdown")

@dp.message(F.text == "👤 حسابي المعرّف")
async def show_my_account(message: types.Message):
    telegram_id = message.from_user.id
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(f"معرّف اللعبة المسجل بحسابك هو: `{user[0]}`", parse_mode="Markdown")
    else:
        await message.answer("غير مسجل لدينا، يرجى إرسال /start للتسجيل.")

# ================= إحصائيات الأدمن =================
@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect("creators_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE submission_month = ?", (current_month,))
    total_videos = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"📈 **إحصائيات النظام:**\n\n"
        f"👥 إجمالي صناع المحتوى المسجلين: {total_users}\n"
        f"🎥 المقاطع المرفوعة هذا الشهر ({current_month}): {total_videos}",
        parse_mode="Markdown"
    )

# ================= تشغيل البوت =================
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
