import sqlite3
import re
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8502001864:AAG9DfNx1s_U3tSpMXaUVsTF2WGAhIklLjk"
ADMIN_GROUP_ID = -1003968149974

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")

def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, game_id TEXT UNIQUE, registered_at TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, video_url TEXT UNIQUE, views INTEGER DEFAULT 0, submission_month TEXT, created_at TEXT)")
    conn.commit()
    conn.close()

init_db()

class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_video_url = State()
    waiting_for_views = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 إرسال مقطع جديد")],
        [KeyboardButton(text="📊 مقاطعي هذا الشهر"), KeyboardButton(text="👤 حسابي المعرّف")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ إلغاء / كنسل")]],
    resize_keyboard=True
)

@dp.message(F.text == "❌ إلغاء / كنسل")
@dp.message(Command("cancel", "reset", "fix"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 تم إلغاء العملية وفك التعليق بنجاح!", reply_markup=main_keyboard)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(f"أهلاً بك مجدداً!\nمعرّفك المسجل: {user[0]}", reply_markup=main_keyboard)
    else:
        await message.answer("أهلاً بك! يرجى إرسال معرّف اللاعب (Game ID) الخاص بك للبدء:", reply_markup=cancel_keyboard)
        await state.set_state(Form.waiting_for_game_id)

@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, datetime('now'))", (telegram_id, game_id))
        conn.commit()
        await state.clear()
        await message.answer(f"✅ تم ربط حسابك بمعرّف اللعبة: {game_id}", reply_markup=main_keyboard)
    except sqlite3.IntegrityError:
        await message.answer("❌ عذراً، هذا المعرّف مسجل مسبقاً بحساب آخر!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

@dp.message(F.text == "📤 إرسال مقطع جديد")
async def start_submission(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await message.answer("⚠️ أنت غير مسجل! يرجى إرسال /start أولاً.")
        return

    await message.answer("يرجى إرسال رابط المقطع (TikTok / YouTube / Instagram / Facebook):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_video_url)

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    await state.update_data(video_url=message.text.strip())
    await message.answer("📊 ممتاز! الآن أرسل عدد المشاهدات الحالية (أرقام فقط):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_views)

@dp.message(Form.waiting_for_views)
async def process_video_views(message: types.Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ يرجى إرسال أرقام صحيحة فقط للمشاهدات:")
        return

    views = int(message.text.strip())
    data = await state.get_data()
    video_url = data.get("video_url")
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m") if 'datetime' in globals() else "2026-10"
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO submissions (telegram_id, video_url, views, submission_month, created_at) VALUES (?, ?, ?, ?, datetime('now'))", (telegram_id, video_url, views, current_month))
        conn.commit()
        await message.answer(f"🎉 تم تسجيل المقطع وعدد المشاهدات ({views:,}) بنجاح!", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الرابط مسجل مسبقاً!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

@dp.message(F.text == "👤 حسابي المعرّف")
async def show_my_account(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(f"معرّفك المسجل: {user[0]}", reply_markup=main_keyboard)
    else:
        await message.answer("غير مسجل لدينا، يرجى إرسال /start للتسجيل.", reply_markup=main_keyboard)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
