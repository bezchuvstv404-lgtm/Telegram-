# =====================================================================
# ЧАСТЬ 1: КОНФИГУРАЦИЯ + ИМПОРТЫ
# =====================================================================

import asyncio
import sqlite3
import re
import threading
import requests
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    PreCheckoutQueryHandler
)
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

# ==========================================
# ИМПОРТ ЛИЧНЫХ ДАННЫХ ИЗ CONFIG.PY
# ==========================================
from config import (
    BOT_TOKEN,
    ADMIN_ID,
    API_ID,
    API_HASH,
    YOOMONEY_WALLET,
    DB_NAME,
    ADMIN_CHAT_ID
)

# ==========================================
# СОСТОЯНИЯ ДЛЯ CONVERSATIONHANDLER
# ==========================================
PHONE_PRICE, PHONE_STARS, PHONE_NUMBER = range(10, 13)
ENTER_CODE = 20
ENTER_2FA = 21

# ==========================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ==========================================
clients = {}
accounts = {}
paid_sessions = {}
awaiting_phone_confirmation = {}
pending_rub = {}
clients_lock = asyncio.Lock()
accounts_lock = asyncio.Lock()

print("=" * 60)
print("✅ ЧАСТЬ 1 ЗАГРУЖЕНА: КОНФИГУРАЦИЯ")
print("=" * 60)
# =====================================================================
# ЧАСТЬ 2: РАБОТА С БАЗОЙ ДАННЫХ
# =====================================================================

def init_db():
    """Создаёт таблицу в базе данных"""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            price_rub INTEGER,
            price_stars INTEGER,
            session TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def get_phone_products():
    """Возвращает все номера из базы"""
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute(
        "SELECT id, phone, price_rub, price_stars FROM phone_products ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows

def get_phone_product(product_id):
    """Возвращает один номер по ID"""
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute(
        "SELECT id, phone, price_rub, price_stars, session FROM phone_products WHERE id=?",
        (product_id,)
    ).fetchone()
    conn.close()
    return row

def add_phone_product(phone, price_rub, price_stars, session=""):
    """Добавляет номер в базу данных"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute(
            "INSERT INTO phone_products(phone, price_rub, price_stars, session, created_at) VALUES(?, ?, ?, ?, ?)",
            (phone, price_rub, price_stars, session, datetime.now())
        )
        conn.commit()
        conn.close()
        print(f"✅ Номер {phone} добавлен в базу")
        return True
    except Exception as e:
        print(f"❌ Ошибка добавления: {e}")
        return False

def delete_phone_product(product_id):
    """Удаляет номер из базы данных"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM phone_products WHERE id=?", (product_id,))
        conn.commit()
        conn.close()
        print(f"✅ Номер #{product_id} полностью удалён")
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления: {e}")
        return False

def save_phone_session(phone, session):
    """Сохраняет сессию для номера"""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute(
            "UPDATE phone_products SET session=? WHERE phone=? LIMIT 1",
            (session, phone)
        )
        conn.commit()
        conn.close()
        print(f"✅ Сессия сохранена для {phone}")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения сессии: {e}")
        return False

def get_phone_session(phone):
    """Получает сессию по номеру телефона"""
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute(
        "SELECT session FROM phone_products WHERE phone=? LIMIT 1",
        (phone,)
    ).fetchone()
    conn.close()
    return row[0] if row else None

# Инициализация базы данных
init_db()

print("=" * 60)
print("✅ ЧАСТЬ 2 ЗАГРУЖЕНА: БАЗА ДАННЫХ")
print("=" * 60)
# =====================================================================
# ЧАСТЬ 3: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ + ПРОВЕРКА ОПЛАТЫ
# =====================================================================

def btn(text, cb):
    """Создаёт кнопку"""
    return InlineKeyboardButton(text, callback_data=cb)

def kb(*rows):
    """Создаёт клавиатуру"""
    return InlineKeyboardMarkup(list(rows))

def back(cb="start"):
    """Создаёт кнопку НАЗАД"""
    return kb([btn("🔙 НАЗАД", cb)])

def hide_phone(phone):
    """Скрывает номер телефона"""
    if len(phone) > 6:
        return f"{phone[:4]}****{phone[-4:]}"
    return phone

def validate_phone(phone):
    """Проверяет формат номера"""
    return bool(re.match(r'^\+\d{10,15}$', phone))

