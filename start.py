# ==========================================
# ЧАСТЬ 1: ИМПОРТЫ, НАСТРОЙКИ, БАЗА ДАННЫХ
# ==========================================

import asyncio
import sqlite3
import os
import threading
import re
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    ConversationHandler, MessageHandler, filters, PreCheckoutQueryHandler
)
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import urllib.parse
import urllib.request

# ==========================================
# НАСТРОЙКИ (из config.py)
# ==========================================
from config import BOT_TOKEN, ADMIN_ID, YOOMONEY_WALLET, API_ID, API_HASH

# Состояния для ConversationHandler
NAME, PRICE, CODE = range(3)

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect('shop.db')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, 
            price INTEGER, 
            code TEXT, 
            created_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            product_id INTEGER, 
            status TEXT, 
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
init_db()

# ==========================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ
# ==========================================
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

def save_order(user_id, product_id):
    conn = sqlite3.connect('shop.db')
    conn.execute("INSERT INTO orders(user_id, product_id, status, created_at) VALUES(?, ?, ?, ?)", 
                 (user_id, product_id, 'pending', datetime.now()))
    conn.commit()
    conn.close()

def update_order_status(order_id, status):
    conn = sqlite3.connect('shop.db')
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

def kb(*rows):
    return InlineKeyboardMarkup(list(rows))

def send_telegram(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# Глобальные словари для Telethon
paid_sessions = {}
clients = {}
# ==========================================
# ЧАСТЬ 2: TELETHON — РАБОТА С ТЕЛЕФОНОМ
# ==========================================

# ==========================================
# TELETHON — ФУНКЦИИ ДЛЯ ВХОДА
# ==========================================
async def send_code(phone, chat_id):
    try:
        session_name = f'session_{chat_id}'
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        clients[chat_id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': result.phone_code_hash
        }
        return True, None
    except Exception as e:
        return False, str(e)

async def check_code(code, chat_id):
    try:
        if chat_id not in clients:
            return False, None, "Ошибка сессии"
        client = clients[chat_id]['client']
        phone = clients[chat_id]['phone']
        phone_code_hash = clients[chat_id]['phone_code_hash']
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        me = await client.get_me()
        await client.disconnect()
        del clients[chat_id]
        return True, me.first_name, None
    except errors.SessionPasswordNeededError:
        return False, None, "2FA"
    except Exception as e:
        return False, None, str(e)

async def check_password(password, chat_id):
    try:
        if chat_id not in clients:
            return False, None, "Ошибка сессии"
        client = clients[chat_id]['client']
        await client.sign_in(password=password)
        me = await client.get_me()
        await client.disconnect()
        del clients[chat_id]
        return True, me.first_name, None
    except Exception as e:
        return False, None, str(e)

# ==========================================
# ПОЛУЧЕНИЕ КОДА ЧЕРЕЗ TELETHON
# ==========================================
async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data.split("_")
    nid = int(data[2])

    session_data = paid_sessions.get(uid)
    if not session_data:
        await query.edit_message_text("❌ Данные не найдены. Сначала оплатите номер.")
        return

    phone = session_data["phone"]
    session_str = session_data["session"]

    await query.edit_message_text(f"📲 Подключаюсь к аккаунту `{phone}`...", parse_mode="Markdown")

    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            await query.edit_message_text(
                "❌ Аккаунт не авторизован", 
                reply_markup=kb([btn("🔙 НАЗАД", "start")])
            )
            return

        # Ищем самый последний код (5-6 цифр)
        code_found = None
        last_time = 0
        async for dialog in client.iter_dialogs():
            async for msg in client.iter_messages(dialog.id, limit=30):
                if msg and msg.text and not msg.out:
                    match = re.search(r'\b(\d{5,6})\b', msg.text)
                    if match:
                        code = match.group(1)
                        # Исключаем простые коды
                        if len(set(code)) >= 3 and code not in ["10000", "11111", "12345", "00000"]:
                            t = msg.date.timestamp() if msg.date else 0
                            if t > last_time:
                                code_found = code
                                last_time = t
            if code_found:
                break

        await client.disconnect()

        if code_found:
            ts = datetime.fromtimestamp(last_time).strftime('%H:%M:%S') if last_time else "недавно"
            await query.edit_message_text(
                f"🔑 *КОД НАЙДЕН!*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"🔑 Код: `{code_found}`\n"
                f"⏰ Время: {ts}\n\n"
                f"✅ Код подошёл для входа?\n"
                f"Если нет — нажмите «Запросить новый код»",
                parse_mode="Markdown",
                reply_markup=kb(
                    [btn("✅ КОД ПОДОШЁЛ", f"code_ok_{nid}")],
                    [btn("🔄 ЗАПРОСИТЬ НОВЫЙ КОД", f"get_code_{nid}")]
                )
            )
        else:
            await query.edit_message_text(
                f"⏳ *Код не найден*\n\n"
                f"📞 `{phone}`\n\n"
                f"Возможно, код ещё не пришёл.\n"
                f"Попробуйте ещё раз.",
                parse_mode="Markdown",
                reply_markup=kb([btn("🔄 ПОВТОРИТЬ ПОИСК", f"get_code_{nid}")])
            )

    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка: {e}", 
            reply_markup=kb([btn("🔙 НАЗАД", "start")])
        )

async def code_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Отлично!")

    uid = query.from_user.id
    data = query.data.split("_")
    nid = int(data[2])

    if uid in paid_sessions:
        del paid_sessions[uid]

    await query.edit_message_text(
        f"🎉 *СДЕЛКА ЗАВЕРШЕНА!*\n\n"
        f"✅ Код подошёл! Аккаунт ваш!\n\n"
        f"Спасибо за покупку! 🙏",
        parse_mode="Markdown",
        reply_markup=kb([btn("🏠 ГЛАВНОЕ МЕНЮ", "start")])
    )
  # ==========================================
