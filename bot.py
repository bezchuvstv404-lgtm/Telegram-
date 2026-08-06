# =====================================================================
# ЧАСТЬ 1: ИМПОРТЫ + КОНФИГУРАЦИЯ (ИМПОРТ ИЗ CONFIG.PY)
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

# ==========================================
# ИМПОРТ ЛИЧНЫХ ДАННЫХ ИЗ CONFIG.PY
# ==========================================
import sys
import os

# Добавляем текущую папку в путь поиска
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
        COUNTRIES, HELPER_ID
)
    print("✅ Конфигурация загружена из config.py")
except ImportError:
    print("⚠️ Файл config.py не найден! БОТ НЕ ЗАПУСТИТСЯ!")
    exit()

# ==========================================
# ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ ВЕБХУКА
# ==========================================
application = None
BOT_LOOP = None  # реальный event loop бота (заполняется в main()), нужен для планирования корутин из Flask-потока

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
EDIT_PRICE = 40
EDIT_STARS = 41
AWAITING_OFFER = 50

# ==========================================
# КОНСТАНТЫ ДЛЯ ПРЕДЛОЖЕНИЙ
# ==========================================
CALLBACK_OFFER = "offer"
CALLBACK_ACCEPT = "accept_offer"
CALLBACK_REJECT = "reject_offer"

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
        cursor = conn.cursor()
        # Проверяем, есть ли такой товар
        cursor.execute("SELECT id FROM phone_products WHERE id=?", (product_id,))
        if not cursor.fetchone():
            logger.warning(f"⚠️ Товар {product_id} уже удалён")
            conn.close()
            return True
        # Удаляем
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
            conn.execute("UPDATE phone_products SET session=? WHERE phone=?", (session, phone))
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

init_db()

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 2 ЗАГРУЖЕНА: БАЗА ДАННЫХ")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 3: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

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
    """Проверка оплаты через ЮMoney (заглушка)"""
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

def generate_product_message(phone, age, price_rub, price_stars):
    """Генерирует сообщение с полным номером и предупреждениями"""
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    
    return (
        f"✅ *ОПЛАЧЕНО!*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📱 *ВАШ НОМЕР:* `{phone}`\n"
        f"📅 *Возраст:* {age} дней\n"
        f"💰 {price_rub} ₽ / {price_stars}⭐\n\n"
        f"---\n"
        f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
        f"1️⃣ Смените номер телефона на свой\n"
        f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
        f"3️⃣ Установите облачный пароль\n"
        f"4️⃣ Привяжите почту для восстановления\n\n"
        f"🔑 Нажмите кнопку, чтобы получить код для входа:"
    )

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

async def get_last_code_from_account(phone, session_string):
    """Ищет все коды и возвращает самый свежий"""
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=10)
        if not await client.is_user_authorized():
            await client.disconnect()
            return None, "Аккаунт не авторизован"
        
        telegram_dialog = None
        async for dialog in client.iter_dialogs():
            if "Telegram" in dialog.name:
                telegram_dialog = dialog
                break
        
        if not telegram_dialog:
            await client.disconnect()
            return None, "Диалог Telegram не найден"
        
        all_codes = []
        async for msg in client.iter_messages(telegram_dialog.id, limit=100):
            if not msg or not msg.text or msg.out:
                continue
            if any(word in msg.text.lower() for word in ["login", "new device", "terminate"]):
                continue
            match = re.search(r'\b(\d{5})\b', msg.text)
            if match:
                all_codes.append((match.group(1), msg.date.timestamp() if msg.date else 0))
        
        await client.disconnect()
        
        if all_codes:
            all_codes.sort(key=lambda x: x[1], reverse=True)
            return all_codes[0][0], "Telegram"
        return None, "Коды не найдены"
    except Exception as e:
        return None, str(e)

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 4 ЗАГРУЖЕНА: TELETHON")
logger.info("=" * 60)
# =====================================================================
# ЧАСТЬ 5: ПРОВЕРКА ПОДПИСКИ + СОГЛАШЕНИЕ
# =====================================================================

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

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[btn("Предложение", CALLBACK_OFFER)]])


