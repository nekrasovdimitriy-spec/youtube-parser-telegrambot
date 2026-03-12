import os
import json
import asyncio
import feedparser
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from googleapiclient.discovery import build

# -------------------
# Переменные окружения
# -------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS")
SHEET_NAME = "YouTubeBotSubscriptions"
SHEET_TAB = "Subscriptions"     

if not BOT_TOKEN or not YOUTUBE_API_KEY or not GOOGLE_CREDS_JSON:
    raise ValueError("Не установлены все переменные окружения!")

# -------------------
# Инициализация YouTube API
# -------------------
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

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
# Google Sheets setup
# -------------------
def get_gsheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(SHEET_TAB)
    return sheet

# -------------------
# Telegram команды
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Мои подписки", callback_data="mychannels")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎬 YouTube Tracker Bot\n\nВыберите действие:", reply_markup=reply_markup)

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пришлите ссылку на канал.")
        return

    url = context.args[0]
    channel_id = get_channel_id(url)
    if not channel_id:
        await update.message.reply_text("Не удалось определить канал.")
        return

    rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    chat_id = str(update.message.chat_id)

    sheet = get_gsheet()
    records = sheet.get_all_records()
    if any(r['chat_id']==chat_id and r['channel_rss']==rss for r in records):
        await update.message.reply_text("Вы уже подписаны на этот канал.")
        return

    sheet.append_row([chat_id, url, rss])
    await update.message.reply_text("Канал добавлен! 🎉")

async def mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    sheet = get_gsheet()
    records = sheet.get_all_records()
    user_channels = [r["channel_url"] for r in records if str(r["chat_id"]) == chat_id]
    if not user_channels:
        await update.message.reply_text("Вы пока ни на что не подписаны.")
        return
    await update.message.reply_text("Ваши подписки:\n" + "\n".join(user_channels))

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
        sheet = get_gsheet()
        records = sheet.get_all_records()
        for r in records:
            chat_id = r['chat_id']
            rss = r['channel_rss']
            feed = feedparser.parse(rss)
            if not feed.entries:
                continue
            video = feed.entries[0]
            key = f"{chat_id}_{rss}"
            if not hasattr(check_videos, "last_videos"):
                check_videos.last_videos = {}
            if key in check_videos.last_videos and check_videos.last_videos[key] == video.id:
                continue
            try:
                await app.bot.send_message(chat_id=int(chat_id),
                                           text=f"🎬 Новое видео!\n{video.title}\n{video.link}")
                check_videos.last_videos[key] = video.id
            except Exception as e:
                print("Ошибка автопостинга:", e)
        await asyncio.sleep(300)

# -------------------
# Инициализация бота
# -------------------
async def post_init(app):
    app.create_task(check_videos(app))

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))
app.add_handler(CommandHandler("mychannels", mychannels))
app.add_handler(CallbackQueryHandler(button_handler))
app.post_init = post_init
app.run_polling()


