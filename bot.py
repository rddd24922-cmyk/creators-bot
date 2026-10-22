import os
import re
import asyncio
import logging
import calendar
from datetime import datetime, timedelta
import psycopg2
import discord
from discord import app_commands
from discord.ext import commands

# --- المتغيرات البيئية ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- قاعدة البيانات ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            discord_id BIGINT PRIMARY KEY,
            added_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id BIGINT PRIMARY KEY,
            game_id TEXT UNIQUE,
            registered_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creator_platforms (
            id SERIAL PRIMARY KEY,
            discord_id BIGINT,
            platform TEXT,
            status TEXT DEFAULT 'pending',
            requested_at TEXT,
            UNIQUE(discord_id, platform)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            discord_id BIGINT,
            video_url TEXT UNIQUE,
            views INTEGER DEFAULT 0,
            submission_month TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- التحقق من الصلاحيات ---
def is_admin(interaction: discord.Interaction) -> bool:
    # يمكنك تعديل الشرط هنا ليتطابق مع صلاحيات المشرفين في سيرفرك (رتبة أو أيدي محدد)
    return interaction.user.guild_permissions.administrator

def is_allowed(discord_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id FROM whitelist WHERE discord_id = %s", (discord_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None or is_admin

# --- حساب الرتب ---
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

URL_PATTERNS = {
    "TikTok": r"(https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com)/\S+)",
    "YouTube": r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)",
    "Instagram": r"(https?://(?:www\.)?instagram\.com/\S+)",
    "Facebook": r"(https?://(?:www\.)?(?:facebook\.com|fb\.watch)/\S+)"
}

@bot.event
async def on_ready():
    logging.info(f"تم تسجيل الدخول بنجاح باسم: {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        logging.info(f"تم مزامنة {len(synced)} من الأوامر بنجاح.")
    except Exception as e:
        logging.error(f"خطأ في مزامنة الأوامر: {e}")

# --- الأوامر المائلة (Slash Commands) لصناع المحتوى ---

@bot.tree.command(name="register", description="تسجيل وربط حسابك بمعرف اللعبة Game ID")
async def register(interaction: discord.Interaction, game_id: str):
    if not game_id.isdigit():
        await interaction.response.send_message("❌ يرجى إدخال أرقام صحيحة فقط لمعرف اللعبة.", ephemeral=True)
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (discord_id, game_id, registered_at) VALUES (%s, %s, %s)", (interaction.user.id, game_id, now))
        conn.commit()
        await interaction.response.send_message(f"✅ تم ربط حسابك بمعرف اللعبة `{game_id}` بنجاح!", ephemeral=True)
    except psycopg2.IntegrityError:
        conn.rollback()
        cursor.execute("UPDATE users SET game_id = %s WHERE discord_id = %s", (game_id, interaction.user.id))
        conn.commit()
        await interaction.response.send_message(f"✅ تم تحديث معرف اللعبة الخاص بك إلى `{game_id}` بنجاح!", ephemeral=True)
    finally:
        conn.close()

@bot.tree.command(name="submit", description="إرسال مقطع جديد مع عدد المشاهدات")
@app_commands.describe(video_url="رابط المقطع (تيك توك، يوتيوب، إلخ)", views="عدد المشاهدات الحالية")
async def submit(interaction: discord.Interaction, video_url: str, views: int):
    discord_id = interaction.user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE discord_id = %s", (discord_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        await interaction.response.send_message("⚠️ أنت غير مسجل في النظام! استخدم الأمر `/register` أولاً.", ephemeral=True)
        return

    matched_platform, clean_url = None, None
    for plat, pattern in URL_PATTERNS.items():
        match = re.search(pattern, video_url)
        if match:
            matched_platform = plat
            clean_url = match.group(0)
            break

    if not matched_platform:
        conn.close()
        await interaction.response.send_message("❌ الرابط غير صالح أو المنصة غير مدعومة!", ephemeral=True)
        return

    current_month = datetime.now().strftime("%Y-%m")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cursor.execute("INSERT INTO submissions (discord_id, video_url, views, submission_month, created_at) VALUES (%s, %s, %s, %s, %s)", (discord_id, clean_url, views, current_month, now))
        conn.commit()

        cursor.execute("SELECT COUNT(*), SUM(views) FROM submissions WHERE discord_id = %s AND submission_month = %s", (discord_id, current_month))
        stats = cursor.fetchone()
        v_count, total_views = stats[0] or 1, stats[1] or views
        
        rank = calculate_rank(total_views, v_count)

        embed = discord.Embed(title="🎬 تم تسجيل المقطع بنجاح", color=discord.Color.green())
        embed.add_field(name="المنصة", value=matched_platform, inline=True)
        embed.add_field(name="المشاهدات", value=f"{views:,}", inline=True)
        embed.add_field(name="إجمالي مقاطعك هذا الشهر", value=str(v_count), inline=True)
        embed.add_field(name="إجمالي المشاهدات", value=f"{total_views:,}", inline=True)
        embed.add_field(name="الرتبة الحالية", value=rank, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
    except psycopg2.IntegrityError:
        conn.rollback()
        await interaction.response.send_message("❌ هذا الرابط مسجل مسبقاً في النظام!", ephemeral=True)
    finally:
        conn.close()

@bot.tree.command(name="my_stats", description="عرض إحصائياتك ومقاطعك المسجلة لهذا الشهر")
async def my_stats(interaction: discord.Interaction):
    discord_id = interaction.user.id
    current_month = datetime.now().strftime("%Y-%m")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM users WHERE discord_id = %s", (discord_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        await interaction.response.send_message("⚠️ لم تقم بالتسجيل بعد. استخدم الأمر `/register`.", ephemeral=True)
        return

    cursor.execute("SELECT video_url, views FROM submissions WHERE discord_id = %s AND submission_month = %s ORDER BY id ASC", (discord_id, current_month))
    rows = cursor.fetchall()
    conn.close()

    total_views = sum(r[1] for r in rows)
    v_count = len(rows)
    rank = calculate_rank(total_views, v_count)

    embed = discord.Embed(title=f"📊 إحصائياتك لشهر {current_month}", color=discord.Color.blue())
    embed.add_field(name="Game ID", value=user[0], inline=True)
    embed.add_field(name="المقاطع المسجلة", value=str(v_count), inline=True)
    embed.add_field(name="إجمالي المشاهدات", value=f"{total_views:,}", inline=True)
    embed.add_field(name="الرتبة", value=rank, inline=False)

    if rows:
        desc = ""
        for idx, r in enumerate(rows, 1):
            desc += f"**{idx}.** [رابط المقطع]({r[0]}) — 👁️ **{r[1]:,}**\n"
        embed.description = desc
    else:
        embed.description = "لا توجد مقاطع مسجلة هذا الشهر حتى الآن."

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- تشغيل البوت ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
