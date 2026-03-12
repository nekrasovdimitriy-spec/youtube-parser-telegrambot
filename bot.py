import os
import asyncio
import json
import feedparser
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# -------------------
# Переменные окружения
# -------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

if not BOT_TOKEN:
    raise ValueError("Не установлена переменная BOT_TOKEN!")
if not YOUTUBE_API_KEY:
    raise ValueError("Не установлена переменная YOUTUBE_API_KEY!")

# -------------------
# Инициализация YouTube API
# -------------------
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# -------------------
# Файлы для хранения данных
# -------------------
USERS_FILE = "users.json"
LAST_VIDEOS_FILE = "last_videos.json"

try:
    with open(USERS_FILE, "r") as f:
        users = json.load(f)
except FileNotFoundError:
    users = {}

try:
    with open(LAST_VIDEOS_FILE, "r") as f:
        last_videos = json.load(f)
except FileNotFoundError:
    last_videos = {}

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def save_last_videos():
    with open(LAST_VIDEOS_FILE, "w") as f:
        json.dump(last_videos, f)

# -------------------
# Получение channel_id
# -------------------
def get_channel_id(url: str) -> str | None:
    if "/channel/" in url:
        return url.split("/channel/")[1]
    if "@" in url:
        username = url.split("@")[1]
        try:
            request = youtube.search().list(
                part="snippet",
                q=username,
                type="channel",
                maxResults=1
            )
            response = request.execute()
            if response["items"]:
                return response["items"][0]["snippet"]["channelId"]
        except Exception as e:
            print("Ошибка YouTube API:", e)
            return None
    return None

# -------------------
# Telegram команды
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Мои подписки", callback_data="mychannels")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎬 YouTube Tracker Bot\n\nВыберите действие:", reply_markup=reply_markup
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пришлите ссылку на канал.")
        return

    youtube_url = context.args[0]
    channel_id = get_channel_id(youtube_url)
    if not channel_id:
        await update.message.reply_text("Не удалось определить канал.")
        return

    rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    chat_id = str(update.message.chat_id)

    if chat_id not in users:
        users[chat_id] = []

    # Проверяем, подписан ли уже
    if any(x["rss"] == rss for x in users[chat_id]):
        await update.message.reply_text("Вы уже подписаны на этот канал.")
        return

    users[chat_id].append({"rss": rss, "url": youtube_url})
    save_users()
    await update.message.reply_text("Канал добавлен! 🎉")

async def mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in users or not users[chat_id]:
        await update.message.reply_text("Вы пока ни на что не подписаны.")
        return

    message = "Ваши подписки:\n" + "\n".join(x["url"] for x in users[chat_id])
    await update.message.reply_text(message)

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "mychannels":
        await mychannels(query, context)

# -------------------
# Автопроверка новых видео
# -------------------
async def check_videos(app):
    await asyncio.sleep(5)
    while True:
        for chat_id, channels in users.items():
            for ch in channels:
                rss = ch["rss"]
                feed = feedparser.parse(rss)
                if not feed.entries:
                    continue
                video = feed.entries[0]
                if chat_id not in last_videos:
                    last_videos[chat_id] = {}
                if rss not in last_videos[chat_id]:
                    last_videos[chat_id][rss] = video.id
                    save_last_videos()
                    continue
                if video.id != last_videos[chat_id][rss]:
                    try:
                        await app.bot.send_message(
                            chat_id=int(chat_id),
                            text=f"🎬 Новое видео!\n{video.title}\n{video.link}"
                        )
                        last_videos[chat_id][rss] = video.id
                        save_last_videos()
                    except Exception as e:
                        print("Ошибка при автопостинге:", e)
        await asyncio.sleep(300)  # проверка каждые 5 минут

# -------------------
# Инициализация Telegram
# -------------------
async def post_init(app):
    app.create_task(check_videos(app))

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))
app.add_handler(CommandHandler("mychannels", mychannels))
app.add_handler(CallbackQueryHandler(button_handler))
app.post_init = post_init

# -------------------
# Запуск бота
# -------------------
app.run_polling()