def offer_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [btn("Сделать своё предложение", "make_offer" )],
            [btn("Назад", "start")],
        ]
    )


# ─── Хендлеры ───────────────────────────────────────────────────────────
async def offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💡 Вы можете сделать предложение по улучшению бота!\n\n"
        "Нажмите «Сделать своё предложение», затем отправьте вашу идею "
        "одним сообщением — она будет передана администратору.",
        reply_markup=offer_menu_keyboard(),
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

    await query.answer()
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

    # Кнопки для администратора (с ID автора в данных)
    keyboard = InlineKeyboardMarkup(
        [
            [
                btn("Принять", f"{CALLBACK_ACCEPT}:{user.id}"),
                btn("Отклонить", f"{CALLBACK_REJECT}:{user.id}"),
            ]
        ]
    )

    await context.bot.send_message(
        chat_id=HELPER_ID,
        text=admin_text,
        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Ваше предложение отправлено администратору!\n"
        "Когда будет принято решение, вы получите уведомление."
    )
    return ConversationHandler.END


async def accept_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, user_id = query.data.split(":")
    user_id = int(user_id)

    await query.edit_message_text(
        query.message.text + "\n\n✅ Предложение принято!"
    )

    await context.bot.send_message(
        chat_id=user_id,
        text="✅ Ваше предложение было принято администратором!",
    )
    return ConversationHandler.END


