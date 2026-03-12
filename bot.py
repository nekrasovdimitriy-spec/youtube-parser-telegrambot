import os
import asyncio
import feedparser
from googleapiclient.discovery import build
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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
# Хранилища данных
# -------------------
users = {}         # chat_id → RSS канал
last_videos = {}   # chat_id → последнее видео

# -------------------
# Функция для получения channel_id
# -------------------
def get_channel_id(url: str) -> str | None:
    """Возвращает channel_id по ссылке @username или /channel/UCxxx"""
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
# Команды Telegram
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 YouTube Tracker Bot\n\n"
        "Отправь команду:\n"
        "/track <ссылка_на_канал>\n\n"
        "Пример:\n"
        "/track https://www.youtube.com/@kuplinovplay"
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пришли ссылку на канал.")
        return

    url = context.args[0]
    channel_id = get_channel_id(url)

    if not channel_id:
        await update.message.reply_text("Не удалось определить канал.")
        return

    rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    chat_id = update.message.chat_id
    users[chat_id] = rss

    await update.message.reply_text("Канал добавлен! 🎉 Теперь буду присылать новые видео.")

# -------------------
# Автопроверка новых видео
# -------------------
async def check_videos(app):
    await asyncio.sleep(5)  # ждём старта приложения

    while True:
        for chat_id, rss in users.items():
            feed = feedparser.parse(rss)
            if not feed.entries:
                continue

            video = feed.entries[0]

            # если бот только начал следить — запоминаем текущее видео
            if chat_id not in last_videos:
                last_videos[chat_id] = video.id
                continue

            # новое видео
            if video.id != last_videos[chat_id]:
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"🎬 Новое видео!\n\n{video.title}\n{video.link}"
                    )
                    last_videos[chat_id] = video.id
                except Exception as e:
                    print("Ошибка при автопостинге:", e)

        await asyncio.sleep(300)  # проверка каждые 5 минут

# -------------------
# Инициализация приложения Telegram
# -------------------
async def post_init(app):
    app.create_task(check_videos(app))

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))

app.post_init = post_init

# -------------------
# Запуск бота
# -------------------
app.run_polling()
