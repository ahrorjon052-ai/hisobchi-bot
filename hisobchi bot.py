import logging
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler

# --- SOZLAMALAR ---
BOT_TOKEN = "8350521805:AAFM4fJIn6TSvAmBRnLqx5YILWgFWS0maes"

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

# --- HEALTH CHECK SERVER (Render o'chib qolmasligi uchun) ---
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

# --- KLAVIATURA ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("➕ Kirim"), KeyboardButton("➖ Chiqim")],
        [KeyboardButton("📊 Balans"), KeyboardButton("📅 Hisobot")],
        [KeyboardButton("🔄 Restart")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- START FUNKSIYASI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Xush kelibsiz! Men sizning shaxsiy moliya yordamchingizman.\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=main_menu_keyboard()
    )

# --- TRANZAKSIYA BOSHLASH ---
async def start_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['type'] = "Kirim" if "➕" in text else "Chiqim"
    
    await update.message.reply_text(
        f"{context.user_data['type']} summasini kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Amal bekor qilindi.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    try:
        context.user_data['amount'] = float(update.message.text)
        await update.message.reply_text("Sababini (nima uchunligini) kiriting:")
        return REASON
    except ValueError:
        await update.message.reply_text("Iltimos, faqat raqam kiriting (masalan: 50000):")
        return AMOUNT

async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    user_id = update.effective_user.id
    t_type = context.user_data['type']
    amount = context.user_data['amount']
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", (user_id, t_type, amount, reason, date_now))
    conn.commit()
    conn.close()

    emoji = "✅" if t_type == "Kirim" else "❌"
    await update.message.reply_text(
        f"{emoji} Saqlandi!\n💰 Summa: {amount} so'm\n📌 Sabab: {reason}",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# --- BALANS VA HISOBOT ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("SELECT type, amount FROM transactions WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    kirim = sum(r[1] for r in rows if r[0] == "Kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "Chiqim")
    
    text = (f"💰 Umumiy balansingiz:\n\n"
            f"➕ Kirim: {kirim:,.0f} so'm\n"
            f"➖ Chiqim: {chiqim:,.0f} so'm\n"
            f"💳 Sof balans: {(kirim - chiqim):,.0f} so'm")
    await update.message.reply_text(text)

async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    one_month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE user_id=? AND date >= ? ORDER BY date DESC", (user_id, one_month_ago))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("Oxirgi 30 kunda ma'lumotlar mavjud emas.")
        return

    report = "📋 Oxirgi 1 oylik hisobot:\n\n"
    for r in rows[:15]: # Oxirgi 15 ta amalni ko'rsatish
        sign = "➕" if r[1] == "Kirim" else "➖"
        report += f"🕒 {r[4][5:16]} | {sign}{r[2]:,.0f} | {r[3]}\n"
    
    await update.message.reply_text(report)

async def restart_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🔄 Barcha ma'lumotlaringiz o'chirib tashlandi.", reply_markup=main_menu_keyboard())

# --- ASOSIY ---
if __name__ == '__main__':
    init_db()
    
    # Render uchun portni ochiq saqlash
    threading.Thread(target=run_health_check, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(➕ Kirim|➖ Chiqim)$'), start_transaction)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex('^📊 Balans$'), show_balance))
    app.add_handler(MessageHandler(filters.Regex('^📅 Hisobot$'), show_report))
    app.add_handler(MessageHandler(filters.Regex('^🔄 Restart$'), restart_history))
    app.add_handler(conv_handler)

    print("Bot ishga tushdi...")
    app.run_polling()