async def reject_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, user_id = query.data.split(":")
    user_id = int(user_id)

    await query.edit_message_text(
        query.message.text + "\n\n❌ Предложение отклонено!"
    )

    await context.bot.send_message(
        chat_id=user_id,
        text="❌ Ваше предложение было отклонено администратором.",
    )
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
        [btn("📱 ДОБАВИТЬ НОМЕР", "add_phone")],
        [btn("✏️ ИЗМЕНИТЬ ЦЕНУ", "edit_price")]
    ]
    if is_super_admin(user_id):
        buttons.append([btn("➕ ДОБАВИТЬ АДМИНА", "add_admin")])
        buttons.append([btn("🗑️ УДАЛИТЬ АДМИНА", "remove_admin")])
        buttons.append([btn("📊 СПИСОК АДМИНОВ", "list_admins")])
        buttons.append([btn("🗑️ УДАЛИТЬ НОМЕР", "delete_phone")])
    buttons.append([btn("🔙 НАЗАД", "start")])
    role = "👑 ГЛАВНЫЙ АДМИН" if is_super_admin(user_id) else "🛠️ МОДЕРАТОР"
    await query.edit_message_text(f"👥 *АДМИН-ПАНЕЛЬ*\n\nВаша роль: {role}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

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
    await update.message.reply_text(f"✅ Добавлен! ID: `{new_admin_id}`", parse_mode="Markdown", reply_markup=back("admin_panel"))
    return ConversationHandler.END

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    rows = [[btn(f"👑 {ADMINS[0]} (Главный)", "noop")]]
    for mod_id in MODERATORS:
        rows.append([btn(f"🗑️ {mod_id}", f"remove_admin_{mod_id}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("🗑️ Выберите для удаления:", reply_markup=InlineKeyboardMarkup(rows))

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

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 6 ЗАГРУЖЕНА: ОТЗЫВЫ, ПОДДЕРЖКА, АДМИН-ПАНЕЛЬ")
logger.info("=" * 60)
# =====================================================================
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
        rows = [
            [btn("🛒 МАГАЗИН", "shop")],
            [btn("📦 МОИ ПОКУПКИ", "my_purchases")],
            [btn("⭐ ОТЗЫВЫ", "reviews")],
            [btn("👨‍❤️‍💋‍👨 ПРЕДЛОЖКА", "offer")],
            [btn("🆘 ПОДДЕРЖКА", "support")]
        ]
        if is_admin(user_id):
            rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
        text = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
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

        else:
            await update.message.reply_text("❌ Ошибка добавления!")
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
    for pid, phone, price_rub, price_stars, age in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"✏️ {flag} {phone} - {price_stars}⭐ / {price_rub}₽", f"edit_select_{pid}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("✏️ *ВЫБЕРИ НОМЕР ДЛЯ ИЗМЕНЕНИЯ ЦЕНЫ*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

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
    for pid, phone, price_rub, price_stars, age in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"🗑️ {flag} {phone} ({age} дн.)", f"del_phone_{pid}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    await query.edit_message_text("🗑️ *ВЫБЕРИ НОМЕР ДЛЯ УДАЛЕНИЯ*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

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
    await query.edit_message_text(
        f"⚠️ УДАЛИТЬ?\n\n📱 {flag} {phone}\n📅 Возраст: {age} дней",
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
    for pid, phone, price_rub, price_stars, age in products:
        if phone.startswith(country['phone_code']):
            country_phones.append((pid, phone, price_rub, price_stars, age))
    if not country_phones:
        await query.edit_message_text(f"❌ Нет номеров для {country['flag']} {country['name']}", reply_markup=back("shop"))
        return
    country_phones.sort(key=lambda x: x[2])
    rows = []
    for idx, (pid, phone, price_rub, price_stars, age) in enumerate(country_phones, 1):
        rows.append([btn(f"[{idx}] {country['flag']} {country['phone_code']} | {price_stars}⭐ / {price_rub}₽ | {age}дн.", f"select_phone_{pid}")])
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
    pid, phone, price_rub, price_stars, age, session = product[:6]
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
        f"💳 *ОПЛАТА*\n\n🌍 *Страна:* {flag} {name} ({code})\n📱 *Номер:* `{hidden_phone}`\n📅 *Возраст:* {age} дней\n⭐ *Цена:* {price_stars} Stars\n💰 *Цена:* {price_rub} ₽\n\n⚠️ После оплаты вы получите полный номер и код для входа.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
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
    row = conn.execute("SELECT phone, price_rub, price_stars, age, session, country_code, purchased_at FROM purchases WHERE id=?", (purchase_id,)).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, price_rub, price_stars, age, session, country_code, purchased_at = row
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    date_str = purchased_at if isinstance(purchased_at, str) else str(purchased_at)
    await query.edit_message_text(
        f"📱 *ИНФОРМАЦИЯ О НОМЕРЕ*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📞 *Номер:* `{phone}`\n"
        f"📅 *Возраст:* {age} дней\n"
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
    await query.edit_message_text(f"🔍 *ИЩУ КОД ДЛЯ НОМЕРА*\n\n📞 {phone}\n⏳ Подключаюсь к аккаунту...", parse_mode="Markdown")
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
        await query.edit_message_text("📦 *МОИ ПОКУПКИ*\n\nУ вас нет покупок для очистки.", parse_mode="Markdown", reply_markup=back("my_purchases"))
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


logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 7 ЗАГРУЖЕНА: ДОБАВЛЕНИЕ НОМЕРА + МАГАЗИН + МОИ ПОКУПКИ")
logger.info("=" * 60)

# =====================================================================
# ЧАСТЬ 8: ОПЛАТА + ПОЛУЧЕНИЕ КОДА + FLASK (ДО main())
# =====================================================================

from flask import Flask, request

flask_app = Flask(__name__)

# ==========================================
# ОПЛАТА ЗВЁЗДАМИ
# ==========================================

async def pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата звёздами"""
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
    except Exception as e:
        logger.error(f"❌ Ошибка оплаты звёздами: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

# ==========================================
# ПРЕДПРОВЕРКА ОПЛАТЫ
# ==========================================

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предварительная проверка оплаты"""
    await update.pre_checkout_query.answer(ok=True)

# ==========================================
# УСПЕШНАЯ ОПЛАТА ЗВЁЗДАМИ
# ==========================================

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Успешная оплата звёздами"""
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

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id,
        "session": session
    }

    await update.message.reply_text(
        generate_product_message(phone, age, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

# ==========================================
# ОПЛАТА РУБЛЯМИ
# ==========================================

async def pay_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оплата рублями — ссылка встроена в кнопку, автоматическая выдача"""
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    
    if not product:
        await query.edit_message_text("❌ Номер больше не доступен!")
        return
    
    product_id, phone, price_rub, price_stars, age, session = product
    user_id = query.from_user.id
    
    # Определяем страну
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    country_flag = country['flag'] if country else "🌍"
    country_name = country['name'] if country else "Неизвестно"
    phone_code = country['phone_code'] if country else ""
    
    # Скрытый номер
    hidden_phone = f"{phone[:4]}****{phone[-4:]}" if len(phone) > 6 else phone
    
    # Уникальная метка для платежа
    label = f"rub_{product_id}_{user_id}_{int(time.time())}"
    
    # Сохраняем в ожидании
    pending_rub[user_id] = {
        'product_id': product_id,
        'phone': phone,
        'label': label,
        'message_id': query.message.message_id,
        'chat_id': query.message.chat_id
    }
    
    # Ссылка на оплату (ВСТРОЕНА В КНОПКУ)
    payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=small&sum={price_rub}&label={label}"
    
    # КНОПКА С ВСТРОЕННОЙ ССЫЛКОЙ (без кнопки "ПРОВЕРИТЬ")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 ОПЛАТИТЬ {price_rub} ₽", url=payment_url)],
        [btn("🔙 НАЗАД", "shop")]
    ])
    
    await query.edit_message_text(
        f"💳 *ОПЛАТА РУБЛЯМИ*\n\n"
        f"🌍 *Страна:* {country_flag} {country_name} ({phone_code})\n"
        f"📱 *Номер:* `{hidden_phone}`\n"
        f"📅 *Возраст:* {age} дней\n"
        f"💰 *Сумма:* {price_rub} ₽\n\n"
        f"🔗 Нажмите на кнопку ниже для оплаты\n"
        f"✅ После оплаты товар выдастся АВТОМАТИЧЕСКИ",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ==========================================
# ПРОВЕРКА ОПЛАТЫ РУБЛЯМИ (ЗАГЛУШКА)
# ==========================================

async def check_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка оплаты рублями (заглушка)"""
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
    
    product_id, phone, price_rub, price_stars, age, session = product
    
    delete_phone_product(product_id)
    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code)
    
    awaiting_phone_confirmation[user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session
    }
    
    del pending_rub[user_id]
    
    await query.edit_message_text(
        generate_product_message(phone, age, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

# ==========================================
# АВТОМАТИЧЕСКАЯ ВЫДАЧА ТОВАРА (ДЛЯ ВЕБХУКА)
# ==========================================
async def auto_deliver_product(user_id, product_id):
    """АВТОМАТИЧЕСКАЯ ВЫДАЧА ТОВАРА ПОСЛЕ ОПЛАТЫ РУБЛЯМИ"""
    logger.info(f"🎁 АВТОМАТИЧЕСКАЯ ВЫДАЧА ТОВАРА ДЛЯ {user_id}")

    # === ПОЛУЧАЕМ ТОВАР ИЗ БД ===
    product = get_phone_product(product_id)
    if not product:
        logger.error(f"❌ Товар {product_id} не найден в БД!")
        return

    product_id, phone, price_rub, price_stars, age, session = product
    logger.info(f"📱 Найден товар в БД: {phone}")

    # === УДАЛЯЕМ ИЗ МАГАЗИНА ===
    delete_result = delete_phone_product(product_id)
    if delete_result:
        logger.info(f"✅ Товар {phone} УДАЛЁН из магазина")
    else:
        logger.error(f"❌ Ошибка удаления товара {phone}!")

    # === СОХРАНЯЕМ ПОКУПКУ (С ПРОВЕРКОЙ) ===
    country_code = get_country_by_phone(phone)
    if not country_code:
        country_code = "UNKNOWN"
        logger.warning(f"⚠️ Страна не найдена для {phone}, установлено UNKNOWN")
    
    logger.info(f"📝 Сохраняем покупку: user_id={user_id}, phone={phone}, country_code={country_code}")
    
    try:
        purchase_result = add_purchase(user_id, phone, price_rub, price_stars, age, session, country_code)
        if purchase_result:
            logger.info(f"✅ Покупка сохранена в БД: {phone}")
        else:
            logger.error(f"❌ add_purchase вернула False для {phone}!")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении покупки: {e}")

    # === ПРОВЕРЯЕМ, СОХРАНИЛАСЬ ЛИ ===
    purchases = get_user_purchases(user_id)
    if purchases:
        logger.info(f"✅ Найдено {len(purchases)} покупок у пользователя {user_id}")
        for p in purchases:
            logger.info(f"   📱 {p[1]} - {p[2]}₽ / {p[3]}⭐")
    else:
        logger.error(f"❌ У пользователя {user_id} НЕТ покупок в БД!")

    # === СОХРАНЯЕМ ДЛЯ ПОЛУЧЕНИЯ КОДА ===
    awaiting_phone_confirmation[user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session
    }
    logger.info(f"✅ Данные сохранены для получения кода")

    # === УДАЛЯЕМ ИЗ ОЖИДАНИЯ ===
    if user_id in pending_rub:
        del pending_rub[user_id]
        logger.info(f"✅ pending_rub очищен для {user_id}")

    # === ОТПРАВЛЯЕМ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЮ ===
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=generate_product_message(phone, age, price_rub, price_stars),
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
            message = generate_product_message(phone, age, price_rub, price_stars)
            keyboard = {"inline_keyboard": [[{"text": "🔑 ПОЛУЧИТЬ КОД", "callback_data": "get_code"}]]}
            requests.post(url, json={
                "chat_id": user_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }, timeout=5)
            logger.info(f"✅ Сообщение отправлено через requests")
        except Exception as e2:
            logger.error(f"❌ Ошибка через requests: {e2}")
# ==========================================
# ГЕНЕРАЦИЯ СООБЩЕНИЯ С ТОВАРОМ
# ==========================================

def generate_product_message(phone, age, price_rub, price_stars):
    """Генерирует сообщение с полным номером и предупреждениями"""
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    
    return (
        f"✅ *ОПЛАЧЕНО!*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📱 *ВАШ НОМЕР:* `{phone}`\n"
        f"📅 *Возраст:* {age} дней\n"
        f"💰 {price_rub} ₽ / {price_stars}⭐\n\n"
        f"---\n"
        f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
        f"1️⃣ Смените номер телефона на свой\n"
        f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
        f"3️⃣ Установите облачный пароль\n"
        f"4️⃣ Привяжите почту для восстановления\n\n"
        f"🔑 Нажмите кнопку, чтобы получить код для входа:"
    )

# ==========================================
# ПОЛУЧЕНИЕ КОДА
# ==========================================

async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение кода — с подробным логированием"""
    logger.info("🔴🔴🔴 get_code_button ВЫЗВАНА! 🔴🔴🔴")
    
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    logger.info(f"👤 user_id: {user_id}")
    logger.info(f"📊 awaiting_phone_confirmation: {awaiting_phone_confirmation}")
    
    if user_id not in awaiting_phone_confirmation:
        logger.error(f"❌ НЕТ ДАННЫХ ДЛЯ {user_id}")
        await query.edit_message_text("❌ Нет номеров для получения кода! Оплатите номер сначала.")
        return
    
    data = awaiting_phone_confirmation[user_id]
    phone = data['phone']
    session = data['session']
    logger.info(f"📞 НОМЕР: {phone}")
    logger.info(f"🔑 СЕССИЯ: {session[:30]}...")
    
    await query.edit_message_text(
        f"🔍 *ИЩУ КОД ДЛЯ НОМЕРА*\n\n"
        f"📞 {phone}\n\n"
        f"⏳ Подключаюсь к аккаунту...",
        parse_mode="Markdown"
    )
    
    try:
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

# ==========================================
# КОД ПОДОШЁЛ
# ==========================================

async def code_ok_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Код подошёл — показываем кнопку для отзыва"""
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

# ==========================================
# ОТПРАВКА УВЕДОМЛЕНИЙ В ТЕЛЕГРАМ
# ==========================================

def send_notification_to_telegram(data):
    """Отправляет уведомление от ЮMoney в Telegram (для реальных и тестовых)"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        # === ПРОВЕРЯЕМ, ТЕСТОВОЕ ЛИ ЭТО УВЕДОМЛЕНИЕ ===
        is_test = data.get('test_notification') == 'true'
        
        # === ПОЛУЧАЕМ ДАННЫЕ ===
        notification_type = data.get('notification_type', 'Неизвестно')
        amount = data.get('amount', '0')
        sender = data.get('sender', 'Неизвестно')
        label = data.get('label', 'Отсутствует')
        operation_id = data.get('operation_id', 'Неизвестно')
        datetime_str = data.get('datetime', 'Неизвестно')
        
        # === ОПРЕДЕЛЯЕМ ЭМОДЗИ И ТИП ===
        if is_test:
            emoji = "🧪"
            type_text = "ТЕСТОВОЕ УВЕДОМЛЕНИЕ"
        else:
            emoji = "💳"
            type_text = "НОВАЯ ОПЛАТА"
        
        # === ОПРЕДЕЛЯЕМ ПОДТИП ПЛАТЕЖА ===
        if notification_type == 'card-incoming':
            sub_type = "Платёж по карте"
        elif notification_type == 'p2p-incoming':
            sub_type = "Перевод между кошельками"
        else:
            sub_type = notification_type
        
        # === ФОРМИРУЕМ СООБЩЕНИЕ ===
        if is_test:
            message = (
                f"{emoji} *{type_text}*\n\n"
                f"📌 Тип: {sub_type}\n"
                f"💰 Сумма: {amount} ₽\n"
                f"🏦 Отправитель: `{sender}`\n"
                f"🏷️ Метка: `{label}`\n"
                f"🔢 ID: `{operation_id}`\n"
                f"📅 Дата: {datetime_str}\n\n"
                f"⚠️ Это тестовое уведомление"
            )
        else:
            message = (
                f"{emoji} *{type_text}*\n\n"
                f"📌 Тип: {sub_type}\n"
                f"💰 Сумма: {amount} ₽\n"
                f"🏦 Отправитель: `{sender}`\n"
                f"🏷️ Метка: `{label}`\n"
                f"🔢 ID: `{operation_id}`\n"
                f"📅 Дата: {datetime_str}\n\n"
                f"✅ Статус: ОПЛАЧЕНО"
            )
        
        # === ОТПРАВЛЯЕМ АДМИНУ ===
        response = requests.post(
            url,
            json={
                "chat_id": ADMIN_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Уведомление отправлено в Telegram")
        else:
            logger.error(f"❌ Ошибка отправки: {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

# ==========================================
# FLASK-СЕРВЕР ДЛЯ ВЕБХУКА
# ==========================================

def start_flask():
    """Запускает Flask-сервер"""
    flask_app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)


@flask_app.route('/', methods=['POST'])
def yoomoney_webhook():
    """Обработка уведомлений от ЮMoney — с поддержкой тестовых"""
    data = request.form
    logger.info(f"📨 Получен вебхук: {data}")
    
    # === ОТПРАВЛЯЕМ ВСЕ УВЕДОМЛЕНИЯ В БОТА ===
    send_notification_to_telegram(data)
    
    # === ОБРАБОТКА ТЕСТОВОГО УВЕДОМЛЕНИЯ ===
    if data.get('test_notification') == 'true':
        logger.info("🧪 Тестовое уведомление — пропускаем")
        return "OK", 200
    
    # === ПРОВЕРЯЕМ, ЧТО ЭТО РЕАЛЬНЫЙ ПЛАТЁЖ ===
    if data.get('notification_type') != 'card-incoming':
        logger.info(f"⏭️ Не card-incoming — пропускаем")
        return "OK", 200
    
    # === ОБРАБОТКА РЕАЛЬНОГО ПЛАТЕЖА ===
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
    """Проверка работы вебхука"""
    return "✅ Webhook работает!", 200

# ==========================================
# ОБРАБОТЧИК ОШИБОК
# ==========================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        except:
            pass
  # ЧАСТЬ 9: ЗАПУСК БОТА
# =====================================================================

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
    
    global application
    application = app
    
    # ConversationHandler для добавления админа
    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    # ConversationHandler для добавления номера
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
    
    # ConversationHandler для изменения цены в рублях
    edit_rub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_rub_start, pattern="^edit_rub$")],
        states={EDIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_rub_input)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    # ConversationHandler для изменения цены в Stars
    edit_stars_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_stars_start, pattern="^edit_stars$")],
        states={EDIT_STARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_stars_input)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    # ConversationHandler для предложений
    offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(make_offer, pattern="^make_offer$")],
        states={AWAITING_OFFER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_offer)]},
        fallbacks=[CommandHandler("start", start)]
    )
    
    # === РЕГИСТРАЦИЯ ВСЕХ ОБРАБОТЧИКОВ ===
    app.add_handler(add_admin_conv)
    app.add_handler(add_phone_conv)
    app.add_handler(edit_rub_conv)
    app.add_handler(edit_stars_conv)
    app.add_handler(offer_conv)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_callback, pattern="^start$"))
    app.add_handler(CallbackQueryHandler(check_subscription_button, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(agree_terms, pattern="^agree_terms$"))
    app.add_handler(CallbackQueryHandler(disagree_terms, pattern="^disagree_terms$"))
    app.add_handler(CallbackQueryHandler(reviews, pattern="^reviews$"))
    app.add_handler(CallbackQueryHandler(offer, pattern="^offer$"))
    app.add_handler(CallbackQueryHandler(accept_offer, pattern="^accept_offer:\\d+$"))
    app.add_handler(CallbackQueryHandler(reject_offer, pattern="^reject_offer:\\d+$"))
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
    
    app.add_handler(CallbackQueryHandler(edit_price_start, pattern="^edit_price$"))
    app.add_handler(CallbackQueryHandler(edit_select_phone, pattern="^edit_select_\\d+$"))
    
    app.add_handler(CallbackQueryHandler(pay_stars, pattern="^pay_stars_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_rub, pattern="^pay_rub_\\d+$"))
    app.add_handler(CallbackQueryHandler(check_rub, pattern="^check_rub_\\d+$"))
    
    app.add_handler(CallbackQueryHandler(get_code_button, pattern="^get_code$"))
    app.add_handler(CallbackQueryHandler(code_ok_button, pattern="^code_ok$"))
    
    app.add_handler(CallbackQueryHandler(my_purchases, pattern="^my_purchases$"))
    app.add_handler(CallbackQueryHandler(purchase_code, pattern="^purchase_code_\\d+$"))
    app.add_handler(CallbackQueryHandler(purchase_get_code, pattern="^purchase_get_code_\\d+$"))
    app.add_handler(CallbackQueryHandler(purchase_ok, pattern="^purchase_ok_\\d+$"))
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
    
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            global BOT_LOOP
            BOT_LOOP = loop
            loop.run_until_complete(app.run_polling())
            break
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning("🔄 Перезапуск цикла...")
                continue
            else:
                raise e
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            logger.info("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
        finally:
            try:
                loop.close()
            except:
                pass

if __name__ == "__main__":
    main()

logger.info("=" * 60)
logger.info("✅ ЧАСТЬ 9 ЗАГРУЖЕНА: ЗАПУСК БОТА")
logger.info("=" * 60)
