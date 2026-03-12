import asyncio
import feedparser
import requests
import re
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- берём токен из переменной окружения ---
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")

# Словарь: chat_id → RSS канал
users = {}

# Словарь: chat_id → последнее видео
last_videos = {}

# --- функция для получения channel_id из ссылки ---
def get_channel_id(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    html = r.text

    # основной способ
    match = re.search(r'"channelId":"(UC[\w-]+)"', html)
    if match:
        return match.group(1)

    # запасной способ
    match = re.search(r'channelId=(UC[\w-]+)', html)
    if match:
        return match.group(1)

    # если ссылка уже вида /channel/UCxxxx
    if "/channel/" in url:
        return url.split("/channel/")[1]

    return None

# --- команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 YouTube Tracker Bot\n\n"
        "Отправь команду:\n"
        "/track ссылка_на_канал\n\n"
        "Пример:\n"
        "/track https://www.youtube.com/@kuplinovplay"
    )

# --- команда /track ---
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

# --- функция проверки новых видео ---
async def check_videos(app):
    await asyncio.sleep(5)  # ждём, пока бот стартует
    while True:
        for chat_id, rss in users.items():
            feed = feedparser.parse(rss)
            if not feed.entries:
                continue

            video = feed.entries[0]

            # если бот только начал следить, запоминаем видео
            if chat_id not in last_videos:
                last_videos[chat_id] = video.id
                continue

            # если появилось новое видео
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

# --- запуск автопроверки после старта ---
async def post_init(app):
    app.create_task(check_videos(app))

# --- создаём приложение ---
app = ApplicationBuilder().token(TOKEN).build()

# команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))

# автопостинг
app.post_init = post_init

# запуск
app.run_polling()
