# bot.py
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA")  # GitHub Secrets mein daal
DATA_FILE = "votes.json"

# Vote state
votes = {}

def load_votes():
    global votes
    try:
        with open(DATA_FILE, "r") as f:
            votes = json.load(f)
    except:
        votes = {}

def save_votes():
    with open(DATA_FILE, "w") as f:
        json.dump(votes, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✅ Option A", callback_data="A")],
        [InlineKeyboardButton("✅ Option B", callback_data="B")],
        [InlineKeyboardButton("📊 Show Board", callback_data="board")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗳️ Vote karo:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user.id
    data = query.data

    if data in ["A", "B"]:
        votes[str(user)] = data
        save_votes()
        await query.edit_message_text(f"✅ Tune vote kiya: {data}")

    elif data == "board":
        a = sum(1 for v in votes.values() if v == "A")
        b = sum(1 for v in votes.values() if v == "B")
        await query.edit_message_text(
            f"📊 *Live Board*\n"
            f"✅ Option A: {a} votes\n"
            f"✅ Option B: {b} votes\n"
            f"Total: {len(votes)}"
        )

def main():
    load_votes()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__ == "__main__":
    main()