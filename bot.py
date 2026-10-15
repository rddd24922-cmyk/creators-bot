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
        return "Emperor (24,000)"
    elif views >= 1000000 and videos_count >= 20:
        return "Icon (20,000)"
    elif views >= 500000 and videos_count >= 20:
        return "Legend (16,000)"
    elif views >= 100000 and videos_count >= 20:
        return "Sultan (13,000)"
    elif views >= 50000 and videos_count >= 20:
        return "Leader (9,000)"
    elif views >= 15000 and videos_count >= 15:
        return "Commander (6,000)"
    elif views >= 5000 and videos_count >= 12:
        return "Knight (3,500)"
    elif views >= 1500 and videos_count >= 8:
        return "Warrior (2,000)"
    elif views >= 150 and videos_count >= 5:
        return "Recruit (800)"
    elif views >= 50 and videos_count >= 1:
        return "Beginner (200)"
    else:
        return "Candidate"

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Submit New Video")],
        [KeyboardButton(text="My Submissions"), KeyboardButton(text="My Game ID")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Cancel")]
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
                    await bot.send_message(ADMIN_GROUP_ID, "Reminder: 2 days left before submission closes.")
                except Exception as e:
                    logging.error(f"Error: {e}")

        target_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if now >= target_time:
            target_time = target_time.replace(day=target_time.day + 1)
            
        wait_seconds = (target_time - datetime.now()).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        if ADMIN_GROUP_ID != 0:
            today_date = datetime.now().strftime("%Y-%m-%d")
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("SELECT u.game_id, s.video_url, s.views, s.created_at FROM submissions s LEFT JOIN users u ON s.telegram_id = u.telegram_id WHERE DATE(s.created_at) = ?", (today_date,))
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                report_text = f"Daily Report ({today_date}):\n\n"
                for idx, row in enumerate(rows, 1):
                    report_text += f"{idx}. Game ID: {row[0] or 'Unknown'}\nURL: {row[1]}\nViews: {row[2]:,}\nTime: {row[3]}\n\n"
                try:
                    await bot.send_message(ADMIN_GROUP_ID, report_text, disable_web_page_preview=True)
                except Exception as e:
                    logging.error(f"Error: {e}")
            else:
                try:
                    await bot.send_message(ADMIN_GROUP_ID, f"Daily Report ({today_date}): No submissions today.")
                except Exception as e:
                    logging.error(f"Error: {e}")
                    
        await asyncio.sleep(60)

@dp.message(Command("allow"))
async def allow_user(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Usage: /allow TELEGRAM_ID")
        return
    target_id = int(args[1].strip())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO whitelist (telegram_id, added_at) VALUES (?, ?)", (target_id, now))
        conn.commit()
        await message.answer(f"User {target_id} allowed successfully.")
    except sqlite3.IntegrityError:
        await message.answer("User already allowed.")
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
    await message.answer(f"User {target_id} removed.")

@dp.message(F.text.in_({"Cancel", "إلغاء", "كنسل"}))
@dp.message(Command("cancel", "reset", "fix", "start"))
async def global_commands_handler(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    if not is_allowed(telegram_id):
        await message.answer("Access denied. Authorized users only.")
        return
    await state.clear()
    if message.text and message.text.startswith("/start"):
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT game_id FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            await message.answer(f"Welcome back! Your registered Game ID is: {user[0]}", reply_markup=main_keyboard)
        else:
            await message.answer("Welcome! Please send your Game ID to begin:", reply_markup=cancel_keyboard)
            await state.set_state(Form.waiting_for_game_id)
    else:
        await message.answer("Operation cancelled successfully.", reply_markup=main_keyboard)

@dp.message(Command("user"))
async def search_user_stats(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /user GAME_ID")
        return
    target_game_id = args[1].strip()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (target_game_id,))
    user_info = cursor.fetchone()
    if not user_info:
        conn.close()
        await message.answer(f"No creator found with Game ID: {target_game_id}")
        return
    telegram_id = user_info[0]
    cursor.execute("SELECT video_url, views, created_at FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    submissions = cursor.fetchall()
    cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    stats = cursor.fetchone()
    conn.close()
    v_count, total_views = stats[0] or 0, stats[1] or 0
    rank = calculate_rank(total_views, v_count)
    report = f"Stats for Game ID {target_game_id}:\nViews: {total_views:,}\nVideos: {v_count}\nRank: {rank}\n\n"
    if submissions:
        report += "Submissions:\n"
        for idx, sub in enumerate(submissions, 1):
            report += f"{idx}. {sub[0]} - Views: {sub[1]:,} - {sub[2]}\n"
    else:
        report += "No submissions this month."
    await message.answer(report, disable_web_page_preview=True)

@dp.message(Command("myid"))
async def get_group_id(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Chat ID: {message.chat.id}\nTelegram ID: {message.from_user.id}")

@dp.message(Command("admin_stats"))
async def admin_stats_handler(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    await state.clear()
    current_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT u.game_id, COUNT(s.id), SUM(s.views) FROM users u LEFT JOIN submissions s ON u.telegram_id = s.telegram_id AND s.submission_month = ? GROUP BY u.telegram_id", (current_month,))
    creators = cursor.fetchall()
    conn.close()
    if not creators:
        await message.answer(f"No records found for {current_month}.")
        return
    text = f"Creators Stats for {current_month}:\n\n"
    for idx, c in enumerate(creators, 1):
        v_count, v_views = c[1] or 0, c[2] or 0
        text += f"{idx}. Game ID: {c[0]} - Videos: {v_count} - Views: {v_views:,} - Rank: {calculate_rank(v_views, v_count)}\n"
    await message.answer(text)

@dp.message(Command("admin_summary"))
async def admin_summary_handler(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
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
    summary_text = f"Summary for {current_month}:\nTotal Views: {total_views:,}\nTotal Videos: {total_videos}\n\nTop Creators:\n"
    if not top_creators:
        summary_text += "No views recorded yet."
    else:
        for idx, creator in enumerate(top_creators, 1):
            summary_text += f"{idx}. Game ID: {creator[0]} - Views: {creator[1]:,} - Videos: {creator[2]}\n"
    await message.answer(summary_text)

@dp.message(F.text.contains("My Submissions"))
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
        await message.answer(f"No submissions for {current_month}.", reply_markup=main_keyboard)
        return
    res = f"Your submissions for {current_month}:\n\n"
    for idx, row in enumerate(rows, 1):
        res += f"{idx}. {row[0]}\nViews: {row[1]:,} | {row[2]}\n\n"
    res += f"Total Views: {total_views:,}\nTotal Videos: {v_count}\nRank: {calculate_rank(total_views, v_count)}"
    await message.answer(res, disable_web_page_preview=True, reply_markup=main_keyboard)

@dp.message(F.text.contains("My Game ID"))
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
        await message.answer(f"Your registered Game ID is: {user[0]}", reply_markup=main_keyboard)
    else:
        await message.answer("Not registered. Send /start to register.", reply_markup=main_keyboard)

@dp.message(Form.waiting_for_game_id)
async def process_game_id(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    telegram_id = message.from_user.id
    game_id = message.text.strip()
    if not game_id.isdigit():
        await message.answer("Please send a valid numeric Game ID:", reply_markup=cancel_keyboard)
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (telegram_id, game_id, registered_at) VALUES (?, ?, ?)", (telegram_id, game_id, now))
        conn.commit()
        await state.clear()
        await message.answer(f"Game ID {game_id} registered successfully!", reply_markup=main_keyboard)
    except sqlite3.IntegrityError:
        cursor.execute("SELECT telegram_id FROM users WHERE game_id = ?", (game_id,))
        owner = cursor.fetchone()
        if owner and owner[0] == telegram_id:
            await state.clear()
            await message.answer(f"You are already registered with Game ID: {game_id}", reply_markup=main_keyboard)
        else:
            await message.answer("This Game ID is already registered by another user.", reply_markup=main_keyboard)
            await state.clear()
    finally:
        conn.close()

@dp.message(F.text.contains("Submit New Video"))
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
        await message.answer("You are not registered! Send /start first.", reply_markup=main_keyboard)
        return
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE telegram_id = ? AND submission_month = ?", (telegram_id, current_month))
    count = cursor.fetchone()[0]
    conn.close()
    if count >= MAX_VIDEOS_PER_MONTH:
        await message.answer("You have reached the monthly limit.", reply_markup=main_keyboard)
        return
    await message.answer("Send the video URL (YouTube / TikTok / Instagram / Facebook):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_video_url)

URL_PATTERN = r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch)/\S+)"

@dp.message(Form.waiting_for_video_url)
async def process_video_url(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    text = message.text.strip()
    if not re.search(URL_PATTERN, text):
        await message.answer("Invalid URL. Send a valid link:", reply_markup=cancel_keyboard)
        return
    match = re.search(URL_PATTERN, text)
    clean_url = match.group(0) if match else text
    await state.update_data(video_url=clean_url)
    await message.answer("Send the current views (numbers only):", reply_markup=cancel_keyboard)
    await state.set_state(Form.waiting_for_views)

@dp.message(Form.waiting_for_views)
async def process_video_views(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Please send numbers only for views:", reply_markup=cancel_keyboard)
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
        await message.answer(f"Video registered successfully!\nTotal Views: {stats[1]:,}\nRank: {current_rank}", reply_markup=main_keyboard)
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("This URL is already registered!", reply_markup=main_keyboard)
        await state.clear()
    finally:
        conn.close()

async def main():
    asyncio.create_task(daily_report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
