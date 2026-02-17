import os
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Logging for debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Environment variables from Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

# Flask app for webhook
flask_app = Flask(__name__)

# Telegram application
application = Application.builder().token(BOT_TOKEN).build()

# --- Handlers ---
async def start(update: Update, context):
    keyboard = [[InlineKeyboardButton("Create Post", callback_data="create_post")]]
    await update.message.reply_text(
        "Welcome! Click below to create a post.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "create_post":
        context.user_data["state"] = "waiting_for_content"
        await query.edit_message_text("Send me text or a photo with caption.")
    elif query.data == "send_now":
        text = context.user_data.get("post_text")
        photo = context.user_data.get("post_photo")
        if photo:
            await context.bot.send_photo(CHANNEL_ID, photo=photo, caption=text)
        elif text:
            await context.bot.send_message(CHANNEL_ID, text=text)
        await query.edit_message_text("Post sent!")

async def message_handler(update: Update, context):
    state = context.user_data.get("state")
    if state == "waiting_for_content":
        if update.message.photo:
            context.user_data["post_photo"] = update.message.photo[-1].file_id
            context.user_data["post_text"] = update.message.caption or ""
        else:
            context.user_data["post_text"] = update.message.text
        keyboard = [[InlineKeyboardButton("Send Now", callback_data="send_now")]]
        await update.message.reply_text(
            "Preview ready. Send?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# --- Register handlers ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

# --- Webhook route ---
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok"

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
