import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

TOKEN = "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"  # YAHAN DAAL DE

votes = {"A": 0, "B": 0}

async def start(update, context):
    keyboard = [[InlineKeyboardButton("✅ A", callback_data="A"), InlineKeyboardButton("✅ B", callback_data="B")],
                [InlineKeyboardButton("📊 Board", callback_data="board")]]
    await update.message.reply_text("VOTE:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "board":
        await query.edit_message_text(f"📊 A: {votes['A']} | B: {votes['B']}")
    else:
        votes[query.data] += 1
        await query.edit_message_text(f"✅ Voted {query.data}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.run_polling()
