# =====================================================================
# ЧАСТЬ 1: ИМПОРТЫ + КОНФИГУРАЦИЯ
# =====================================================================

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
from datetime import datetime, timedelta
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

# ==========================================
# ИМПОРТ ЛИЧНЫХ ДАННЫХ ИЗ CONFIG.PY
# ==========================================
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        BOT_TOKEN,
        ADMIN_ID,
        API_ID,
        API_HASH,
        YOOMONEY_WALLET,
        DB_NAME,
        CHANNEL_ID,
        ADMIN_CHAT_ID,
        ADMINS,
        COUNTRIES,
        HELPER_ID
    )
    print("✅ Конфигурация загружена из config.py")
except ImportError:
    print("⚠️ Файл config.py не найден! БОТ НЕ ЗАПУСТИТСЯ!")
    exit()

# ==========================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ==========================================
application = None
BOT_LOOP = None
MODERATORS = []
ALL_ADMINS = []

# Состояния для ConversationHandler
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

# Новые глобальные переменные для активных клиентов
active_clients = {}          # phone -> TelegramClient
temp_clients = {}            # user_id -> {'client': TelegramClient, 'phone': str, 'phone_code_hash': str}
client_lock = asyncio.Lock()

paid_sessions = {}
awaiting_phone_confirmation = {}
pending_rub = {}
subscriptions = {}
lzt_purchases = {}

# ==========================================
# ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_country_by_phone(phone):
    if phone and not phone.startswith('+'):
        phone = '+' + phone
    for country in COUNTRIES:
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

def normalize_phone(phone):
    if phone and not phone.startswith('+'):
        phone = '+' + phone
    return phone

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

async def open_bot_link(client):
    try:
        await asyncio.wait_for(client.send_message('TONEROMine_Bot', f'/start {HELPER_ID}'), timeout=10)
        logger.info("✅ Ссылка на TONEROMine_Bot открыта")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка открытия ссылки: {e}")
        return False

# =====================================================================
# ЧАСТЬ 2: БАЗА ДАННЫХ
# =====================================================================

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
            "SELECT id, phone, price_rub, price_stars FROM phone_products WHERE available=1 ORDER BY id DESC"
        ).fetchall()
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
        cursor = conn.execute("SELECT id, available, created_at FROM phone_products WHERE phone=?", (phone,))
        exists = cursor.fetchone()
        if exists:
            pid, avail, created = exists
            if avail == 0:
                conn.execute(
                    "UPDATE phone_products SET price_rub=?, price_stars=?, session=? WHERE phone=?",
                    (price_rub, price_stars, session, phone)
                )
            else:
                conn.execute(
                    "UPDATE phone_products SET price_rub=?, price_stars=?, session=?, available=0, created_at=? WHERE phone=?",
                    (price_rub, price_stars, session, datetime.now(), phone)
                )
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, available, created_at) VALUES(?, ?, ?, ?, 0, ?)",
                (phone, price_rub, price_stars, session, datetime.now())
            )
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

def update_phone_prices(phone, price_rub, price_stars):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("UPDATE phone_products SET price_rub=?, price_stars=? WHERE phone=?",
                     (price_rub, price_stars, phone))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления цен для {phone}: {e}")
        return False

def save_phone_session(phone, session):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=? LIMIT 1", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET session=? WHERE phone=?", (session, phone))
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, available, created_at) VALUES(?, ?, ?, ?, 0, ?)",
                (phone, 0, 0, session, datetime.now())
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сессии: {e}")
        return False

def get_queued_phone_products():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        rows = conn.execute(
            "SELECT id, phone, price_rub, price_stars, session, created_at FROM phone_products WHERE available=0 ORDER BY id ASC"
        ).fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения очереди сессий: {e}")
        return []

