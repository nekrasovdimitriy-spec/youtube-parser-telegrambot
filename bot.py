import os
import json
import asyncio
import feedparser
import gspread

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes


# =========================
# ENV VARIABLES
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

# Проверяем наличие всех необходимых переменных для Google credentials
required_google_vars = {
    "GOOGLE_PROJECT_ID": os.environ.get("GOOGLE_PROJECT_ID"),
    "GOOGLE_PRIVATE_KEY_ID": os.environ.get("GOOGLE_PRIVATE_KEY_ID"),
    "GOOGLE_PRIVATE_KEY": os.environ.get("GOOGLE_PRIVATE_KEY"),
    "GOOGLE_CLIENT_EMAIL": os.environ.get("GOOGLE_CLIENT_EMAIL"),
    "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID")
}

if not BOT_TOKEN:
    raise ValueError("Не установлена переменная окружения BOT_TOKEN!")

if not YOUTUBE_API_KEY:
    raise ValueError("Не установлена переменная окружения YOUTUBE_API_KEY!")

# Проверяем каждую переменную
missing_vars = []
for var_name, var_value in required_google_vars.items():
    if not var_value:
        missing_vars.append(var_name)

if missing_vars:
    error_message = "Не установлены следующие переменные окружения:\n"
    for var in missing_vars:
        error_message += f"  - {var}\n"
    raise ValueError(error_message)

print("Все переменные окружения установлены:")
print(f"GOOGLE_PROJECT_ID: {required_google_vars['GOOGLE_PROJECT_ID'][:10]}...")
print(f"GOOGLE_PRIVATE_KEY_ID: {required_google_vars['GOOGLE_PRIVATE_KEY_ID'][:10]}...")
print(f"GOOGLE_PRIVATE_KEY: длина {len(required_google_vars['GOOGLE_PRIVATE_KEY'])} символов")
print(f"GOOGLE_CLIENT_EMAIL: {required_google_vars['GOOGLE_CLIENT_EMAIL']}")
print(f"GOOGLE_CLIENT_ID: {required_google_vars['GOOGLE_CLIENT_ID'][:10]}...")


# =========================
# GOOGLE CREDS FROM ENV VARIABLES
# =========================

google_creds = {
    "type": "service_account",
    "project_id": required_google_vars["GOOGLE_PROJECT_ID"],
    "private_key_id": required_google_vars["GOOGLE_PRIVATE_KEY_ID"],
    "private_key": required_google_vars["GOOGLE_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": required_google_vars["GOOGLE_CLIENT_EMAIL"],
    "client_id": required_google_vars["GOOGLE_CLIENT_ID"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{required_google_vars['GOOGLE_CLIENT_EMAIL']}"
}

# Проверим, что private_key содержит правильный формат
print("\nПроверка GOOGLE_PRIVATE_KEY:")
if "BEGIN PRIVATE KEY" in google_creds["private_key"]:
    print("  ✅ Ключ содержит BEGIN PRIVATE KEY")
else:
    print("  ❌ Ключ не содержит BEGIN PRIVATE KEY")

if "END PRIVATE KEY" in google_creds["private_key"]:
    print("  ✅ Ключ содержит END PRIVATE KEY")
else:
    print("  ❌ Ключ не содержит END PRIVATE KEY")

print(f"  Количество строк в ключе: {len(google_creds['private_key'].splitlines())}")

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    credentials = Credentials.from_service_account_info(google_creds, scopes=scopes)
    print("\n✅ Credentials созданы успешно")
except Exception as e:
    print(f"\n❌ Ошибка создания credentials: {e}")
    raise

try:
    gc = gspread.authorize(credentials)
    print("✅ gspread авторизован успешно")
except Exception as e:
    print(f"❌ Ошибка авторизации gspread: {e}")
    raise

SHEET_NAME = "YouTubeBotSubscriptions"
try:
    sheet = gc.open(SHEET_NAME).sheet1
    print(f"✅ Таблица '{SHEET_NAME}' открыта успешно")
except Exception as e:
    print(f"❌ Ошибка открытия таблицы '{SHEET_NAME}': {e}")
    raise


# =========================
# YOUTUBE API
# =========================

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def get_channel_id(url):

    if "/channel/" in url:
        return url.split("/channel/")[1]

    if "@" in url:
        username = url.split("@")[1]

        request = youtube.search().list(
            part="snippet",
            q=username,
            type="channel",
            maxResults=1
        )

        response = request.execute()

        if response["items"]:
            return response["items"][0]["snippet"]["channelId"]

    return None


# =========================
# TELEGRAM COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton("📺 Мои подписки", callback_data="mychannels")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "YouTube Tracker Bot\n\nИспользуй:\n/track ссылка_на_канал",
        reply_markup=reply_markup
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

    chat_id = str(update.message.chat_id)

    records = sheet.get_all_records()

    for r in records:
        if r["chat_id"] == chat_id and r["channel_rss"] == rss:
            await update.message.reply_text("Ты уже подписан на этот канал.")
            return

    sheet.append_row([chat_id, url, rss])

    await update.message.reply_text("Канал добавлен ✅")


async def mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = str(update.effective_chat.id)

    records = sheet.get_all_records()

    channels = []

    for r in records:
        if str(r["chat_id"]) == chat_id:
            channels.append(r["channel_url"])

    if not channels:
        await update.message.reply_text("У тебя нет подписок.")
        return

    text = "📺 Твои подписки:\n\n" + "\n".join(channels)

    await update.message.reply_text(text)


async def button_handler(update, context):

    query = update.callback_query
    await query.answer()

    if query.data == "mychannels":
        await mychannels(update, context)


# =========================
# VIDEO CHECKER
# =========================

last_videos = {}


async def check_videos(app):

    await asyncio.sleep(10)

    while True:

        records = sheet.get_all_records()

        for r in records:

            chat_id = r["chat_id"]
            rss = r["channel_rss"]

            feed = feedparser.parse(rss)

            if not feed.entries:
                continue

            video = feed.entries[0]

            key = f"{chat_id}_{rss}"

            if key in last_videos and last_videos[key] == video.id:
                continue

            try:

                await app.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"🎬 Новое видео!\n\n{video.title}\n{video.link}"
                )

                last_videos[key] = video.id

            except Exception as e:
                print("Ошибка отправки:", e)

        await asyncio.sleep(300)


# =========================
# APP INIT
# =========================

async def post_init(app):
    print("\n✅ Бот запущен и готов к работе!")
    app.create_task(check_videos(app))


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("track", track))
app.add_handler(CommandHandler("mychannels", mychannels))
app.add_handler(CallbackQueryHandler(button_handler))

app.post_init = post_init

print("🚀 Запуск бота...")
app.run_polling()
