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

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = -1003968149974
MAX_VIDEOS_PER_MONTH = 60

# تمت إضافة رقمك التعريفي (556767982) ومجموعة الإدارة لصلاحيات كاملة فورية
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
    expiry_date = (datetime.now() - timedelta(days=33)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM submissions WHERE created_at < ?", (expiry_date,))
    conn.commit()
    conn.close()

class Form(StatesGroup):
    waiting_for_game_id = State()
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
        [KeyboardButton(text="📤 إرسال مقطع جديد")],
        [KeyboardButton(text="📊 مقاطعي هذا الشهر"), KeyboardButton(text="👤 حسابي المعرّف")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❌ إلغاء / كنسل")]
    ],
    resize_keyboard=True
)

async def daily_report_scheduler():
    while True:
        clean_old_submissions()
        now = datetime.now()
        
        if now.day == 27 and now.hour == 12 and now.minute == 0:
            if ADMIN_GROUP_ID != 0:
                try:
                    await bot.send_message(
                        ADMIN_GROUP_ID, 
                        "⚠️ **تنبيه إداري تلقائي:** بقي يومان على إغلاق استقبال المقاطع (يوم 28). نذكر الجميع بأن حذف الفيديوهات ممنوع تماماً ويؤدي للاستبعاد!"
                    )
                except Exception as e:
                    logging.error(f"Error sending alert: {e}")

        target_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if now >= target_time:
            target_time = target_time.replace(day=target_time.day + 1)
            
        wait_seconds = (target_time - datetime.now()).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        if ADMIN_GROUP_ID != 0:
            today_date = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect(get_db_path())
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
                    report_text += f"{idx}. 🎮 Game ID: `{row[0] or 'غير معروف'}`\n   🔗 الرابط: {row[1]}\n   👁 المشاهدات: **{row[2]:,}**\n   🗓 الوقت: {row[3]}\n\n"
                try:
                    await bot.send_message(ADMIN_GROUP_ID, report_text, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception as e:
                    logging.error(f"Failed to send daily report: {e}")
            else:
                try:
                    await bot.send_message(ADMIN_GROUP_ID, f"📊 **التقرير اليومي ({today_date}):**\nلم يتم تسجيل أي مقاطع جديدة اليوم.", parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Failed to send empty report: {e}")
                    
        await asyncio.sleep(60)

@dp.message(Command("allow"))
async def allow_user(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("⚠️ **طريقة الاستخدام:**\n`/allow 123456789`", parse_mode="Markdown")
        return
        
    target_id = int(args[1].strip())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO whitelist (telegram_id, added_at) VALUES (?, ?)", (target_id, now))
        conn.commit()
        await message.answer(f"✅ **تمت إضافة الحساب `{target_id}` بنجاح!**", parse_mode="Markdown")
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الحساب مسموح له بالفعل مسبقاً.")
    finally:
        conn.close()

@dp.message(Command("unallow"))
async def unallow_user(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        return
    target_id = int(args[1].strip())
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelist WHERE telegram_id = ?", (target_id,))
    conn.commit()
    conn.close()
    await message.answer(f"🗑 **تم إزالة الحساب `{target_id}`.**", parse_mode="Markdown")

@dp.message(F.text.in_({"❌ إلغاء / كنسل", "إلغاء", "كنسل"}))
@dp.message(Command("cancel", "reset", "fix", "start"))
async def global_commands_handler(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    
    if not is_allowed(telegram_id):
        await message.answer("⛔ **عذراً، هذا البوت مخصص لصناع المحتوى المعتمدين فقط.**", parse_mode="Markdown")
        return
        
    await state.clear()
    
    if message.text and message.text.startswith("/start"):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            await message.answer(f"أهلاً بك مجدداً يا بطل أرض الشجعان! 🎬\nمعرّفك المسجل بحسابك: `{user[0]}`", reply_markup=main_keyboard, parse_mode="Markdown")
        else:
            await message.answer("أهلاً بك في بوت برنامج صناع المحتوى (أرض الشجعان)! 🚀\nيرجى إرسال **معرّف اللاعب (Game ID)** الخاص بك للبدء:", reply_markup=cancel_keyboard, parse_mode="Markdown")
            await state.set_state(Form.waiting_for_game_id)
    else:
        await message.answer("🔄 **تم إلغاء العملية وفك التعليق بنجاح!**", reply_markup=main_keyboard, parse_mode="Markdown")

@dp.message(Command("user"))
async def search_user_stats(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ **طريقة الاستخدام الصحيحة:**\nأرسل الأمر متبوعاً بمعرّف اللاعب (Game ID)، مثال:\n`/user 123456`", parse_mode="Markdown")
        return
    
    target_game_id = args[1].strip()
    current_month = datetime.now().strftime("%Y-%m")
    
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, registered_at FROM users WHERE game_id = ?", (target_game_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        conn.close()
        await message.answer(f"❌ لم يتم العثور على أي صانع محتوى مسجل بمعرّف اللعبة: `{target_game_id}`", parse_mode="Markdown")
        return
        
    telegram_id = user_info[0]
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    submissions = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    stats = cursor.fetchone()
    conn.close()
    
    v_count, total_views = stats[0] or 0, stats[1] or 0
    rank = calculate_rank(total_views, v_count)
    
    report = f"👤 **تقرير إنجازات صانع المحتوى ({target_game_id}):**\n"
    report += f"🎮 Game ID: `{target_game_id}`\n"
    report += f"📈 مشاهدات هذا الشهر ({current_month}): **{total_views:,}** 👁\n"
    report += f"📹 عدد المقاطع المرفوعة: **{v_count}**\n"
    report += f"🎖 الرتبة المستحقة: **{rank}**\n"
    report += f"━━━━━━━━━━━━━━━━━━━\n"
    
    if submissions:
        report += "🎬 **سجل المقاطع المرفوعة:**\n\n"
        for idx, sub in enumerate(submissions, 1):
            report += f"{idx}. {sub[0]}\n   👁 المشاهدات: **{sub[1]:,}** | 🗓 {sub[2]}\n\n"
    else:
        report += "لم يقم برفع أي مقاطع لهذا الشهر حتى الآن."

    await message.answer(report, parse_mode="Markdown", disable_web_page_preview=True)

@dp.message(Command("myid"))
async def get_group_id(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"🆔 معرف المحادثة (Chat ID): `{message.chat.id}`\n🆔 معرف حسابك (Telegram ID): `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(Command("admin_stats"))
async def admin_stats_handler(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.game_id, COUNT(s.id), SUM(s.views)
        FROM users u
        LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = ?
        GROUP BY u.telegram_id
    """, (current_month,))
    creators = cursor.fetchall()
    conn.close()
    
    if not creators:
        await message.answer(f"📊 لا توجد أي بيانات مسجلة لصناع المحتوى لشهر {current_month} حتى الآن.")
        return

    text = f"👑 **تقرير رتب وإحصائيات صناع المحتوى لشهر {current_month}:**\n\n"
    for idx, c in enumerate(creators, 1):
        v_count, v_views = c[1] or 0, c[2] or 0
        text += f"{idx}.
