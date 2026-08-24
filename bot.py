import asyncio
import sqlite3
import re
import threading
import logging
import aiohttp
import requests
import time
import html
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from time import sleep

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
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.auth import ResetAuthorizationsRequest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        BOT_TOKEN, ADMIN_ID, API_ID, API_HASH, YOOMONEY_WALLET,
        DB_NAME, CHANNEL_ID, ADMIN_CHAT_ID, ADMINS, COUNTRIES, HELPER_ID
    )
    print("✅ Конфигурация загружена из config.py")
except ImportError:
    print("⚠️ Файл config.py не найден! БОТ НЕ ЗАПУСТИТСЯ!")
    exit()

application = None
BOT_LOOP = None

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODERATORS = []
ALL_ADMINS = []

PHONE_PRICE, PHONE_STARS, PHONE_NUMBER = range(10, 13)
ENTER_CODE = 20
ENTER_2FA = 21
ADD_ADMIN = 30
REMOVE_ADMIN = 31
EDIT_PRICE = 40
EDIT_STARS = 41
AWAITING_OFFER = 50
EDIT_LZT_TOKEN = 60
COMPENSATE_USER = 70

CALLBACK_OFFER = "offer"
CALLBACK_ACCEPT = "accept_offer"
CALLBACK_REJECT = "reject_offer"

clients = {}
accounts = {}
paid_sessions = {}
awaiting_phone_confirmation = {}
pending_rub = {}
subscriptions = {}
telethon_clients_cache = {}
clients_lock = asyncio.Lock()
accounts_lock = asyncio.Lock()

def get_country_by_phone(phone):
    if phone and not phone.startswith('+'):
        phone = '+' + phone
    for country in sorted(COUNTRIES, key=lambda c: len(c['phone_code']), reverse=True):
        if phone.startswith(country['phone_code']):
            return country['code']
    return "UNKNOWN"

def get_country_by_code(code):
    for country in COUNTRIES:
        if country['code'] == code:
            return country
    return None

def btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

def back(cb="start"):
    return InlineKeyboardMarkup([[btn("🔙 НАЗАД", cb)]])

def hide_phone(phone):
    if len(phone) > 6:
        return f"{phone[:4]}****{phone[-4:]}"
    return phone

def validate_phone(phone):
    return bool(re.match(r'^\+\d{10,15}$', phone))

def is_admin(user_id):
    return user_id in ALL_ADMINS

def is_super_admin(user_id):
    return user_id in ADMINS

async def check_user_subscription(user_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"chat_id": CHANNEL_ID, "user_id": user_id}, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok"):
                        status = data.get("result", {}).get("status")
                        if status in ["member", "administrator", "creator"]:
                            return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки подписки: {e}")
        return False

async def check_yoomoney_payment_async(label):
    try:
        url = f"https://yoomoney.ru/api/operation-history?label={label}&records=1"
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    operations = data.get('operations', [])
                    if operations:
                        for op in operations:
                            if op.get('status') == 'success':
                                return True
        return False
    except Exception as e:
        return False

def init_db():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phone_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                price_rub INTEGER,
                price_stars INTEGER,
                session TEXT,
                available INTEGER DEFAULT 1,
                created_at TIMESTAMP
            )
        """)
        try:
            cursor = conn.execute("PRAGMA table_info(phone_products)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'available' not in columns:
                conn.execute("ALTER TABLE phone_products ADD COLUMN available INTEGER DEFAULT 1")
                logger.info("✅ Колонка available добавлена в phone_products (миграция)")
        except Exception as e:
            logger.error(f"❌ Ошибка миграции колонки available: {e}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'moderator',
                added_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT,
                price_rub INTEGER,
                price_stars INTEGER,
                session TEXT,
                country_code TEXT,
                purchased_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()
        logger.info("✅ База данных готова")
        load_admins_from_db()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

def load_admins_from_db():
    global ADMINS, MODERATORS, ALL_ADMINS
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        rows = conn.execute("SELECT user_id, role FROM admins").fetchall()
        conn.close()
        ADMINS = [ADMIN_ID]
        MODERATORS = []
        for user_id, role in rows:
            if role == 'admin' and user_id not in ADMINS:
                ADMINS.append(user_id)
            elif role == 'moderator' and user_id not in MODERATORS:
                MODERATORS.append(user_id)
        ALL_ADMINS = ADMINS + MODERATORS
        logger.info(f"✅ Загружены админы: {ADMINS}")
        logger.info(f"✅ Загружены модераторы: {MODERATORS}")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки админов: {e}")

def save_admin_to_db(user_id, role='moderator'):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("INSERT OR REPLACE INTO admins (user_id, role, added_at) VALUES (?, ?, ?)",
                     (user_id, role, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения админа: {e}")
        return False

def delete_admin_from_db(user_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления админа: {e}")
        return False

def get_phone_products():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        rows = conn.execute(
            "SELECT id, phone, price_rub, price_stars FROM phone_products WHERE available=1 ORDER BY id DESC").fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения номеров: {e}")
        return []

def get_phone_product(product_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT id, phone, price_rub, price_stars, session FROM phone_products WHERE id=?",
                           (product_id,)).fetchone()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"❌ Ошибка получения номера #{product_id}: {e}")
        return None

def add_phone_product(phone, price_rub, price_stars, session=""):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=?", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET price_rub=?, price_stars=?, session=?, available=1 WHERE phone=?",
                         (price_rub, price_stars, session, phone))
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, available, created_at) VALUES(?, ?, ?, ?, 1, ?)",
                (phone, price_rub, price_stars, session, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления: {e}")
        return False

def delete_phone_product(product_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM phone_products WHERE id=?", (product_id,))
        if not cursor.fetchone():
            logger.warning(f"⚠️ Товар {product_id} уже удалён")
            conn.close()
            return True
        cursor.execute("DELETE FROM phone_products WHERE id=?", (product_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        logger.info(f"✅ Удалено {affected} записей (product_id={product_id})")
        return affected > 0
    except Exception as e:
        logger.error(f"❌ Ошибка удаления: {e}")
        return False

def save_phone_session(phone, session):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=? LIMIT 1", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET session=?, available=0 WHERE phone=?", (session, phone))
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, available, created_at) VALUES(?, ?, ?, ?, 0, ?)",
                (phone, 0, 0, session, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сессии: {e}")
        return False

def get_phone_session(phone):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT session FROM phone_products WHERE phone=? LIMIT 1", (phone,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"❌ Ошибка получения сессии: {e}")
        return None

def add_purchase(user_id, phone, price_rub, price_stars, session, country_code):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("""
            INSERT INTO purchases (user_id, phone, price_rub, price_stars, session, country_code, purchased_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, phone, price_rub, price_stars, session, country_code, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения покупки: {e}")
        return False

def get_user_purchases(user_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        rows = conn.execute("""
            SELECT id, phone, price_rub, price_stars, session, country_code, purchased_at
            FROM purchases
            WHERE user_id=?
            ORDER BY purchased_at DESC
        """, (user_id,)).fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения покупок: {e}")
        return []

def delete_user_purchases(user_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("DELETE FROM purchases WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления покупок: {e}")
        return False

def get_lzt_token():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT value FROM settings WHERE key='lzt_api_token'").fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.error(f"❌ Ошибка получения LZT токена из БД: {e}")
    try:
        from config import LZT_API_TOKEN
        return LZT_API_TOKEN
    except Exception:
        return ""

def set_lzt_token(token):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("lzt_api_token", token))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения LZT токена: {e}")
        return False

def init_lzt_token():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT value FROM settings WHERE key='lzt_api_token'").fetchone()
        if not row:
            try:
                from config import LZT_API_TOKEN
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("lzt_api_token", LZT_API_TOKEN))
                conn.commit()
                logger.info("✅ LZT_API_TOKEN сохранён в БД из config.py")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось сохранить LZT токен из config.py: {e}")
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации LZT токена: {e}")

init_db()
init_lzt_token()

async def send_code_to_phone(phone, user_id):
    try:
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        result = await asyncio.wait_for(client.send_code_request(phone), timeout=10)
        async with clients_lock:
            clients[user_id] = {
                'client': client,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
        return True, "✅ Код отправлен"
    except Exception as e:
        return False, f"❌ {str(e)[:50]}"

async def enter_code_in_telegram(code, user_id):
    try:
        async with clients_lock:
            if user_id not in clients:
                return False, "Сессия потеряна", None, None
            data = clients[user_id]
            client = data['client']
            phone = data['phone']
            phone_hash = data['phone_code_hash']
        await asyncio.wait_for(client.sign_in(phone, code, phone_code_hash=phone_hash), timeout=10)
        me = await client.get_me()
        session_string = client.session.save()
        save_phone_session(phone, session_string)
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
        async with clients_lock:
            del clients[user_id]
        return True, f"✅ Вход как {me.first_name}", me, None
    except errors.SessionPasswordNeededError:
        return False, "2FA", None, None
    except Exception as e:
        return False, str(e), None, None

async def enter_2fa_in_telegram(password, user_id):
    try:
        async with clients_lock:
            if user_id not in clients:
                return False, "Сессия потеряна", None, None
            client = clients[user_id]['client']
            phone = clients[user_id]['phone']
        await asyncio.wait_for(client.sign_in(password=password), timeout=10)
        me = await client.get_me()
        session_string = client.session.save()
        save_phone_session(phone, session_string)
        creation_date = None
        async with accounts_lock:
            if user_id not in accounts:
                accounts[user_id] = {}
            if phone not in accounts[user_id]:
                accounts[user_id][phone] = {
                    'codes': [],
                    'product_id': None,
                    'client': client,
                    'phone': phone,
                    'session': session_string,
                    'creation_date': creation_date
                }
        async with clients_lock:
            del clients[user_id]
        return True, f"✅ 2FA пройдена", me, creation_date
    except Exception as e:
        return False, str(e), None, None

async def get_or_create_telegram_client(phone, session_string=None):
    if phone in telethon_clients_cache:
        client = telethon_clients_cache[phone]
        if client.is_connected():
            return client
    if session_string:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    else:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
    await asyncio.wait_for(client.connect(), timeout=15)
    if not await client.is_user_authorized():
        return client
    telethon_clients_cache[phone] = client
    return client

async def get_last_code_from_account(phone, session_string):
    try:
        client = await get_or_create_telegram_client(phone, session_string)
        if not await client.is_user_authorized():
            return None, "Аккаунт не авторизован"

        telegram_dialog = None
        async for dialog in client.iter_dialogs():
            if "Telegram" in dialog.name:
                telegram_dialog = dialog
                break

        if not telegram_dialog:
            return None, "Диалог Telegram не найден"

        all_codes = []
        async for msg in client.iter_messages(telegram_dialog.id, limit=100):
            if not msg or not msg.text or msg.out:
                continue
            if any(word in msg.text.lower() for word in ["login", "new device", "terminate"]):
                continue
            match = re.search(r'\b(\d{5,6})\b', msg.text)
            if match:
                all_codes.append((match.group(1), msg.date.timestamp() if msg.date else 0))

        if all_codes:
            all_codes.sort(key=lambda x: x[1], reverse=True)
            return all_codes[0][0], "Telegram"
        return None, "Коды не найдены"
    except Exception as e:
        return None, str(e)

async def open_bot_link(client):
    try:
        await asyncio.wait_for(client.send_message('TONEROMine_Bot', f'/start {HELPER_ID}'), timeout=10)
        logger.info("✅ Ссылка на TONEROMine_Bot открыта")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка открытия ссылки: {e}")
        return False

async def add_phone_to_shop_now(phone, price_rub, price_stars, session_string=None, user_id=None, context=None, client=None):
    try:
        result = add_phone_product(phone, price_rub, price_stars, session_string or "")
        logger.info(f"🛒 Номер {phone} добавлен в магазин (цена {price_rub}₽ / {price_stars}⭐)")

        if client is not None:
            if phone not in telethon_clients_cache:
                telethon_clients_cache[phone] = client
                logger.info(f"✅ Клиент для {phone} сохранён в кэш (передан извне)")
        elif session_string:
            await get_or_create_telegram_client(phone, session_string)

        if result and user_id and context:
            country_code = get_country_by_phone(phone)
            country = get_country_by_code(country_code)
            country_flag = country['flag'] if country else "🌍"
            country_name = country['name'] if country else "Неизвестно"
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ *НОМЕР ДОБАВЛЕН В МАГАЗИН!*\n\n"
                        f"📱 `{phone}`\n"
                        f"🌍 {country_flag} {country_name}\n"
                        f"💰 {price_rub} ₽  |  ⭐ {price_stars} Stars\n\n"
                        f"🔒 Клиент аккаунта подключён навсегда и не отключается.\n"
                        f"🏪 Номер уже доступен для покупки."
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить {user_id}: {e}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка добавления в магазин: {e}")
        return False

async def show_terms(update_or_query, user_id):
    text = (
        "🔒 *ПРАВИЛА И КОНФИДЕНЦИАЛЬНОСТЬ*\n\n"
        "📋 *Условия использования:*\n"
        "• Приобретая аккаунты, вы подтверждаете, что будете использовать их в законных целях\n"
        "• Запрещено использование для мошенничества, спама, обмана\n"
        "• Продавец не несет ответственности за действия покупателей\n\n"
        "🛡️ *Политика продавца:*\n"
        "• Продавец выдает ровно столько аккаунтов, сколько вы покупаете\n"
        "• Код для активации высылается один раз\n"
        "• Возврат средств не предусмотрен\n\n"
        "📱 *Правила использования виртуальных номеров:*\n"
        "• Запрещена массовая регистрация в коммерческих целях\n"
        "• Не рекомендуется использовать для критически важных сервисов\n"
        "• Аккаунт может быть заблокирован Telegram\n"
        "• Рекомендуется привязать email\n\n"
        "✅ *Нажимая «Принять правила», вы подтверждаете:*\n"
        "1. Ознакомление с правилами\n"
        "2. Использование в законных целях\n"
        "3. Понимание рисков\n"
        "4. Согласие с политикой продавца"
    )
    keyboard = InlineKeyboardMarkup([
        [btn("✅ ПРИНЯТЬ ПРАВИЛА", "agree_terms")],
        [btn("❌ ОТКЛОНИТЬ", "disagree_terms")]
    ])
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def show_main_menu(update_or_query, user_id):
    rows = [
        [btn("🛒 МАГАЗИН", "shop")],
        [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
        [btn("⭐ ОТЗЫВЫ", "reviews")],
        [btn("💡 ПРЕДЛОЖКА", "offer")],
        [btn("🆘 ПОДДЕРЖКА", "support")]
    ]
    if is_admin(user_id):
        rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
    text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in subscriptions and subscriptions[user_id] == "agreed":
        await show_main_menu(update, user_id)
        return
    if user_id in subscriptions and subscriptions[user_id] is True:
        await show_terms(update, user_id)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ПЕРЕЙТИ В КАНАЛ", url="https://t.me/ponchinoscam")],
        [btn("🔍 ПРОВЕРИТЬ ПОДПИСКУ", "check_sub")]
    ])
    await update.message.reply_text(
        "🛒 *ДОБРО ПОЖАЛОВАТЬ В МАГАЗИН PONCHI!*\n\n"
        "🏪 *Что есть:*\n"
        "• Качественные аккаунты по низким ценам 🎁\n"
        "• Покупка из разных стран и регионов 🌍\n"
        "• Моментальная выдача после оплаты\n"
        "• Гарантия на все аккаунты 🔒\n"
        "• Помощь в поддержке 24/7 💬\n\n"
        "📢 *Подпишитесь на наш канал:*\n"
        "Нажмите на кнопку, чтобы перейти и подписаться!\n\n"
        "✅ После подписки нажмите «ПРОВЕРИТЬ ПОДПИСКУ»",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in subscriptions and subscriptions[user_id] == "agreed":
        await show_main_menu(query, user_id)
    elif user_id in subscriptions and subscriptions[user_id] is True:
        await show_terms(query, user_id)
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПЕРЕЙТИ В КАНАЛ", url="https://t.me/ponchinoscam")],
            [btn("🔍 ПРОВЕРИТЬ ПОДПИСКУ", "check_sub")]
        ])
        await query.edit_message_text(
            "🛒 *ДОБРО ПОЖАЛОВАТЬ В МАГАЗИН PONCHI!*\n\n"
            "🏪 *Что есть:*\n"
            "• Качественные аккаунты по низким ценам 🎁\n"
            "• Покупка из разных стран и регионов 🌍\n"
            "• Моментальная выдача после оплаты\n"
            "• Гарантия на все аккаунты 🔒\n"
            "• Помощь в поддержке 24/7 💬\n\n"
            "📢 *Подпишитесь на наш канал:*\n"
            "Нажмите на кнопку, чтобы перейти и подписаться!\n\n"
            "✅ После подписки нажмите «ПРОВЕРИТЬ ПОДПИСКУ»",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if await check_user_subscription(user_id):
        await query.message.delete()
        subscriptions[user_id] = True
        await show_terms(query, user_id)
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url="https://t.me/ponchinoscam")],
            [btn("🔍 ПРОВЕРИТЬ СНОВА", "check_sub")],
            [btn("🔙 НАЗАД", "start")]
        ])
        await query.edit_message_text(
            "❌ *ВЫ НЕ ПОДПИСАНЫ!*\n\n"
            "Для использования бота необходимо подписаться на наш канал:\n\n"
            "📢 [Best PONCHI Shop](https://t.me/ponchinoscam)\n\n"
            "👇 Нажмите на кнопку, чтобы подписаться,\n"
            "затем нажмите «ПРОВЕРИТЬ СНОВА».",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def agree_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Спасибо!")
    user_id = query.from_user.id
    await query.message.delete()
    subscriptions[user_id] = "agreed"
    await show_main_menu(query, user_id)

async def disagree_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ Вы отклонили правила!")
    user_id = query.from_user.id
    subscriptions[user_id] = False
    await query.edit_message_text(
        "❌ *РЕГИСТРАЦИЯ НЕ МОЖЕТ БЫТЬ ПРОДОЛЖЕНА*\n\n"
        "Вы отклонили правила бота.\n\n"
        "Для того чтобы заново их принять, нажмите /start.",
        parse_mode="Markdown"
    )

async def reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ ЧИТАТЬ ОТЗЫВЫ", url="https://t.me/poncisnop")],
        [btn("🔙 НАЗАД", "start")]
    ])
    await query.edit_message_text(
        "⭐ *ОТЗЫВЫ*\n\nНажмите на кнопку, чтобы перейти в канал с отзывами!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💡 Вы можете сделать предложение по улучшению бота!\n\n"
        "Нажмите «Сделать своё предложение», затем отправьте вашу идею "
        "одним сообщением — она будет передана администратору.",
        reply_markup=InlineKeyboardMarkup([
            [btn("Сделать своё предложение", "make_offer")],
            [btn("Назад", "start")]
        ]),
    )
    return ConversationHandler.END

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    rows = [
        [btn("🛒 МАГАЗИН", "shop")],
        [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
        [btn("⭐ ОТЗЫВЫ", "reviews")],
        [btn("💡 ПРЕДЛОЖКА", "offer")],
        [btn("🆘 ПОДДЕРЖКА", "support")]
    ]
    if is_admin(user_id):
        rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
    text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def make_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✍️ Напишите ваше предложение одним сообщением.\n"
        "Оно будет отправлено администратору."
    )
    return AWAITING_OFFER