def find_code_in_text(text):
    """Находит код (5 цифр) в тексте"""
    match = re.search(r'\b(\d{5})\b', text)
    return match.group(1) if match else None

def check_yoomoney_payment(label):
    """Проверяет статус платежа через API ЮMoney"""
    try:
        url = f"https://yoomoney.ru/api/operation-history?label={label}&records=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            operations = data.get('operations', [])
            if operations:
                for op in operations:
                    if op.get('status') == 'success':
                        return True
        return False
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

print("=" * 60)
print("✅ ЧАСТЬ 3 ЗАГРУЖЕНА: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ")
print("=" * 60)
# =====================================================================
# ЧАСТЬ 4: РАБОТА С TELEGRAM API (TELETHON)
# =====================================================================

async def send_code_to_phone(phone, user_id):
    """Отправляет код на номер"""
    try:
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)

        async with clients_lock:
            clients[user_id] = {
                'client': client,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
        print(f"✅ Код отправлен на {phone}")
        return True, "✅ Код отправлен"
    except Exception as e:
        return False, f"❌ {str(e)[:50]}"

async def enter_code_in_telegram(code, user_id):
    """Вводит код в Telegram и получает сессию"""
    try:
        async with clients_lock:
            if user_id not in clients:
                return False, "Сессия потеряна", None

            data = clients[user_id]
            client = data['client']
            phone = data['phone']
            phone_hash = data['phone_code_hash']

        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        me = await client.get_me()

        session_string = client.session.save()
        save_phone_session(phone, session_string)

        print(f"✅ ВОШЁЛ В АККАУНТ {phone} как {me.first_name}")

        async with accounts_lock:
            if user_id not in accounts:
                accounts[user_id] = {}
            if phone not in accounts[user_id]:
                accounts[user_id][phone] = {
                    'codes': [],
                    'product_id': None,
                    'client': client,
                    'phone': phone,
                    'session': session_string
                }
            else:
                accounts[user_id][phone]['client'] = client

        async with clients_lock:
            del clients[user_id]

        return True, f"✅ Вход как {me.first_name}", me

    except errors.SessionPasswordNeededError:
        return False, "2FA", None
    except errors.InvalidPhoneCodeError:
        return False, "❌ Неверный код", None
    except errors.PhoneCodeExpiredError:
        return False, "❌ Код истёк", None
    except Exception as e:
        return False, str(e), None

async def enter_2fa_in_telegram(password, user_id):
    """Вводит 2FA пароль"""
    try:
        async with clients_lock:
            if user_id not in clients:
                return False, "Сессия потеряна", None

            client = clients[user_id]['client']
            phone = clients[user_id]['phone']

        await client.sign_in(password=password)
        me = await client.get_me()

        session_string = client.session.save()
        save_phone_session(phone, session_string)

        print(f"✅ 2FA ПРОЙДЕНА для {phone}")

        async with accounts_lock:
            if user_id not in accounts:
                accounts[user_id] = {}
            if phone not in accounts[user_id]:
                accounts[user_id][phone] = {
                    'codes': [],
                    'product_id': None,
                    'client': client,
                    'phone': phone,
                    'session': session_string
                }
            else:
                accounts[user_id][phone]['client'] = client

        async with clients_lock:
            del clients[user_id]

        return True, f"✅ 2FA пройдена", me

    except Exception as e:
        return False, str(e), None

async def get_last_code_from_account(phone, session_string):
    """Находит ПОСЛЕДНИЙ ПЯТИЗНАЧНЫЙ КОД из SMS в Telegram"""
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return None, "Аккаунт не авторизован"

        code_found = None
        last_time = 0

        async for dialog in client.iter_dialogs():
            if "Telegram" in dialog.name:
                async for msg in client.iter_messages(dialog.id, limit=30):
                    if not msg or not msg.text or msg.out:
                        continue

                    text = msg.text

                    if "login" in text.lower() or "new device" in text.lower():
                        continue

                    match = re.search(r'\b(\d{5})\b', text)
                    if match:
                        code = match.group(1)
                        t = msg.date.timestamp() if msg.date else 0
                        if t > last_time:
                            code_found = code
                            last_time = t
                            print(f"✅ НАЙДЕН КОД: {code}")

        await client.disconnect()

        if code_found:
            return code_found, "Telegram"
        return None, "Код не найден"

    except Exception as e:
        return None, str(e)

async def listen_codes(client, chat_id, phone):
    """Слушает коды в фоне"""
    last_id = 0
    while True:
        await asyncio.sleep(3)
        try:
            async with accounts_lock:
                if chat_id not in accounts or phone not in accounts[chat_id]:
                    break
            if not client.is_connected():
                await client.connect()
            async for message in client.iter_messages('me', limit=30, min_id=last_id):
                if not message or message.id <= last_id:
                    continue
                text = message.text or ''
                codes = re.findall(r'\b(\d{5})\b', text)
                for code in codes:
                    async with accounts_lock:
                        if chat_id in accounts and phone in accounts[chat_id]:
                            if code not in accounts[chat_id][phone]['codes']:
                                accounts[chat_id][phone]['codes'].append(code)
                    last_id = max(last_id, message.id)
                    print(f"✅ Найден код: {code} для {phone}")
        except:
            await asyncio.sleep(5)

print("=" * 60)
print("✅ ЧАСТЬ 4 ЗАГРУЖЕНА: TELETHON")
print("=" * 60)
# =====================================================================
# ЧАСТЬ 5: ОСНОВНОЙ БОТ
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    user_id = update.effective_user.id
    rows = [[btn("🛒 МАГАЗИН", "shop")]]
    if user_id == ADMIN_ID:
        rows.append([btn("📱 ДОБАВИТЬ НОМЕР", "add_phone")])
        rows.append([btn("🗑️ УДАЛИТЬ НОМЕР", "delete_phone")])
    await update.message.reply_text(
        "🏪 МАГАЗИН НОМЕРОВ\n\nВыбери действие:",
        reply_markup=kb(*rows)
    )

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню (из колбэка)"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    rows = [[btn("🛒 МАГАЗИН", "shop")]]
    if user_id == ADMIN_ID:
        rows.append([btn("📱 ДОБАВИТЬ НОМЕР", "add_phone")])
        rows.append([btn("🗑️ УДАЛИТЬ НОМЕР", "delete_phone")])
    await query.edit_message_text(
        "🏪 МАГАЗИН НОМЕРОВ\n\nВыбери действие:",
        reply_markup=kb(*rows)
    )

async def add_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 Введи цену в рублях:")
    return PHONE_PRICE

async def add_phone_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0!")
            return PHONE_PRICE
        context.user_data['price_rub'] = price
        await update.message.reply_text("⭐ Введи цену в Stars:")
        return PHONE_STARS
    except:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_PRICE

async def add_phone_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stars = int(update.message.text.strip())
        if stars <= 0:
            await update.message.reply_text("❌ Цена должна быть больше 0!")
            return PHONE_STARS
        context.user_data['price_stars'] = stars
        await update.message.reply_text("📱 Введи номер (например, +79991234567):")
        return PHONE_NUMBER
    except:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_STARS

async def add_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not validate_phone(phone):
        await update.message.reply_text("❌ Неверный формат! Пример: +79991234567")
        return PHONE_NUMBER

    context.user_data['adding_phone'] = phone
    context.user_data['adding_price_rub'] = context.user_data['price_rub']
    context.user_data['adding_price_stars'] = context.user_data['price_stars']

    await update.message.reply_text("⏳ Отправляю код на номер...")
    success, msg = await send_code_to_phone(phone, update.effective_user.id)

    if success:
        await update.message.reply_text("📲 Введи код из SMS/Telegram:")
        return ENTER_CODE
    else:
        await update.message.reply_text(msg)
        return PHONE_NUMBER

async def add_phone_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id

    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ Код должен быть из 5 цифр! Попробуй ещё:")
        return ENTER_CODE

    await update.message.reply_text(f"🔑 Ввожу код `{code}` в Telegram...", parse_mode="Markdown")

    success, msg, me = await enter_code_in_telegram(code, user_id)

    if success:
        phone = context.user_data['adding_phone']
        price_rub = context.user_data['adding_price_rub']
        price_stars = context.user_data['adding_price_stars']

        session_string = ""
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')

        result = add_phone_product(phone, price_rub, price_stars, session_string)

        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ!\n\n"
            f"📱 Номер: {phone}\n"
            f"👤 Имя: {me.first_name}\n"
        )

        if result:
            await update.message.reply_text(
                f"✅ НОМЕР ДОБАВЛЕН В МАГАЗИН!\n\n"
                f"📱 {phone}\n"
                f"💰 {price_rub} ₽\n"
                f"⭐ {price_stars} Stars"
            )
        else:
            await update.message.reply_text("❌ Ошибка при добавлении в базу!")

        return ConversationHandler.END

    elif msg == "2FA":
        await update.message.reply_text("🔐 На аккаунте включена 2FA! Введи пароль:")
        return ENTER_2FA
    else:
        await update.message.reply_text(f"❌ {msg}\n\nПопробуй ещё:")
        return ENTER_CODE

