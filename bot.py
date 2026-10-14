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

MAX_VIDEOS_PER_MONTH = 60  # تم رفع الحد لدعم رتبة الإمبراطور (حتى 60+ فيديو شهرياً)

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

# ================= قاعدة البيانات المحدثة =================
def init_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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

# ================= حساب الرتبة بناءً على الدليل =================
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
        return "📌 مرشح (لم يستوفِ الحد الأدنى بعد)"

# ================= مهمة التقرير اليومي التلقائي (11:59 PM) =================
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

# ================= أوامر المشرفين والإصلاح =================
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

# لوحة تقارير المشرفين الشاملة للشهر الحالي
@dp.message(Command("admin_stats"))
async def admin_stats_handler(message: types.Message, state: FSMContext):
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # جلب إحصائيات كل صانع محتوى لهذا الشهر
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
        g_id = c[0]
        v_count = c[1] or 0
        v_views = c[2] or 0
        rank = calculate_rank(v_views, v_count)
        text += f"{idx}. 🎮 Game ID: `{g_id}`\n   📹 عدد المقاطع: **{v_count}**\n   👁 إجمالي المشاهدات: **{v_views:,}**\n   🎖 الرتبة المقترحة: {rank}\n\n"

    await message.answer(text, parse_mode="Markdown")

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
            f"أهلاً بك مجدداً في برنامج صناع المحتوى! 🎬\nمعرّفك المسجل بحسابك: `{user[0]}`\nاختر من القائمة أدناه:",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer("أهلاً بك في بوت برنامج صناع المحتوى (أرض الشجعان)! 🚀\nيرجى إرسال **معرّف اللاعب (Game ID)** الخاص بك للبدء:")
        await state.set_state(Form.waiting_for_game_id)

@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creators_bot.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, ?)",
            (telegram_id, game_id, now)
        )
        conn.commit()
        await state.clear()
        await message.answer(f"✅ تم ربط حسابك حصرياً بمعرّف اللعبة: `{game_id}` بنجاح!", reply_markup=main_keyboard, parse_mode="Markdown")
    except sqlite3.IntegrityError:
        cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (game_id,))
        owner = cursor.fetchone()
        
        if owner and owner[0] == telegram_id:
            await state.clear()
            await message.answer(f"✅ أنت مسجل مسبقاً بهذا المعرّف: `{game_id}`", reply_markup=main_keyboard, parse_mode="Markdown")
        else:
            await message.answer("❌ **عذراً، هذا المعرّف (Game ID) مسجل مسبقاً بحساب صانع محتوى آخر!**", reply_markup=main_keyboard, parse_mode="Markdown")
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
    
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        await message.answer("⚠️ أنت غير مسجل في النظام! يرجى إرسال /start لتسجيل معرّف اللعبة أولاً.")
        return

    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    count = cursor.fetchone()[0]
    conn.close()
    
    if count >= MAX_VIDEOS_PER_MONTH:
        await message.answer(f"⚠️ وصلت للحد الأقصى لهذا الشهر.", reply_markup=main_keyboard)
        return

    await message.answer(f"يرجى إرسال رابط المقطع (TikTok / YouTube / Instagram / Facebook).\nالمقاطع المرسلة هذا الشهر: {count}")
    await state.set_state(Form.waiting_for_video_url)

URL_PATTERN = r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch)/.+)"

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
        
        # حساب الرتبة الحالية للصانع لتعريفه بها فورياً
        cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
        stats = cursor.fetchone()
        v_count = stats[0] or 1
        v_views = stats[1] or views
        current_rank = calculate_rank(v_views, v_count)
        
        await message.answer(f"🎉 تم تسجيل مقطعك بنجاح!\n📈 إجمالي مشاهداتك هذا الشهر: {v_views:,}\n🎖 رتبتك الحالية: {current_rank}", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("⚠️ هذا الرابط تم تسجيله مسبقاً في النظام ولا يمكن تكراره!", reply_markup=main_keyboard)
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
    
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    stats = cursor.fetchone()
    v_count = stats[0] or 0
    total_views = stats[1] or 0
    conn.close()
    
    current_rank = calculate_rank(total_views, v_count)

    if not rows:
        await message.answer(f"لم تقم بإرسال أي مقاطع لشهر {current_month} حتى الآن.", reply_markup=main_keyboard)
        return

    res = f"🎬 **مقاطعك المسجلة لشهر {current_month}:**\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\n👁 المشاهدات: **{row[1]:,}**\n🗓 {row[2]}\n\n"
    
    res += f"━━━━━━━━━━━━━━━━━━━\n📈 **إجمالي المشاهدات:** {total_views:,}\n📹 **عدد الفيديوهات:** {v_count}\n🎖 **رتبتك الحالية:** {current_rank}"
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
