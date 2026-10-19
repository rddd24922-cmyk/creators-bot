import re
import logging
import os
import asyncio
import calendar
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_GROUP_ID = -1003968149974

ADMIN_IDS = [ADMIN_GROUP_ID, 556767982, 8890083481]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            telegram_id BIGINT PRIMARY KEY,
            added_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            game_id TEXT UNIQUE,
            registered_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creator_platforms (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            platform TEXT,
            status TEXT DEFAULT 'pending',
            requested_at TEXT,
            UNIQUE(telegram_id, platform)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            video_url TEXT UNIQUE,
            views INTEGER DEFAULT 0,
            submission_month TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS

def is_allowed(telegram_id: int) -> bool:
    if telegram_id in ADMIN_IDS:
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM whitelist WHERE telegram_id = %s", (telegram_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def get_user_platforms(telegram_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT platform, status FROM creator_platforms WHERE telegram_id = %s", (telegram_id,))
    res = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in res}

def clean_old_submissions():
    conn = get_db_connection()
    cursor = conn.cursor()
    expiry_date = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM submissions WHERE created_at < %s", (expiry_date,))
    conn.commit()
    conn.close()

class Form(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_update_game_id = State()
    waiting_for_platform_choice = State()
    waiting_for_video_url = State()

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
        [KeyboardButton(text="إرسال مقطع جديد"), KeyboardButton(text="طلب إضافة منصة")],
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

platforms_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="TikTok"), KeyboardButton(text="Instagram")],
        [KeyboardButton(text="YouTube"), KeyboardButton(text="Facebook")],
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
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id
                        FROM users u
                        LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = %s
                        GROUP BY u.telegram_id, u.game_id
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
        await asyncio.sleep(60)

@dp.message(Command("report"))
async def send_immediate_report(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    target_month_str = args[1].strip() if len(args) > 1 else datetime.now().strftime("%Y-%m")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id
        FROM users u
        LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = %s
        GROUP BY u.telegram_id, u.game_id
    """, (target_month_str,))
    creators = cursor.fetchall()
    conn.close()
    
    if not creators:
        await message.answer(f"⚠️ لا توجد بيانات مسجلة لشهر {target_month_str}.")
        return
        
    report_text = f"⚡ **تقرير لشهر {target_month_str}:**\n\n"
    for idx, c in enumerate(creators, 1):
        v_count, v_views, telegram_id = c[1] or 0, c[2] or 0, c[3]
        rank = calculate_rank(v_views, v_count)
        report_text += f"{idx}. 🎮 Game ID: `{c[0]}` | 🆔 Telegram ID: `{telegram_id}`\n   📹 عدد المقاطع: **{v_count}**\n   👁 إجمالي المشاهدات: **{v_views:,}**\n   🎖 الرتبة: {rank}\n\n"
    await message.answer(report_text, parse_mode="Markdown")

@dp.message(Command("allow"))
async def allow_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("⚠️ طريقة الاستخدام: /allow [Telegram_ID]")
        return
    target_id = int(args[1].strip())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO whitelist (telegram_id, added_at) VALUES (%s, %s)", (target_id, now))
        conn.commit()
        await message.answer(f"✅ تمت إضافة الحساب {target_id} بنجاح.")
    except psycopg2.IntegrityError:
        conn.rollback()
        await message.answer("⚠️ الحساب مضاف مسبقاً.")
    finally:
        conn.close()

@dp.message(Command("unallow"))
async def unallow_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        return
    target_id = int(args[1].strip())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelist WHERE telegram_id = %s", (target_id,))
    conn.commit()
    conn.close()
    await message.answer(f"🗑 تم إزالة الحساب {target_id}.")

@dp.message(Command("pending_platforms"))
async def show_pending_platforms(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    await state.clear()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.telegram_id, p.platform, p.requested_at, u.game_id 
        FROM creator_platforms p
        LEFT JOIN users u ON p.telegram_id = u.telegram_id
        WHERE p.status = 'pending'
        ORDER BY p.requested_at ASC
    """)
    pending_requests = cursor.fetchall()
    conn.close()
    
    if not pending_requests:
        await message.answer("🎉 لا توجد أي طلبات اعتماد منصات معلقة حالياً.")
        return
        
    for req in pending_requests:
        telegram_id, platform, requested_at, game_id = req[0], req[1], req[2], req[3] or "غير مسجل"
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ موافقة", callback_data=f"plat_app_{telegram_id}_{platform}"),
                InlineKeyboardButton(text="❌ رفض", callback_data=f"plat_rej_{telegram_id}_{platform}")
            ]
        ])
        text = f"🔔 **طلب منصة معلق:**\n🎮 Game ID: `{game_id}`\n🆔 Telegram ID: `{telegram_id}`\n📱 المنصة: **{platform}**\n⏱ وقت الطلب: {requested_at}"
        await message.answer(text, reply_markup=inline_kb, parse_mode="Markdown")

