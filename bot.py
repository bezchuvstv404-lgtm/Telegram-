# ==========================================
# АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ
# ==========================================
import subprocess
import sys

def install_dependencies():
    dependencies = ["aiohttp", "flask", "python-telegram-bot", "requests", "telethon"]
    for package in dependencies:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package} уже установлен")
        except ImportError:
            print(f"📦 Устанавливаю {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package, "--quiet"])
            print(f"✅ {package} установлен")

install_dependencies()
print("✅ Все зависимости проверены!")
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
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetParticipantRequest

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
    CHANNEL_ID,
    ADMIN_CHAT_ID,
    ADMINS,
    COUNTRIES
)

# ==========================================
# ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# МОДЕРАТОРЫ (ЗАГРУЖАЮТСЯ ИЗ БД)
# ==========================================
MODERATORS = []
ALL_ADMINS = []

# ==========================================
# СОСТОЯНИЯ ДЛЯ CONVERSATIONHANDLER
# ==========================================
PHONE_PRICE, PHONE_STARS, PHONE_AGE, PHONE_NUMBER = range(10, 14)
ENTER_CODE = 20
ENTER_2FA = 21
ADD_ADMIN = 30
REMOVE_ADMIN = 31

# ==========================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ==========================================
clients = {}
accounts = {}
paid_sessions = {}
awaiting_phone_confirmation = {}
pending_rub = {}
subscriptions = {}
telethon_clients_cache = {}
clients_lock = asyncio.Lock()
accounts_lock = asyncio.Lock()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СТРАН
# ==========================================
def get_country_by_phone(phone):
    """Определяет страну по номеру телефона"""
    for country in COUNTRIES:
        if phone.startswith(country['phone_code']):
            return country['code']
    return "UNKNOWN"

def get_country_by_code(code):
    """Возвращает данные страны по коду"""
    for country in COUNTRIES:
        if country['code'] == code:
            return country
    return None

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 1 ЗАГРУЖЕНА: ИМПОРТЫ + КОНФИГ")
logger.info(f"👑 ГЛАВНЫЙ АДМИН: {ADMINS[0]}")
logger.info(f"📢 ID КАНАЛА: {CHANNEL_ID}")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 2: БАЗА ДАННЫХ
# =====================================================================