async def add_phone_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id

    await update.message.reply_text("🔐 Ввожу пароль 2FA в Telegram...")

    success, msg, me = await enter_2fa_in_telegram(password, user_id)

    if success:
        phone = context.user_data['adding_phone']
        price_rub = context.user_data['adding_price_rub']
        price_stars = context.user_data['adding_price_stars']

        session_string = ""
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')

        result = add_phone_product(phone, price_rub, price_stars, session_string)

        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ!\n\n"
            f"📱 Номер: {phone}\n"
            f"👤 Имя: {me.first_name}\n"
        )

        if result:
            await update.message.reply_text(
                f"✅ НОМЕР ДОБАВЛЕН В МАГАЗИН!\n\n"
                f"📱 {phone}\n"
                f"💰 {price_rub} ₽\n"
                f"⭐ {price_stars} Stars"
            )
        else:
            await update.message.reply_text("❌ Ошибка при добавлении в базу!")

        return ConversationHandler.END
    else:
        await update.message.reply_text(f"❌ {msg}\n\nПопробуй ещё:")
        return ENTER_2FA

async def delete_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.edit_message_text(
            "❌ Нет номеров",
            reply_markup=kb([btn("🔙 НАЗАД", "start")])
        )
        return
    rows = []
    for pid, phone, price_rub, price_stars in products:
        rows.append([btn(f"🗑️ {phone}", f"del_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text(
        "Выбери номер для удаления:",
        reply_markup=kb(*rows)
    )

async def delete_phone_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Не найден")
        return
    pid, phone = product[0], product[1]
    await query.edit_message_text(
        f"⚠️ УДАЛИТЬ?\n\n📱 {phone}",
        reply_markup=kb(
            [btn("✅ ДА", f"del_yes_{pid}")],
            [btn("❌ НЕТ", "delete_phone")]
        )
    )

async def delete_phone_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    delete_phone_product(product_id)
    await query.edit_message_text(
        "✅ УДАЛЕНО",
        reply_markup=kb([btn("🔙 НАЗАД", "start")])
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.edit_message_text(
            "❌ Номеров нет",
            reply_markup=kb([btn("🔙 НАЗАД", "start")])
        )
        return
    rows = []
    for pid, phone, price_rub, price_stars in products:
        rows.append([btn(
            f"📱 {hide_phone(phone)} - {price_stars}⭐ / {price_rub}₽",
            f"select_phone_{pid}"
        )])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text(
        "🛒 ВЫБЕРИ НОМЕР:",
        reply_markup=kb(*rows)
    )

async def select_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Не найден")
        return
    pid, phone, price_rub, price_stars = product[:4]

    await query.edit_message_text(
        f"💳 ОПЛАТА\n\n"
        f"📱 {hide_phone(phone)}\n"
        f"💰 {price_rub} ₽\n"
        f"⭐ {price_stars} Stars",
        reply_markup=kb(
            [btn(f"⭐ Оплатить {price_stars} Stars", f"pay_stars_{product_id}")],
            [btn(f"💳 Оплатить {price_rub} ₽", f"pay_rub_{product_id}")],
            [btn("🔙 НАЗАД", "shop")]
        )
    )

async def pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user_id = query.from_user.id
        product_id = int(query.data.split("_")[2])
        product = get_phone_product(product_id)
        if not product:
            await query.edit_message_text("❌ Не найден")
            return
        pid, phone, price_rub, price_stars = product[:4]

        await query.message.reply_invoice(
            title=f"Номер {hide_phone(phone)}",
            description="Получите доступ к номеру",
            payload=f"product_{product_id}_{user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Номер", amount=price_stars)],
            start_parameter=f"buy_phone_{product_id}"
        )
        await query.edit_message_text(
            f"⭐ СЧЁТ ОТПРАВЛЕН!\n\n"
            f"📱 {hide_phone(phone)}\n"
            f"⭐ {price_stars} Stars\n\n"
            f"Нажмите на счёт для оплаты"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def pay_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user_id = query.from_user.id
        product_id = int(query.data.split("_")[2])
        product = get_phone_product(product_id)
        if not product:
            await query.edit_message_text("❌ Не найден")
            return
        pid, phone, price_rub, price_stars = product[:4]

        label = f"rub_{product_id}_{user_id}_{int(datetime.now().timestamp())}"

        pending_rub[user_id] = {
            "product_id": product_id,
            "phone": phone,
            "label": label
        }

        payment_url = (
            f"https://yoomoney.ru/quickpay/confirm.xml?"
            f"receiver={YOOMONEY_WALLET}&"
            f"quickpay-form=small&"
            f"sum={price_rub}&"
            f"label={label}"
        )

        await query.edit_message_text(
            f"💳 *ОПЛАТА {price_rub} ₽*\n\n"
            f"📱 {hide_phone(phone)}\n\n"
            f"🔗 [Нажмите для оплаты]({payment_url})\n\n"
            f"✅ После оплаты бот автоматически выдаст номер",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("🔄 ПРОВЕРИТЬ ОПЛАТУ", f"check_rub_{product_id}")],
                [btn("🔙 НАЗАД", "shop")]
            )
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def check_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет оплату через API ЮMoney"""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    user_id = query.from_user.id

    pending = pending_rub.get(user_id)
    if not pending or pending["product_id"] != product_id:
        await query.edit_message_text(
            "❌ Активный заказ не найден.",
            reply_markup=kb([btn("🔙 НАЗАД", "shop")])
        )
        return

    phone = pending["phone"]
    label = pending["label"]

    # ✅ ПРОВЕРЯЕМ ОПЛАТУ ЧЕРЕЗ API
    is_paid = check_yoomoney_payment(label)

    if not is_paid:
        await query.edit_message_text(
            f"⏳ *ОПЛАТА НЕ ОБНАРУЖЕНА*\n\n"
            f"Проверьте, прошёл ли платёж.\n"
            f"Если оплатили, нажмите «ПРОВЕРИТЬ» ещё раз.",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("🔄 ПРОВЕРИТЬ СНОВА", f"check_rub_{product_id}")],
                [btn("🔙 НАЗАД", "shop")]
            )
        )
        return

    # ✅ ОПЛАТА ПОДТВЕРЖДЕНА
    product = get_phone_product(product_id)
    if product:
        delete_phone_product(product_id)

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id
    }

    await query.edit_message_text(
        f"✅ *ОПЛАЧЕНО РУБЛЯМИ!*\n\n"
        f"📱 *ВАШ НОМЕР:*\n`{phone}`\n\n"
        f"🔑 *Нажмите кнопку, чтобы получить код для входа:*",
        parse_mode="Markdown",
        reply_markup=kb(
            [btn("🔑 ПОЛУЧИТЬ КОД", f"get_code_{phone}")]
        )
    )
    pending_rub.pop(user_id, None)

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    parts = payload.split("_")
    product_id = int(parts[1])
    user_id = update.effective_user.id

    product = get_phone_product(product_id)
    if not product:
        await update.message.reply_text("❌ Ошибка! Номер не найден")
        return

    pid, phone, price_rub, price_stars, session = product

    delete_phone_product(product_id)

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id,
        "session": session
    }

    await update.message.reply_text(
        f"✅ *ОПЛАЧЕНО ЗВЁЗДАМИ!*\n\n"
        f"📱 *ВАШ НОМЕР:*\n`{phone}`\n\n"
        f"🔑 *Нажмите кнопку, чтобы получить код для входа:*",
        parse_mode="Markdown",
        reply_markup=kb(
            [btn("🔑 ПОЛУЧИТЬ КОД", f"get_code_{phone}")]
        )
    )

async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ПОСЛЕДНИЙ код (5 цифр) из сообщений"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    phone = query.data.replace("get_code_", "")

    print(f"🔍 ПОИСК ПОСЛЕДНЕГО КОДА для {phone}")

    pending = awaiting_phone_confirmation.get(user_id)
    if not pending or pending["phone"] != phone:
        await query.edit_message_text(
            f"❌ *ОШИБКА!*\n\n"
            f"Номер {phone} не найден в ваших покупках.",
            parse_mode="Markdown",
            reply_markup=kb([btn("🏠 ГЛАВНОЕ МЕНЮ", "start")])
        )
        return

    session = pending.get("session")
    if not session:
        session = get_phone_session(phone)

    if not session:
        await query.edit_message_text(
            f"❌ *ОШИБКА!*\n\n"
            f"Сессия для номера {phone} не найдена.\n"
            f"Обратитесь к администратору.",
            parse_mode="Markdown",
            reply_markup=kb([btn("🏠 ГЛАВНОЕ МЕНЮ", "start")])
        )
        return

    await query.edit_message_text(
        f"🔍 *ИЩУ ПОСЛЕДНИЙ КОД...*\n\n"
        f"📞 Номер: {phone}\n"
        f"⏳ Подключаюсь к аккаунту...",
        parse_mode="Markdown"
    )

    code_found, result = await get_last_code_from_account(phone, session)

    if code_found:
        await query.edit_message_text(
            f"🔑 *ПОСЛЕДНИЙ КОД НАЙДЕН!*\n\n"
            f"📞 Номер: {phone}\n"
            f"🔑 Код: `{code_found}`\n\n"
            f"✅ Код подошёл для входа?",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("✅ КОД ПОДОШЁЛ", f"code_ok_{phone}")],
                [btn("🔄 ПОЛУЧИТЬ НОВЫЙ КОД", f"get_code_{phone}")]
            )
        )
    else:
        await query.edit_message_text(
            f"⚠️ *КОД НЕ НАЙДЕН!*\n\n"
            f"📞 Номер: {phone}\n\n"
            f"❌ В последних сообщениях нет кода.\n"
            f"Попробуйте ещё раз.",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("🔄 ПОВТОРИТЬ ПОИСК", f"get_code_{phone}")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            )
        )

async def code_ok_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки КОД ПОДОШЁЛ"""
    query = update.callback_query
    await query.answer("✅ Отлично!")

    user_id = query.from_user.id
    phone = query.data.replace("code_ok_", "")

    awaiting_phone_confirmation.pop(user_id, None)
    paid_sessions.pop(user_id, None)

    await query.edit_message_text(
        f"🎉 *СДЕЛКА ЗАВЕРШЕНА!*\n\n"
        f"✅ Код подошёл! Аккаунт ваш!\n\n"
        f"Спасибо за покупку! 🙏",
        parse_mode="Markdown",
        reply_markup=kb([btn("🏠 ГЛАВНОЕ МЕНЮ", "start")])
    )

print("=" * 60)
print("✅ ЧАСТЬ 5 ЗАГРУЖЕНА: ОСНОВНОЙ БОТ")
print("=" * 60)
# =====================================================================
# ЧАСТЬ 6: FLASK-СЕРВЕР + УВЕДОМЛЕНИЯ В TELEGRAM + ЗАПУСК
# =====================================================================

from flask import Flask, request

flask_app = Flask(__name__)

def send_notification_to_telegram(data):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        notification_type = data.get('notification_type', 'Неизвестно')
        amount = data.get('amount', '0')
        sender = data.get('sender', 'Неизвестно')
        is_test = data.get('test_notification') == 'true'
        label = data.get('label', 'Нет label')
        operation_id = data.get('operation_id', 'Неизвестно')
        datetime_str = data.get('datetime', 'Неизвестно')
        
        status_emoji = "🧪" if is_test else "💳"
        status_text = "ТЕСТОВОЕ" if is_test else "РЕАЛЬНЫЙ ПЛАТЁЖ"
        
        message = f"""{status_emoji} *УВЕДОМЛЕНИЕ ОТ ЮMONEY*

📌 *Тип:* {status_text}
📋 *Тип уведомления:* {notification_type}
💰 *Сумма:* {amount} ₽
🏦 *Отправитель:* {sender}
🏷️ *Label:* `{label}`
🆔 *ID операции:* {operation_id}
📅 *Дата/время:* {datetime_str}

---
*Статус:* {'✅ УСПЕШНО' if data.get('status') == 'success' else '⏳ ОЖИДАНИЕ'}
"""
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "📊 Проверить платёж", "callback_data": "check_payment"}
            ]]
        }
        
        response = requests.post(url, json={
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": keyboard
        })
        print(f"✅ Уведомление отправлено в Telegram: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")

