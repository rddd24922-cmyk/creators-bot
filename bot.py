
import sqlite3
import re
import logging
import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ================= إعدادات البوت =================
TOKEN = "8502001864:AAG9DfNx1s_U3tSpMXaUVsTF2WGAhIklLjk"
ADMIN_GROUP_ID = -1003968149974

MAX_VIDEOS_PER_MONTH = 5

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= لوحة الأزرار =================
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 إرسال مقطع جديد")],
        [KeyboardButton(text="📊 مقاطعي هذا الشهر"), KeyboardButton(text="👤 حسابي المعرّف")]
    ],
    resize_keyboard=True
)

# ================= قاعدة البيانات المحمية =================
def init_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # جدول المستخدمين: ربط حصري بين telegram_id و game_id
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

class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_video_url = State()
    waiting_for_views = State()

# ================= مهمة التقرير اليومي (11:59 PM) =================
async def daily_report_scheduler():
    while True:
        now = datetime.now()
        target_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        
        if now >= target_time:
            target_time = target_time.replace(day=target_time.day + 1)
            
        wait_seconds = (target_time - datetime.now()).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        if ADMIN_GROUP_ID != 0:
            today_date = datetime.now().strftime("%Y-%m-%d")
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT u.game_id, s.video_url, s.views, s.created_at 
                FROM submissions s 
                LEFT JOIN users u ON s.telegram_id = u.telegram_id 
                WHERE DATE(s.created_at) = ?
            """, (today_date,))
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                report_text = f"📊 **التقرير اليومي الشامل للمقاطع المسجلة ({today_date}):**\n\n"
                for idx, row in enumerate(rows, 1):
                    g_id = row[0] or "غير معروف"
                    v_url = row[1]
                    v_views = row[2]
                    v_time = row[3]
                    report_text += f"{idx}. 🎮 Game ID: `{g_id}`\n   🔗 الرابط: {v_url}\n   👁 المشاهدات: **{v_views:,}**\n   🗓 الوقت: {v_time}\n\n"
                
                try:
                    await bot.send_message(ADMIN_GROUP_ID, report_text, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception as e:
                    logging.error(f"Failed to send daily report: {e}")
            else:
                try:
                    await bot.send_message(ADMIN_GROUP_ID, f"📊 **التقرير اليومي ({today_date}):**\nلم يتم تسجيل أي مقاطع جديدة اليوم.", parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Failed to send empty daily report: {e}")
        
        await asyncio.sleep(60)

# ================= الأوامر والإصلاح الذاتي =================
@dp.message(Command("cancel", "reset", "fix"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 **تم فك التعليق بنجاح!** البوت جاهز للاستخدام.", reply_markup=main_keyboard, parse_mode="Markdown")

@dp.message(Command("myid"))
async def get_group_id(message: types.Message, state: FSMContext):
    await state.clear()
    chat_id = message.chat.id
    chat_title = message.chat.title or "خاص"
    await message.answer(f"🆔 معرف المحادثة (Chat ID): `{chat_id}`", parse_mode="Markdown")

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
            f"أهلاً بك مجدداً! 🎬\nمعرّفك المسجل بحسابك: `{user[0]}`\nاختر من القائمة أدناه:",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer("أهلاً بك في بوت برنامج صناع المحتوى! 🚀\nيرجى إرسال **معرّف اللاعب (Game ID)** الخاص بك للبدء:")
        await state.set_state(Form.waiting_for_game_id)

# ================= حماية ضد سرقة وتسجيل Game ID الخاص بالآخرين =================
@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # محاولة حفظ الربط الحصري
        cursor.execute(
            "INSERT INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, ?)",
            (telegram_id, game_id, now)
        )
        conn.commit()
        await state.clear()
        await message.answer(f"✅ تم ربط حسابك حصرياً بمعرّف اللعبة: `{game_id}` بنجاح!", reply_markup=main_keyboard, parse_mode="Markdown")
    except sqlite3.IntegrityError:
        # إذا كان المعرّف مسجلاً مسبقاً بحساب تيليجرام آخر
        cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (game_id,))
        owner = cursor.fetchone()
        
        if owner and owner[0] == telegram_id:
            # إذا كان المستخدم الحالي هو نفسه المالك مسجلاً مسبقاً
            await state.clear()
            await message.answer(f"✅ أنت مسجل مسبقاً بهذا المعرّف: `{game_id}`", reply_markup=main_keyboard, parse_mode="Markdown")
        else:
            # محاولة تخريب من شخص آخر!
            await message.answer("❌ **عذراً، هذا المعرّف (Game ID) مسجل مسبقاً بحساب صانع محتوى آخر ولا يمكن استخدامه!**\nإذا كان هذا معرّفك الحقيقي وحصل خطأ، تواصل مع المشرفين.", reply_markup=main_keyboard, parse_mode="Markdown")
            await state.clear()
    finally:
        conn.close()

@dp.message(F.text == "📤 إرسال مقطع جديد")
async def start_submission(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # التأكد أن المستخدم مسجل ولديه Game ID أصلاً
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        await message.answer("⚠️ أنت غير مسجل في النظام! يرجى إرسال /start لتسجيل معرّف اللعبة الخاص بك أولاً.")
        return

    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    count = cursor.fetchone()[0]
    conn.close()
    
    if count >= MAX_VIDEOS_PER_MONTH:
        await message.answer(f"⚠️ وصلت للحد الأقصى لهذا الشهر ({MAX_VIDEOS_PER_MONTH} مقاطع).", reply_markup=main_keyboard)
        return

    await message.answer(f"يرجى إرسال رابط المقطع (TikTok / YouTube / Instagram).\nالمتبقي لك هذا الشهر: {MAX_VIDEOS_PER_MONTH - count} مقاطع.")
    await state.set_state(Form.waiting_for_video_url)

URL_PATTERN = r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|youtube\.com|youtu\.be|instagram\.com)/.+)"

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not re.match(URL_PATTERN, text):
        await message.answer("❌ الرابط غير صالح! أرسل رابط صحيح أو /cancel للإلغاء.")
        return

    if datetime.now().day > 28:
        await state.clear()
        await message.answer("⏳ عذراً، تم إغلاق استقبال المقاطع لهذا الشهر.", reply_markup=main_keyboard)
        return

    await state.update_data(video_url=text)
    await message.answer("📊 ممتاز! الآن أرسل **عدد المشاهدات** الحالية للمقطع (أرقام فقط):")
    await state.set_state(Form.waiting_for_views)

@dp.message(Form.waiting_for_views)
async def process_video_views(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ يرجى إرسال أرقام صحيحة فقط للمشاهدات أو /cancel للإلغاء:")
        return

    views = int(text)
    data = await state.get_data()
    video_url = data.get("video_url")
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO submissions (telegram_id, video_url, views, submission_month, created_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, video_url, views, current_month, now)
        )
        conn.commit()
        await message.answer(f"🎉 تم تسجيل مقطعك وعدد المشاهدات ({views:,}) بنجاح! سيتم إدراجه في التقرير اليومي.", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الرابط تم تسجيله مسبقاً في النظام!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

@dp.message(F.text == "📊 مقاطعي هذا الشهر")
async def show_my_submissions(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    rows = cursor.fetchall()
    
    cursor.execute("SELECT SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    total_views = cursor.fetchone()[0] or 0
    conn.close()
    
    if not rows:
        await message.answer(f"لم تقم بإرسال أي مقاطع لشهر {current_month} حتى الآن.", reply_markup=main_keyboard)
        return

    res = f"🎬 **مقاطعك المسجلة لشهر {current_month}:**\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\n👁 المشاهدات: **{row[1]:,}**\n🗓 {row[2]}\n\n"
    
    res += f"━━━━━━━━━━━━━━━━━━━\n📈 **إجمالي المشاهدات هذا الشهر: {total_views:,} مشاهدة**"
    await message.answer(res, disable_web_page_preview=True, parse_mode="Markdown", reply_markup=main_keyboard)

@dp.message(F.text == "👤 حسابي المعرّف")
async def show_my_account(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        await message.answer(f"معرّف اللعبة المسجل بحسابك هو: `{user[0]}`", parse_mode="Markdown", reply_markup=main_keyboard)
    else:
        await message.answer("غير مسجل لدينا، يرجى إرسال /start للتسجيل.", reply_markup=main_keyboard)

async def main():
    asyncio.create_task(daily_report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
