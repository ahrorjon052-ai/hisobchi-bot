import logging
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

# --- SOZLAMALAR ---
BOT_TOKEN = "8350521805:AAFM4fJIn6TSvAmBRnLqx5YILWgFWS0maes"
CHANNEL_ID = "@qashqirlar_makoniuzbek"

# Holatlar
AMOUNT, REASON = range(2)

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (user_id INTEGER, type TEXT, amount REAL, reason TEXT, date TEXT)''')
    conn.commit()
    conn.close()

# --- HEALTH CHECK SERVER (Render uchun) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("Bot is alive!", "utf-8"))

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    httpd.serve_forever()

# --- KLAVIATURALAR ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("➕ Kirim"), KeyboardButton("➖ Chiqim")],
        [KeyboardButton("📊 Balans"), KeyboardButton("📅 Hisobot")],
        [KeyboardButton("🔄 Restart")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- FUNKSIYALAR ---
async def is_subscribed(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_subscribed(user_id, context):
        await update.message.reply_text("📌 Asosiy menyu", reply_markup=main_menu_keyboard())
    else:
        keyboard = [
            [InlineKeyboardButton("Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("Obuna bo'ldim ✅", callback_data="check_subs")]
        ]
        await update.message.reply_text(f"Botdan foydalanish uchun {CHANNEL_ID} kanaliga a'zo bo'ling!", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await is_subscribed(query.from_user.id, context):
        await query.answer("Rahmat! Obuna tasdiqlandi.")
        await query.message.delete()
        await query.message.reply_text("✅ Xush kelibsiz!", reply_markup=main_menu_keyboard())
    else:
        await query.answer("Siz hali kanalga a'zo emassiz! ❌", show_alert=True)

async def filter_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_subscribed(update.effective_user.id, context):
        await start(update, context)
        return False
    return True

async def start_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await filter_subscribers(update, context): return
    context.user_data['type'] = "Kirim" if "➕" in update.message.text else "Chiqim"
    await update.message.reply_text(f"{context.user_data['type']} summasini kiriting:", 
                                   reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True))
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    try:
        context.user_data['amount'] = float(update.message.text)
        await update.message.reply_text("Sababini kiriting:")
        return REASON
    except:
        await update.message.reply_text("Faqat raqam kiriting!")
        return AMOUNT

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", 
              (user_id, context.user_data['type'], context.user_data['amount'], reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Saqlandi!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await filter_subscribers(update, context): return
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("SELECT type, amount FROM transactions WHERE user_id=?", (update.effective_user.id,))
    rows = c.fetchall()
    kirim = sum(r[1] for r in rows if r[0] == "Kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "Chiqim")
    await update.message.reply_text(f"➕ Kirim: {kirim}\n➖ Chiq