@flask_app.route('/', methods=['POST'])
def yoomoney_webhook():
    data = request.form
    print(f"📨 ПОЛУЧЕНО УВЕДОМЛЕНИЕ ОТ ЮMONEY: {data}")
    
    send_notification_to_telegram(data)
    
    if data.get('test_notification') == 'true':
        print("🧪 ПОЛУЧЕНО ТЕСТОВОЕ УВЕДОМЛЕНИЕ! ВСЁ РАБОТАЕТ!")
        return "OK", 200
    
    label = data.get('label')
    if not label:
        print("❌ Нет label в уведомлении")
        return "OK", 200
    
    parts = label.split('_')
    if len(parts) >= 3:
        try:
            product_id = int(parts[1])
            user_id = int(parts[2])
        except:
            print(f"❌ Ошибка парсинга label: {label}")
            return "OK", 200
        
        status = data.get('status')
        print(f"📊 Статус: {status}")
        
        if status == 'success':
            print(f"✅ ОПЛАТА ПРОШЛА! product_id={product_id}, user_id={user_id}")
            send_payment_success_to_bot(user_id, product_id)
        else:
            print(f"❌ Статус оплаты: {status}")
    
    return "OK", 200

@flask_app.route('/', methods=['GET'])
def test():
    return "✅ Webhook работает! ЮMoney может отправлять уведомления."