def init_db():
    """Создаёт таблицы в базе данных"""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phone_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                price_rub INTEGER,
                price_stars INTEGER,
                age INTEGER,
                session TEXT,
                created_at TIMESTAMP
            )
        """)
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
                age INTEGER,
                session TEXT,
                country_code TEXT,
                purchased_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("✅ База данных готова")
        load_admins_from_db()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

def load_admins_from_db():
    """Загружает админов из БД"""
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
        rows = conn.execute("SELECT id, phone, price_rub, price_stars, age FROM phone_products ORDER BY id DESC").fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения номеров: {e}")
        return []

def get_phone_product(product_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT id, phone, price_rub, price_stars, age, session FROM phone_products WHERE id=?", (product_id,)).fetchone()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"❌ Ошибка получения номера #{product_id}: {e}")
        return None

def add_phone_product(phone, price_rub, price_stars, age, session=""):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=?", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET price_rub=?, price_stars=?, age=?, session=? WHERE phone=?",
                         (price_rub, price_stars, age, session, phone))
        else:
            conn.execute("INSERT INTO phone_products(phone, price_rub, price_stars, age, session, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                         (phone, price_rub, price_stars, age, session, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления: {e}")
        return False

def delete_phone_product(product_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("DELETE FROM phone_products WHERE id=?", (product_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления: {e}")
        return False

def save_phone_session(phone, session):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=? LIMIT 1", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET session=? WHERE phone=? LIMIT 1", (session, phone))
        else:
            conn.execute("INSERT INTO phone_products(phone, price_rub, price_stars, age, session, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                         (phone, 0, 0, 0, session, datetime.now()))
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

def add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("""
            INSERT INTO purchases (user_id, phone, price_rub, price_stars, age, session, country_code, purchased_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, phone, price_rub, price_stars, age, session, country_code, datetime.now()))
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
            SELECT id, phone, price_rub, price_stars, age, session, country_code, purchased_at
            FROM purchases
            WHERE user_id=?
            ORDER BY purchased_at DESC
        """, (user_id,)).fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения покупок: {e}")
        return []

init_db()

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 2 ЗАГРУЖЕНА: БАЗА ДАННЫХ")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 3: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

def btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

def kb(*rows):
    return InlineKeyboardMarkup(list(rows))

def back(cb="start"):
    return kb([btn("🔙 НАЗАД", cb)])

def hide_phone(phone):
    if len(phone) > 6:
        return f"{phone[:4]}****{phone[-4:]}"
    return phone

def validate_phone(phone):
    return bool(re.match(r'^\+\d{10,15}$', phone))

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

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 3 ЗАГРУЖЕНА: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 4: TELETHON
# =====================================================================

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

async def get_account_creation_date_direct(client):
    try:
        full_user = await client(GetFullUserRequest(id='me'))
        return full_user.user.date
    except Exception as e:
        return None

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
        creation_date = await get_account_creation_date_direct(client)
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
        return True, f"✅ Вход как {me.first_name}", me, creation_date
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
        creation_date = await get_account_creation_date_direct(client)
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

async def get_last_code_from_account(phone, session_string):
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None, "Аккаунт не авторизован"
        code_found = None
        last_time = 0
        last_dialog = ""
        async for dialog in client.iter_dialogs():
            if "Telegram" not in dialog.name and "Служебные" not in dialog.name:
                continue
            async for msg in client.iter_messages(dialog.id, limit=100):
                if not msg or not msg.text or msg.out:
                    continue
                text = msg.text
                if any(word in text.lower() for word in ["login", "new device", "terminate"]):
                    continue
                match = re.search(r'\b(\d{5})\b', text)
                if match:
                    code = match.group(1)
                    t = msg.date.timestamp() if msg.date else 0
                    if t > last_time:
                        code_found = code
                        last_time = t
                        last_dialog = dialog.name
        await client.disconnect()
        if code_found:
            return code_found, last_dialog
        return None, "Код не найден"
    except Exception as e:
        return None, str(e)

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 4 ЗАГРУЖЕНА: TELETHON")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 5: ПРОВЕРКА ПОДПИСКИ + СОГЛАШЕНИЕ
# =====================================================================

async def check_user_subscription(user_id):
    logger.info(f"🔍 Проверяем подписку для {user_id}")
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"chat_id": CHANNEL_ID, "user_id": user_id}, timeout=aiohttp.ClientTimeout(total=5)) as response:
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
    keyboard = kb([btn("✅ ПРИНЯТЬ ПРАВИЛА", "agree_terms")], [btn("❌ ОТКЛОНИТЬ", "disagree_terms")])
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def show_main_menu(update_or_query, user_id):
    if user_id not in subscriptions or subscriptions[user_id] != "agreed":
        await show_terms(update_or_query, user_id)
        return
    rows = [
        [btn("🛒 МАГАЗИН", "shop")],
        [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
        [btn("⭐ ОТЗЫВЫ", "reviews")],
        [btn("🆘 ПОДДЕРЖКА", "support")]
    ]
    if user_id in ALL_ADMINS:
        rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
    text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb(*rows))
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb(*rows))

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
    is_subscribed = await check_user_subscription(user_id)
    if is_subscribed:
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

async def sub_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url="https://t.me/ponchinoscam")],
        [btn("🔍 ПРОВЕРИТЬ ПОДПИСКУ", "check_sub")],
        [btn("🔙 НАЗАД", "start")]
    ])
    await query.edit_message_text(
        "📢 *ПОДПИШИТЕСЬ НА НАШ КАНАЛ*\n\n"
        "Нажмите на кнопку, чтобы подписаться:\n\n"
        "✅ После подписки вернитесь и нажмите «ПРОВЕРИТЬ ПОДПИСКУ»",
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

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 5 ЗАГРУЖЕНА: ПРОВЕРКА ПОДПИСКИ + СОГЛАШЕНИЕ")
logger.info("=" * 60)
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
    if user_id not in ALL_ADMINS:
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("start"))
        return
    buttons = [[btn("📱 ДОБАВИТЬ НОМЕР", "add_phone")]]
    if user_id in ADMINS:
        buttons.append([btn("➕ ДОБАВИТЬ АДМИНА", "add_admin")])
        buttons.append([btn("🗑️ УДАЛИТЬ АДМИНА", "remove_admin")])
        buttons.append([btn("📊 СПИСОК АДМИНОВ", "list_admins")])
        buttons.append([btn("🗑️ УДАЛИТЬ НОМЕР", "delete_phone")])
    buttons.append([btn("🔙 НАЗАД", "start")])
    role = "👑 ГЛАВНЫЙ АДМИН" if user_id in ADMINS else "🛠️ МОДЕРАТОР"
    await query.edit_message_text(f"👥 *АДМИН-ПАНЕЛЬ*\n\nВаша роль: {role}", parse_mode="Markdown", reply_markup=kb(*buttons))

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in ADMINS:
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    await query.edit_message_text("➕ Введите ID пользователя:", reply_markup=back("admin_panel"))
    return ADD_ADMIN

async def add_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
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
    await update.message.reply_text(f"✅ Добавлен! ID: `{new_admin_id}`", parse_mode="Markdown", reply_markup=back("admin_panel"))
    return ConversationHandler.END

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in ADMINS:
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    rows = [[btn(f"👑 {ADMINS[0]} (Главный)", "noop")]]
    for mod_id in MODERATORS:
        rows.append([btn(f"🗑️ {mod_id}", f"remove_admin_{mod_id}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("🗑️ Выберите для удаления:", reply_markup=kb(*rows))

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in ADMINS:
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
    if update.effective_user.id not in ADMINS:
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    text = "📊 *СПИСОК*\n\n👑 Главный: `{}`\n".format(ADMINS[0])
    if MODERATORS:
        text += "\n🛠️ Модераторы:\n" + "\n".join([f"• `{m}`" for m in MODERATORS])
    else:
        text += "\n🛠️ Модераторов нет"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back("admin_panel"))

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 6 ЗАГРУЖЕНА: ОТЗЫВЫ, ПОДДЕРЖКА, АДМИН-ПАНЕЛЬ")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 7: ДОБАВЛЕНИЕ НОМЕРА + МАГАЗИН + МОИ ПОКУПКИ
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
        await update.message.reply_text("📅 Введи возраст аккаунта (дней):")
        return PHONE_AGE
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_STARS

async def add_phone_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text.strip())
        if age < 0:
            await update.message.reply_text("❌ Отрицательный возраст!")
            return PHONE_AGE
        context.user_data['age'] = age
        await update.message.reply_text("📱 Введи номер (+79991234567):")
        return PHONE_NUMBER
    except ValueError:
        await update.message.reply_text("❌ Введи число!")
        return PHONE_AGE

async def add_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not validate_phone(phone):
        await update.message.reply_text("❌ Неверный формат! Пример: +79991234567")
        return PHONE_NUMBER
    context.user_data['adding_phone'] = phone
    context.user_data['adding_price_rub'] = context.user_data['price_rub']
    context.user_data['adding_price_stars'] = context.user_data['price_stars']
    context.user_data['age'] = context.user_data['age']
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
        age = context.user_data['age']
        session_string = ""
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')
        result = add_phone_product(phone, price_rub, price_stars, age, session_string)
        if session_string:
            save_phone_session(phone, session_string)
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        creation_text = creation_date.strftime('%d.%m.%Y %H:%M') if creation_date else "Неизвестно"
        age_text = str((datetime.now() - creation_date).days) if creation_date else "Неизвестно"
        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`\n"
            f"📅 {creation_text}\n"
            f"⏳ {age_text} дней"
        )
        if result:
            await update.message.reply_text(
                f"✅ НОМЕР ДОБАВЛЕН!\n\n"
                f"📱 {phone}\n"
                f"🌍 {country_flag} {country_name}\n"
                f"💰 {price_rub} ₽\n"
                f"⭐ {price_stars} Stars\n"
                f"📅 {age} дней"
            )
        else:
            await update.message.reply_text("❌ Ошибка добавления!")
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
        age = context.user_data['age']
        session_string = ""
        async with accounts_lock:
            if user_id in accounts and phone in accounts[user_id]:
                session_string = accounts[user_id][phone].get('session', '')
        result = add_phone_product(phone, price_rub, price_stars, age, session_string)
        if session_string:
            save_phone_session(phone, session_string)
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        creation_text = creation_date.strftime('%d.%m.%Y %H:%M') if creation_date else "Неизвестно"
        age_text = str((datetime.now() - creation_date).days) if creation_date else "Неизвестно"
        await update.message.reply_text(
            f"✅ ВОШЁЛ В АККАУНТ (2FA)!\n\n"
            f"📱 {phone}\n"
            f"🌍 {country_flag} {country_name}\n"
            f"👤 {me.first_name}\n"
            f"🆔 `{me.id}`\n"
            f"📅 {creation_text}\n"
            f"⏳ {age_text} дней"
        )
        if result:
            await update.message.reply_text(
                f"✅ НОМЕР ДОБАВЛЕН!\n\n"
                f"📱 {phone}\n"
                f"🌍 {country_flag} {country_name}\n"
                f"💰 {price_rub} ₽\n"
                f"⭐ {price_stars} Stars\n"
                f"📅 {age} дней"
            )
        else:
            await update.message.reply_text("❌ Ошибка добавления!")
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ENTER_2FA

async def delete_phone_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.edit_message_text("❌ Нет номеров", reply_markup=back("start"))
        return
    rows = []
    for pid, phone, price_rub, price_stars, age in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"🗑️ {flag} {phone} ({age} дн.)", f"del_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text("Выбери номер:", reply_markup=kb(*rows))

async def delete_phone_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Не найден")
        return
    pid, phone, price_rub, price_stars, age = product[:5]
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code)
    flag = country['flag'] if country else "🌍"
    await query.edit_message_text(f"⚠️ УДАЛИТЬ?\n\n📱 {flag} {phone}\n📅 {age} дней", reply_markup=kb([btn("✅ ДА", f"del_yes_{pid}")], [btn("❌ НЕТ", "delete_phone")]))

async def delete_phone_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    delete_phone_product(product_id)
    await query.edit_message_text("✅ УДАЛЕНО", reply_markup=back("start"))

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_phone_products()
    if not products:
        await query.message.reply_text("❌ Номеров нет", reply_markup=back("start"))
        return
    countries_data = {}
    for pid, phone, price_rub, price_stars, age in products:
        country_code = get_country_by_phone(phone)
        if country_code not in countries_data:
            countries_data[country_code] = []
        countries_data[country_code].append((pid, phone, price_rub, price_stars, age))
    sorted_countries = sorted(countries_data.items(), key=lambda x: get_country_by_code(x[0])['name'] if get_country_by_code(x[0]) else x[0])
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
            rows.append([btn(f"{country['flag']} {country['name']} ({country['phone_code']}) · {count} шт.", f"shop_country_{country_code}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(btn("⬅️ НАЗАД", f"shop_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(btn("➡️ ДАЛЕЕ", f"shop_page_{page+1}"))
    if nav_buttons:
        rows.append(nav_buttons)
    rows.append([btn("🔙 НАЗАД", "start")])
    text = f"🏪 *МАГАЗИН PONCHI*\n\nВыберите страну:\n\n📄 Страница {page+1} из {total_pages}"
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb(*rows))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb(*rows))

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
    for pid, phone, price_rub, price_stars, age in products:
        if phone.startswith(country['phone_code']):
            country_phones.append((pid, phone, price_rub, price_stars, age))
    if not country_phones:
        await query.edit_message_text(f"❌ Нет номеров для {country['flag']} {country['name']}", reply_markup=back("shop"))
        return
    country_phones.sort(key=lambda x: x[2])
    rows = []
    for idx, (pid, phone, price_rub, price_stars, age) in enumerate(country_phones, 1):
        flag = country['flag']
        code = country['phone_code']
        rows.append([btn(f"[ {idx} ] {flag} {code} Цена {price_stars}⭐ / {price_rub}₽", f"select_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "shop")])
    await query.edit_message_text(
        f"📍 *{country['flag']} {country['name']} ({country['phone_code']})*\n\n"
        f"📱 Доступно: {len(country_phones)} номеров\n\n"
        f"Выберите номер (сортировка по цене ↑):",
        parse_mode="Markdown",
        reply_markup=kb(*rows)
    )

async def select_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.edit_message_text("❌ Номер уже продан или удалён")
        return
    pid, phone, price_rub, price_stars, age, session = product[:6]
    hidden_phone = f"{phone[:4]}****{phone[-4:]}" if len(phone) > 6 else phone
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code)
    country_flag = country['flag'] if country else "🌍"
    country_name = country['name'] if country else "Неизвестно"
    buttons = []
    if price_stars > 0:
        buttons.append([btn(f"⭐ Оплатить {price_stars} Stars", f"pay_stars_{product_id}")])
    else:
        buttons.append([btn("⭐ Бесплатно (Stars)", f"pay_stars_{product_id}")])
    if price_rub > 0:
        buttons.append([btn(f"💳 Оплатить {price_rub} ₽", f"pay_rub_{product_id}")])
    else:
        buttons.append([btn("💳 Бесплатно (Рубли)", f"pay_rub_{product_id}")])
    buttons.append([btn("🔙 НАЗАД", "shop")])
    await query.edit_message_text(
        f"💳 *ОПЛАТА*\n\n"
        f"📱 {country_flag} {hidden_phone}\n"
        f"🌍 {country_name}\n"
        f"📅 {age} дней\n"
        f"💰 {price_rub} ₽\n"
        f"⭐ {price_stars} Stars",
        parse_mode="Markdown",
        reply_markup=kb(*buttons)
    )

async def my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    purchases = get_user_purchases(user_id)
    if not purchases:
        await query.edit_message_text("📦 *МОИ ПОКУПКИ*\n\nУ вас пока нет покупок.", parse_mode="Markdown", reply_markup=back("start"))
        return
    rows = []
    for purchase in purchases:
        pid, phone, price_rub, price_stars, age, session, country_code, purchased_at = purchase
        country = get_country_by_code(country_code) if country_code else None
        flag = country['flag'] if country else "🌍"
        code = country['phone_code'] if country else ""
        rows.append([btn(f"{flag} {code} {phone} - {price_stars}⭐ / {price_rub}₽", f"purchase_code_{pid}")])
    rows.append([btn("🔙 НАЗАД", "start")])
    await query.edit_message_text(
        f"📦 *МОИ ПОКУПКИ*\n\n📱 Всего покупок: {len(purchases)}\n\nВыберите номер для получения кода:",
        parse_mode="Markdown",
        reply_markup=kb(*rows)
    )

async def purchase_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    purchase_id = int(query.data.replace("purchase_code_", ""))
    conn = sqlite3.connect(DB_NAME, timeout=10)
    row = conn.execute("SELECT phone, price_rub, price_stars, age, session, country_code FROM purchases WHERE id=?", (purchase_id,)).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, price_rub, price_stars, age, session, country_code = row
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    await query.edit_message_text(f"🔍 *ИЩУ КОД...*\n\n{flag} {phone}\n📅 {age} дней\n💰 {price_rub} ₽ / {price_stars}⭐", parse_mode="Markdown")
    code_found, result = await get_last_code_from_account(phone, session)
    if code_found:
        await query.edit_message_text(
            f"🔑 *КОД НАЙДЕН!*\n\n{flag} {phone}\n🔑 `{code_found}`\n\n✅ Код подошёл?",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                [btn("🔄 ПОЛУЧИТЬ НОВЫЙ КОД", f"purchase_code_{purchase_id}")],
                [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
            )
        )
    else:
        await query.edit_message_text(
            f"⚠️ *КОД НЕ НАЙДЕН*\n\n{flag} {phone}",
            parse_mode="Markdown",
            reply_markup=kb(
                [btn("🔄 ПОВТОРИТЬ", f"purchase_code_{purchase_id}")],
                [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
            )
        )

async def purchase_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Отлично!")
    purchase_id = int(query.data.replace("purchase_ok_", ""))
    await query.edit_message_text(
        f"🎉 *ОТЛИЧНО!*\n\n✅ Код подошёл! Аккаунт ваш! 🙏",
        parse_mode="Markdown",
        reply_markup=kb([btn("📦 МОИ ПОКУПКИ", "my_purchases")], [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")])
    )

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 7 ЗАГРУЖЕНА: ДОБАВЛЕНИЕ НОМЕРА + МАГАЗИН + МОИ ПОКУПКИ")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 8: ОПЛАТА + ПОЛУЧЕНИЕ КОДА + FLASK + ЗАПУСК
# =====================================================================

from flask import Flask, request

flask_app = Flask(__name__)

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
        pid, phone, price_rub, price_stars, age, session = product[:6]
        await query.message.reply_invoice(
            title=f"Номер {phone[:4]}****{phone[-4:]}",
            description=f"Возраст: {age} дней",
            payload=f"product_{product_id}_{user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Номер", amount=price_stars)],
            start_parameter=f"buy_phone_{product_id}"
        )
        await query.edit_message_text(f"⭐ СЧЁТ ОТПРАВЛЕН!\n\n📱 {phone[:4]}****{phone[-4:]}\n📅 {age} дней\n⭐ {price_stars} Stars")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
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
        pid, phone, price_rub, price_stars, age, session = product[:6]
        label = f"rub_{product_id}_{user_id}_{int(datetime.now().timestamp())}"
        pending_rub[user_id] = {"product_id": product_id, "phone": phone, "label": label}
        payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=small&sum={price_rub}&label={label}"
        await query.edit_message_text(
            f"💳 *ОПЛАТА {price_rub} ₽*\n\n📱 {phone[:4]}****{phone[-4:]}\n📅 {age} дней\n\n🔗 [Оплатить]({payment_url})\n\n✅ После оплаты нажмите «ПРОВЕРИТЬ»",
            parse_mode="Markdown",
            reply_markup=kb([btn("🔄 ПРОВЕРИТЬ ОПЛАТУ", f"check_rub_{product_id}")], [btn("🔙 НАЗАД", "shop")])
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def check_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    pending = pending_rub.get(user_id)
    if not pending or pending["product_id"] != product_id:
        await query.edit_message_text("❌ Заказ не найден.", reply_markup=back("shop"))
        return
    phone = pending["phone"]
    label = pending["label"]
    is_paid = await check_yoomoney_payment_async(label)
    if not is_paid:
        await query.edit_message_text("⏳ Оплата не обнаружена.", reply_markup=kb([btn("🔄 ПРОВЕРИТЬ СНОВА", f"check_rub_{product_id}")], [btn("🔙 НАЗАД", "shop")]))
        return
    product = get_phone_product(product_id)
    if product:
        pid, phone, price_rub, price_stars, age, session = product[:6]
        delete_phone_product(product_id)
        country_code = get_country_by_phone(phone)
        add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code)
    else:
        session = None
        age = "Неизвестно"
    awaiting_phone_confirmation[user_id] = {"phone": phone, "product_id": product_id, "session": session}
    await query.edit_message_text(f"✅ *ОПЛАЧЕНО РУБЛЯМИ!*\n\n📱 *НОМЕР:* `{phone}`\n📅 {age} дней\n\n🔑 *Нажмите кнопку:*", parse_mode="Markdown", reply_markup=kb([btn("🔑 ПОЛУЧИТЬ КОД", f"get_code_{phone}")]))
    pending_rub.pop(user_id, None)

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
    pid, phone, price_rub, price_stars, age, session = product[:6]
    delete_phone_product(product_id)
    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code)
    awaiting_phone_confirmation[user_id] = {"phone": phone, "product_id": product_id, "session": session}
    await update.message.reply_text(f"✅ *ОПЛАЧЕНО ЗВЁЗДАМИ!*\n\n📱 *НОМЕР:* `{phone}`\n📅 {age} дней\n\n🔑 *Нажмите кнопку:*", parse_mode="Markdown", reply_markup=kb([btn("🔑 ПОЛУЧИТЬ КОД", f"get_code_{phone}")]))

async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    phone = query.data.replace("get_code_", "")
    pending = awaiting_phone_confirmation.get(user_id)
    if not pending or pending["phone"] != phone:
        await query.edit_message_text("❌ Номер не найден", reply_markup=back("start"))
        return
    session = pending.get("session")
    if not session:
        session = get_phone_session(phone)
    if not session:
        await query.edit_message_text("❌ Сессия не найдена", reply_markup=back("start"))
        return
    await query.edit_message_text("🔍 *ИЩУ ПОСЛЕДНИЙ КОД...*", parse_mode="Markdown")
    code_found, result = await get_last_code_from_account(phone, session)
    if code_found:
        await query.edit_message_text(f"🔑 *КОД НАЙДЕН!*\n\n📞 {phone}\n🔑 `{code_found}`\n\n✅ Код подошёл?", parse_mode="Markdown", reply_markup=kb([btn("✅ КОД ПОДОШЁЛ", f"code_ok_{phone}")], [btn("🔄 ПОЛУЧИТЬ НОВЫЙ КОД", f"get_code_{phone}")]))
    else:
        await query.edit_message_text("⚠️ *КОД НЕ НАЙДЕН!*", parse_mode="Markdown", reply_markup=kb([btn("🔄 ПОВТОРИТЬ", f"get_code_{phone}")], [btn("🏠 МЕНЮ", "start")]))

async def code_ok_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Отлично!")
    user_id = query.from_user.id
    phone = query.data.replace("code_ok_", "")
    awaiting_phone_confirmation.pop(user_id, None)
    paid_sessions.pop(user_id, None)
    await query.edit_message_text("🎉 *СДЕЛКА ЗАВЕРШЕНА!*\n\n✅ Аккаунт ваш! 🙏", parse_mode="Markdown", reply_markup=back("start"))

def send_notification_to_telegram(data):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        is_test = data.get('test_notification') == 'true'
        amount = data.get('amount', '0')
        sender = data.get('sender', 'Неизвестно')
        label = data.get('label', 'Нет label')
        status_emoji = "🧪" if is_test else "💳"
        status_text = "ТЕСТОВОЕ" if is_test else "РЕАЛЬНЫЙ ПЛАТЁЖ"
        message = f"{status_emoji} *УВЕДОМЛЕНИЕ ОТ ЮMONEY*\n\n📌 Тип: {status_text}\n💰 Сумма: {amount} ₽\n🏦 Отправитель: {sender}\n🏷️ Label: `{label}`"
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

@flask_app.route('/', methods=['POST'])
def yoomoney_webhook():
    data = request.form
    logger.info(f"📨 Уведомление от ЮMoney: {data}")
    send_notification_to_telegram(data)
    if data.get('test_notification') == 'true':
        return "OK", 200
    label = data.get('label')
    if not label:
        return "OK", 200
    parts = label.split('_')
    if len(parts) >= 3:
        try:
            product_id = int(parts[1])
            user_id = int(parts[2])
        except:
            return "OK", 200
        if data.get('status') == 'success':
            send_payment_success_to_bot(user_id, product_id)
    return "OK", 200

@flask_app.route('/', methods=['GET'])
def test():
    return "✅ Webhook работает!"

def send_payment_success_to_bot(user_id, product_id):
    product = get_phone_product(product_id)
    if not product:
        return
    pid, phone, price_rub, price_stars, age, session = product[:6]
    delete_phone_product(product_id)
    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code)
    awaiting_phone_confirmation[user_id] = {"phone": phone, "product_id": product_id, "session": session}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    message = f"✅ *ОПЛАЧЕНО РУБЛЯМИ!*\n\n📱 *НОМЕР:* `{phone}`\n📅 {age} дней\n\n🔑 *Нажмите кнопку:*"
    keyboard = {"inline_keyboard": [[{"text": "🔑 ПОЛУЧИТЬ КОД", "callback_data": f"get_code_{phone}"}]]}
    try:
        requests.post(url, json={"chat_id": user_id, "text": message, "parse_mode": "Markdown", "reply_markup": keyboard}, timeout=5)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

def start_flask():
    flask_app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)

def main():
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК БОТА...")
    logger.info("=" * 60)
    load_admins_from_db()
    logger.info(f"👑 АДМИНЫ: {ADMINS}")
    logger.info(f"🛠️ МОДЕРАТОРЫ: {MODERATORS}")
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask-сервер запущен на порту 10000")
    app = Application.builder().token(BOT_TOKEN).build()
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
            PHONE_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_age)],
            PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_number)],
            ENTER_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_code)],
            ENTER_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_phone_2fa)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(add_admin_conv)
    app.add_handler(add_phone_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(sub_channels, pattern="^sub_channels$"))
    app.add_handler(CallbackQueryHandler(agree_terms, pattern="^agree_terms$"))
    app.add_handler(CallbackQueryHandler(disagree_terms, pattern="^disagree_terms$"))
    app.add_handler(CallbackQueryHandler(reviews, pattern="^reviews$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(remove_admin, pattern="^remove_admin$"))
    app.add_handler(CallbackQueryHandler(remove_admin_confirm, pattern="^remove_admin_\\d+$"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="^list_admins$"))
    app.add_handler(CallbackQueryHandler(shop, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(shop_page, pattern="^shop_page_\\d+$"))
    app.add_handler(CallbackQueryHandler(shop_country, pattern="^shop_country_"))
    app.add_handler(CallbackQueryHandler(select_phone, pattern="^select_phone_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_phone_start, pattern="^delete_phone$"))
    app.add_handler(CallbackQueryHandler(delete_phone_confirm, pattern="^del_phone_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_phone_yes, pattern="^del_yes_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_rub, pattern="^pay_rub_\\d+$"))
    app.add_handler(CallbackQueryHandler(check_rub, pattern="^check_rub_\\d+$"))
    app.add_handler(CallbackQueryHandler(get_code_button, pattern="^get_code_\\+"))
    app.add_handler(CallbackQueryHandler(code_ok_button, pattern="^code_ok_\\+"))
    app.add_handler(CallbackQueryHandler(my_purchases, pattern="^my_purchases$"))
    app.add_handler(CallbackQueryHandler(purchase_code, pattern="^purchase_code_\\d+$"))
    app.add_handler(CallbackQueryHandler(purchase_ok, pattern="^purchase_ok_\\d+$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    logger.info("=" * 60)
    logger.info("✅ БОТ ГОТОВ К РАБОТЕ!")
    logger.info("=" * 60)
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(app.run_polling())
            break
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning("🔄 Перезапуск цикла...")
                continue
            else:
                raise e
        finally:
            try:
                loop.close()
            except:
                pass

if __name__ == "__main__":
    main()

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 8 ЗАГРУЖЕНА: ОПЛАТА + ПОЛУЧЕНИЕ КОДА + FLASK + ЗАПУСК")
logger.info("=" * 60)
