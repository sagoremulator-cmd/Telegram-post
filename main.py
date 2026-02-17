import os
import re
import logging
from copy import deepcopy
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import TelegramError

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

flask_app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

# Handlers
async def start(update: Update, context):
    keyboard = [[InlineKeyboardButton("Create Post", callback_data="create_post")]]
    await update.message.reply_text("Welcome! Click to create a post.", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data.clear()

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "create_post":
        context.user_data["state"] = "waiting_for_content"
        await query.edit_message_text("Please send the text (with formatting) or a photo (with formatted caption).")
        return

    elif data == "add_url":
        context.user_data["state"] = "waiting_for_urls"
        await context.bot.send_message(chat_id=chat_id, text="Send URL buttons: Text - https://...\nOne per line.")
        return

    elif data == "send_now":
        text = context.user_data.get("post_text", "")
        entities = context.user_data.get("post_entities", [])
        photo = context.user_data.get("post_photo")
        buttons = context.user_data.get("post_buttons", [])
        markup = get_button_markup(buttons) if buttons else None

        try:
            if photo:
                await context.bot.send_photo(CHANNEL_ID, photo=photo, caption=text, caption_entities=entities, reply_markup=markup)
            elif text:
                await context.bot.send_message(CHANNEL_ID, text=text, entities=entities, reply_markup=markup)
            await context.bot.send_message(chat_id, text="Post sent successfully!")
        except TelegramError as e:
            await context.bot.send_message(chat_id, text=f"Error: {e}")

        context.user_data.clear()
        await context.bot.send_message(chat_id, text="Ready for next?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Create Post", callback_data="create_post")]]))

async def message_handler(update: Update, context):
    message = update.message
    chat_id = message.chat_id
    state = context.user_data.get("state")

    if state == "waiting_for_content":
        text, entities, photo = "", [], None
        if message.photo:
            photo = message.photo[-1].file_id
            text = message.caption or ""
            entities = message.caption_entities or []
        elif message.text:
            text = message.text
            entities = message.entities or []
        else:
            await message.reply_text("Send text or photo with caption.")
            return

        context.user_data.update({"post_text": text, "post_entities": deepcopy(entities), "post_photo": photo})
        context.user_data.pop("state", None)
        await refresh_preview(context, chat_id)
        return

    elif state == "waiting_for_urls":
        if not message.text:
            await message.reply_text("Send button lines please.")
            return
        lines = message.text.strip().split("\n")
        buttons = []
        for line in lines:
            if "-" in line:
                btn_text, url = [p.strip() for p in line.split("-", 1)]
                if url.startswith(("http://", "https://")):
                    buttons.append((btn_text, url))
        if not buttons:
            await message.reply_text("Invalid. Use: Text - https://...\nOne per line.")
            return
        context.user_data["post_buttons"] = buttons
        context.user_data.pop("state", None)
        await refresh_preview(context, chat_id)
        return

    await message.reply_text("Use /start or buttons please.")

async def refresh_preview(context, chat_id):
    text = context.user_data.get("post_text", "")
    entities = context.user_data.get("post_entities", [])
    photo = context.user_data.get("post_photo")
    buttons = context.user_data.get("post_buttons", [])
    markup = get_button_markup(buttons) if buttons else None

    if photo:
        msg = await context.bot.send_photo(chat_id, photo=photo, caption=text, caption_entities=entities, reply_markup=markup)
    else:
        msg = await context.bot.send_message(chat_id, text=text, entities=entities, reply_markup=markup)

    context.user_data["preview_id"] = msg.message_id
    keyboard = [[InlineKeyboardButton("Add URL", callback_data="add_url")], [InlineKeyboardButton("Send Now", callback_data="send_now")]]
    await context.bot.send_message(chat_id, text="Preview updated. Next action?", reply_markup=InlineKeyboardMarkup(keyboard))

def get_button_markup(buttons):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, url=u) for t, u in buttons]]) if buttons else None

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

# Webhook route
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "ok"

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