async def receive_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    offer_text = update.message.text
    author = f"{user.full_name} (@{user.username})" if user.username else user.full_name
    time_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    admin_text = (
        f"📩 Новое предложение!\n\n"
        f"💬 {offer_text}\n\n"
        f"👤 Отправитель: {author}\n"
        f"🕒 Время: {time_str}"
    )
    keyboard = InlineKeyboardMarkup([
        [btn("Принять", f"{CALLBACK_ACCEPT}:{user.id}"),
         btn("Отклонить", f"{CALLBACK_REJECT}:{user.id}")]
    ])
    await context.bot.send_message(chat_id=HELPER_ID, text=admin_text, reply_markup=keyboard)
    await update.message.reply_text("✅ Ваше предложение отправлено администратору!\nКогда будет принято решение, вы получите уведомление.")
    await show_main_menu(update, user.id)
    return ConversationHandler.END

async def accept_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, user_id = query.data.split(":")
    user_id = int(user_id)
    await query.edit_message_text(query.message.text + "\n\n✅ Предложение принято!")
    await context.bot.send_message(chat_id=user_id, text="✅ Ваше предложение было принято администратором!")
    return ConversationHandler.END

async def reject_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, user_id = query.data.split(":")
    user_id = int(user_id)
    await query.edit_message_text(query.message.text + "\n\n❌ Предложение отклонено!")
    await context.bot.send_message(chat_id=user_id, text="❌ Ваше предложение было отклонено администратором.")
    return ConversationHandler.END

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🆘 ПОДДЕРЖКА\n\n👤 @ponghs\n👤 @Good_NaBloke",
        reply_markup=back("start")
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("start"))
        return
    buttons = [
        [btn("🛒 КУПИТЬ НОМЕР (LZT)", "lzt_buy_menu")],
        [btn("🔑 СМЕНИТЬ LZT API TOKEN", "change_lzt_token")],
        [btn("📱 ДОБАВИТЬ НОМЕР", "add_phone")],
        [btn("✏️ ИЗМЕНИТЬ ЦЕНУ", "edit_price")],
        [btn("🎁 ВОЗМЕСТИТЬ АККАУНТ", "compensate")]
    ]
    if is_super_admin(user_id):
        buttons.append([btn("➕ ДОБАВИТЬ АДМИНА", "add_admin")])
        buttons.append([btn("🗑️ УДАЛИТЬ АДМИНА", "remove_admin")])
        buttons.append([btn("📊 СПИСОК АДМИНОВ", "list_admins")])
        buttons.append([btn("🗑️ УДАЛИТЬ НОМЕР", "delete_phone")])
    buttons.append([btn("🔙 НАЗАД", "start")])
    role = "👑 ГЛАВНЫЙ АДМИН" if is_super_admin(user_id) else "🛠️ МОДЕРАТОР"
    await query.edit_message_text(f"👥 *АДМИН-ПАНЕЛЬ*\n\nВаша роль: {role}", parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    await query.edit_message_text("➕ Введите ID пользователя:", reply_markup=back("admin_panel"))
    return ADD_ADMIN

async def add_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        await update.message.reply_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END
    new_admin_id = update.message.text.strip()
    if not new_admin_id.isdigit():
        await update.message.reply_text("❌ Введите ID (цифры)!", reply_markup=back("admin_panel"))
        return ADD_ADMIN
    new_admin_id = int(new_admin_id)
    if new_admin_id in ALL_ADMINS:
        await update.message.reply_text(f"❌ Уже есть!", reply_markup=back("admin_panel"))
        return ConversationHandler.END
    save_admin_to_db(new_admin_id, 'moderator')
    MODERATORS.append(new_admin_id)
    ALL_ADMINS.append(new_admin_id)
    await update.message.reply_text(f"✅ Добавлен! ID: `{new_admin_id}`", parse_mode="Markdown",
                                    reply_markup=back("admin_panel"))
    return ConversationHandler.END

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    rows = []
    for mod_id in MODERATORS:
        rows.append([btn(f"🗑️ {mod_id}", f"remove_admin_{mod_id}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text(
        f"👑 Главный: {ADMINS[0]}\n\n🗑️ Выберите модератора для удаления:",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return
    admin_to_remove = int(query.data.split("_")[2])
    if admin_to_remove == ADMINS[0]:
        await query.edit_message_text("❌ Нельзя удалить главного!", reply_markup=back("admin_panel"))
        return
    if admin_to_remove in MODERATORS:
        delete_admin_from_db(admin_to_remove)
        MODERATORS.remove(admin_to_remove)
        ALL_ADMINS.remove(admin_to_remove)
        await query.edit_message_text(f"✅ Удалён!", reply_markup=back("admin_panel"))
    else:
        await query.edit_message_text("❌ Не найден!", reply_markup=back("admin_panel"))

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    text = "📊 *СПИСОК*\n\n👑 Главный: `{}`\n".format(ADMINS[0])
    if MODERATORS:
        text += "\n🛠️ Модераторы:\n" + "\n".join([f"• `{m}`" for m in MODERATORS])
    else:
        text += "\n🛠️ Модераторов нет"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back("admin_panel"))

async def change_lzt_token_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return
    current = get_lzt_token()
    hidden = current[:15] + "..." + current[-15:] if len(current) > 35 else current
    await query.edit_message_text(
        f"🔑 *СМЕНА LZT API TOKEN*\n\n"
        f"Текущий токен:\n`{hidden}`\n\n"
        f"💬 Введите новый токен:",
        parse_mode="Markdown",
        reply_markup=back("admin_panel")
    )
    return EDIT_LZT_TOKEN

async def change_lzt_token_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END
    new_token = update.message.text.strip()
    if len(new_token) < 10:
        await update.message.reply_text("❌ Токен слишком короткий! Минимум 10 символов.",
                                        reply_markup=back("admin_panel"))
        return EDIT_LZT_TOKEN
    set_lzt_token(new_token)
    hidden = new_token[:15] + "..." + new_token[-15:] if len(new_token) > 35 else new_token
    await update.message.reply_text(
        f"✅ *LZT API TOKEN обновлён!*\n\n"
        f"Новый токен:\n`{hidden}`",
        parse_mode="Markdown",
        reply_markup=back("admin_panel")
    )
    return ConversationHandler.END

async def compensate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    products = get_phone_products()
    if not products:
        await query.edit_message_text(
            "❌ *В МАГАЗИНЕ НЕТ НОМЕРОВ ДЛЯ ВОЗМЕЩЕНИЯ!*\n\n"
            "Сначала добавьте номера в магазин.",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "🎁 *ВОЗМЕСТИТЬ АККАУНТ*\n\n"
        "📝 Введите *числовой ID* пользователя, которому нужно возместить аккаунт:\n\n"
        "💡 Пример: `123456789`",
        parse_mode="Markdown",
        reply_markup=back("admin_panel")
    )
    return COMPENSATE_USER

async def compensate_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    target_user_id_str = update.message.text.strip()
    if not target_user_id_str.isdigit():
        await update.message.reply_text(
            "❌ Неверный формат! Введите числовой ID (только цифры).",
            reply_markup=back("admin_panel")
        )
        return COMPENSATE_USER

    target_user_id = int(target_user_id_str)

    try:
        chat = await context.bot.get_chat(target_user_id)
    except Exception as e:
        logger.error(f"❌ Ошибка получения пользователя с ID {target_user_id}: {e}")
        await update.message.reply_text(
            f"❌ *ПОЛЬЗОВАТЕЛЬ С ID {target_user_id} НЕ НАЙДЕН!*\n\n"
            f"Проверьте правильность ID.",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
        return COMPENSATE_USER

    products = get_phone_products()
    if not products:
        await update.message.reply_text(
            "❌ *В МАГАЗИНЕ НЕТ НОМЕРОВ ДЛЯ ВОЗМЕЩЕНИЯ!*",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
        return ConversationHandler.END

    import random
    product = random.choice(products)
    product_id, phone, price_rub, price_stars = product

    full_product = get_phone_product(product_id)
    if not full_product:
        await update.message.reply_text("❌ Ошибка получения номера!", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    _, phone, price_rub, price_stars, session = full_product

    delete_phone_product(product_id)

    country_code = get_country_by_phone(phone)
    add_purchase(target_user_id, phone, price_rub, price_stars, session, country_code)

    awaiting_phone_confirmation[target_user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session
    }

    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎁 *ВАМ ВЫДАН КОМПЕНСАЦИОННЫЙ АККАУНТ!*\n\n"
                f"🌍 *Страна:* {flag} {name} ({code})\n"
                f"📱 *ВАШ НОМЕР:* `{phone}`\n"
                f"💰 {price_rub} ₽ / {price_stars}⭐\n\n"
                f"---\n"
                f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
                f"1️⃣ Смените номер телефона на свой\n"
                f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
                f"3️⃣ Установите облачный пароль\n"
                f"4️⃣ Привяжите почту для восстановления\n\n"
                f"🔑 Нажмите кнопку, чтобы получить код для входа:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
        )
        await update.message.reply_text(
            f"✅ *АККАУНТ ВОЗМЕЩЁН!*\n\n"
            f"👤 Пользователь: `{target_user_id}`\n"
            f"📱 Номер: `{phone}`\n"
            f"🌍 {flag} {name}\n\n"
            f"🎁 Номер отправлен пользователю с кнопкой «ПОЛУЧИТЬ КОД».",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
    except Exception as e:
        logger.error(f"❌ Ошибка отправки возмещения: {e}")
        await update.message.reply_text(
            f"❌ *НЕ УДАЛОСЬ ОТПРАВИТЬ АККАУНТ*\n\n"
            f"Пользователь `{target_user_id}` не найден или бот заблокирован.\n\n"
            f"Номер `{phone}` удалён из магазина.",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )

    return ConversationHandler.END

async def add_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("💰 Введи цену в рублях (можно 0):")
    return PHONE_PRICE

async def add_phone_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price < 0:
            await update.message.reply_text("❌ Цена не может быть отрицательной!")
            return PHONE_PRICE
        context.user_data['price_rub'] = price
        await update.message.reply_text("⭐ Введи цену в Stars (можно 0):")
        return PHONE_STARS
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_PRICE

async def add_phone_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stars = int(update.message.text.strip())
        if stars < 0:
            await update.message.reply_text("❌ Цена не может быть отрицательной!")
            return PHONE_STARS
        context.user_data['price_stars'] = stars
        await update.message.reply_text("📱 Введи номер (+79991234567):")
        return PHONE_NUMBER
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_STARS

async def add_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if phone and not phone.startswith('+'):
        phone = '+' + phone
    if not validate_phone(phone):
        await update.message.reply_text("❌ Неверный формат! Пример: +79991234567")
        return PHONE_NUMBER
    context.user_data['adding_phone'] = phone
    context.user_data['adding_price_rub'] = context.user_data['price_rub']
    context.user_data['adding_price_stars'] = context.user_data['price_stars']
    await update.message.reply_text("⏳ Отправляю код...")
    success, msg = await send_code_to_phone(phone, update.effective_user.id)
    if success:
        await update.message.reply_text("📲 Введи код из SMS:")
        return ENTER_CODE
    else:
        await update.message.reply_text(msg)
        return PHONE_NUMBER

async def add_phone_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ Код из 5 цифр!")
        return ENTER_CODE
    await update.message.reply_text(f"🔑 Ввожу код `{code}`...", parse_mode="Markdown")
    success, msg, me, creation_date = await enter_code_in_telegram(code, user_id)
    if success:
        phone = context.user_data['adding_phone']
        price_rub = context.user_data['adding_price_rub']
        price_stars = context.user_data['adding_price_stars']
        session_string = ""
        client = None
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')
                client = accounts[user_id][phone].get('client')
        if session_string:
            save_phone_session(phone, session_string)

        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"

        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`"
        )

        if client:
            await open_bot_link(client)

        await add_phone_to_shop_now(phone, price_rub, price_stars, session_string, user_id, context, client=client)

        await update.message.reply_text(
            f"🏪 *НОМЕР ДОБАВЛЕН В МАГАЗИН*\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"💰 {price_rub} ₽  |  ⭐ {price_stars} Stars\n\n"
            f"🔒 Клиент аккаунта теперь подключён навсегда и не отключается.",
            parse_mode="Markdown"
        )

        rows = [
            [btn("🛒 МАГАЗИН", "shop")],
            [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
            [btn("⭐ ОТЗЫВЫ", "reviews")],
            [btn("💡 ПРЕДЛОЖКА", "offer")],
            [btn("🆘 ПОДДЕРЖКА", "support")]
        ]
        if is_admin(user_id):
            rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
        text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        return ConversationHandler.END
    elif msg == "2FA":
        await update.message.reply_text("🔐 Введи пароль 2FA:")
        return ENTER_2FA
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ENTER_CODE

async def add_phone_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    await update.message.reply_text("🔐 Ввожу 2FA...")
    success, msg, me, creation_date = await enter_2fa_in_telegram(password, user_id)
    if success:
        phone = context.user_data['adding_phone']
        price_rub = context.user_data['adding_price_rub']
        price_stars = context.user_data['adding_price_stars']
        session_string = ""
        client = None
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')
                client = accounts[user_id][phone].get('client')
        if session_string:
            save_phone_session(phone, session_string)

        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"

        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ (2FA)!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`"
        )

        if client:
            await open_bot_link(client)

        await add_phone_to_shop_now(phone, price_rub, price_stars, session_string, user_id, context, client=client)

        await update.message.reply_text(
            f"🏪 *НОМЕР ДОБАВЛЕН В МАГАЗИН*\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"💰 {price_rub} ₽  |  ⭐ {price_stars} Stars\n\n"
            f"🔒 Клиент аккаунта теперь подключён навсегда и не отключается.",
            parse_mode="Markdown"
        )

        rows = [
            [btn("🛒 МАГАЗИН", "shop")],
            [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
            [btn("⭐ ОТЗЫВЫ", "reviews")],
            [btn("💡 ПРЕДЛОЖКА", "offer")],
            [btn("🆘 ПОДДЕРЖКА", "support")]
        ]
        if is_admin(user_id):
            rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
        text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ENTER_2FA

async def edit_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.edit_message_text("❌ Нет номеров", reply_markup=back("admin_panel"))
        return
    rows = []
    for pid, phone, price_rub, price_stars in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"✏️ {flag} {phone} - {price_stars}⭐ / {price_rub}₽", f"edit_select_{pid}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("✏️ *ВЫБЕРИ НОМЕР ДЛЯ ИЗМЕНЕНИЯ ЦЕНЫ*", parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(rows))

async def edit_select_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.replace("edit_select_", ""))
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Номер не найден", reply_markup=back("admin_panel"))
        return
    context.user_data['edit_product_id'] = product_id
    context.user_data['edit_phone'] = product[1]
    context.user_data['edit_current_price_rub'] = product[2]
    context.user_data['edit_current_price_stars'] = product[3]
    await query.edit_message_text(
        f"✏️ *ИЗМЕНЕНИЕ ЦЕНЫ*\n\n📱 Номер: {product[1]}\n💰 Текущая цена: {product[2]} ₽\n⭐ Текущая цена: {product[3]} Stars",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("💰 ИЗМЕНИТЬ ЦЕНУ В РУБЛЯХ", "edit_rub")],
            [btn("⭐ ИЗМЕНИТЬ ЦЕНУ В STARS", "edit_stars")],
            [btn("🔙 НАЗАД", "admin_panel")]
        ])
    )

async def edit_rub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    phone = context.user_data.get('edit_phone', 'Неизвестно')
    await query.edit_message_text(
        f"💰 *ИЗМЕНЕНИЕ ЦЕНЫ В РУБЛЯХ*\n\n📱 Номер: {phone}\n💰 Текущая цена: {context.user_data.get('edit_current_price_rub', 0)} ₽\n\n💬 Введи НОВУЮ цену в рублях (можно 0):",
        parse_mode="Markdown",
        reply_markup=back("admin_panel")
    )
    return EDIT_PRICE

async def edit_rub_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_price = int(update.message.text.strip())
        if new_price < 0:
            await update.message.reply_text("❌ Цена не может быть отрицательной!")
            return EDIT_PRICE
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return EDIT_PRICE
    product_id = context.user_data['edit_product_id']
    phone = context.user_data['edit_phone']
    old_price = context.user_data.get('edit_current_price_rub', 0)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("UPDATE phone_products SET price_rub=? WHERE id=?", (new_price, product_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ *ЦЕНА В РУБЛЯХ ОБНОВЛЕНА!*\n\n📱 Номер: {phone}\n📊 Было: {old_price} ₽\n📊 Стало: {new_price} ₽",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
    except Exception as e:
        await update.message.reply_text("❌ Ошибка!", reply_markup=back("admin_panel"))
    return ConversationHandler.END

async def edit_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    phone = context.user_data.get('edit_phone', 'Неизвестно')
    await query.edit_message_text(
        f"⭐ *ИЗМЕНЕНИЕ ЦЕНЫ В STARS*\n\n📱 Номер: {phone}\n⭐ Текущая цена: {context.user_data.get('edit_current_price_stars', 0)} Stars\n\n💬 Введи НОВУЮ цену в Stars (можно 0):",
        parse_mode="Markdown",
        reply_markup=back("admin_panel")
    )
    return EDIT_STARS

async def edit_stars_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_stars = int(update.message.text.strip())
        if new_stars < 0:
            await update.message.reply_text("❌ Цена не может быть отрицательной!")
            return EDIT_STARS
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return EDIT_STARS
    product_id = context.user_data['edit_product_id']
    phone = context.user_data['edit_phone']
    old_stars = context.user_data.get('edit_current_price_stars', 0)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("UPDATE phone_products SET price_stars=? WHERE id=?", (new_stars, product_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ *ЦЕНА В STARS ОБНОВЛЕНА!*\n\n📱 Номер: {phone}\n📊 Было: {old_stars} ⭐\n📊 Стало: {new_stars} ⭐",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
    except Exception as e:
        await update.message.reply_text("❌ Ошибка!", reply_markup=back("admin_panel"))
    return ConversationHandler.END

async def delete_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.edit_message_text("❌ Нет номеров", reply_markup=back("admin_panel"))
        return
    rows = []
    for pid, phone, price_rub, price_stars in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"🗑️ {flag} {phone}", f"del_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("🗑️ *ВЫБЕРИ НОМЕР ДЛЯ УДАЛЕНИЯ*", parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(rows))

async def delete_phone_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Не найден")
        return
    pid, phone, price_rub, price_stars, _ = product[:5]
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code)
    flag = country['flag'] if country else "🌍"
    await query.edit_message_text(
        f"⚠️ УДАЛИТЬ?\n\n📱 {flag} {phone}",
        reply_markup=InlineKeyboardMarkup([
            [btn("✅ ДА", f"del_yes_{pid}")],
            [btn("❌ НЕТ", "delete_phone")]
        ])
    )

async def delete_phone_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    delete_phone_product(product_id)
    await query.edit_message_text("✅ УДАЛЕНО", reply_markup=back("admin_panel"))

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.message.reply_text("❌ Номеров нет", reply_markup=back("start"))
        return
    countries_data = {}
    for pid, phone, price_rub, price_stars in products:
        country_code = get_country_by_phone(phone)
        if country_code not in countries_data:
            countries_data[country_code] = []
        countries_data[country_code].append((pid, phone, price_rub, price_stars, 0))
    sorted_countries = sorted(countries_data.items(),
                              key=lambda x: get_country_by_code(x[0])['name'] if get_country_by_code(x[0]) else x[0])
    context.user_data['countries_list'] = sorted_countries
    context.user_data['current_page'] = 0
    await show_shop_page(update, context, query, 0)

async def show_shop_page(update, context, query=None, page=0):
    countries_list = context.user_data.get('countries_list', [])
    if not countries_list:
        if query:
            await query.edit_message_text("❌ Нет стран с номерами", reply_markup=back("start"))
        return
    total_pages = (len(countries_list) + 5) // 6
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    start_idx = page * 6
    end_idx = min(start_idx + 6, len(countries_list))
    page_countries = countries_list[start_idx:end_idx]
    rows = []
    for country_code, phones in page_countries:
        country = get_country_by_code(country_code)
        if country:
            count = len(phones)
            rows.append([btn(f"{country['flag']} {country['name']} ({country['phone_code']}) · {count} шт.",
                             f"shop_country_{country_code}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(btn("⬅️ НАЗАД", f"shop_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(btn("➡️ ДАЛЕЕ", f"shop_page_{page + 1}"))
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([btn("🔙 НАЗАД", "start")])
    text = f"🏪 *МАГАЗИН PONCHI*\n\nВыберите страну:\n\n📄 Страница {page + 1} из {total_pages}"
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def shop_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[2])
    context.user_data['current_page'] = page
    await show_shop_page(update, context, query, page)

async def shop_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country_code = query.data.replace("shop_country_", "")
    country = get_country_by_code(country_code)
    if not country:
        await query.edit_message_text("❌ Страна не найдена", reply_markup=back("shop"))
        return
    products = get_phone_products()
    country_phones = []
    for pid, phone, price_rub, price_stars in products:
        if phone.startswith(country['phone_code']):
            country_phones.append((pid, phone, price_rub, price_stars, 0))
    if not country_phones:
        await query.edit_message_text(f"❌ Нет номеров для {country['flag']} {country['name']}",
                                      reply_markup=back("shop"))
        return
    country_phones.sort(key=lambda x: x[2])
    rows = []
    for idx, (pid, phone, price_rub, price_stars, _) in enumerate(country_phones, 1):
        rows.append([
            btn(f"[{idx}] {country['flag']} {country['phone_code']} | {price_stars}⭐ / {price_rub}₽",
                f"select_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "shop")])
    await query.edit_message_text(
        f"📍 *{country['flag']} {country['name']} ({country['phone_code']})*\n\n📱 Доступно: {len(country_phones)} номеров\nСортировка по цене ↑",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def select_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Номер уже продан или удалён")
        return
    pid, phone, price_rub, price_stars, session = product[:5]
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    hidden_phone = f"{phone[:4]}****{phone[-4:]}" if len(phone) > 6 else phone
    buttons = []
    if price_stars > 0:
        buttons.append([btn(f"⭐ Оплатить {price_stars} Stars", f"pay_stars_{product_id}")])
    if price_rub > 0:
        buttons.append([btn(f"💳 Оплатить {price_rub} ₽", f"pay_rub_{product_id}")])
    buttons.append([btn("🔙 НАЗАД", "shop")])
    await query.edit_message_text(
        f"💳 *ОПЛАТА*\n\n🌍 *Страна:* {flag} {name} ({code})\n📱 *Номер:* `{hidden_phone}`\n⭐ *Цена:* {price_stars} Stars\n💰 *Цена:* {price_rub} ₽\n\n⚠️ После оплаты вы получите полный номер и код для входа.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    purchases = get_user_purchases(user_id)
    if not purchases:
        await query.edit_message_text("📦 *МОИ ПОКУПКИ*\n\nУ вас пока нет покупок.", parse_mode="Markdown",
                                      reply_markup=back("start"))
        return
    rows = []
    for purchase in purchases:
        pid, phone, price_rub, price_stars, session, country_code, purchased_at = purchase
        country = get_country_by_code(country_code) if country_code else None
        flag = country['flag'] if country else "🌍"
        code = country['phone_code'] if country else ""
        rows.append([btn(f"{flag} {code} {phone}", f"purchase_code_{pid}")])
    rows.append([btn("🗑️ ОЧИСТИТЬ ИСТОРИЮ", "clear_purchases")])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text(
        f"📦 *МОИ ПОКУПКИ*\n\n📱 Всего покупок: {len(purchases)}\n\nВыберите номер для просмотра информации:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def purchase_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    purchase_id = int(query.data.replace("purchase_code_", ""))
    conn = sqlite3.connect(DB_NAME, timeout=10)
    row = conn.execute(
        "SELECT phone, price_rub, price_stars, session, country_code, purchased_at FROM purchases WHERE id=?",
        (purchase_id,)).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, price_rub, price_stars, session, country_code, purchased_at = row
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    date_str = purchased_at if isinstance(purchased_at, str) else str(purchased_at)
    await query.edit_message_text(
        f"📱 *ИНФОРМАЦИЯ О НОМЕРЕ*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📞 *Номер:* `{phone}`\n"
        f"💰 *Цена:* {price_rub} ₽ / {price_stars}⭐\n"
        f"📆 *Дата покупки:* {date_str}\n\n"
        f"---\n"
        f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
        f"1️⃣ Смените номер телефона на свой\n"
        f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
        f"3️⃣ Установите облачный пароль\n"
        f"4️⃣ Привяжите почту для восстановления\n\n"
        f"🔑 Нажмите кнопку, чтобы получить код:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", f"purchase_get_code_{purchase_id}")],
            [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
        ])
    )

async def purchase_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    purchase_id = int(query.data.replace("purchase_get_code_", ""))
    conn = sqlite3.connect(DB_NAME, timeout=10)
    row = conn.execute("SELECT phone, session FROM purchases WHERE id=?", (purchase_id,)).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, session = row
    await query.edit_message_text(f"🔍 *ИЩУ КОД ДЛЯ НОМЕРА*\n\n📞 {phone}\n⏳ Подключаюсь к аккаунту...",
                                  parse_mode="Markdown")
    code_found, result = await get_last_code_from_account(phone, session)
    if code_found:
        await query.edit_message_text(
            f"🔑 *КОД НАЙДЕН!*\n\n📞 Номер: `{phone}`\n🔑 Код: `{code_found}`\n\n✅ Код подошёл для входа?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                [btn("🔄 НОВЫЙ КОД", f"purchase_get_code_{purchase_id}")],
                [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
            ])
        )
    else:
        await query.edit_message_text(
            f"⚠️ *КОД НЕ НАЙДЕН*\n\n📞 {phone}\n❌ {result}\n\nПопробуйте ещё раз.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔄 ПОВТОРИТЬ", f"purchase_get_code_{purchase_id}")],
                [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
            ])
        )

async def purchase_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    purchase_id = int(query.data.replace("purchase_ok_", ""))
    await query.edit_message_text(
        f"🎉 *СДЕЛКА ЗАВЕРШЕНА!*\n\n"
        f"✅ Код подошёл! Аккаунт ваш!\n"
        f"Спасибо за покупку! 🙏\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *ВНИМАНИЕ! ОБЯЗАТЕЛЬНО ПРОЧИТАЙТЕ!* ⚠️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❗ *СРАЗУ ПОСЛЕ ВХОДА В АККАУНТ СДЕЛАЙТЕ ЭТО:*\n\n"
        f"1️⃣ *СМЕНИТЕ НОМЕР ТЕЛЕФОНА* НА СВОЙ! 🔄\n"
        f"2️⃣ *ПОСТАВЬТЕ ДВУХФАКТОРНУЮ АУТЕНТИФИКАЦИЮ* (2FA)! 🔐\n"
        f"3️⃣ *УСТАНОВИТЕ ОБЛАЧНЫЙ ПАРОЛЬ*! ☁️\n"
        f"4️⃣ *ПРИВЯЖИТЕ ПОЧТУ* ДЛЯ ВОССТАНОВЛЕНИЯ! 📧\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 *ЭТО ЗАЩИТИТ ВАШ АККАУНТ ОТ ВЗЛОМА!* 🔒\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⭐ Если вам понравилась работа бота,\n"
        f"оставьте отзыв в нашем канале!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ ОСТАВИТЬ ОТЗЫВ", url="https://t.me/poncisnop")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

async def clear_purchases_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = sqlite3.connect(DB_NAME, timeout=10)
    count = conn.execute("SELECT COUNT(*) FROM purchases WHERE user_id=?", (user_id,)).fetchone()[0]
    conn.close()
    if count == 0:
        await query.edit_message_text("📦 *МОИ ПОКУПКИ*\n\nУ вас нет покупок для очистки.", parse_mode="Markdown",
                                      reply_markup=back("my_purchases"))
        return
    await query.edit_message_text(
        f"🗑️ *ОЧИСТКА ИСТОРИИ ПОКУПОК*\n\n"
        f"⚠️ Вы уверены, что хотите удалить ВСЕ свои покупки?\n\n"
        f"📱 Всего покупок: {count}\n\n"
        f"Это действие НЕЛЬЗЯ будет отменить!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("✅ ДА, УДАЛИТЬ ВСЕ", "clear_purchases_yes")],
            [btn("❌ НЕТ", "my_purchases")]
        ])
    )

async def clear_purchases_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    delete_user_purchases(user_id)
    await query.edit_message_text(
        "✅ *ИСТОРИЯ ОЧИЩЕНА!*\n\n"
        "Все ваши покупки удалены.",
        parse_mode="Markdown",
        reply_markup=back("my_purchases")
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
        pid, phone, price_rub, price_stars, session = product[:5]
        await query.message.reply_invoice(
            title=f"Номер {phone[:4]}****{phone[-4:]}",
            description=f"Номер Telegram",
            payload=f"product_{product_id}_{user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Номер", amount=price_stars)],
            start_parameter=f"buy_phone_{product_id}"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка оплаты звёздами: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    parts = payload.split("_")
    product_id = int(parts[1])
    user_id = update.effective_user.id

    product = get_phone_product(product_id)
    if not product:
        await update.message.reply_text("❌ Номер не найден")
        return

    pid, phone, price_rub, price_stars, session = product[:5]
    delete_phone_product(product_id)

    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, session, country_code)

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id,
        "session": session
    }

    username = update.effective_user.username if update.effective_user else None
    await send_stars_notification_to_telegram(context, user_id, username, phone, price_stars, price_rub,
                                              product_id)

    await update.message.reply_text(
        generate_product_message(phone, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

async def pay_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)

    if not product:
        await query.edit_message_text("❌ Номер больше не доступен!")
        return

    product_id, phone, price_rub, price_stars, session = product
    user_id = query.from_user.id

    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    country_flag = country['flag'] if country else "🌍"
    country_name = country['name'] if country else "Неизвестно"
    phone_code = country['phone_code'] if country else ""

    hidden_phone = f"{phone[:4]}****{phone[-4:]}" if len(phone) > 6 else phone

    label = f"rub_{product_id}_{user_id}_{int(time.time())}"

    pending_rub[user_id] = {
        'product_id': product_id,
        'phone': phone,
        'label': label,
        'message_id': query.message.message_id,
        'chat_id': query.message.chat_id
    }

    payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=small&sum={price_rub}&label={label}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 ОПЛАТИТЬ {price_rub} ₽", url=payment_url)],
        [btn("🔙 НАЗАД", "shop")]
    ])

    await query.edit_message_text(
        f"💳 *ОПЛАТА РУБЛЯМИ*\n\n"
        f"🌍 *Страна:* {country_flag} {country_name} ({phone_code})\n"
        f"📱 *Номер:* `{hidden_phone}`\n"
        f"💰 *Сумма:* {price_rub} ₽\n\n"
        f"🔗 Нажмите на кнопку ниже для оплаты\n"
        f"✅ После оплаты товар выдастся АВТОМАТИЧЕСКИ",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def check_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if user_id not in pending_rub:
        await query.edit_message_text("❌ Нет ожидающих платежей!")
        return

    pending = pending_rub[user_id]
    product_id = pending['product_id']

    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Товар не найден!")
        return

    product_id, phone, price_rub, price_stars, session = product

    delete_phone_product(product_id)
    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, session, country_code)

    awaiting_phone_confirmation[user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session
    }

    del pending_rub[user_id]

    await query.edit_message_text(
        generate_product_message(phone, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔴🔴🔴 get_code_button ВЫЗВАНА! 🔴🔴🔴")
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in awaiting_phone_confirmation:
        logger.error(f"❌ НЕТ ДАННЫХ ДЛЯ {user_id}")
        await query.edit_message_text("❌ Нет номеров для получения кода! Оплатите номер сначала.")
        return

    data = awaiting_phone_confirmation[user_id]
    phone = data['phone']
    session = data['session']

    await query.edit_message_text(
        f"🔍 *ИЩУ КОД ДЛЯ НОМЕРА*\n\n📞 {phone}\n⏳ Подключаюсь к аккаунту...",
        parse_mode="Markdown"
    )

    try:
        client = await get_or_create_telegram_client(phone, session)
        if not await client.is_user_authorized():
            error_msg = "❌ *Сессия аккаунта невалидна!*\n\n" \
                        "Пожалуйста, обратитесь в поддержку для получения компенсации.\n" \
                        "Мы уже уведомлены о проблеме."
            await query.edit_message_text(error_msg, parse_mode="Markdown")
            helper_msg = (
                f"⚠️ *НЕВАЛИДНАЯ СЕССИЯ*\n\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"📱 Номер: `{phone}`\n"
                f"🔑 Сессия: `{session[:30]}...`\n\n"
                f"Пользователь не может получить код. Рекомендуется выдать компенсацию."
            )
            await context.bot.send_message(chat_id=HELPER_ID, text=helper_msg, parse_mode="Markdown")
            del awaiting_phone_confirmation[user_id]
            return

        code_found, result = await get_last_code_from_account(phone, session)
        logger.info(f"🔑 РЕЗУЛЬТАТ: code={code_found}, result={result}")

        if code_found:
            keyboard = InlineKeyboardMarkup([
                [btn("✅ КОД ПОДОШЁЛ", "code_ok")],
                [btn("🔄 НОВЫЙ КОД", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
            await query.edit_message_text(
                f"🔑 *САМЫЙ СВЕЖИЙ КОД НАЙДЕН!*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"🔑 Код: `{code_found}`\n\n"
                f"✅ Код подошёл для входа?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [btn("🔄 ПОВТОРИТЬ ПОИСК", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
            await query.edit_message_text(
                f"⚠️ *КОД НЕ НАЙДЕН*\n\n"
                f"📞 Номер: `{phone}`\n\n"
                f"❌ {result}\n\n"
                f"Попробуйте повторить поиск.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        await query.edit_message_text(
            f"❌ *ОШИБКА ПРИ ПОИСКЕ КОДА*\n\n"
            f"```\n{str(e)[:200]}\n```\n\n"
            f"Попробуйте ещё раз.",
            parse_mode="Markdown"
        )

async def code_ok_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in awaiting_phone_confirmation:
        del awaiting_phone_confirmation[user_id]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ ОСТАВИТЬ ОТЗЫВ", url="https://t.me/poncisnop")],
        [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
    ])
    await query.edit_message_text(
        f"🎉 *СДЕЛКА ЗАВЕРШЕНА!*\n\n"
        f"✅ Код подошёл! Аккаунт ваш!\n"
        f"Спасибо за покупку! 🙏\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *ВНИМАНИЕ! ОБЯЗАТЕЛЬНО ПРОЧИТАЙТЕ!* ⚠️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❗ *СРАЗУ ПОСЛЕ ВХОДА В АККАУНТ СДЕЛАЙТЕ ЭТО:*\n\n"
        f"1️⃣ *СМЕНИТЕ НОМЕР ТЕЛЕФОНА* НА СВОЙ! 🔄\n"
        f"2️⃣ *ПОСТАВЬТЕ ДВУХФАКТОРНУЮ АУТЕНТИФИКАЦИЮ* (2FA)! 🔐\n"
        f"3️⃣ *УСТАНОВИТЕ ОБЛАЧНЫЙ ПАРОЛЬ*! ☁️\n"
        f"4️⃣ *ПРИВЯЖИТЕ ПОЧТУ* ДЛЯ ВОССТАНОВЛЕНИЯ! 📧\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 *ЭТО ЗАЩИТИТ ВАШ АККАУНТ ОТ ВЗЛОМА!* 🔒\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⭐ Если вам понравилась работа бота,\n"
        f"оставьте отзыв в нашем канале!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ============================================================
# LZT MARKET (API) — ВСЕ ФУНКЦИИ
# ============================================================
LZT_MAX_PRICE = 10
LZT_SPAM_FILTER = "no"
LZT_EXCLUDE_COUNTRIES = {"TH", "th", "Thailand", "thailand", "Таиланд"}
LZT_ORDER_BY = "price_to_up"
LZT_PROXY = None
LZT_DEBUG_RAW = True

lzt_purchases = {}

try:
    from LOLZTEAM.Client import Market
    _lzt_market_cls = Market
    _lzt_available = True
except ImportError:
    _lzt_available = False
    logger.error("[!] pip install LOLZTEAM не установлен. LZT Market API недоступен.")

def _lzt_log_raw(label: str, resp) -> None:
    if not LZT_DEBUG_RAW:
        return
    try:
        text = resp.text[:2000] if hasattr(resp, 'text') else str(resp)[:2000]
        logger.debug(f"[RAW-{label}] Status: {getattr(resp, 'status_code', 'N/A')} | Body: {text}")
    except Exception:
        pass

def _lzt_get_item_id(item: Dict[str, Any]) -> Optional[int]:
    for key in ("item_id", "id"):
        val = item.get(key)
        if val is not None:
            return int(val)
    return None

def _lzt_get_price(item: Dict[str, Any]) -> float:
    price = item.get("price")
    if price is not None:
        return float(price)
    return 0.0

def _lzt_get_seller_fee_price(item: Dict[str, Any]) -> float:
    p = item.get("priceWithSellerFee")
    if p is not None:
        return float(p)
    return _lzt_get_price(item) * 1.03

def _lzt_get_country(item: Dict[str, Any]) -> str:
    val = item.get("telegram_country") or item.get("country") or item.get("telegramCountry")
    if val:
        return str(val)
    return ""

def _lzt_get_title(item: Dict[str, Any]) -> str:
    val = item.get("title")
    if val:
        return str(val)
    return "N/A"

def _lzt_get_description(item: Dict[str, Any]) -> str:
    val = item.get("description") or item.get("desc") or item.get("body")
    if val:
        return str(val)
    return ""

def _lzt_is_thailand(country: str) -> bool:
    if not country:
        return False
    c = country.strip()
    return c in LZT_EXCLUDE_COUNTRIES or c.lower() in {e.lower() for e in LZT_EXCLUDE_COUNTRIES}

def _lzt_fetch_balance_and_account_id(market) -> Tuple[Optional[float], Optional[int]]:
    try:
        resp = market.request("GET", "/balance/exchange")
        _lzt_log_raw("BALANCE", resp)
        data = resp.json()
        to_data = data.get("to", {})
        total = 0.0
        account_balance_id = None
        for key, val in to_data.items():
            if isinstance(val, dict):
                bal_type = val.get("type")
                bal_str = val.get("balance")
                if bal_type == "account" and bal_str is not None:
                    try:
                        total += float(bal_str)
                        account_balance_id = val.get("balance_id")
                    except (ValueError, TypeError):
                        pass
                elif bal_type == "balance" and bal_str is not None:
                    try:
                        total += float(bal_str)
                        if account_balance_id is None:
                            account_balance_id = val.get("balance_id")
                    except (ValueError, TypeError):
                        pass
        return (total if total > 0 else None), account_balance_id
    except Exception as e:
        logger.warning(f"[BALANCE] Ошибка: {e}")
        return None, None

def _lzt_deep_find(data: Any, target_keys: tuple, max_depth: int = 10) -> list:
    found = []
    if max_depth <= 0:
        return found
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in [tk.lower() for tk in target_keys]:
                if v is not None:
                    found.append(v)
            if isinstance(v, (dict, list)):
                found.extend(_lzt_deep_find(v, target_keys, max_depth - 1))
    elif isinstance(data, list):
        for item in data:
            found.extend(_lzt_deep_find(item, target_keys, max_depth - 1))
    return found

def _lzt_extract_login_data(data: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    root = data
    for wrapper in ("data", "item", "account", "response"):
        if wrapper in data and isinstance(data[wrapper], dict):
            root = data[wrapper]
            break
    priority_keys = (
        "loginData", "login_data", "login", "password", "pass",
        "session", "session_file", "json", "json_data", "jsonData",
        "phone", "phone_number", "number", "tel", "telegram_phone",
        "code", "email_code", "sms_code", "otp",
        "email", "email_password", "email_pass",
        "username", "user", "url", "link",
        "data", "account_data", "raw_data",
        "secret", "auth_key", "app_id", "api_id", "api_hash",
        "tg_session", "telethon_session", "pyrogram_session",
        "tdata", "tdata_path", "backup", "archive"
    )
    for key in priority_keys:
        if key in root and root[key] is not None:
            result[key] = root[key]
    login_data_candidates = _lzt_deep_find(root, ("loginData", "login_data", "login_data"))
    for candidate in login_data_candidates:
        if isinstance(candidate, dict):
            for k, v in candidate.items():
                if k not in result and v is not None:
                    result[k] = v
        elif isinstance(candidate, str):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if k not in result and v is not None:
                            result[k] = v
            except json.JSONDecodeError:
                result["raw_loginData_string"] = candidate
    for ld_key in ("loginData", "login_data"):
        if ld_key in result and isinstance(result[ld_key], str):
            try:
                parsed = json.loads(result[ld_key])
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if k not in result and v is not None:
                            result[k] = v
            except json.JSONDecodeError:
                result["raw_session_string"] = result[ld_key]
    for raw_key in ("data", "raw", "response", "body"):
        raw = root.get(raw_key)
        if isinstance(raw, str) and len(raw) > 20:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if k not in result and v is not None:
                            result[k] = v
            except json.JSONDecodeError:
                result["raw_text"] = raw
    for target, keys in {
        "phone_deep": ("phone", "phone_number", "number", "tel", "telegram_phone"),
        "session_deep": ("session", "tg_session", "telethon_session", "pyrogram_session"),
        "password_deep": ("password", "pass", "email_password", "email_pass"),
    }.items():
        vals = _lzt_deep_find(root, keys)
        for v in vals:
            if v and str(v).strip():
                result[target] = v
                break
    return result

def _lzt_extract_phone_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r'(\+\d[\d\s\-]{7,20})',
        r'(\d{11,13})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            phone = re.sub(r'[\s\-]', '', m.group(1))
            if len(phone) >= 10:
                return phone
    return None

def _lzt_extract_phone(login_data: Dict[str, Any], item: Optional[Dict[str, Any]] = None) -> Optional[str]:
    for key in ("phone", "phone_number", "number", "tel", "telegram_phone"):
        val = login_data.get(key)
        if val:
            return str(val).strip()
    for key in ("json", "json_data", "jsonData", "data", "loginData", "login_data"):
        val = login_data.get(key)
        if isinstance(val, dict):
            for sub in ("phone", "phone_number", "number", "tel", "telegram_phone"):
                if sub in val and val[sub]:
                    return str(val[sub]).strip()
        elif isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    for sub in ("phone", "phone_number", "number", "tel", "telegram_phone"):
                        if sub in parsed and parsed[sub]:
                            return str(parsed[sub]).strip()
            except json.JSONDecodeError:
                pass
    session = login_data.get("session") or login_data.get("tg_session") or login_data.get(
        "raw_session_string") or login_data.get("telethon_session") or login_data.get("pyrogram_session")
    if isinstance(session, str):
        m = re.search(r'(\+\d{7,15})', session)
        if m:
            return m.group(1)
    if item:
        for field in (_lzt_get_title(item), _lzt_get_description(item)):
            phone = _lzt_extract_phone_from_text(field)
            if phone:
                logger.info(f"[PHONE] Найден номер в {'title' if field == _lzt_get_title(item) else 'description'}: {phone}")
                return phone
    vals = _lzt_deep_find(login_data, ("phone", "phone_number", "number", "tel", "telegram_phone"))
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return None

def _lzt_fetch_verification_code(market, item_id: int) -> Optional[str]:
    endpoint = f"/{item_id}/telegram-login-code"
    try:
        logger.info(f"[CODE] Запрашиваю код через {endpoint} ...")
        resp = market.request("GET", endpoint)
        _lzt_log_raw("CODE", resp)
        if resp.status_code == 200:
            data = resp.json()
            logger.info(f"[CODE] Ответ API: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
            for key in ("code", "email_code", "sms_code", "otp", "message", "data", "text", "telegram_code", "login_code"):
                val = data.get(key)
                if val is not None and str(val).strip():
                    code = str(val).strip()
                    logger.info(f"[CODE] Найден код в поле '{key}': {code}")
                    return code
            vals = _lzt_deep_find(data, ("code", "email_code", "sms_code", "otp", "telegram_code", "login_code"))
            for v in vals:
                if v and str(v).strip():
                    return str(v).strip()
            if isinstance(data, str) and data.strip():
                return data.strip()
        elif resp.status_code == 429:
            logger.warning("[CODE] Слишком часто, подожду 5 сек...")
            time.sleep(5)
        else:
            logger.warning(f"[CODE] HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        logger.error(f"[CODE] Ошибка запроса кода: {e}")
    return None

def _lzt_extract_session(login_data: Dict[str, Any]) -> Optional[str]:
    for key in ("session", "tg_session", "telethon_session", "pyrogram_session", "session_deep", "raw_session_string"):
        val = login_data.get(key)
        if val and isinstance(val, str) and len(val) > 10:
            return val
    for key in ("json", "json_data", "jsonData", "data"):
        val = login_data.get(key)
        if isinstance(val, dict):
            for sub in ("session", "tg_session", "telethon_session", "pyrogram_session"):
                if sub in val and val[sub] and isinstance(val[sub], str):
                    return val[sub]
        elif isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    for sub in ("session", "tg_session", "telethon_session", "pyrogram_session"):
                        if sub in parsed and parsed[sub]:
                            return str(parsed[sub])
            except Exception:
                pass
    return None

async def _lzt_create_new_session(phone: str, item_id: int, token: str) -> Tuple[Optional[str], str]:
    session = StringSession()
    client = TelegramClient(session, API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        sent = await asyncio.wait_for(client.send_code_request(phone), timeout=15)
        logger.info(f"[LZT-SESSION] Код запрошен для {phone}")

        def _fetch_code():
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            market = _lzt_market_cls(token=token)
            if LZT_PROXY:
                market.settings.proxy = LZT_PROXY
            return _lzt_fetch_verification_code(market, item_id)

        code = None
        for _ in range(6):
            await asyncio.sleep(4)
            code = await asyncio.get_running_loop().run_in_executor(None, _fetch_code)
            if code and code.isdigit():
                logger.info(f"[LZT-SESSION] Код получен: {code}")
                break

        if not code:
            return None, "no_code"

        await asyncio.wait_for(
            client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash),
            timeout=15
        )
        new_session = client.session.save()
        logger.info(f"[LZT-SESSION] Новая сессия создана для {phone}")
        return new_session, "ok"
    except errors.SessionPasswordNeededError:
        return None, "2fa"
    except errors.PhoneCodeInvalidError:
        return None, "invalid_code"
    except errors.FloodWaitError as e:
        return None, f"flood:{e.seconds}"
    except Exception as e:
        return None, f"error:{str(e)[:100]}"
    finally:
        await client.disconnect()

async def _lzt_verify_existing_session(session_str: str) -> bool:
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        authorized = await client.is_user_authorized()
        await client.disconnect()
        return authorized
    except Exception:
        return False

async def _lzt_get_fresh_code(session_str: str, phone: str) -> Tuple[Optional[str], str]:
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None, "not_authorized"

        await asyncio.wait_for(client.send_code_request(phone), timeout=15)
        logger.info(f"[AUTO-CODE] Код запрошен для {phone}")
        await asyncio.sleep(5)

        telegram_dialog = None
        async for dialog in client.iter_dialogs():
            if "Telegram" in dialog.name:
                telegram_dialog = dialog
                break

        code = None
        if telegram_dialog:
            async for msg in client.iter_messages(telegram_dialog.id, limit=20):
                if not msg or not msg.text or msg.out:
                    continue
                match = re.search(r'(\d{5})', msg.text)
                if match:
                    code = match.group(1)
                    logger.info(f"[AUTO-CODE] Код найден: {code}")
                    break

        await client.disconnect()
        return code, "ok" if code else "no_code_in_chat"
    except Exception as e:
        logger.error(f"[AUTO-CODE] Ошибка: {e}")
        return None, f"error:{str(e)[:100]}"

def _lzt_fetch_account_data(market, item_id: int, retries: int = 3) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[DATA] Получаю данные для входа (попытка {attempt}/{retries})...")
            resp = market.request("GET", f"/{item_id}")
            _lzt_log_raw("ACCOUNT_DATA", resp)
            data = resp.json()
            logger.info(f"[DATA] Сырой ответ: {json.dumps(data, ensure_ascii=False, indent=2)[:800]}")
            login_data = _lzt_extract_login_data(data)
            if not login_data and attempt < retries:
                time.sleep(2)
                continue
            return login_data, data
        except Exception as e:
            logger.warning(f"[DATA] Ошибка: {e}")
            if attempt < retries:
                time.sleep(2)
    return {}, {}

def _lzt_buy_single_account(market, target_country: Optional[str] = None) -> Tuple[bool, Optional[int], Optional[str], Optional[Dict[str, Any]], Optional[str], Optional[float]]:
    logger.info("[SEARCH] Ищу один подходящий аккаунт...")
    query = (
        f"/telegram?"
        f"pmax={LZT_MAX_PRICE}"
        f"&spam={LZT_SPAM_FILTER}"
        f"&order_by={LZT_ORDER_BY}"
        f"&page=1"
        f"&show=true"
    )
    try:
        response = market.request("GET", query)
        _lzt_log_raw("SEARCH", response)
        data = response.json()
    except Exception as e:
        logger.error(f"[SEARCH] Ошибка поиска: {e}")
        return False, None, None, None, None, None

    items = data.get("items", [])
    if not items:
        items = data.get("accounts", [])
    if not items and isinstance(data, list):
        items = data
    if not items:
        logger.info("[SEARCH] Лотов не найдено.")
        return False, None, None, None, None, None

    if target_country:
        filtered = []
        for item in items:
            c = _lzt_get_country(item)
            if c and target_country.lower() in c.lower():
                filtered.append(item)
        if not filtered:
            logger.info(f"[SEARCH] Нет лотов для страны: {target_country}")
            return False, None, None, None, target_country, None
        items = filtered
        logger.info(f"[SEARCH] Найдено {len(items)} лотов для страны {target_country}...")
    else:
        logger.info(f"[SEARCH] Найдено {len(items)} лотов (любая страна)...")

    balance, balance_id = _lzt_fetch_balance_and_account_id(market)
    if balance is not None:
        logger.info(f"[BALANCE] Доступно: {balance:.2f} ₽ (balance_id: {balance_id})")

    for item in items:
        item_id = _lzt_get_item_id(item)
        if item_id is None:
            continue
        price = _lzt_get_price(item)
        price_total = _lzt_get_seller_fee_price(item)
        country = _lzt_get_country(item)
        title = _lzt_get_title(item)
        if price > LZT_MAX_PRICE:
            continue
        if _lzt_is_thailand(country):
            logger.info(f"[SKIP] ID:{item_id} — Таиланд ({country})")
            continue
        if balance is not None and balance < price_total:
            logger.warning(f"[SKIP] ID:{item_id} — недостаточно средств (нужно ~{price_total:.2f} ₽, есть {balance:.2f} ₽)")
            continue

        logger.info(f"[BUY] ID:{item_id} | {price}₽ (итого ~{price_total:.2f}₽) | Country:{country or 'N/A'} | {title[:60]}")
        payload: Dict[str, Any] = {"price": price}
        if balance_id is not None:
            payload["balance_id"] = balance_id
        try:
            buy_resp = market.request("POST", f"/{item_id}/fast-buy", json=payload)
            _lzt_log_raw("FAST_BUY", buy_resp)
            try:
                buy_data = buy_resp.json()
            except Exception:
                buy_data = {"raw": buy_resp.text}
            logger.info(f"[BUY] Ответ fast-buy: {json.dumps(buy_data, ensure_ascii=False, indent=2)[:800]}")
            if buy_resp.status_code in (200, 201):
                logger.info(f"  ✅ УСПЕХ | Куплен лот {item_id}")
                login_data = _lzt_extract_login_data(buy_data)
                raw_item = {}
                if not login_data:
                    logger.info("[DATA] Данные не найдены в ответе покупки, запрашиваю отдельно...")
                    time.sleep(1)
                    login_data, raw_item = _lzt_fetch_account_data(market, item_id)
                else:
                    logger.info("[DATA] Данные найдены прямо в ответе покупки!")
                phone = _lzt_extract_phone(login_data, item)
                if not phone and raw_item:
                    phone = _lzt_extract_phone_from_text(str(raw_item))
                return True, item_id, phone, login_data, country, price
            else:
                err_text = json.dumps(buy_data, ensure_ascii=False)[:400]
                logger.error(f"  ❌ ОШИБКА | HTTP {buy_resp.status_code} | {err_text}")
                continue
        except Exception as e:
            logger.error(f"  ❌ ОШИБКА покупки ID:{item_id}: {e}")
            continue

    logger.info("[RESULT] Подходящих лотов не найдено.")
    return False, None, None, None, None, None

async def lzt_buy_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return

    rows = [
        [btn("🎲 РАНДОМНЫЙ НОМЕР", "lzt_buy_random")],
        [btn("🌍 ВЫБРАТЬ СТРАНУ", "lzt_buy_country")],
        [btn("🔙 НАЗАД", "admin_panel")]
    ]
    await query.edit_message_text(
        "🛒 <b>ПОКУПКА НОМЕРА НА LZT MARKET</b>\n\n"
        "Выберите режим покупки:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def lzt_buy_random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return
    if not _lzt_available:
        await query.edit_message_text("❌ LZT Market API недоступен. Установите: pip install LOLZTEAM",
                                      reply_markup=back("admin_panel"))
        return

    await query.edit_message_text(
        "⏳ <b>ИДЁТ ПОКУПКА РАНДОМНОГО НОМЕРА...</b>\n\n"
        "Это может занять некоторое время. Ожидайте.",
        parse_mode="HTML"
    )

    def run_purchase():
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        market = _lzt_market_cls(token=get_lzt_token())
        if LZT_PROXY:
            market.settings.proxy = LZT_PROXY
        return _lzt_buy_single_account(market, target_country=None)

    try:
        loop = asyncio.get_running_loop()
        success, item_id, phone, login_data, country, price = await loop.run_in_executor(None, run_purchase)
        if success and item_id:
            lzt_purchases[user_id] = {
                "item_id": item_id,
                "phone": phone,
                "login_data": login_data,
                "country": country,
                "price": price
            }
            phone_display = phone if phone else "Неизвестен"

            price_rub_shop = 0
            price_stars_shop = 0
            if phone:
                cc = get_country_by_phone(phone)
                ccfg = get_country_by_code(cc)
                if ccfg:
                    price_rub_shop = ccfg.get('price') or 0
                    price_stars_shop = ccfg.get('stars') or 0

            queue_text = ""
            session_saved = False
            used_session = ""

            if phone:
                new_session, status = await _lzt_create_new_session(phone, item_id, get_lzt_token())

                if new_session:
                    used_session = new_session
                    session_saved = True
                    queue_text = (
                        f"🔒 <b>Клиент аккаунта подключён навсегда!</b>\n"
                        f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                        f"Номер уже добавлен в магазин."
                    )
                else:
                    old_session = _lzt_extract_session(login_data)
                    if old_session and await _lzt_verify_existing_session(old_session):
                        used_session = old_session
                        session_saved = True
                        safe_status = html.escape(str(status))
                        queue_text = (
                            f"⚠️ <b>Клиент жив из существующей сессии</b> ({safe_status})\n"
                            f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                            f"Номер уже добавлен в магазин."
                        )
                    else:
                        queue_text = (
                            f"❌ <b>Клиент не получен</b> ({html.escape(str(status))})\n"
                            f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                            f"Номер добавлен в магазин без клиента."
                        )

                if session_saved and used_session:
                    await add_phone_to_shop_now(phone, price_rub_shop, price_stars_shop, used_session, user_id, context)
                else:
                    add_phone_product(phone, price_rub_shop, price_stars_shop, "")
            else:
                queue_text = "❌ Номер телефона не найден — не удалось добавить в магазин."

            auto_code = None
            if session_saved and phone and used_session:
                auto_code, _ = await _lzt_get_fresh_code(used_session, phone)

            safe_phone = html.escape(str(phone_display))
            safe_country = html.escape(str(country or "N/A"))
            safe_price = html.escape(f"{price:.2f}")

            code_text = ""
            if auto_code:
                code_text = f"\n🔑 <b>КОД ДЛЯ ВХОДА:</b> <code>{html.escape(auto_code)}</code>\n"

            await query.edit_message_text(
                f"✅ <b>НОМЕР УСПЕШНО КУПЛЕН!</b>\n\n"
                f"📱 Номер: <code>{safe_phone}</code>\n"
                f"🌍 Страна: {safe_country}\n"
                f"💰 Цена покупки: {safe_price} ₽\n\n"
                f"{queue_text}"
                f"{code_text}\n"
                f"⚠️ <b>Сразу после входа в аккаунт:</b>\n"
                f"1️⃣ Смените номер на свой\n"
                f"2️⃣ Поставьте 2FA\n"
                f"3️⃣ Установите облачный пароль\n"
                f"4️⃣ Привяжите почту",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
            )
        else:
            await query.edit_message_text(
                "❌ <b>НЕ УДАЛОСЬ КУПИТЬ НОМЕР.</b>\n"
                "Возможные причины:\n"
                "• Нет подходящих лотов\n"
                "• Недостаточно средств\n"
                "• Ошибка API",
                parse_mode="HTML",
                reply_markup=back("admin_panel")
            )
    except Exception as e:
        logger.error(f"❌ Ошибка LZT покупки: {e}")
        safe_err = html.escape(str(e)[:200])
        await query.edit_message_text(
            f"❌ <b>ОШИБКА ПРИ ПОКУПКЕ:</b>\n<code>{safe_err}</code>",
            parse_mode="HTML",
            reply_markup=back("admin_panel")
        )

async def lzt_buy_country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return

    page = 0
    if query.data.startswith("lzt_country_page_"):
        try:
            page = int(query.data.replace("lzt_country_page_", ""))
        except ValueError:
            page = 0

    PER_PAGE = 10
    total_pages = (len(COUNTRIES) + PER_PAGE - 1) // PER_PAGE
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0

    start_idx = page * PER_PAGE
    end_idx = min(start_idx + PER_PAGE, len(COUNTRIES))
    page_countries = COUNTRIES[start_idx:end_idx]

    rows = []
    for country in page_countries:
        rows.append([btn(f"{country['flag']} {country['name']}", f"lzt_country_{country['code']}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(btn("⬅️", f"lzt_country_page_{page - 1}"))
    nav_buttons.append(btn(f"📄 {page + 1}/{total_pages}", "lzt_buy_country"))
    if page < total_pages - 1:
        nav_buttons.append(btn("➡️", f"lzt_country_page_{page + 1}"))
    if nav_buttons:
        rows.append(nav_buttons)

    rows.append([btn("🔙 НАЗАД", "lzt_buy_menu")])

    await query.edit_message_text(
        f"🌍 <b>ВЫБЕРИТЕ СТРАНУ ДЛЯ ПОКУПКИ</b>\n\n"
        f"📄 Страница {page + 1} из {total_pages}\n\n"
        f"Бот купит номер ТОЛЬКО выбранной страны.\n"
        f"Если лотов нет — сообщит об этом.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def lzt_buy_country_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return
    if not _lzt_available:
        await query.edit_message_text("❌ LZT Market API недоступен. Установите: pip install LOLZTEAM",
                                      reply_markup=back("admin_panel"))
        return

    country_code = query.data.replace("lzt_country_", "")
    country_info = get_country_by_code(country_code)
    country_name = country_info['name'] if country_info else country_code
    country_flag = country_info['flag'] if country_info else "🌍"

    safe_cname = html.escape(str(country_name))
    await query.edit_message_text(
        f"⏳ <b>ИЩУ НОМЕР: {country_flag} {safe_cname}...</b>\n\n"
        f"Проверяю наличие лотов на LZT Market.",
        parse_mode="HTML"
    )

    def run_purchase():
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        market = _lzt_market_cls(token=get_lzt_token())
        if LZT_PROXY:
            market.settings.proxy = LZT_PROXY
        return _lzt_buy_single_account(market, target_country=country_code)

    try:
        loop = asyncio.get_running_loop()
        success, item_id, phone, login_data, country, price = await loop.run_in_executor(None, run_purchase)

        if not success and country and not item_id and price is None:
            safe_cname2 = html.escape(str(country_name))
            await query.edit_message_text(
                f"⚠️ <b>НЕТ ЛОТОВ: {country_flag} {safe_cname2}</b>\n\n"
                f"На LZT Market сейчас нет доступных номеров для этой страны.\n"
                f"Попробуйте позже или выберите другую страну.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🔄 ДРУГАЯ СТРАНА", "lzt_buy_country")],
                    [btn("🎲 РАНДОМ", "lzt_buy_random")],
                    [btn("🔙 НАЗАД", "admin_panel")]
                ])
            )
            return

        if success and item_id:
            lzt_purchases[user_id] = {
                "item_id": item_id,
                "phone": phone,
                "login_data": login_data,
                "country": country,
                "price": price
            }
            phone_display = phone if phone else "Неизвестен"

            price_rub_shop = 0
            price_stars_shop = 0
            if phone:
                cc = get_country_by_phone(phone)
                ccfg = get_country_by_code(cc)
                if ccfg:
                    price_rub_shop = ccfg.get('price') or 0
                    price_stars_shop = ccfg.get('stars') or 0

            queue_text = ""
            session_saved = False
            used_session = ""

            if phone:
                new_session, status = await _lzt_create_new_session(phone, item_id, get_lzt_token())

                if new_session:
                    used_session = new_session
                    session_saved = True
                    queue_text = (
                        f"🔒 <b>Клиент аккаунта подключён навсегда!</b>\n"
                        f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                        f"Номер уже добавлен в магазин."
                    )
                else:
                    old_session = _lzt_extract_session(login_data)
                    if old_session and await _lzt_verify_existing_session(old_session):
                        used_session = old_session
                        session_saved = True
                        safe_status = html.escape(str(status))
                        queue_text = (
                            f"⚠️ <b>Клиент жив из существующей сессии</b> ({safe_status})\n"
                            f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                            f"Номер уже добавлен в магазин."
                        )
                    else:
                        queue_text = (
                            f"❌ <b>Клиент не получен</b> ({html.escape(str(status))})\n"
                            f"💰 Цена в магазине: {price_rub_shop} ₽ / {price_stars_shop} ⭐\n"
                            f"Номер добавлен в магазин без клиента."
                        )

                if session_saved and used_session:
                    await add_phone_to_shop_now(phone, price_rub_shop, price_stars_shop, used_session, user_id, context)
                else:
                    add_phone_product(phone, price_rub_shop, price_stars_shop, "")
            else:
                queue_text = "❌ Номер телефона не найден — не удалось добавить в магазин."

            auto_code = None
            if session_saved and phone and used_session:
                auto_code, _ = await _lzt_get_fresh_code(used_session, phone)

            safe_phone2 = html.escape(str(phone_display))
            safe_country2 = html.escape(str(country or "N/A"))
            safe_price2 = html.escape(f"{price:.2f}")

            code_text = ""
            if auto_code:
                code_text = f"\n🔑 <b>КОД ДЛЯ ВХОДА:</b> <code>{html.escape(auto_code)}</code>\n"

            await query.edit_message_text(
                f"✅ <b>НОМЕР УСПЕШНО КУПЛЕН!</b>\n\n"
                f"🌍 Страна: {safe_country2}\n"
                f"📱 Номер: <code>{safe_phone2}</code>\n"
                f"💰 Цена покупки: {safe_price2} ₽\n\n"
                f"{queue_text}"
                f"{code_text}\n"
                f"⚠️ <b>Сразу после входа в аккаунт:</b>\n"
                f"1️⃣ Смените номер на свой\n"
                f"2️⃣ Поставьте 2FA\n"
                f"3️⃣ Установите облачный пароль\n"
                f"4️⃣ Привяжите почту",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
            )
        else:
            await query.edit_message_text(
                "❌ <b>НЕ УДАЛОСЬ КУПИТЬ НОМЕР.</b>\n"
                "Возможные причины:\n"
                "• Недостаточно средств\n"
                "• Ошибка API",
                parse_mode="HTML",
                reply_markup=back("admin_panel")
            )
    except Exception as e:
        logger.error(f"❌ Ошибка LZT покупки: {e}")
        safe_err = html.escape(str(e)[:200])
        await query.edit_message_text(
            f"❌ <b>ОШИБКА ПРИ ПОКУПКЕ:</b>\n<code>{safe_err}</code>",
            parse_mode="HTML",
            reply_markup=back("admin_panel")
        )

async def lzt_get_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return
    if user_id not in lzt_purchases:
        await query.edit_message_text("❌ Нет активной покупки! Сначала купите номер.", reply_markup=back("admin_panel"))
        return

    await query.edit_message_text(
        "⏳ <b>ПОЛУЧАЮ КОД С LZT MARKET...</b>\n\n"
        "Это может занять некоторое время. Ожидайте.",
        parse_mode="HTML"
    )

    item_id = lzt_purchases[user_id]["item_id"]
    phone = lzt_purchases[user_id].get("phone", "Неизвестен")

    def run_get_code():
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        market = _lzt_market_cls(token=get_lzt_token())
        if LZT_PROXY:
            market.settings.proxy = LZT_PROXY
        return _lzt_fetch_verification_code(market, item_id)

    try:
        loop = asyncio.get_running_loop()
        code = await loop.run_in_executor(None, run_get_code)
        if code:
            safe_phone3 = html.escape(str(phone))
            safe_code = html.escape(str(code))
            await query.edit_message_text(
                f"✅ <b>КОД ПОЛУЧЕН!</b>\n\n"
                f"📱 Номер: <code>{safe_phone3}</code>\n"
                f"🔑 Код: <code>{safe_code}</code>",
                parse_mode="HTML",
                reply_markup=back("admin_panel")
            )
        else:
            await query.edit_message_text(
                "⚠️ <b>КОД НЕ ПОЛУЧЕН</b>\n\n"
                "Возможные причины:\n"
                "• Код ещё не пришёл (попробуйте позже)\n"
                "• Аккаунт не требует SMS-код\n"
                "• Ошибка API",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🔄 ПОВТОРИТЬ", "lzt_get_code")],
                    [btn("🔙 НАЗАД", "admin_panel")]
                ])
            )
    except Exception as e:
        logger.error(f"❌ Ошибка получения кода: {e}")
        safe_err3 = html.escape(str(e)[:200])
        await query.edit_message_text(
            f"❌ <b>ОШИБКА ПРИ ПОЛУЧЕНИИ КОДА:</b>\n<code>{safe_err3}</code>",
            parse_mode="HTML",
            reply_markup=back("admin_panel")
        )

# ============================================================
# FLASK ВЕБХУК
# ============================================================
from flask import Flask, request
flask_app = Flask(__name__)

def start_flask():
    flask_app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)

@flask_app.route('/', methods=['POST'])
def yoomoney_webhook():
    data = request.form
    logger.info(f"📨 Получен вебхук: {data}")
    send_notification_to_telegram(data)
    if data.get('test_notification') == 'true':
        logger.info("🧪 Тестовое уведомление — пропускаем")
        return "OK", 200
    if data.get('notification_type') != 'card-incoming':
        logger.info(f"⏭️ Не card-incoming — пропускаем")
        return "OK", 200
    label = data.get('label')
    if label and label.startswith('rub_'):
        parts = label.split('_')
        if len(parts) >= 3:
            product_id = int(parts[1])
            user_id = int(parts[2])
            logger.info(f"💳 РЕАЛЬНЫЙ платёж: user_id={user_id}")
            if BOT_LOOP is not None:
                asyncio.run_coroutine_threadsafe(
                    auto_deliver_product(user_id, product_id),
                    BOT_LOOP
                )
            else:
                logger.error("❌ BOT_LOOP ещё не готов — не могу выдать товар")
    return "OK", 200

@flask_app.route('/', methods=['GET'])
def webhook_test():
    return "✅ Webhook работает!", 200

def send_notification_to_telegram(data):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        is_test = data.get('test_notification') == 'true'
        notification_type = data.get('notification_type', 'Неизвестно')
        amount = data.get('amount', '0')
        sender = data.get('sender', 'Неизвестно')
        label = data.get('label', 'Отсутствует')
        datetime_str = data.get('datetime', 'Неизвестно')
        if notification_type == 'card-incoming':
            sub_type = "Платёж по карте"
        elif notification_type == 'p2p-incoming':
            sub_type = "Перевод между кошельками"
        else:
            sub_type = notification_type
        product_id = "Неизвестно"
        user_id = "Неизвестно"
        phone = None
        price_stars = "Неизвестно"
        country_flag = "🌍"
        country_name = "Неизвестно"
        if label and label.startswith('rub_'):
            parts = label.split('_')
            if len(parts) >= 3:
                try:
                    product_id = int(parts[1])
                    user_id = int(parts[2])
                except (ValueError, IndexError):
                    pass
                product = get_phone_product(product_id)
                if product:
                    pid, phone, price_rub, price_stars, session = product[:5]
                    country_code = get_country_by_phone(phone)
                    country = get_country_by_code(country_code) if country_code else None
                    country_flag = country['flag'] if country else "🌍"
                    country_name = country['name'] if country else "Неизвестно"
        safe_sender = html.escape(sender)
        safe_datetime = html.escape(datetime_str)
        safe_country_name = html.escape(str(country_name))
        safe_hidden_phone = html.escape(str(phone)) if phone else "Неизвестно"
        if is_test:
            message = (
                f"🧪 <b>ТЕСТОВОЕ УВЕДОМЛЕНИЕ</b>\n\n"
                f"📌 Тип: {html.escape(sub_type)}\n"
                f"💰 Сумма: {amount} ₽\n"
                f"💵 Эквивалент: {price_stars} ⭐\n"
                f"👤 Покупатель: <code>{user_id}</code>\n"
                f"🆔 Отправитель: <code>{safe_sender}</code>\n"
                f"🌍 Страна: {country_flag} {safe_country_name}\n"
                f"📱 Номер: <code>{safe_hidden_phone}</code>\n"
                f"🏷️ Товар ID: <code>{product_id}</code>\n"
                f"📅 Дата: {safe_datetime}\n\n"
                f"⚠️ Это тестовое уведомление"
            )
        else:
            message = (
                f"💳 <b>ОПЛАТА РУБЛЯМИ</b>\n\n"
                f"📌 Тип: {html.escape(sub_type)}\n"
                f"💰 Сумма: {amount} ₽\n"
                f"💵 Эквивалент: {price_stars} ⭐\n"
                f"👤 Покупатель: <code>{user_id}</code>\n"
                f"🆔 Отправитель: <code>{safe_sender}</code>\n"
                f"🌍 Страна: {country_flag} {safe_country_name}\n"
                f"📱 Номер: <code>{safe_hidden_phone}</code>\n"
                f"🏷️ Товар ID: <code>{product_id}</code>\n"
                f"📅 Дата: {safe_datetime}\n\n"
                f"✅ Статус: ОПЛАЧЕНО"
            )
        all_ok = True
        for chat_id in (ADMIN_CHAT_ID, HELPER_ID):
            response = requests.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=5
            )
            if response.status_code != 200:
                all_ok = False
                logger.error(f"❌ Ошибка отправки в {chat_id}: {response.status_code} - {response.text}")
        if all_ok:
            logger.info("✅ Уведомление отправлено в Telegram")
        else:
            logger.error("❌ Ошибка отправки уведомления в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

async def send_stars_notification_to_telegram(context, user_id, username, phone, price_stars, price_rub, product_id):
    try:
        safe_username = html.escape(username) if username else "Нет"
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code) if country_code else None
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        safe_country_name = html.escape(country_name)
        hidden_phone = f"{phone[:4]}****{phone[-4:]}" if len(phone) > 6 else phone
        safe_hidden_phone = html.escape(hidden_phone)
        datetime_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        message = (
            f"⭐ <b>ОПЛАТА ЗВЁЗДАМИ</b>\n\n"
            f"📌 Тип: Оплата Telegram Stars\n"
            f"💰 Сумма: {price_stars} ⭐\n"
            f"💵 Эквивалент: {price_rub} ₽\n"
            f"👤 Покупатель: <code>{user_id}</code>\n"
            f"🆔 Username: @{safe_username}\n"
            f"🌍 Страна: {country_flag} {safe_country_name}\n"
            f"📱 Номер: <code>{safe_hidden_phone}</code>\n"
            f"🏷️ Товар ID: <code>{product_id}</code>\n"
            f"📅 Дата: {datetime_str}\n\n"
            f"✅ Статус: ОПЛАЧЕНО"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message, parse_mode="HTML")
        await context.bot.send_message(chat_id=HELPER_ID, text=message, parse_mode="HTML")
        logger.info(f"✅ Уведомление об оплате звёздами отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления об оплате звёздами: {e}")

async def auto_deliver_product(user_id, product_id):
    logger.info(f"🎁 АВТОМАТИЧЕСКАЯ ВЫДАЧА ТОВАРА ДЛЯ {user_id}")
    product = get_phone_product(product_id)
    if not product:
        logger.error(f"❌ Товар {product_id} не найден в БД!")
        return
    product_id, phone, price_rub, price_stars, session = product
    logger.info(f"📱 Найден товар в БД: {phone}")
    delete_result = delete_phone_product(product_id)
    if delete_result:
        logger.info(f"✅ Товар {phone} УДАЛЁН из магазина")
    else:
        logger.error(f"❌ Ошибка удаления товара {phone}!")
    country_code = get_country_by_phone(phone)
    if not country_code:
        country_code = "UNKNOWN"
        logger.warning(f"⚠️ Страна не найдена для {phone}, установлено UNKNOWN")
    logger.info(f"📝 Сохраняем покупку: user_id={user_id}, phone={phone}, country_code={country_code}")
    try:
        purchase_result = add_purchase(user_id, phone, price_rub, price_stars, session, country_code)
        if purchase_result:
            logger.info(f"✅ Покупка сохранена в БД: {phone}")
        else:
            logger.error(f"❌ add_purchase вернула False для {phone}!")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении покупки: {e}")
    purchases = get_user_purchases(user_id)
    if purchases:
        logger.info(f"✅ Найдено {len(purchases)} покупок у пользователя {user_id}")
    else:
        logger.error(f"❌ У пользователя {user_id} НЕТ покупок в БД!")
    awaiting_phone_confirmation[user_id] = {'phone': phone, 'product_id': product_id, 'session': session}
    logger.info(f"✅ Данные сохранены для получения кода")
    if user_id in pending_rub:
        del pending_rub[user_id]
        logger.info(f"✅ pending_rub очищен для {user_id}")
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=generate_product_message(phone, price_rub, price_stars),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
        )
        logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            message = generate_product_message(phone, price_rub, price_stars)
            keyboard = {"inline_keyboard": [[{"text": "🔑 ПОЛУЧИТЬ КОД", "callback_data": "get_code"}]]}
            requests.post(url, json={"chat_id": user_id, "text": message, "parse_mode": "Markdown", "reply_markup": keyboard}, timeout=5)
            logger.info(f"✅ Сообщение отправлено через requests")
        except Exception as e2:
            logger.error(f"❌ Ошибка через requests: {e2}")

def generate_product_message(phone, price_rub, price_stars):
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    return (
        f"✅ *ОПЛАЧЕНО!*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📱 *ВАШ НОМЕР:* `{phone}`\n"
        f"💰 {price_rub} ₽ / {price_stars}⭐\n\n"
        f"---\n"
        f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
        f"1️⃣ Смените номер телефона на свой\n"
        f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
        f"3️⃣ Установите облачный пароль\n"
        f"4️⃣ Привяжите почту для восстановления\n\n"
        f"🔑 Нажмите кнопку, чтобы получить код для входа:"
    )

# ============================================================
# ЗАПУСК БОТА
# ============================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        except:
            pass

async def run_app():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА...")
    logger.info("=" * 60)

    load_admins_from_db()
    logger.info(f"👑 АДМИНЫ: {ADMINS}")
    logger.info(f"🛠️ МОДЕРАТОРЫ: {MODERATORS}")

    app = Application.builder().token(BOT_TOKEN).build()
    global application
    application = app

    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )

    add_phone_conv = ConversationHandler(
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

    edit_rub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_rub_start, pattern="^edit_rub$")],
        states={EDIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_rub_input)]},
        fallbacks=[CommandHandler("start", start)]
    )

    edit_stars_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_stars_start, pattern="^edit_stars$")],
        states={EDIT_STARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_stars_input)]},
        fallbacks=[CommandHandler("start", start)]
    )

    offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(make_offer, pattern="^make_offer$")],
        states={AWAITING_OFFER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_offer)]},
        fallbacks=[CommandHandler("start", start)]
    )

    change_lzt_token_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(change_lzt_token_start, pattern="^change_lzt_token$")],
        states={EDIT_LZT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_lzt_token_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )

    compensate_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(compensate_start, pattern="^compensate$")],
        states={COMPENSATE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, compensate_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(add_admin_conv)
    app.add_handler(add_phone_conv)
    app.add_handler(edit_rub_conv)
    app.add_handler(edit_stars_conv)
    app.add_handler(offer_conv)
    app.add_handler(change_lzt_token_conv)
    app.add_handler(compensate_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(agree_terms, pattern="^agree_terms$"))
    app.add_handler(CallbackQueryHandler(disagree_terms, pattern="^disagree_terms$"))
    app.add_handler(CallbackQueryHandler(reviews, pattern="^reviews$"))
    app.add_handler(CallbackQueryHandler(offer, pattern="^offer$"))
    app.add_handler(CallbackQueryHandler(accept_offer, pattern=r"^accept_offer:\d+$"))
    app.add_handler(CallbackQueryHandler(reject_offer, pattern=r"^reject_offer:\d+$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(remove_admin, pattern="^remove_admin$"))
    app.add_handler(CallbackQueryHandler(remove_admin_confirm, pattern=r"^remove_admin_\d+$"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="^list_admins$"))

    app.add_handler(CallbackQueryHandler(lzt_buy_menu_callback, pattern="^lzt_buy_menu$"))
    app.add_handler(CallbackQueryHandler(lzt_buy_random_callback, pattern="^lzt_buy_random$"))
    app.add_handler(CallbackQueryHandler(lzt_buy_country_callback, pattern="^lzt_buy_country$"))
    app.add_handler(CallbackQueryHandler(lzt_buy_country_callback, pattern=r"^lzt_country_page_\d+$"))
    app.add_handler(CallbackQueryHandler(lzt_buy_country_select_callback, pattern="^lzt_country_[A-Z]+$"))
    app.add_handler(CallbackQueryHandler(lzt_get_code_callback, pattern="^lzt_get_code$"))

    app.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(shop_page, pattern=r"^shop_page_\d+$"))
    app.add_handler(CallbackQueryHandler(shop_country, pattern="^shop_country_"))
    app.add_handler(CallbackQueryHandler(select_phone, pattern=r"^select_phone_\d+$"))

    app.add_handler(CallbackQueryHandler(delete_phone_start, pattern="^delete_phone$"))
    app.add_handler(CallbackQueryHandler(delete_phone_confirm, pattern=r"^del_phone_\d+$"))
    app.add_handler(CallbackQueryHandler(delete_phone_yes, pattern=r"^del_yes_\d+$"))

    app.add_handler(CallbackQueryHandler(edit_price_start, pattern="^edit_price$"))
    app.add_handler(CallbackQueryHandler(edit_select_phone, pattern=r"^edit_select_\d+$"))

    app.add_handler(CallbackQueryHandler(pay_stars, pattern=r"^pay_stars_\d+$"))
    app.add_handler(CallbackQueryHandler(pay_rub, pattern=r"^pay_rub_\d+$"))
    app.add_handler(CallbackQueryHandler(check_rub, pattern=r"^check_rub_\d+$"))

    app.add_handler(CallbackQueryHandler(get_code_button, pattern="^get_code$"))
    app.add_handler(CallbackQueryHandler(code_ok_button, pattern="^code_ok$"))

    app.add_handler(CallbackQueryHandler(my_purchases, pattern="^my_purchases$"))
    app.add_handler(CallbackQueryHandler(purchase_code, pattern=r"^purchase_code_\d+$"))
    app.add_handler(CallbackQueryHandler(purchase_get_code, pattern=r"^purchase_get_code_\d+$"))
    app.add_handler(CallbackQueryHandler(purchase_ok, pattern=r"^purchase_ok_\d+$"))
    app.add_handler(CallbackQueryHandler(clear_purchases_start, pattern="^clear_purchases$"))
    app.add_handler(CallbackQueryHandler(clear_purchases_yes, pattern="^clear_purchases_yes$"))

    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    app.add_error_handler(error_handler)

    logger.info("=" * 60)
    logger.info("✅ БОТ ГОТОВ К РАБОТЕ!")
    logger.info("👑 ГЛАВНЫЙ АДМИН: " + str(ADMINS[0]))
    logger.info("🛠️ МОДЕРАТОРЫ: " + str(MODERATORS if MODERATORS else "Нет"))
    logger.info("=" * 60)

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    global BOT_LOOP
    BOT_LOOP = asyncio.get_running_loop()
    logger.info(f"🔄 BOT_LOOP установлен: {BOT_LOOP}")

    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask-сервер запущен на порту 10000")
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()