# ЧАСТЬ 3: ОСНОВНАЯ ЛОГИКА БОТА
# ==========================================

# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================
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

# ==========================================
# МАГАЗИН
# ==========================================
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        products = get_products()
        if not products:
            await query.edit_message_text(
                "❌ Товаров нет!", 
                reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "start")]])
            )
            return
        rows = []
        for pid, name, price, code in products:
            rows.append([btn(f"📦 {name} — {price} ₽", f"buy_{pid}")])
        rows.append([btn("🔙 НАЗАД", "start")])
        await query.edit_message_text(
            "🛒 *ВЫБЕРИТЕ ТОВАР:*", 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(rows)
        )

# ==========================================
# ПОКУПКА (ЮMoney)
# ==========================================
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
            f"💳 *ОПЛАТА {price} ₽*\n\n"
            f"📦 *Товар:* {name}\n"
            f"🔒 *Код будет выдан после оплаты*\n\n"
            f"🔗 [Нажмите для оплаты]({payment_url})\n\n"
            f"✅ После оплаты код придёт сюда!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "shop")]])
        )

# ==========================================
# ДОБАВЛЕНИЕ ТОВАРА (АДМИН)
# ==========================================
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
        await update.message.reply_text("🔑 Введите КОД товара (будет выдан после оплаты):")
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
        f"✅ *ТОВАР ДОБАВЛЕН!*\n\n"
        f"📦 Название: {name}\n"
        f"💰 Цена: {price} ₽\n"
        f"🔒 Код будет выдан ПОСЛЕ оплаты",
        parse_mode="Markdown"
    )
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
    return ConversationHandler.END

# ==========================================
# УДАЛЕНИЕ ТОВАРА (АДМИН)
# ==========================================
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
        await query.edit_message_text(
            "🗑️ *ВЫБЕРИТЕ ТОВАР ДЛЯ УДАЛЕНИЯ:*", 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(rows)
        )

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
            f"⚠️ *ВЫ УВЕРЕНЫ?*\n\n"
            f"📦 {name}\n"
            f"💰 {price} ₽\n\n"
            f"Это действие нельзя отменить!",
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
        await query.edit_message_text(
            "✅ *ТОВАР УДАЛЁН!*", 
            reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "start")]])
        )

# ==========================================
# ОПЛАТА ЧЕРЕЗ TELEGRAM STARS (заглушка)
# ==========================================
async def pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Здесь логика оплаты Stars (добавьте при необходимости)
    pass

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Здесь логика успешной оплаты Stars
    pass
  # ==========================================
# ЧАСТЬ 4: FLASK-СЕРВЕР И ЗАПУСК
# ==========================================

# ==========================================
# FLASK-СЕРВЕР ДЛЯ УВЕДОМЛЕНИЙ ЮMONEY
# ==========================================
app = Flask(__name__)

@app.route('/', methods=['POST'])
def yoomoney_notification():
    try:
        params = request.form.to_dict()
        print(f"📩 Уведомление от ЮMoney: {params}")

        label = params.get('label')
        if not label:
            return 'Label not found', 400

        parts = label.split('_')
        if len(parts) < 3 or not label.startswith('rub_'):
            return 'Invalid label', 400

        product_id = int(parts[1])
        user_id = int(parts[2])

        product = get_product(product_id)
        if not product:
            print(f"❌ Товар с ID {product_id} не найден!")
            return 'Product not found', 404

        pid, name, price, code = product

        buyer_msg = f"✅ *ОПЛАЧЕНО!*\n\n"
        buyer_msg += f"📦 *Товар:* {name}\n"
        buyer_msg += f"🔑 *Код:* `{code}`\n\n"
        buyer_msg += f"🎁 Спасибо за покупку!"

        admin_msg = f"📦 *Новая продажа!*\n\n"
        admin_msg += f"👤 Покупатель: {user_id}\n"
        admin_msg += f"📦 Товар: {name}\n"
        admin_msg += f"💰 Сумма: {price} RUB"

        send_telegram(user_id, buyer_msg)
        send_telegram(ADMIN_ID, admin_msg)

        delete_product(product_id)

        return 'OK', 200
    except Exception as e:
        print(f"❌ Ошибка обработки уведомления: {e}")
        return 'Error', 500

@app.route('/')
def index():
    return 'Server is ready for YooMoney! POST to /'

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# ЗАПУСК БОТА
# ==========================================
def main():
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask).start()
    
    # Создаём бота
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app_bot = Application.builder().token(BOT_TOKEN).build()

    # Конверсация для добавления товара
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_product_start, pattern="^add_product$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_code)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    # Добавляем все обработчики
    app_bot.add_handler(add_conv)
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app_bot.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    app_bot.add_handler(CallbackQueryHandler(buy, pattern="^buy_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_start, pattern="^delete_product$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_confirm, pattern="^del_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(delete_product_yes, pattern="^del_yes_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(get_code, pattern="^get_code_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(code_ok, pattern="^code_ok_\\d+$"))
    app_bot.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app_bot.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("=" * 60)
    print("🚀 БОТ И СЕРВЕР ЗАПУЩЕНЫ!")
    print("📌 /start — главное меню")
    print("📌 Админ: ➕ ДОБАВИТЬ ТОВАР → название → цена → код")
    print("📌 После оплаты ЮMoney бот автоматически выдаёт товар!")
    print("=" * 60)

    app_bot.run_polling()

if __name__ == "__main__":
    main()
  
