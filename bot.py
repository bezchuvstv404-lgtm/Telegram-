import asyncio
import sqlite3
import os
import threading
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
import urllib.parse
import urllib.request

# ==========================================
# НАСТРОЙКИ (из config.py)
# ==========================================
from config import BOT_TOKEN, ADMIN_ID, YOOMONEY_WALLET

NAME, PRICE, CODE = range(3)

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect('shop.db')
    conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER, code TEXT, created_at TIMESTAMP)")
    conn.commit()
    conn.close()
init_db()

def get_products():
    conn = sqlite3.connect('shop.db')
    rows = conn.execute("SELECT id, name, price, code FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return rows

def add_product(name, price, code):
    conn = sqlite3.connect('shop.db')
    conn.execute("INSERT INTO products(name, price, code, created_at) VALUES(?, ?, ?, ?)", 
                 (name, price, code, datetime.now()))
    conn.commit()
    conn.close()

def get_product(product_id):
    conn = sqlite3.connect('shop.db')
    row = conn.execute("SELECT id, name, price, code FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    return row

def delete_product(product_id):
    conn = sqlite3.connect('shop.db')
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = [[btn("🛒 МАГАЗИН", "shop")]]
    if user_id == ADMIN_ID:
        rows.append([btn("➕ ДОБАВИТЬ ТОВАР", "add_product")])
        rows.append([btn("🗑️ УДАЛИТЬ ТОВАР", "delete_product")])
    markup = InlineKeyboardMarkup(rows)
    await update.message.reply_text(
        "🏪 *МАГАЗИН ТОВАРОВ*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=markup
    )

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = update.effective_user.id
        rows = [[btn("🛒 МАГАЗИН", "shop")]]
        if user_id == ADMIN_ID:
            rows.append([btn("➕ ДОБАВИТЬ ТОВАР", "add_product")])
            rows.append([btn("🗑️ УДАЛИТЬ ТОВАР", "delete_product")])
        markup = InlineKeyboardMarkup(rows)
        await query.edit_message_text(
            "🏪 *МАГАЗИН ТОВАРОВ*\n\nВыберите действие:",
            parse_mode="Markdown",
            reply_markup=markup
        )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        products = get_products()
        if not products:
            await query.edit_message_text("❌ Товаров нет!", reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "start")]]))
            return
        rows = []
        for pid, name, price, code in products:
            rows.append([btn(f"📦 {name} — {price} ₽", f"buy_{pid}")])
        rows.append([btn("🔙 НАЗАД", "start")])
        await query.edit_message_text("🛒 *ВЫБЕРИТЕ ТОВАР:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = update.effective_user.id
        product_id = int(query.data.split("_")[1])
        product = get_product(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден!")
            return
        pid, name, price, code = product
        context.user_data['buy_product_id'] = pid
        label = f"rub_{pid}_{user_id}_{int(datetime.now().timestamp())}"
        payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=small&sum={price}&label={label}"
        await query.edit_message_text(
            f"💳 *ОПЛАТА {price} ₽*\n\n📦 *Товар:* {name}\n🔑 *Код:* `{code}`\n\n🔗 [Нажмите для оплаты]({payment_url})\n\n✅ После оплаты товар придёт сюда!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "shop")]])
        )

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("✏️ Введите НАЗВАНИЕ товара:")
        return NAME

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 1:
        await update.message.reply_text("❌ Название не может быть пустым!")
        return NAME
    context.user_data['new_name'] = name
    await update.message.reply_text("💰 Введите ЦЕНУ в рублях:")
    return PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price < 1:
            await update.message.reply_text("❌ Цена должна быть больше 0!")
            return PRICE
        context.user_data['new_price'] = price
        await update.message.reply_text("🔑 Введите КОД товара:")
        return CODE
    except:
        await update.message.reply_text("❌ Введите число!")
        return PRICE

async def add_product_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if len(code) < 1:
        await update.message.reply_text("❌ Код не может быть пустым!")
        return CODE
    name = context.user_data.get('new_name', 'Без названия')
    price = context.user_data.get('new_price', 0)
    add_product(name, price, code)
    await update.message.reply_text(
        f"✅ *ТОВАР ДОБАВЛЕН!*\n\n📦 Название: {name}\n💰 Цена: {price} ₽\n🔑 Код: `{code}`\n\nТовар доступен в магазине!",
        parse_mode="Markdown"
    )
    user_id = update.effective_user.id
    rows = [[btn("🛒 МАГАЗИН", "shop")]]
    if user_id == ADMIN_ID:
        rows.append([btn("➕ ДОБАВИТЬ ТОВАР", "add_product")])
        rows.append([btn("🗑️ УДАЛИТЬ ТОВАР", "delete_product")])
    markup = InlineKeyboardMarkup(rows)
    await update.message.reply_text("🏪 *МАГАЗИН ТОВАРОВ*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=markup)
    return ConversationHandler.END

async def delete_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        products = get_products()
        if not products:
            await query.edit_message_text("❌ Нет товаров для удаления!")
            return
        rows = []
        for pid, name, price, code in products:
            rows.append([btn(f"🗑️ {name}", f"del_{pid}")])
        rows.append([btn("🔙 НАЗАД", "start")])
        await query.edit_message_text("🗑️ *ВЫБЕРИТЕ ТОВАР ДЛЯ УДАЛЕНИЯ:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def delete_product_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        product_id = int(query.data.split("_")[1])
        product = get_product(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден!")
            return
        pid, name, price, code = product
        await query.edit_message_text(
            f"⚠️ *ВЫ УВЕРЕНЫ?*\n\n📦 {name}\n💰 {price} ₽\n\nЭто действие нельзя отменить!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("✅ ДА, УДАЛИТЬ", f"del_yes_{pid}")],
                [btn("❌ ОТМЕНА", "delete_product")]
            ])
        )

async def delete_product_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        product_id = int(query.data.split("_")[2])
        product = get_product(product_id)
        if not product:
            await query.edit_message_text("❌ Товар не найден!")
            return
        delete_product(product_id)
        await query.edit_message_text("✅ *ТОВАР УДАЛЁН!*", reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "start")]]))

# ==========================================
# FLASK-СЕРВЕР ДЛЯ УВЕДОМЛЕНИЙ ЮMONEY
# ==========================================
app = Flask(__name__)

@app.route('/', methods=['POST'])
def yoomoney_notification():
    return 'OK', 200

@app.route('/')
def index():
    return 'Server is ready for YooMoney! POST to /'

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ЗАПУСК (В ДВУХ ПОТОКАХ)
# ==========================================
def main():
    threading.Thread(target=run_flask).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app_bot = Application.builder().token(BOT_TOKEN).build()
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_product_start, pattern="^add_product$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_code)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app_bot.add_handler(add_conv)
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app_bot.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    app_bot.add_handler(CallbackQueryHandler(buy, pattern="^buy_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_start, pattern="^delete_product$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_confirm, pattern="^del_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_yes, pattern="^del_yes_\\d+$"))
    print("=" * 60)
    print("🚀 БОТ И СЕРВЕР ЗАПУЩЕНЫ!")
    print("📌 /start — главное меню")
    print("=" * 60)
    app_bot.run_polling()

if __name__ == "__main__":
    main()
