import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

# --- SOZLAMALAR ---
# Xavfsizlik uchun tokenni o'zgaruvchidan yoki muhitdan olish yaxshi
BOT_TOKEN = "8350521805:AAFM4fJIn6TSvAmBRnLqx5YILWgFWS0maes"
CHANNEL_ID = "@qashqirlar_makoniuzbek" 
PORT = int(os.environ.get('PORT', '8443')) # Portni muhitdan oladi yoki 8443 dan foydalanadi

# Holatlar
AMOUNT, REASON = range(2)

# Loglash
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (user_id INTEGER, type TEXT, amount REAL, reason TEXT, date TEXT)''')
    conn.commit()
    conn.close()

# --- ASOSIY KLAVIATURA ---
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("➕ Kirim"), KeyboardButton("➖ Chiqim")],
        [KeyboardButton("📊 Balans"), KeyboardButton("📅 Hisobot")],
        [KeyboardButton("🔄 Restart")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- OBUNANI TEKSHIRISH ---
async def is_subscribed(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# --- HANDLERLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_subscribed(user_id, context):
        await update.message.reply_text("📌 Asosiy menyu", reply_markup=main_menu_keyboard())
    else:
        keyboard = [
            [InlineKeyboardButton("Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("Obuna bo'ldim ✅", callback_data="check_subs")]
        ]
        await update.message.reply_text(
            f"Botdan foydalanish uchun {CHANNEL_ID} kanaliga a'zo bo'ling!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

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
    except ValueError:
        await update.message.reply_text("Faqat raqam kiriting!")
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
    await update.message.reply_text(f"{emoji} {amount} so'm qo'shildi.\n📌 Sabab: {reason}", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await filter_subscribers(update, context): return
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("SELECT type, amount FROM transactions WHERE user_id=?", (update.effective_user.id,))
    rows = c.fetchall()
    conn.close()
    
    kirim = sum(r[1] for r in rows if r[0] == "Kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "Chiqim")
    text = (f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"➕ Kirim: {kirim} so'm\n➖ Chiqim: {chiqim} so'm\n"
            f"💳 Balans: {kirim - chiqim} so'm")
    await update.message.reply_text(text)

async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await filter_subscribers(update, context): return
    user_id = update.effective_user.id
    one_month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE user_id=? AND date >= ?", (user_id, one_month_ago))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("Ma'lumot topilmadi.")
        return

    report = "📋 1 oylik hisobot:\n\n"
    for r in rows:
        sign = "+" if r[1] == "Kirim" else "-"
        report += f"🕒 {r[4]} | {sign}{r[2]} | {r[3]}\n"
    await update.message.reply_text(report)

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await filter_subscribers(update, context): return
    conn = sqlite3.connect('finance_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE user_id=?", (update.effective_user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🔄 Tarix tozalandi.", reply_markup=main_menu_keyboard())

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(➕ Kirim|➖ Chiqim)$'), start_transaction)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
        },
        fallbacks=[CommandHandler('cancel', start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_button_callback, pattern="check_subs"))
    app.add_handler(MessageHandler(filters.Regex('^📊 Balans$'), show_balance))
    app.add_handler(MessageHandler(filters.Regex('^📅 Hisobot$'), show_report))
    app.add_handler(MessageHandler(filters.Regex('^🔄 Restart$'), restart))
    app.add_handler(conv_handler)

    print(f"Bot {PORT} portida ishga tushmoqda...")
    
    # Portda ishlashi uchun Webhook yoki Polling'ni port bilan sozlash:
    # Render yoki shunga o'xshash servislar uchun run_polling ham ishlayveradi, 
    # lekin PORT o'zgaruvchisini aniqlash majburiy.
    app.run_polling(poll_interval=1.0)