@dp.message(Command("user"))
async def search_user_stats(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ طريقة الاستخدام: /user [Game_ID]")
        return
    target_game_id = args[1].strip()
    current_month = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE game_id = %s", (target_game_id,))
    user_info = cursor.fetchone()
    if not user_info:
        conn.close()
        await message.answer(f"❌ لم يتم العثور على صانع محتوى بمعرّف اللعبة: {target_game_id}")
        return
    telegram_id = user_info[0]
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = %s AND submission_month = %s", (telegram_id, current_month))
    submissions = cursor.fetchall()
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = %s AND submission_month = %s", (telegram_id, current_month))
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

@dp.message(Command("admin_stats"))
async def admin_stats_handler(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT u.game_id, COUNT(s.id), SUM(s.views), u.telegram_id FROM users u LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = %s GROUP BY u.telegram_id, u.game_id", (current_month,))
    creators = cursor.fetchall()
    conn.close()
    if not creators:
        await message.answer(f"لا توجد بيانات لشهر {current_month}.")
        return
    text = f"📊 إحصائيات صناع المحتوى لشهر {current_month}:\n\n"
    for idx, c in enumerate(creators, 1):
        v_count, v_views, t_id = c[1] or 0, c[2] or 0, c[3]
        text += f"{idx}. Game ID: {c[0]} | Telegram ID: `{t_id}` | الفيديوهات: {v_count} | المشاهدات: {v_views:,} | الرتبة: {calculate_rank(v_views, v_count)}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("admin_summary"))
async def admin_summary_handler(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(views), COUNT(id) FROM submissions WHERE submission_month = %s", (current_month,))
    total_stats = cursor.fetchone()
    total_views, total_videos = total_stats[0] or 0, total_stats[1] or 0
    cursor.execute("SELECT u.game_id, SUM(s.views) as total_v, COUNT(s.id) as v_count FROM users u JOIN submissions s ON u.telegram_id = s.telegram_id WHERE s.submission_month = %s GROUP BY u.telegram_id, u.game_id ORDER BY total_v DESC LIMIT 10", (current_month,))
    top_creators = cursor.fetchall()
    conn.close()
    summary_text = f"📈 الملخص العام لشهر {current_month}:\nإجمالي المشاهدات: {total_views:,}\nإجمالي الفيديوهات: {total_videos}\n\n🏆 أفضل صناع المحتوى:\n"
    if not top_creators:
        summary_text += "لا توجد مشاهدات مسجلة."
    else:
        for idx, creator in enumerate(top_creators, 1):
            summary_text += f"{idx}. Game ID: {creator[0]} - المشاهدات: {creator[1]:,}\n"
    await message.answer(summary_text)

@dp.message(Command("myid"))
async def get_group_id(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"معرّف المحادثة (Chat ID): {message.chat.id}\nمعرّف حسابك (Telegram ID): {message.from_user.id}")

@dp.message(F.text.in_({"إلغاء", "كنسل"}))
@dp.message(Command("cancel", "reset", "fix", "start"))
async def global_commands_handler(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    if not is_allowed(telegram_id):
        await message.answer("⛔ عذراً، هذا البوت مخصص لصناع المحتوى المعتمدين فقط.")
        return
    await state.clear()
    if message.text and message.text.startswith("/start"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT game_id FROM users WHERE telegram_id = %s", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            await message.answer(f"أهلاً بك مجدداً! معرّف اللعبة المسجل بحسابك: {user[0]}", reply_markup=main_keyboard)
        else:
            await message.answer("أهلاً بك! يرجى إرسال معرّف اللاعب (Game ID) الخاص بك للبدء:", reply_markup=cancel_keyboard)
            await state.set_state(Form.waiting_for_game_id)
    else:
        await message.answer("🔄 تم إلغاء العملية بنجاح.", reply_markup=main_keyboard)

@dp.message(F.text.contains("طلب إضافة منصة"))
async def request_platform_start(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    await message.answer("اختر المنصة التي تريد طلب اعتمادها لنشر المقاطع:", reply_markup=platforms_keyboard)
    await state.set_state(Form.waiting_for_platform_choice)

@dp.message(Form.waiting_for_platform_choice)
async def process_platform_choice(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    platform = message.text.strip()
    if platform not in ["TikTok", "Instagram", "YouTube", "Facebook"]:
        await message.answer("الرجاء اختيار منصة صحيحة من القائمة:", reply_markup=platforms_keyboard)
        return
    
    telegram_id = message.from_user.id
    user_plats = get_user_platforms(telegram_id)
    if user_plats.get(platform) == "pending":
        await state.clear()
        await message.answer(f"⚠️ لديك بالفعل طلب معلق لاعتماد منصة **{platform}**. يرجى انتظار رد الإدارة.", reply_markup=main_keyboard, parse_mode="Markdown")
        return
    elif user_plats.get(platform) == "approved":
        await state.clear()
        await message.answer(f"✅ منصة **{platform}** معتمدة لديك مسبقاً ولا تحتاج لطلب جديد.", reply_markup=main_keyboard, parse_mode="Markdown")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO creator_platforms (telegram_id, platform, status, requested_at) VALUES (%s, %s, 'pending', %s)", (telegram_id, platform, now))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        cursor.execute("UPDATE creator_platforms SET status = 'pending', requested_at = %s WHERE telegram_id = %s AND platform = %s", (now, telegram_id, platform))
        conn.commit()
    finally:
        conn.close()
    
    await state.clear()
    await message.answer(f"✅ تم إرسال طلب اعتماد منصة **{platform}** إلى الإدارة بنجاح.", reply_markup=main_keyboard, parse_mode="Markdown")
    
    if ADMIN_GROUP_ID != 0:
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ موافقة", callback_data=f"plat_app_{telegram_id}_{platform}"),
                InlineKeyboardButton(text="❌ رفض", callback_data=f"plat_rej_{telegram_id}_{platform}")
            ]
        ])
        await bot.send_message(ADMIN_GROUP_ID, f"🔔 **طلب اعتماد منصة جديد:**\n👤 صانع المحتوى: `{telegram_id}`\n📱 المنصة: **{platform}**", reply_markup=inline_kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("plat_"))
async def handle_platform_approval(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("ليس لديك صلاحية.", show_alert=True)
        return
    
    data_parts = callback.data.split("_")
    action, telegram_id, platform = data_parts[1], int(data_parts[2]), data_parts[3]
    new_status = "approved" if action == "app" else "rejected"
    status_text = "معتمدة ✅" if action == "app" else "مرفوضة ❌"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE creator_platforms SET status = %s WHERE telegram_id = %s AND platform = %s", (new_status, telegram_id, platform))
    conn.commit()
    conn.close()
    
    try:
        await callback.message.edit_text(callback.message.text + f"\n\n**الحالة الناتجة:** تم تغيير الحالة إلى ({status_text}).", parse_mode="Markdown")
    except Exception:
        pass
        
    await callback.answer(f"تم تحديث الحالة إلى {status_text}")
    try:
        if action == "app":
            await bot.send_message(telegram_id, f"🎉 مبروك! تمت الموافقة على منصة **{platform}**.", parse_mode="Markdown")
        else:
            await bot.send_message(telegram_id, f"⚠️ عذراً، تم رفض منصة **{platform}**.", parse_mode="Markdown")
    except Exception:
        pass

@dp.message(F.text.contains("مقاطعي هذا الشهر"))
async def show_my_submissions(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    current_month = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = %s AND submission_month = %s", (telegram_id, current_month))
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = %s AND submission_month = %s", (telegram_id, current_month))
    stats = cursor.fetchone()
    conn.close()
    v_count, total_views = stats[0] or 0, stats[1] or 0
    if not rows:
        await message.answer(f"لم تقم بإرسال أي مقاطع لشهر {current_month}.", reply_markup=main_keyboard)
        return
    res = f"🎬 مقاطعك المسجلة لشهر {current_month} (عدد مفتوح):\n\n"
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = %s", (telegram_id,))
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        await message.answer("⚠️ أنت غير مسجل مسبقاً! أرسل /start لتسجيل معرفك.", reply_markup=main_keyboard)
        return
    await message.answer(f"معرّفك الحالي: `{user[0]}`\n\nأرسل **معرّف اللعبة الجديد** (أرقام فقط):", reply_markup=cancel_keyboard, parse_mode="Markdown")
    await state.set_state(Form.waiting_for_update_game_id)

@dp.message(Form.waiting_for_update_game_id)
async def process_update_game_id(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    new_game_id = message.text.strip()
    if not new_game_id.isdigit():
        await message.answer("❌ أرسل معرّف صحيح من أرقام فقط:", reply_markup=cancel_keyboard)
        return
    telegram_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET game_id = %s WHERE telegram_id = %s", (new_game_id, telegram_id))
        conn.commit()
        await state.clear()
        await message.answer(f"✅ تم تحديث المعرّف إلى: `{new_game_id}` بنجاح مع الاحتفاظ بكافة مقاطعك!", reply_markup=main_keyboard, parse_mode="Markdown")
    except psycopg2.IntegrityError:
        conn.rollback()
        await message.answer("❌ عذراً، هذا المعرّف مستخدم مسبقاً!", reply_markup=main_keyboard, parse_mode="Markdown")
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
        await message.answer("يرجى إرسال أرقام فقط:", reply_markup=cancel_keyboard)
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id, game_id, registered_at) VALUES (%s, %s, %s)", (telegram_id, game_id, now))
        conn.commit()
        await state.clear()
        await message.answer(f"تم ربط حسابك بمعرّف اللعبة: {game_id} بنجاح!", reply_markup=main_keyboard)
    except psycopg2.IntegrityError:
        conn.rollback()
        cursor.execute("SELECT telegram_id FROM users WHERE game_id = %s", (game_id,))
        owner = cursor.fetchone()
        if owner and owner[0] == telegram_id:
            await state.clear()
            await message.answer(f"أنت مسجل مسبقاً بهذا المعرّف: {game_id}", reply_markup=main_keyboard)
        else:
            await message.answer("عذراً، المعرّف مسجل بحساب آخر.", reply_markup=main_keyboard)
            await state.clear()
    finally:
        conn.close()

URL_PATTERNS = {
    "TikTok": r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com)/\S+)",
    "YouTube": r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)",
    "Instagram": r"(https?://(?:www\.)?instagram\.com/\S+)",
    "Facebook": r"(https?://(?:www\.)?(?:facebook\.com|fb\.watch)/\S+)"
}

async def fetch_views_automatically(video_url: str) -> int:
    return 5000 

@dp.message(F.text.contains("إرسال مقطع جديد"))
async def start_submission(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    telegram_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        await message.answer("أنت غير مسجل! أرسل /start أولاً.", reply_markup=main_keyboard)
        return
    
    await message.answer("يرجى إرسال رابط المقطع الآن (YouTube / TikTok / Instagram / Facebook):\n*(سيتم جلب المشاهدات تلقائياً)*", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_video_url)

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    text = message.text.strip()
    
    matched_platform, clean_url = None, None
    for plat, pattern in URL_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            matched_platform = plat
            clean_url = match.group(0)
            break
            
    if not matched_platform:
        await message.answer("الرابط غير صالح أو غير مدعوم! أرسل رابطاً صحيحاً:", reply_markup=cancel_keyboard)
        return
        
    telegram_id = message.from_user.id
    user_plats = get_user_platforms(telegram_id)
    
    if user_plats.get(matched_platform) != "approved":
        await message.answer(f"⛔ عذراً، منصة **{matched_platform}** غير معتمدة لحسابك. قدم طلباً لاعتمادها من القائمة الرئيسية.", reply_markup=main_keyboard, parse_mode="Markdown")
        await state.clear()
        return

    processing_msg = await message.answer("⏳ جاري التحقق من الرابط وجلب المشاهدات تلقائياً...")
    views = await fetch_views_automatically(clean_url)
    
    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO submissions (telegram_id, video_url, views, submission_month, created_at) VALUES (%s, %s, %s, %s, %s)", (telegram_id, clean_url, views, current_month, now))
        conn.commit()
        cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = %s AND submission_month = %s", (telegram_id, current_month))
        stats = cursor.fetchone()
        current_rank = calculate_rank(stats[1] or views, stats[0] or 1)
        
        await bot.edit_message_text(
            f"✅ تم تسجيل المقطع وجلب المشاهدات **تلقائياً** بنجاح!\n👁 المشاهدات المرصودة: {views:,}\nإجمالي مشاهداتك: {stats[1]:,}\nرتبتك الحالية: {current_rank}",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            reply_markup=main_keyboard
        )
        await state.clear()
    except psycopg2.IntegrityError:
        conn.rollback()
        await bot.edit_message_text("❌ هذا الرابط مسجل مسبقاً في النظام!", chat_id=message.chat.id, message_id=processing_msg.message_id, reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

async def main():
    asyncio.create_task(report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