def send_payment_success_to_bot(user_id, product_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    product = get_phone_product(product_id)
    if not product:
        print(f"❌ Номер #{product_id} не найден")
        return

    pid, phone, price_rub, price_stars, session = product
    print(f"📱 Найден номер: {phone}")

    delete_phone_product(product_id)

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id,
        "session": session
    }

    message = f"""✅ *ОПЛАЧЕНО РУБЛЯМИ!*

📱 *ВАШ НОМЕР:*
`{phone}`

🔑 *Нажмите кнопку, чтобы получить код для входа:*"""

    keyboard = {
        "inline_keyboard": [[
            {"text": "🔑 ПОЛУЧИТЬ КОД", "callback_data": f"get_code_{phone}"}
        ]]
    }

    try:
        response = requests.post(url, json={
            "chat_id": user_id,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": keyboard
        })
        print(f"✅ Сообщение отправлено покупателю: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def start_flask():
    flask_app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)

def main():
    print("=" * 60)
    print("🚀 ЗАПУСК БОТА...")
    print("=" * 60)

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask-сервер запущен на порту 10000")

    app = Application.builder().token(BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_phone_start, pattern="^add_phone$")],
        states={
            PHONE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_price)],
            PHONE_STARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_stars)],
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_number)],
            ENTER_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_code)],
            ENTER_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_2fa)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(add_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(select_phone, pattern="^select_phone_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_phone_start, pattern="^delete_phone$"))
    app.add_handler(CallbackQueryHandler(delete_phone_confirm, pattern="^del_phone_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_phone_yes, pattern="^del_yes_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_rub, pattern="^pay_rub_\\d+$"))
    app.add_handler(CallbackQueryHandler(check_rub, pattern="^check_rub_\\d+$"))
    app.add_handler(CallbackQueryHandler(get_code_button, pattern="^get_code_\\+"))
    app.add_handler(CallbackQueryHandler(code_ok_button, pattern="^code_ok_\\+"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("=" * 60)
    print("✅ БОТ ГОТОВ К РАБОТЕ!")
    print("✅ ДОБАВЛЯЙТЕ НОМЕРА ЧЕРЕЗ АДМИНКУ")
    print("✅ ПОКУПАТЕЛИ ПОЛУЧАЮТ КОД ПО КНОПКЕ")
    print("✅ УВЕДОМЛЕНИЯ ОТ ЮMONEY ПРИХОДЯТ В TELEGRAM")
    print("=" * 60)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(app.run_polling())
    finally:
        loop.close()

if __name__ == "__main__":
    main()

print("=" * 60)
print("✅ ЧАСТЬ 6 ЗАГРУЖЕНА: FLASK + УВЕДОМЛЕНИЯ + ЗАПУСК")
print("=" * 60)