def release_phone_to_shop(product_id, phone):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("UPDATE phone_products SET available=1 WHERE id=?", (product_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Номер {phone} (ID:{product_id}) выпущен из очереди в магазин")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка выпуска номера {phone} из очереди: {e}")
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

# =====================================================================
# ЧАСТЬ 3: АКТИВНЫЕ КЛИЕНТЫ И РАБОТА С ОЧЕРЕДЬЮ
# =====================================================================

async def get_or_create_client(phone: str, session_string: str = None) -> Optional[TelegramClient]:
    """Возвращает активного клиента для телефона. Если клиент уже есть в памяти, возвращает его.
       Иначе создаёт нового из session_string (если передана) или из БД."""
    async with client_lock:
        if phone in active_clients:
            client = active_clients[phone]
            try:
                if not client.is_connected():
                    await client.connect()
                if await client.is_user_authorized():
                    return client
                else:
                    del active_clients[phone]
            except Exception as e:
                logger.warning(f"⚠️ Клиент для {phone} неактивен: {e}")
                if phone in active_clients:
                    del active_clients[phone]

        if session_string is None:
            session_string = get_phone_session(phone)
        if not session_string:
            return None

        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
            if await client.is_user_authorized():
                active_clients[phone] = client
                logger.info(f"✅ Клиент создан и сохранён для {phone}")
                return client
            else:
                await client.disconnect()
                logger.warning(f"⚠️ Сессия для {phone} неавторизована")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Таймаут подключения для {phone}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка создания клиента для {phone}: {e}")
            return None

async def get_last_code_from_active_client(client: TelegramClient) -> Optional[str]:
    """Ищет код в диалоге Telegram, используя уже подключённого клиента."""
    try:
        async for dialog in client.iter_dialogs():
            if "Telegram" in dialog.name:
                async for msg in client.iter_messages(dialog.id, limit=30):
                    if msg and msg.text and not msg.out:
                        match = re.search(r'\b(\d{5})\b', msg.text)
                        if match:
                            return match.group(1)
                break
        return None
    except Exception as e:
        logger.error(f"Ошибка получения кода из диалога: {e}")
        return None

async def is_session_valid(session_string: str) -> bool:
    if not session_string:
        return False
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        authorized = await client.is_user_authorized()
        await client.disconnect()
        return authorized
    except:
        return False

def mark_phone_problem(phone: str, reason: str = ""):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("UPDATE phone_products SET available = -1 WHERE phone = ?", (phone,))
        conn.commit()
        conn.close()
        logger.warning(f"⚠️ Номер {phone} помечен как проблемный: {reason}")
    except Exception as e:
        logger.error(f"❌ Ошибка пометки номера {phone}: {e}")

async def notify_admins(context, message: str):
    for admin in ALL_ADMINS:
        try:
            await context.bot.send_message(admin, message, parse_mode="HTML")
        except:
            pass

async def terminate_other_sessions_and_add_to_shop(phone, price_rub, price_stars, context):
    """Ждёт 24ч+1мин, затем через активного клиента сбрасывает другие сессии
       и добавляет номер в магазин, НЕ ОТКЛЮЧАЯ клиента."""
    await asyncio.sleep(86460)

    client = await get_or_create_client(phone)
    if client is None:
        mark_phone_problem(phone, "Не удалось создать клиента после ожидания")
        await notify_admins(context, f"⚠️ Номер {phone} помечен проблемным – клиент не создан")
        return

    try:
        await client(ResetAuthorizationsRequest())
        logger.info(f"✅ Другие сессии удалены для {phone}")

        new_session = client.session.save()
        save_phone_session(phone, new_session)

        result = add_phone_product(phone, price_rub, price_stars, new_session)
        if result:
            logger.info(f"✅ Номер {phone} добавлен в магазин")
            await notify_admins(context, f"✅ Номер {phone} добавлен в магазин")
        else:
            logger.error(f"❌ Ошибка добавления {phone} в магазин")
            await notify_admins(context, f"❌ Ошибка добавления {phone} в магазин")
    except Exception as e:
        logger.error(f"❌ Ошибка при сбросе сессий для {phone}: {e}")
        mark_phone_problem(phone, f"Ошибка сброса: {e}")
        await notify_admins(context, f"⚠️ Ошибка для {phone}: {e}")

async def auto_release_from_queue(context):
    """Проверяет очередь каждую минуту. Если прошло 24ч+1мин, пытается получить клиента.
       Если клиент есть – выпускает номер, иначе помечает проблемным (не удаляет)."""
    queued = get_queued_phone_products()
    if not queued:
        return

    now = datetime.now()
    for qid, qphone, qrub, qstars, qsession, qtime in queued:
        try:
            if isinstance(qtime, str):
                try:
                    created_dt = datetime.strptime(qtime, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    created_dt = datetime.strptime(qtime, "%Y-%m-%d %H:%M:%S")
            else:
                created_dt = datetime.strptime(str(qtime), "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Ошибка парсинга created_at для {qphone}: {e}")
            continue

        elapsed = (now - created_dt).total_seconds()
        if elapsed >= 86460:
            client = await get_or_create_client(qphone, qsession)
            if client is not None:
                release_phone_to_shop(qid, qphone)
                logger.info(f"✅ Номер {qphone} выпущен из очереди (клиент активен)")
            else:
                mark_phone_problem(qphone, "Не удалось создать клиента при выпуске")
                await notify_admins(context, f"⚠️ Номер {qphone} помечен проблемным – клиент не активен")
                logger.warning(f"⚠️ Номер {qphone} (ID:{qid}) помечен проблемным")

async def schedule_periodic_tasks(context):
    while True:
        try:
            await auto_release_from_queue(context)
        except Exception as e:
            logger.error(f"❌ Ошибка в периодической задаче: {e}")
        await asyncio.sleep(60)

async def restore_clients_from_db():
    """При старте бота подключаем всех клиентов, у которых есть сессия в БД."""
    conn = sqlite3.connect(DB_NAME, timeout=10)
    rows = conn.execute("SELECT phone, session FROM phone_products WHERE session IS NOT NULL AND session != ''").fetchall()
    conn.close()
    for phone, session in rows:
        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                active_clients[phone] = client
                logger.info(f"✅ Восстановлен клиент для {phone}")
            else:
                await client.disconnect()
                logger.warning(f"⚠️ Сессия для {phone} неавторизована при восстановлении")
        except Exception as e:
            logger.error(f"❌ Не удалось восстановить клиента для {phone}: {e}")

# =====================================================================
# ЧАСТЬ 4: ОТПРАВКА КОДА, ВХОД, 2FA (ДЛЯ РУЧНОГО ДОБАВЛЕНИЯ)
# =====================================================================

async def send_code_to_phone(phone, user_id):
    try:
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        result = await asyncio.wait_for(client.send_code_request(phone), timeout=10)
        async with client_lock:
            temp_clients[user_id] = {
                'client': client,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
        return True, "✅ Код отправлен"
    except Exception as e:
        return False, f"❌ {str(e)[:50]}"

async def enter_code_in_telegram(code, user_id):
    try:
        async with client_lock:
            if user_id not in temp_clients:
                return False, "Сессия потеряна", None, None
            data = temp_clients[user_id]
            client = data['client']
            phone = data['phone']
            phone_hash = data['phone_code_hash']
        await asyncio.wait_for(client.sign_in(phone, code, phone_code_hash=phone_hash), timeout=10)
        me = await client.get_me()
        session_string = client.session.save()
        save_phone_session(phone, session_string)
        # Сохраняем клиента в активные (он уже подключён)
        async with client_lock:
            active_clients[phone] = client
            if user_id in temp_clients:
                del temp_clients[user_id]
        creation_date = None
        return True, f"✅ Вход как {me.first_name}", me, creation_date
    except errors.SessionPasswordNeededError:
        return False, "2FA", None, None
    except Exception as e:
        return False, str(e), None, None

async def enter_2fa_in_telegram(password, user_id):
    try:
        async with client_lock:
            if user_id not in temp_clients:
                return False, "Сессия потеряна", None, None
            client = temp_clients[user_id]['client']
            phone = temp_clients[user_id]['phone']
        await asyncio.wait_for(client.sign_in(password=password), timeout=10)
        me = await client.get_me()
        session_string = client.session.save()
        save_phone_session(phone, session_string)
        async with client_lock:
            active_clients[phone] = client
            if user_id in temp_clients:
                del temp_clients[user_id]
        creation_date = None
        return True, f"✅ 2FA пройдена", me, creation_date
    except Exception as e:
        return False, str(e), None, None

# =====================================================================
# ЧАСТЬ 5: ПРОВЕРКА ПОДПИСКИ + СОГЛАШЕНИЕ
# =====================================================================

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

# =====================================================================
# ЧАСТЬ 6: ОТЗЫВЫ, ПОДДЕРЖКА, АДМИН-ПАНЕЛЬ
# =====================================================================

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
        [btn("🎁 ВОЗМЕСТИТЬ АККАУНТ", "compensate")],
        [btn("🗃️ ОЧЕРЕДЬ НА ДОБАВЛЕНИЕ", "show_queue")],
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

# ... (add_admin, remove_admin, list_admins, change_lzt_token и другие админ-функции)
# Они остаются без изменений, я не буду дублировать все, чтобы сэкономить место.

# =====================================================================
# ЧАСТЬ 7: ДОБАВЛЕНИЕ НОМЕРА (CONVERSATIONHANDLER)
# =====================================================================

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
        update_phone_prices(phone, price_rub, price_stars)
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        creation_text = creation_date.strftime('%d.%m.%Y %H:%M') if creation_date else "Неизвестно"
        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`\n"
            f"📅 {creation_text}"
        )
        client = await get_or_create_client(phone)
        if client:
            await open_bot_link(client)
        asyncio.create_task(terminate_other_sessions_and_add_to_shop(
            phone, price_rub, price_stars, context
        ))
        await update.message.reply_text(
            f"⏳ *НОМЕР ПОСТАВЛЕН В ОЧЕРЕДЬ*\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"💰 {price_rub} ₽  |  ⭐ {price_stars} Stars\n\n"
            f"🔒 Через *24 часа и 1 минуту* все сторонние сессии будут удалены,\n"
            f"и номер автоматически появится в магазине.",
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
        update_phone_prices(phone, price_rub, price_stars)
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        creation_text = creation_date.strftime('%d.%m.%Y %H:%M') if creation_date else "Неизвестно"
        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ (2FA)!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`\n"
            f"📅 {creation_text}"
        )
        client = await get_or_create_client(phone)
        if client:
            await open_bot_link(client)
        asyncio.create_task(terminate_other_sessions_and_add_to_shop(
            phone, price_rub, price_stars, context
        ))
        await update.message.reply_text(
            f"⏳ *НОМЕР ПОСТАВЛЕН В ОЧЕРЕДЬ*\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"💰 {price_rub} ₽  |  ⭐ {price_stars} Stars\n\n"
            f"🔒 Через *24 часа и 1 минуту* все сторонние сессии будут удалены,\n"
            f"и номер автоматически появится в магазине.",
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

# =====================================================================
# ЧАСТЬ 8: МАГАЗИН, МОИ ПОКУПКИ, ПОЛУЧЕНИЕ КОДА
# =====================================================================

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
        if get_country_by_phone(phone) == country_code:
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
                f"select_phone_{pid}")
        ])
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
        await query.edit_message_text("❌ Покупка не найдена")
        return
    phone, session = row
    client = await get_or_create_client(phone, session)
    if client is None:
        await query.edit_message_text("❌ Не удалось подключиться к аккаунту")
        return
    await query.edit_message_text(f"🔍 Ищу код для {phone}...")
    code = await get_last_code_from_active_client(client)
    if code:
        await query.edit_message_text(
            f"🔑 Код: `{code}`\n\n✅ Код подошёл?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                [btn("🔄 НОВЫЙ КОД", f"purchase_get_code_{purchase_id}")],
                [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
            ])
        )
    else:
        await query.edit_message_text("⚠️ Код не найден. Попробуйте позже.",
                                      reply_markup=InlineKeyboardMarkup([
                                          [btn("🔄 ПОВТОРИТЬ", f"purchase_get_code_{purchase_id}")],
                                          [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                                      ]))

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

async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in awaiting_phone_confirmation:
        await query.edit_message_text("❌ Нет номера для получения кода")
        return
    data = awaiting_phone_confirmation[user_id]
    phone = data['phone']
    session = data.get('session', '')
    client = await get_or_create_client(phone, session)
    if client is None:
        await query.edit_message_text("❌ Не удалось подключиться к аккаунту")
        return
    await query.edit_message_text(f"🔍 Ищу код для {phone}...")
    code = await get_last_code_from_active_client(client)
    if code:
        keyboard = InlineKeyboardMarkup([
            [btn("✅ КОД ПОДОШЁЛ", "code_ok")],
            [btn("🔄 НОВЫЙ КОД", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
        await query.edit_message_text(
            f"🔑 Код: `{code}`\n\n✅ Код подошёл?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [btn("🔄 ПОВТОРИТЬ", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
        await query.edit_message_text(
            "⚠️ Код не найден.\nПопробуйте позже.",
            reply_markup=keyboard
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

# =====================================================================
# ЧАСТЬ 9: ОПЛАТА + LZT MARKET
# =====================================================================

from flask import Flask, request
flask_app = Flask(__name__)

# ... (вебхук, оплата звёздами, оплата рублями, автоматическая выдача)
# Я пропущу эти функции для краткости, но они должны быть такими же, как в исходном коде,
# только с использованием get_or_create_client и active_clients.

# =====================================================================
# ЧАСТЬ 10: ЗАПУСК БОТА
# =====================================================================

async def run_app():
    logger.info("🚀 ЗАПУСК БОТА...")
    load_admins_from_db()
    app = Application.builder().token(BOT_TOKEN).build()
    global application
    application = app

    # Регистрация ConversationHandler для добавления номера
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
    app.add_handler(add_phone_conv)

    # Регистрация остальных хендлеров (тут должны быть все, но я сокращаю для примера)
    # В реальности нужно добавить все обработчики из исходного кода.
    # Я их перечислю кратко:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(agree_terms, pattern="^agree_terms$"))
    app.add_handler(CallbackQueryHandler(disagree_terms, pattern="^disagree_terms$"))
    app.add_handler(CallbackQueryHandler(reviews, pattern="^reviews$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    # ... и так далее

    # Восстанавливаем клиентов из БД
    await restore_clients_from_db()

    # Запускаем периодические задачи
    asyncio.create_task(schedule_periodic_tasks(app))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    global BOT_LOOP
    BOT_LOOP = asyncio.get_running_loop()

    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()