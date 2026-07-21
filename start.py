import sqlite3
import re
import asyncio
from datetime import datetime
from urllib.parse import urlencode
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# ==========================================
# ИМПОРТ НАСТРОЕК ИЗ ОТДЕЛЬНОЙ ПАПКИ
# ==========================================
from config.config import BOT_TOKEN, API_ID, API_HASH, MASTER_ADMIN_ID, YOOMONEY_WALLET

DB_NAME = "numbers.db"

# Состояния для добавления номера
PRICE_RUB, PRICE_STARS, PHONE, AUTH_CODE, AUTH_2FA = range(5)

# Глобальные словари
pending_auth = {}
pending_rub = {}
paid_sessions = {}

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DROP TABLE IF EXISTS numbers")
    conn.execute("""
        CREATE TABLE numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            session TEXT,
            price_rub INTEGER,
            price_stars INTEGER
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
    print("✅ База данных готова")

def num_add(phone: str, session: str, price_rub: int, price_stars: int):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT INTO numbers(phone, session, price_rub, price_stars) VALUES(?,?,?,?)",
                 (phone, session, price_rub, price_stars))
    conn.commit()
    conn.close()

def num_all():
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("SELECT id, phone, price_stars, price_rub FROM numbers").fetchall()
    conn.close()
    return rows

def num_del(nid: int):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM numbers WHERE id=?", (nid,))
    conn.commit()
    conn.close()

def num_get(nid: int):
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute("SELECT id, phone, session, price_rub, price_stars FROM numbers WHERE id=?", (nid,)).fetchone()
    conn.close()
    return row

init_db()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def is_admin(uid: int) -> bool:
    return uid == MASTER_ADMIN_ID

def hide_phone(phone: str) -> str:
    return phone[:4] + "****" + phone[-4:] if len(phone) >= 8 else phone

def generate_yoomoney_link(amount: int, label: str) -> str:
    return "https://yoomoney.ru/quickpay/confirm.xml?" + urlencode({
        "receiver": YOOMONEY_WALLET,
        "quickpay-form": "small",
        "sum": f"{amount:.2f}",
        "label": label
    })

def btn(text: str, cb: str):
    return InlineKeyboardButton(text, callback_data=cb)

def kb(*rows):
    return InlineKeyboardMarkup(list(rows))

def back(cb: str = "start"):
    return kb([btn("🔙 НАЗАД", cb)])

# ==========================================
# ОТПРАВКА В TELEGRAM
# ==========================================
def send_telegram(chat_id: int, text: str):
    try:
        import urllib.parse
        import urllib.request
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
        # ==========================================
# ГЛАВНОЕ МЕНЮ И АДМИН-ПАНЕЛЬ
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"🏠 ГЛАВНОЕ МЕНЮ\n\n👋 Привет, {user.first_name}!"
    rows = [[btn("🛒 КУПИТЬ НОМЕР", "buy_menu")]]
    if is_admin(user.id):
        rows.append([btn("👑 АДМИН ПАНЕЛЬ", "admin_panel")])
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "👑 АДМИН ПАНЕЛЬ",
        reply_markup=kb(
            [btn("➕ ДОБАВИТЬ НОМЕР", "add_number")],
            [btn("🔙 НАЗАД", "start")]
        )
    )

# ==========================================
# ДОБАВЛЕНИЕ НОМЕРА (АДМИН)
# ==========================================
async def add_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("💰 Введите цену в РУБЛЯХ:", reply_markup=back("admin_panel"))
    return PRICE_RUB

async def add_price_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price_rub"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число:", reply_markup=back("admin_panel"))
        return PRICE_RUB
    await update.message.reply_text("⭐ Введите цену в STARS:")
    return PRICE_STARS

async def add_price_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price_stars"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число:", reply_markup=back("admin_panel"))
        return PRICE_STARS
    await update.message.reply_text("📞 Введите номер телефона (с +):")
    return PHONE

async def add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith('+') or len(phone) < 8:
        await update.message.reply_text("❌ Формат: +79123456789", reply_markup=back("admin_panel"))
        return PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text("🔐 Отправляю код подтверждения в Telegram...")

    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)

        pending_auth[update.effective_user.id] = {
            "phone": phone,
            "price_rub": context.user_data["price_rub"],
            "price_stars": context.user_data["price_stars"],
            "client": client,
            "phone_code_hash": result.phone_code_hash
        }

        await update.message.reply_text("✏️ Введите код из Telegram (цифры):", reply_markup=back("admin_panel"))
        return AUTH_CODE

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=back("admin_panel"))
        return ConversationHandler.END

async def add_auth_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    auth_data = pending_auth.get(user_id)
    if not auth_data:
        await update.message.reply_text("❌ Сессия истекла. Начните заново.", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    code = update.message.text.strip().replace(" ", "")
    client = auth_data["client"]
    phone = auth_data["phone"]
    phone_code_hash = auth_data["phone_code_hash"]

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        session_str = client.session.save()
        await client.disconnect()

        num_add(phone, session_str, auth_data["price_rub"], auth_data["price_stars"])
        pending_auth.pop(user_id, None)

        await update.message.reply_text(
            f"✅ *НОМЕР ДОБАВЛЕН!*\n\n"
            f"📞 {hide_phone(phone)}\n"
            f"💰 Цена: {auth_data['price_rub']} ₽\n"
            f"⭐ Цена: {auth_data['price_stars']} Stars\n\n"
            f"🔥 Номер доступен в магазине!",
            parse_mode="Markdown",
            reply_markup=kb([btn("🔙 В МЕНЮ", "start")])
        )
        return ConversationHandler.END

    except errors.SessionPasswordNeededError:
        await update.message.reply_text("🔐 Требуется пароль двухфакторной аутентификации.\nВведите пароль 2FA:")
        return AUTH_2FA

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=back("admin_panel"))
        pending_auth.pop(user_id, None)
        return ConversationHandler.END

async def add_auth_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    auth_data = pending_auth.get(user_id)
    if not auth_data:
        await update.message.reply_text("❌ Сессия истекла. Начните заново.", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    password = update.message.text.strip()
    client = auth_data["client"]
    phone = auth_data["phone"]

    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        await client.disconnect()

        num_add(phone, session_str, auth_data["price_rub"], auth_data["price_stars"])
        pending_auth.pop(user_id, None)

        await update.message.reply_text(
            f"✅ *НОМЕР ДОБАВЛЕН (2FA)!*\n\n"
            f"📞 {hide_phone(phone)}\n"
            f"💰 Цена: {auth_data['price_rub']} ₽\n"
            f"⭐ Цена: {auth_data['price_stars']} Stars\n\n"
            f"🔥 Номер доступен в магазине!",
            parse_mode="Markdown",
            reply_markup=kb([btn("🔙 В МЕНЮ", "start")])
        )
        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка 2FA: {e}", reply_markup=back("admin_panel"))
        pending_auth.pop(user_id, None)
        return ConversationHandler.END
        # ==========================================
# МАГАЗИН
# ==========================================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nums = num_all()
    if not nums:
        await query.edit_message_text("❌ Нет номеров", reply_markup=back())
        return
    rows = []
    for nid, phone, price_stars, price_rub in nums:
        rows.append([btn(f"📞 {hide_phone(phone)} — {price_stars}⭐ / {price_rub}₽", f"buy_{nid}")])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text(
        "🛒 *ВЫБЕРИТЕ НОМЕР*\n\n🔒 Полный номер откроется ПОСЛЕ оплаты",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def buy_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    num = num_get(nid)
    if not num:
        await query.edit_message_text("❌ Номер не найден", reply_markup=back("buy_menu"))
        return
    _, phone, session, price_rub, price_stars = num
    context.user_data["selected_nid"] = nid
    context.user_data["selected_phone"] = phone
    context.user_data["selected_session"] = session

    await query.edit_message_text(
        f"📞 {hide_phone(phone)}\n⭐ {price_stars} Stars\n💰 {price_rub} ₽\n\nВыберите способ оплаты:",
        reply_markup=kb(
            [btn(f"⭐ ОПЛАТИТЬ {price_stars} STARS", f"pay_stars_{nid}")],
            [btn(f"💳 ОПЛАТИТЬ {price_rub} ₽", f"pay_rub_{nid}")],
            [btn("🔙 НАЗАД", "buy_menu")]
        )
    )

# ==========================================
# ОПЛАТА STARS
# ==========================================
async def pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    num = num_get(nid)
    if not num:
        await query.edit_message_text("❌ Ошибка")
        return
    _, phone, session, price_rub, price_stars = num
    user = update.effective_user

    await context.bot.send_invoice(
        chat_id=user.id,
        title="Номер Telegram",
        description=hide_phone(phone),
        payload=f"stars_{nid}_{user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("Номер", price_stars)],
        start_parameter="buy"
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    parts = payload.split("_")
    nid = int(parts[1])
    user_id = update.effective_user.id

    num = num_get(nid)
    if not num:
        await update.message.reply_text("❌ Ошибка")
        return
    _, phone, session, price_rub, price_stars = num

    num_del(nid)

    paid_sessions[user_id] = {
        "phone": phone,
        "session": session,
        "nid": nid
    }

    await update.message.reply_text(
        f"✅ *ОПЛАЧЕНО {price_stars} STARS!*\n\n"
        f"🔓 *ВАШ НОМЕР:*\n`{phone}`\n\n"
        f"📌 Нажмите кнопку ниже, чтобы получить код для входа:",
        parse_mode="Markdown",
        reply_markup=kb([btn("📲 ПОЛУЧИТЬ КОД", f"get_code_{nid}")])
    )

# ==========================================
# ОПЛАТА РУБЛЯМИ
# ==========================================
async def pay_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    num = num_get(nid)
    if not num:
        await query.edit_message_text("❌ Ошибка", reply_markup=back("buy_menu"))
        return
    _, phone, session, price_rub, price_stars = num
    user = update.effective_user
    label = f"rub_{nid}_{user.id}_{datetime.now().timestamp()}"
    url = generate_yoomoney_link(price_rub, label)

    pending_rub[user.id] = {"nid": nid, "phone": phone, "session": session, "price_rub": price_rub}

    await query.edit_message_text(
        f"💳 *ОПЛАТА {price_rub} ₽*\n\n"
        f"📞 {hide_phone(phone)}\n\n"
        f"[🔗 НАЖМИТЕ ДЛЯ ОПЛАТЫ]({url})\n\n"
        f"✅ *После оплаты* нажмите кнопку «ПРОВЕРИТЬ ОПЛАТУ»",
        parse_mode="Markdown",
        reply_markup=kb([btn("✅ ПРОВЕРИТЬ ОПЛАТУ", f"check_rub_{nid}")], [btn("🔙 НАЗАД", "buy_menu")])
    )

# ==========================================
# ПРОВЕРКА ОПЛАТЫ РУБЛЯМИ
# ==========================================
async def check_rub_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data.split("_")
    nid = int(data[2])
    
    pending = pending_rub.get(user_id)
    if not pending or pending["nid"] != nid:
        await query.edit_message_text("❌ Нет ожидающих оплат", reply_markup=back("buy_menu"))
        return
    
    phone = pending["phone"]
    session = pending["session"]
    price_rub = pending["price_rub"]
    
    num_del(nid)
    
    paid_sessions[user_id] = {
        "phone": phone,
        "session": session,
        "nid": nid
    }
    
    pending_rub.pop(user_id, None)
    
    await query.edit_message_text(
        f"✅ *ОПЛАЧЕНО {price_rub} ₽!*\n\n"
        f"🔓 *ВАШ НОМЕР:*\n`{phone}`\n\n"
        f"📌 Нажмите кнопку ниже, чтобы получить код для входа:",
        parse_mode="Markdown",
        reply_markup=kb([btn("📲 ПОЛУЧИТЬ КОД", f"get_code_{nid}")])
    )
    # ==========================================
# ПОЛУЧЕНИЕ КОДА (КНОПКА "ПОЛУЧИТЬ КОД")
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
            await query.edit_message_text("❌ Аккаунт не авторизован", reply_markup=kb([btn("🔙 НАЗАД", "start")]))
            return
        
        code_found = None
        last_time = 0
        async for dialog in client.iter_dialogs():
            async for msg in client.iter_messages(dialog.id, limit=30):
                if msg and msg.text and not msg.out:
                    match = re.search(r'\b(\d{5,6})\b', msg.text)
                    if match:
                        code = match.group(1)
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
        await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=kb([btn("🔙 НАЗАД", "start")]))

# ==========================================
# КНОПКА "КОД ПОДОШЁЛ" - ЗАВЕРШАЕТ СДЕЛКУ
# ==========================================
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

        num = num_get(product_id)
        if not num:
            print(f"❌ Товар с ID {product_id} не найден!")
            return 'Product not found', 404

        pid, phone, session, price_rub, price_stars = num

        pending = pending_rub.get(user_id)
        if pending and pending["nid"] == product_id:
            pending_rub.pop(user_id, None)

        num_del(product_id)

        buyer_msg = f"✅ *ОПЛАЧЕНО!*\n\n"
        buyer_msg += f"🔓 *ВАШ НОМЕР:*\n`{phone}`\n\n"
        buyer_msg += f"🎁 Спасибо за покупку!"

        admin_msg = f"📦 *Новая продажа!*\n\n"
        admin_msg += f"👤 Покупатель: {user_id}\n"
        admin_msg += f"📞 Номер: `{phone}`\n"
        admin_msg += f"💰 Сумма: {price_rub} RUB"

        send_telegram(user_id, buyer_msg)
        send_telegram(MASTER_ADMIN_ID, admin_msg)

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
# ЗАПУСК
# ==========================================
def main():
    import threading
    threading.Thread(target=run_flask).start()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app_bot = Application.builder().token(BOT_TOKEN).build()
    
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_number_start, pattern="^add_number$")],
        states={
            PRICE_RUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price_rub)],
            PRICE_STARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price_stars)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone)],
            AUTH_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_auth_code)],
            AUTH_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_auth_2fa)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app_bot.add_handler(add_conv)
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(start, pattern="^start$"))
    app_bot.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app_bot.add_handler(CallbackQueryHandler(buy_menu, pattern="^buy_menu$"))
    app_bot.add_handler(CallbackQueryHandler(buy_number, pattern="^buy_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(pay_rub, pattern="^pay_rub_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(check_rub_payment, pattern="^check_rub_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(get_code, pattern="^get_code_\\d+$"))
    app_bot.add_handler(CallbackQueryHandler(code_ok, pattern="^code_ok_\\d+$"))
    app_bot.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app_bot.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    print("=" * 60)
    print("🚀 БОТ И СЕРВЕР ЗАПУЩЕНЫ!")
    print("📌 /start — главное меню")
    print("📌 Админ: ➕ ДОБАВИТЬ НОМЕР → цена → звёзды → номер → код → 2FA")
    print("📌 Покупатель: 🛒 КУПИТЬ НОМЕР → оплата → получение кода")
    print("📌 ЮMoney: автоматическая выдача товара после оплаты")
    print("=" * 60)
    
    app_bot.run_polling()

if __name__ == "__main__":
    main()
