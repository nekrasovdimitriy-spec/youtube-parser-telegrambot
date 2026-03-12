import asyncio
import feedparser
import requests
import re

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import os
TOKEN = os.environ.get("BOT_TOKEN")

users = {}
last_videos = {}

# получаем channel_id
def get_channel_id(url):

    r = requests.get(url)
    html = r.text

    match = re.search(r'"channelId":"(UC[\w-]+)"', html)

    if match:
        return match.group(1)

    return None


# старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🎬 YouTube Tracker Bot\n\n"
        "Отправь:\n"
        "/track ссылка_на_канал\n\n"
        "Пример:\n"
        "/track https://www.youtube.com/@kuplinovplay"
    )


# подписка
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

    await update.message.reply_text("Канал добавлен! 🎉")


# проверка видео
async def check_videos(app):

    await asyncio.sleep(5)

    while True:

        for chat_id, rss in users.items():

            feed = feedparser.parse(rss)

            if not feed.entries:
                continue

            video = feed.entries[0]

            if chat_id not in last_videos:
                last_videos[chat_id] = video.id
                continue

            if video.id != last_videos[chat_id]:

                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎬 Новое видео\n\n{video.title}\n{video.link}"
                )

                last_videos[chat_id] = video.id

        await asyncio.sleep(300)


async def post_init(app):
    app.create_task(check_videos(app))


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))

app.post_init = post_init

app.run_polling()