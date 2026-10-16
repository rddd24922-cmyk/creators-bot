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

# دالة خاصة بالتحقق من المشرفين الأساسيين فقط (لأوامر الإدارة الحصرية)
def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS

# دالة التحقق من صناع المحتوى المعتمدين (لإرسال المقاطع)
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

# أمر التقرير الفوري (للمشرفين فقط باستخدام is_admin)
@dp.message(Command("report"))
async def send_immediate_report(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
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
        rank = calculate_rank(v_views, v_count)
        report_text += f"{idx}. 🎮 Game ID: `{c[0]}` | 🆔 Telegram ID: `{telegram_id}`\n   📹 عدد المقاطع: **{v_count}**\n   👁 إجمالي المشاهدات: **{v_views:,}**\n   🎖 الرتبة المستحقة: {rank}\n\n"
    
    await message.answer(report_text, parse_mode="Markdown")

@dp.message(Command("allow"))
async def allow_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("⚠️ طريقة الاستخدام: /allow [Telegram_ID]")
        return
    target_id = int(args[1].strip())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO whitelist (telegram_id, added_at) VALUES (?, ?)", (target_id, now))
        conn.commit()
        await message.answer(f"✅ تمت إضافة الحساب {target_id} بنجاح.")
    except sqlite3.IntegrityError:
        await message.answer("⚠️ الحساب مضاف مسبقاً.")
    finally:
        conn.close()

@dp.message(Command("unallow"))
async def unallow_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        return
    target_id = int(args[1].strip())
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelist WHERE telegram_id = ?", (target_id,))
    conn.commit()
    conn.close()
    await message.answer(f"🗑 تم إزالة الحساب {target_id}.")

@dp.message(F.text.in_({"إلغاء", "كنسل"}))
@dp.message(Command("cancel", "reset", "fix", "start"))
async def global_commands_handler(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    if not is_allowed(telegram_id):
        await message.answer("⛔ عذراً، هذا البوت مخصص لصناع المحتوى المعتمدين فقط.")
        return
    await state.clear()
    if message.text and message.text.startswith("/start"):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            await message.answer(f"أهلاً بك مجدداً! معرّف اللعبة المسجل بحسابك: {user[0]}", reply_markup=main_keyboard)
        else:
            await message.answer("أهلاً بك! يرجى إرسال معرّف اللاعب (Game ID) الخاص بك للبدء:", reply_markup=cancel_keyboard)
            await state.set_state(Form.waiting_for_game_id)
    else:
        await message.answer("🔄 تم إلغاء العملية بنجاح.", reply_markup=main_keyboard)

# أمر البحث عن المستخدمين (/user) - محصور حصرياً للمشرفين الأساسيين فقط باستخدام is_admin
@dp.message(Command("user"))
async def search_user_stats(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ طريقة الاستخدام: /user [Game_ID]")
        return
    target_game_id = args[1].strip()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (target_game_id,))
    user_info = cursor.fetchone()
    if not user_info:
        conn.close()
        await message.answer(f"❌ لم يتم العثور على صانع محتوى بمعرّف اللعبة: {target_game_id}")
        return
    telegram_id = user_info[0]
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    submissions = cursor.fetchall()
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    stats = cursor.fetchone()
    conn.close()
    v_count, total_views = stats[0] or 0, stats[1] or 0
    rank = calculate_rank(total_views, v_count)
    report = f"👤 تقرير إنجازات صانع المحتوى ({target_game_id}):\n🆔 Telegram ID: `{telegram_id}`\nإجمالي المشاهدات: {total_views:,}\nعدد الفيديوهات: {v_count}\nالرتبة: {rank}\n\n"
    if submissions:
        report += "سجل المقاطع:\n"
        for idx, sub in enumerate(submissions, 1):
            report += f"{idx}. {sub[0]} - المشاهدات: {sub[1]:,}\n"
    else:
        report += "لا توجد مقاطع مرفوعة هذا الشهر."
    await message.answer(report, disable_web_page_preview=True, parse_mode="Markdown")

@dp.message(Command("myid"))
async def get_group_id(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"معرّف المحادثة (Chat ID): {message.chat.id}\nمعرّف حسابك (Telegram ID): {message.from_user.id}")

# إحصائيات المشرفين العامة (للمشرفين فقط باستخدام is_admin)
@dp.message(Command("admin_stats"))
async def admin_stats_handler(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id FROM users u LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = ? GROUP BY u.telegram_id", (current_month,))
    creators = cursor.fetchall()
    conn.close()
    if not creators:
        await message.answer(f"لا توجد بيانات لشهر {current_month}.")
        return
    text = f"📊 إحصائيات صناع المحتوى لشهر {current_month}:\n\n"
    for idx, c in enumerate(creators, 1):
        v_count, v_views = c[1] or 0, c[2] or 0
        t_id = c[3]
        text += f"{idx}. Game ID: {c[0]} | Telegram ID: `{t_id}` | الفيديوهات: {v_count} | المشاهدات: {v_views:,} | الرتبة: {calculate_rank(v_views, v_count)}\n"
    await message.answer(text, parse_mode="Markdown")

# ملخص المشرفين العام (للمشرفين فقط باستخدام is_admin)
@dp.message(Command("admin_summary"))
async def admin_summary_handler(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(views), COUNT(id) FROM submissions WHERE submission_month = ?", (current_month,))
    total_stats = cursor.fetchone()
    total_views = total_stats[0] or 0
    total_videos = total_stats[1] or 0
    cursor.execute("SELECT u.game_id, SUM(s.views) as total_v, COUNT(s.id) as v_count FROM users u JOIN submissions s ON u.telegram_id = s.telegram_id WHERE s.submission_month = ? GROUP BY u.telegram_id ORDER BY total_v DESC LIMIT 10", (current_month,))
    top_creators = cursor.fetchall()
    conn.close()
    summary_text = f"📈 الملخص العام لشهر {current_month}:\nإجمالي المشاهدات: {total_views:,}\nإجمالي الفيديوهات: {total_videos}\n\n🏆 أفضل صناع المحتوى:\n"
    if not top_creators:
        summary_text += "لا توجد مشاهدات مسجلة."
    else:
        for idx, creator in enumerate(top_creators, 1):
            summary_text += f"{idx}. Game ID: {creator[0]} - المشاهدات: {creator[1]:,}\n"
    await message.answer(summary_text)

@dp.message(F.text.contains("مقاطعي هذا الشهر"))
async def show_my_submissions(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    stats = cursor.fetchone()
    conn.close()
    v_count, total_views = stats[0] or 0, stats[1] or 0
    if not rows:
        await message.answer(f"لم تقم بإرسال أي مقاطع لشهر {current_month}.", reply_markup=main_keyboard)
        return
    res = f"🎬 مقاطعك المسجلة لشهر {current_month}:\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\nالمشاهدات: {row[1]:,} | {row[2]}\n\n"
    res += f"إجمالي المشاهدات: {total_views:,}\nعدد الفيديوهات: {v_count}\nرتبتك الحالية: {calculate_rank(total_views, v_count)}"
    await message.answer(res, disable_web_page_preview=True, reply_markup=main_keyboard)

@dp.message(F.text.contains("حسابي المعرّف"))
async def show_my_account(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        await message.answer(f"معرّف اللعبة المسجل بحسابك هو: {user[0]}", reply_markup=main_keyboard)
    else:
        await message.answer("غير مسجل لدينا، يرجى إرسال /start للتسجيل.", reply_markup=main_keyboard)

@dp.message(F.text.contains("تعديل المعرّف"))
async def start_update_game_id(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await message.answer("⚠️ أنت غير مسجل مسبقاً! أرسل /start لتسجيل معرفك لأول مرة.", reply_markup=main_keyboard)
        return
        
    await message.answer(f"معرّفك الحالي هو: `{user[0]}`\n\nيرجى إرسال **معرّف اللعبة (Game ID) الجديد** (أرقام فقط):", reply_markup=cancel_keyboard, parse_mode="Markdown")
    await state.set_state(Form.waiting_for_update_game_id)

@dp.message(Form.waiting_for_update_game_id)
async def process_update_game_id(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    new_game_id = message.text.strip()
    if not new_game_id.isdigit():
        await message.answer("❌ يرجى إرسال معرّف صحيح يتكون من أرقام فقط:", reply_markup=cancel_keyboard)
        return
        
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET game_id = ? WHERE telegram_id = ?", (new_game_id, telegram_id))
        conn.commit()
        await state.clear()
        await message.answer(f"✅ تم تحديث وتعديل معرّف اللعبة إلى: `{new_game_id}` بنجاح مع الاحتفاظ بكافة مقاطعك ومشاهداتك السابقة!", reply_markup=main_keyboard, parse_mode="Markdown")
    except sqlite3.IntegrityError:
        await message.answer("❌ **عذراً، هذا المعرّف مستخدم مسبقاً من قِبل صانع محتوى آخر!**", reply_markup=main_keyboard, parse_mode="Markdown")
        await state.clear()
    finally:
        conn.close()

@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    if not game_id.isdigit():
        await message.answer("يرجى إرسال معرّف لاعب صحيح يتكون من أرقام فقط:", reply_markup=cancel_keyboard)
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, ?)", (telegram_id, game_id, now))
        conn.commit()
        await state.clear()
        await message.answer(f"تم ربط حسابك بمعرّف اللعبة: {game_id} بنجاح!", reply_markup=main_keyboard)
    except sqlite3.IntegrityError:
        cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (game_id,))
        owner = cursor.fetchone()
        if owner and owner[0] == telegram_id:
            await state.clear()
            await message.answer(f"أنت مسجل مسبقاً بهذا المعرّف: {game_id}", reply_markup=main_keyboard)
        else:
            await message.answer("عذراً، هذا المعرّف مسجل بحساب صانع محتوى آخر.", reply_markup=main_keyboard)
            await state.clear()
    finally:
        conn.close()

@dp.message(F.text.contains("إرسال مقطع جديد"))
async def start_submission(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        await message.answer("أنت غير مسجل! أرسل /start أولاً.", reply_markup=main_keyboard)
        return
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    count = cursor.fetchone()[0]
    conn.close()
    if count >= MAX_VIDEOS_PER_MONTH:
        await message.answer("لقد وصلت للحد الأقصى من المقاطع لهذا الشهر.", reply_markup=main_keyboard)
        return
    await message.answer("يرجى إرسال رابط المقطع الآن (YouTube / TikTok / Instagram / Facebook):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_video_url)

URL_PATTERN = r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch)/\S+)"

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    text = message.text.strip()
    if not re.search(URL_PATTERN, text):
        await message.answer("الرابط غير صالح! يرجى إرسال رابط صحيح:", reply_markup=cancel_keyboard)
        return
    match = re.search(URL_PATTERN, text)
    clean_url = match.group(0) if match else text
    await state.update_data(video_url=clean_url)
    await message.answer("ممتاز! الآن أرسل عدد المشاهدات الحالية للمقطع (أرقام فقط):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_views)

@dp.message(Form.waiting_for_views)
async def process_video_views(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("يرجى إرسال أرقام صحيحة فقط للمشاهدات:", reply_markup=cancel_keyboard)
        return
    views = int(text)
    data = await state.get_data()
    video_url = data.get("video_url")
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO submissions (telegram_id, video_url, views, submission_month, created_at) VALUES (?, ?, ?, ?, ?)", (telegram_id, video_url, views, current_month, now))
        conn.commit()
        cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
        stats = cursor.fetchone()
        current_rank = calculate_rank(stats[1] or views, stats[0] or 1)
        await message.answer(f"تم تسجيل مقطعك بنجاح!\nإجمالي المشاهدات: {stats[1]:,}\nرتبتك الحالية: {current_rank}", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("هذا الرابط مسجل مسبقاً في النظام!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

async def main():
    asyncio.create_task(report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
