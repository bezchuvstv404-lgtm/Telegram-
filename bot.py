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
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta, timezone
import random
import warnings
from time import sleep

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton
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
from telethon import TelegramClient, errors, events, functions, types
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telegram.error import BadRequest
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.auth import ResetAuthorizationsRequest

SHOP_PRICE_RUB = 65   # цена номера в рублях

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _cfg_dir in ("/storage/emulated/0/Download/Автопокупка и парсер аков",
                 "/storage/emulated/0/Download",
                 os.getcwd()):
    if os.path.isfile(os.path.join(_cfg_dir, "config.py")) and _cfg_dir not in sys.path:
        sys.path.append(_cfg_dir)

try:
    from config import (
        BOT_TOKEN, ADMIN_ID, API_ID, API_HASH, YOOMONEY_WALLET,
        DB_NAME, CHANNEL_ID, ADMIN_CHAT_ID, ADMINS, COUNTRIES
    )
    try:
        from config import HELPER_ID
    except ImportError:
        HELPER_ID = ADMIN_ID
        print("⚠️ HELPER_ID не найден в config.py, установлен равным ADMIN_ID")
    print("✅ Конфигурация загружена из config.py")
except ImportError:
    # config.py нет — используем встроенные настройки (config.py, если появится, главнее)
    import types as _types
    _PHONE_DIR = "/storage/emulated/0/Download/Автопокупка и парсер аков"   # там лежит lzt_numbers.db
    _D = os.getenv("BOT_DATA_DIR") or _PHONE_DIR
    _db_fallback = False
    if not os.path.isdir(_D) and not os.getenv("BOT_DATA_DIR"):
        _D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        _db_fallback = True
    _cfg = _types.ModuleType("config")
    _cfg.BOT_TOKEN = os.getenv("BOT_TOKEN") or "8254882046:AAF_d4nqGakunuCFK0g_QK6vRzMPHDOwzSM"
    _cfg.ADMIN_ID = 833009810
    _cfg.API_ID = 37929729
    _cfg.API_HASH = os.getenv("API_HASH") or "a9b0048cb977e7efe52c0e9ebef901e1"
    _cfg.LZT_API_TOKEN = os.getenv("LZT_API_TOKEN") or "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWIiOjk5MTk2MTMsImlzcyI6Imx6dCIsImlhdCI6MTc5MTI5OTg5NiwianRpIjoiMTAyMjk0MCIsInNjb3BlIjoiYmFzaWMgcmVhZCBwb3N0IGNvbnZlcnNhdGUgcGF5bWVudCBpbnZvaWNlIGNoYXRib3ggbWFya2V0IiwiZXhwIjoxOTQ4OTc5ODk2fQ.B41GUuOPhfT47DAQGsFrhb38GXBfHRDT51QHxJ7oyVPv7VWSmqobnVuGGtXBzAtGASp63v0Wyme2hgW7MiWRFmjaxYAFFEw4jyo8UcFf9JwaRTjDMc2_HUP6RqclMu0QCynVJ-KqMxZulMJszd2x2_vkL0iW_2wVOUT-YHOGUEY"
    _cfg.YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET") or "4100119486619208"
    _cfg.YOOMONEY_SECRET = os.getenv("YOOMONEY_SECRET") or ""   # ← вставь сюда секрет из ЮMoney (HTTP-уведомления)
    _cfg.DB_NAME = os.path.join(_D, "lzt_numbers.db")
    _cfg.BUYER_DB_NAME = os.path.join(_D, "lzt_numbers.db")
    _cfg.BUYER_AVATAR_DIR = os.path.join(_D, "avatars")
    _cfg.CHANNEL_ID = "@ponchinoscaamm"
    _cfg.ADMIN_CHAT_ID = _cfg.ADMIN_ID
    _cfg.ADMINS = [_cfg.ADMIN_ID]
    _cfg.COUNTRIES = [
        {"code": "AF", "name": "Афганистан", "flag": "🇦🇫", "phone_code": "+93"},
        {"code": "AL", "name": "Албания", "flag": "🇦🇱", "phone_code": "+355"},
        {"code": "DZ", "name": "Алжир", "flag": "🇩🇿", "phone_code": "+213"},
        {"code": "AO", "name": "Ангола", "flag": "🇦🇴", "phone_code": "+244"},
        {"code": "AR", "name": "Аргентина", "flag": "🇦🇷", "phone_code": "+54"},
        {"code": "AM", "name": "Армения", "flag": "🇦🇲", "phone_code": "+374"},
        {"code": "AU", "name": "Австралия", "flag": "🇦🇺", "phone_code": "+61"},
        {"code": "AT", "name": "Австрия", "flag": "🇦🇹", "phone_code": "+43"},
        {"code": "AZ", "name": "Азербайджан", "flag": "🇦🇿", "phone_code": "+994"},
        {"code": "BH", "name": "Бахрейн", "flag": "🇧🇭", "phone_code": "+973"},
        {"code": "BD", "name": "Бангладеш", "flag": "🇧🇩", "phone_code": "+880"},
        {"code": "BY", "name": "Беларусь", "flag": "🇧🇾", "phone_code": "+375"},
        {"code": "BE", "name": "Бельгия", "flag": "🇧🇪", "phone_code": "+32"},
        {"code": "BO", "name": "Боливия", "flag": "🇧🇴", "phone_code": "+591"},
        {"code": "BA", "name": "Босния и Герцеговина", "flag": "🇧🇦", "phone_code": "+387"},
        {"code": "BR", "name": "Бразилия", "flag": "🇧🇷", "phone_code": "+55"},
        {"code": "BG", "name": "Болгария", "flag": "🇧🇬", "phone_code": "+359"},
        {"code": "KH", "name": "Камбоджа", "flag": "🇰🇭", "phone_code": "+855"},
        {"code": "CM", "name": "Камерун", "flag": "🇨🇲", "phone_code": "+237"},
        {"code": "CL", "name": "Чили", "flag": "🇨🇱", "phone_code": "+56"},
        {"code": "CN", "name": "Китай", "flag": "🇨🇳", "phone_code": "+86"},
        {"code": "CO", "name": "Колумбия", "flag": "🇨🇴", "phone_code": "+57"},
        {"code": "CR", "name": "Коста-Рика", "flag": "🇨🇷", "phone_code": "+506"},
        {"code": "HR", "name": "Хорватия", "flag": "🇭🇷", "phone_code": "+385"},
        {"code": "CU", "name": "Куба", "flag": "🇨🇺", "phone_code": "+53"},
        {"code": "CY", "name": "Кипр", "flag": "🇨🇾", "phone_code": "+357"},
        {"code": "CZ", "name": "Чехия", "flag": "🇨🇿", "phone_code": "+420"},
        {"code": "DK", "name": "Дания", "flag": "🇩🇰", "phone_code": "+45"},
        {"code": "EC", "name": "Эквадор", "flag": "🇪🇨", "phone_code": "+593"},
        {"code": "EG", "name": "Египет", "flag": "🇪🇬", "phone_code": "+20"},
        {"code": "SV", "name": "Сальвадор", "flag": "🇸🇻", "phone_code": "+503"},
        {"code": "EE", "name": "Эстония", "flag": "🇪🇪", "phone_code": "+372"},
        {"code": "ET", "name": "Эфиопия", "flag": "🇪🇹", "phone_code": "+251"},
        {"code": "FI", "name": "Финляндия", "flag": "🇫🇮", "phone_code": "+358"},
        {"code": "FR", "name": "Франция", "flag": "🇫🇷", "phone_code": "+33"},
        {"code": "GE", "name": "Грузия", "flag": "🇬🇪", "phone_code": "+995"},
        {"code": "DE", "name": "Германия", "flag": "🇩🇪", "phone_code": "+49"},
        {"code": "GH", "name": "Гана", "flag": "🇬🇭", "phone_code": "+233"},
        {"code": "GR", "name": "Греция", "flag": "🇬🇷", "phone_code": "+30"},
        {"code": "GT", "name": "Гватемала", "flag": "🇬🇹", "phone_code": "+502"},
        {"code": "HN", "name": "Гондурас", "flag": "🇭🇳", "phone_code": "+504"},
        {"code": "HK", "name": "Гонконг", "flag": "🇭🇰", "phone_code": "+852"},
        {"code": "HU", "name": "Венгрия", "flag": "🇭🇺", "phone_code": "+36"},
        {"code": "IS", "name": "Исландия", "flag": "🇮🇸", "phone_code": "+354"},
        {"code": "IN", "name": "Индия", "flag": "🇮🇳", "phone_code": "+91"},
        {"code": "ID", "name": "Индонезия", "flag": "🇮🇩", "phone_code": "+62"},
        {"code": "IR", "name": "Иран", "flag": "🇮🇷", "phone_code": "+98"},
        {"code": "IQ", "name": "Ирак", "flag": "🇮🇶", "phone_code": "+964"},
        {"code": "IE", "name": "Ирландия", "flag": "🇮🇪", "phone_code": "+353"},
        {"code": "IL", "name": "Израиль", "flag": "🇮🇱", "phone_code": "+972"},
        {"code": "IT", "name": "Италия", "flag": "🇮🇹", "phone_code": "+39"},
        {"code": "CI", "name": "Кот-д'Ивуар", "flag": "🇨🇮", "phone_code": "+225"},
        {"code": "JP", "name": "Япония", "flag": "🇯🇵", "phone_code": "+81"},
        {"code": "JO", "name": "Иордания", "flag": "🇯🇴", "phone_code": "+962"},
        {"code": "KZ", "name": "Казахстан", "flag": "🇰🇿", "phone_code": "+77"},
        {"code": "KE", "name": "Кения", "flag": "🇰🇪", "phone_code": "+254"},
        {"code": "KW", "name": "Кувейт", "flag": "🇰🇼", "phone_code": "+965"},
        {"code": "KG", "name": "Кыргызстан", "flag": "🇰🇬", "phone_code": "+996"},
        {"code": "LA", "name": "Лаос", "flag": "🇱🇦", "phone_code": "+856"},
        {"code": "LV", "name": "Латвия", "flag": "🇱🇻", "phone_code": "+371"},
        {"code": "LB", "name": "Ливан", "flag": "🇱🇧", "phone_code": "+961"},
        {"code": "LY", "name": "Ливия", "flag": "🇱🇾", "phone_code": "+218"},
        {"code": "LT", "name": "Литва", "flag": "🇱🇹", "phone_code": "+370"},
        {"code": "LU", "name": "Люксембург", "flag": "🇱🇺", "phone_code": "+352"},
        {"code": "MO", "name": "Макао", "flag": "🇲🇴", "phone_code": "+853"},
        {"code": "MK", "name": "Северная Македония", "flag": "🇲🇰", "phone_code": "+389"},
        {"code": "MY", "name": "Малайзия", "flag": "🇲🇾", "phone_code": "+60"},
        {"code": "MT", "name": "Мальта", "flag": "🇲🇹", "phone_code": "+356"},
        {"code": "MX", "name": "Мексика", "flag": "🇲🇽", "phone_code": "+52"},
        {"code": "MD", "name": "Молдова", "flag": "🇲🇩", "phone_code": "+373"},
        {"code": "MN", "name": "Монголия", "flag": "🇲🇳", "phone_code": "+976"},
        {"code": "MA", "name": "Марокко", "flag": "🇲🇦", "phone_code": "+212"},
        {"code": "MZ", "name": "Мозамбик", "flag": "🇲🇿", "phone_code": "+258"},
        {"code": "MM", "name": "Мьянма", "flag": "🇲🇲", "phone_code": "+95"},
        {"code": "NP", "name": "Непал", "flag": "🇳🇵", "phone_code": "+977"},
        {"code": "NL", "name": "Нидерланды", "flag": "🇳🇱", "phone_code": "+31"},
        {"code": "NZ", "name": "Новая Зеландия", "flag": "🇳🇿", "phone_code": "+64"},
        {"code": "NI", "name": "Никарагуа", "flag": "🇳🇮", "phone_code": "+505"},
        {"code": "NG", "name": "Нигерия", "flag": "🇳🇬", "phone_code": "+234"},
        {"code": "NO", "name": "Норвегия", "flag": "🇳🇴", "phone_code": "+47"},
        {"code": "OM", "name": "Оман", "flag": "🇴🇲", "phone_code": "+968"},
        {"code": "PK", "name": "Пакистан", "flag": "🇵🇰", "phone_code": "+92"},
        {"code": "PA", "name": "Панама", "flag": "🇵🇦", "phone_code": "+507"},
        {"code": "PY", "name": "Парагвай", "flag": "🇵🇾", "phone_code": "+595"},
        {"code": "PE", "name": "Перу", "flag": "🇵🇪", "phone_code": "+51"},
        {"code": "PH", "name": "Филиппины", "flag": "🇵🇭", "phone_code": "+63"},
        {"code": "PL", "name": "Польша", "flag": "🇵🇱", "phone_code": "+48"},
        {"code": "PT", "name": "Португалия", "flag": "🇵🇹", "phone_code": "+351"},
        {"code": "QA", "name": "Катар", "flag": "🇶🇦", "phone_code": "+974"},
        {"code": "RO", "name": "Румыния", "flag": "🇷🇴", "phone_code": "+40"},
        {"code": "RU", "name": "Россия", "flag": "🇷🇺", "phone_code": "+7"},
        {"code": "SA", "name": "Саудовская Аравия", "flag": "🇸🇦", "phone_code": "+966"},
        {"code": "SN", "name": "Сенегал", "flag": "🇸🇳", "phone_code": "+221"},
        {"code": "RS", "name": "Сербия", "flag": "🇷🇸", "phone_code": "+381"},
        {"code": "SG", "name": "Сингапур", "flag": "🇸🇬", "phone_code": "+65"},
        {"code": "SK", "name": "Словакия", "flag": "🇸🇰", "phone_code": "+421"},
        {"code": "SI", "name": "Словения", "flag": "🇸🇮", "phone_code": "+386"},
        {"code": "ZA", "name": "ЮАР", "flag": "🇿🇦", "phone_code": "+27"},
        {"code": "KR", "name": "Южная Корея", "flag": "🇰🇷", "phone_code": "+82"},
        {"code": "ES", "name": "Испания", "flag": "🇪🇸", "phone_code": "+34"},
        {"code": "LK", "name": "Шри-Ланка", "flag": "🇱🇰", "phone_code": "+94"},
        {"code": "SE", "name": "Швеция", "flag": "🇸🇪", "phone_code": "+46"},
        {"code": "CH", "name": "Швейцария", "flag": "🇨🇭", "phone_code": "+41"},
        {"code": "TW", "name": "Тайвань", "flag": "🇹🇼", "phone_code": "+886"},
        {"code": "TJ", "name": "Таджикистан", "flag": "🇹🇯", "phone_code": "+992"},
        {"code": "TZ", "name": "Танзания", "flag": "🇹🇿", "phone_code": "+255"},
        {"code": "TH", "name": "Таиланд", "flag": "🇹🇭", "phone_code": "+66"},
        {"code": "TN", "name": "Тунис", "flag": "🇹🇳", "phone_code": "+216"},
        {"code": "TR", "name": "Турция", "flag": "🇹🇷", "phone_code": "+90"},
        {"code": "TM", "name": "Туркменистан", "flag": "🇹🇲", "phone_code": "+993"},
        {"code": "UG", "name": "Уганда", "flag": "🇺🇬", "phone_code": "+256"},
        {"code": "UA", "name": "Украина", "flag": "🇺🇦", "phone_code": "+380"},
        {"code": "AE", "name": "ОАЭ", "flag": "🇦🇪", "phone_code": "+971"},
        {"code": "GB", "name": "Великобритания", "flag": "🇬🇧", "phone_code": "+44"},
        {"code": "US", "name": "США/Канада", "flag": "🇺🇸", "phone_code": "+1"},
        {"code": "UY", "name": "Уругвай", "flag": "🇺🇾", "phone_code": "+598"},
        {"code": "UZ", "name": "Узбекистан", "flag": "🇺🇿", "phone_code": "+998"},
        {"code": "VE", "name": "Венесуэла", "flag": "🇻🇪", "phone_code": "+58"},
        {"code": "VN", "name": "Вьетнам", "flag": "🇻🇳", "phone_code": "+84"},
        {"code": "ZM", "name": "Замбия", "flag": "🇿🇲", "phone_code": "+260"},
        {"code": "ZW", "name": "Зимбабве", "flag": "🇿🇼", "phone_code": "+263"},
    ]
    for _c in _cfg.COUNTRIES:
        _c["price_rub"] = SHOP_PRICE_RUB
        _c.setdefault("price_stars", 40)
    _cfg._DB_FALLBACK = _db_fallback
    sys.modules["config"] = _cfg
    os.makedirs(_D, exist_ok=True)
    print("⚠️ config.py не найден — работаю на встроенных настройках")
    from config import (
        BOT_TOKEN, ADMIN_ID, API_ID, API_HASH, YOOMONEY_WALLET,
        DB_NAME, CHANNEL_ID, ADMIN_CHAT_ID, ADMINS, COUNTRIES
    )
    HELPER_ID = ADMIN_ID

# ====== РАСШИРЕННЫЙ СПИСОК СТРАН (добавляется к COUNTRIES из config.py / встроенного) ======
_EXTRA_COUNTRIES = [
    ("AD","Андорра","+376"),("AG","Антигуа и Барбуда","+1268"),("AI","Ангилья","+1264"),
    ("AW","Аруба","+297"),("AS","Американское Самоа","+1684"),("BS","Багамы","+1242"),
    ("BB","Барбадос","+1246"),("BZ","Белиз","+501"),("BJ","Бенин","+229"),
    ("BM","Бермуды","+1441"),("BT","Бутан","+975"),("BW","Ботсвана","+267"),
    ("BN","Бруней","+673"),("BF","Буркина-Фасо","+226"),("BI","Бурунди","+257"),
    ("CV","Кабо-Верде","+238"),("KY","Каймановы острова","+1345"),("CF","ЦАР","+236"),
    ("TD","Чад","+235"),("KM","Коморы","+269"),("CG","Конго","+242"),
    ("CD","ДР Конго","+243"),("CK","Острова Кука","+682"),("CW","Кюрасао","+599"),
    ("DJ","Джибути","+253"),("DM","Доминика","+1767"),("DO","Доминиканская Республика","+1809"),
    ("GQ","Экваториальная Гвинея","+240"),("ER","Эритрея","+291"),("SZ","Эсватини","+268"),
    ("FJ","Фиджи","+679"),("GA","Габон","+241"),("GM","Гамбия","+220"),
    ("GD","Гренада","+1473"),("GU","Гуам","+1671"),("GN","Гвинея","+224"),
    ("GW","Гвинея-Бисау","+245"),("GY","Гайана","+592"),("HT","Гаити","+509"),
    ("JM","Ямайка","+1876"),("KI","Кирибати","+686"),("XK","Косово","+383"),
    ("LS","Лесото","+266"),("LR","Либерия","+231"),("LI","Лихтенштейн","+423"),
    ("MG","Мадагаскар","+261"),("MW","Малави","+265"),("MV","Мальдивы","+960"),
    ("ML","Мали","+223"),("MH","Маршалловы Острова","+692"),("MR","Мавритания","+222"),
    ("MU","Маврикий","+230"),("FM","Микронезия","+691"),("MC","Монако","+377"),
    ("ME","Черногория","+382"),("MS","Монтсеррат","+1664"),("NA","Намибия","+264"),
    ("NR","Науру","+674"),("NE","Нигер","+227"),("KP","Северная Корея","+850"),
    ("PS","Палестина","+970"),("PG","Папуа — Новая Гвинея","+675"),("PR","Пуэрто-Рико","+1787"),
    ("RW","Руанда","+250"),("KN","Сент-Китс и Невис","+1869"),("LC","Сент-Люсия","+1758"),
    ("VC","Сент-Винсент и Гренадины","+1784"),("WS","Самоа","+685"),("SM","Сан-Марино","+378"),
    ("ST","Сан-Томе и Принсипи","+239"),("SC","Сейшелы","+248"),("SL","Сьерра-Леоне","+232"),
    ("SB","Соломоновы Острова","+677"),("SO","Сомали","+252"),("SS","Южный Судан","+211"),
    ("SD","Судан","+249"),("SR","Суринам","+597"),("SY","Сирия","+963"),
    ("TL","Восточный Тимор","+670"),("TG","Того","+228"),("TO","Тонга","+676"),
    ("TT","Тринидад и Тобаго","+1868"),("TV","Тувалу","+688"),("VU","Вануату","+678"),
    ("VA","Ватикан","+379"),("YE","Йемен","+967"),("RE","Реюньон","+262"),
    ("GP","Гваделупа","+590"),("MQ","Мартиника","+596"),("GF","Французская Гвиана","+594"),
    ("PF","Французская Полинезия","+689"),("NC","Новая Каледония","+687"),
    ("FO","Фарерские острова","+298"),("GL","Гренландия","+299"),("GI","Гибралтар","+350"),
    ("VG","Британские Виргинские о-ва","+1284"),("VI","Виргинские о-ва США","+1340"),
    ("TC","Тёркс и Кайкос","+1649"),("MP","Северные Марианские о-ва","+1670"),
    ("SX","Синт-Мартен","+1721"),
]
# дополнительные коды, которые тоже относятся к стране (определение по номеру)
_COUNTRY_EXTRA_PREFIXES = {"DO": ["+1829", "+1849"], "PR": ["+1939"]}

def _flag_by_iso(code):
    try:
        return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code.upper())
    except Exception:
        return "🌍"

def _extend_countries():
    have_codes = {c["code"] for c in COUNTRIES}
    have_phones = {c["phone_code"] for c in COUNTRIES}
    for code, name, pc in _EXTRA_COUNTRIES:
        if code in have_codes or pc in have_phones:
            continue
        COUNTRIES.append({"code": code, "name": name, "flag": _flag_by_iso(code),
                          "phone_code": pc, "price_rub": SHOP_PRICE_RUB, "price_stars": 40})
        have_codes.add(code); have_phones.add(pc)
for _c in COUNTRIES:
    _c["price_rub"] = SHOP_PRICE_RUB

_extend_countries()
# ====== КОНЕЦ РАСШИРЕНИЯ СПИСКА СТРАН ======

application = None
BOT_LOOP = None

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Telethon пишет в INFO служебные строки («Got difference for channel…», «Connecting to…») — оставляем только предупреждения и ошибки
logging.getLogger("telethon").setLevel(logging.WARNING)

MODERATORS = []
ALL_ADMINS = []
ADMIN_SESSIONS = {}   # user_id -> {"phone", "session", "created", "name"} (сессия аккаунта админа)

PHONE_PRICE, PHONE_STARS, PHONE_NUMBER = range(10, 13)
ENTER_CODE = 20
ENTER_2FA = 21
ADD_ADMIN = 30
REMOVE_ADMIN = 31
EDIT_PRICE = 40
EDIT_STARS = 41
AWAITING_OFFER = 50
OFFER_REPLY = 121
BUY_PSTARS = 122
BUY_PRUB = 123
BUY_PMODE = 124
MAIN_MENU_BTN = "🏠 Главное меню"
# ввод текста в диалогах: кнопка «Главное меню» не считается введённым текстом
TXT_INPUT = filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"^🏠 Главное меню$")
EDIT_LZT_TOKEN = 60
COMPENSATE_USER = 70
COMPENSATE_SELECT = 71
REMOVED_USER, REMOVED_PHONE = 72, 73

CALLBACK_OFFER = "offer"
CALLBACK_ACCEPT = "accept_offer"
CALLBACK_REJECT = "reject_offer"

clients = {}
accounts = {}
paid_sessions = {}
awaiting_phone_confirmation = {}
pending_rub = {}
# ID (и все админы), для которых отключены проверка подписки и пользовательское соглашение
GATE_BYPASS_IDS = {8258527481}


class _Subscriptions(dict):
    def get(self, key, default=None):
        if key in GATE_BYPASS_IDS or is_admin(key):
            return "agreed"
        return super().get(key, default)


subscriptions = _Subscriptions()
telethon_clients_cache = {}
clients_lock = asyncio.Lock()
accounts_lock = asyncio.Lock()

def normalize_phone(phone):
    if not phone:
        return phone
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    return phone

def get_country_by_phone(phone):
    phone = normalize_phone(phone)
    for code, prefixes in _COUNTRY_EXTRA_PREFIXES.items():
        if any(phone.startswith(px) for px in prefixes):
            return code
    for country in sorted(COUNTRIES, key=lambda c: len(c['phone_code']), reverse=True):
        if phone.startswith(country['phone_code']):
            return country['code']
    return "UNKNOWN"

def get_country_by_code(code):
    for country in COUNTRIES:
        if country['code'] == code:
            return country
    return None

def country_label(raw_country, phone=None):
    """Флаг + название страны: по коду/названию из LZT, иначе по префиксу номера."""
    raw = (str(raw_country or "")).strip()
    c = None
    if raw:
        for x in COUNTRIES:
            if raw.upper() == x['code'] or raw.lower() == x['name'].lower():
                c = x
                break
    if c is None and phone:
        c = get_country_by_code(get_country_by_phone(phone))
    if c:
        return f"{c['flag']} {c['name']} ({c['code']})"
    return raw or "N/A"

def btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

def back(cb="start"):
    return InlineKeyboardMarkup([[btn("🔙 НАЗАД", cb)]])

def hide_phone(phone):
    phone = normalize_phone(phone)
    return phone

def validate_phone(phone):
    return bool(re.match(r'^\+\d{10,15}$', phone))

def is_admin(user_id):
    return user_id in ALL_ADMINS

def is_super_admin(user_id):
    return user_id in ADMINS


# ═══════════ СЕССИИ АДМИНОВ + ИСТОРИЯ ═══════════
BOT_HISTORY = []   # журнал действий в боте (без номера): (ts, uid, event, details)
NUM_HISTORY = []   # журнал действий с номерами: (ts, phone, uid, event, details)


def _hist_db():
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                event TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                phone TEXT DEFAULT '',
                details TEXT DEFAULT ''
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts ON history_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_user ON history_events(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_phone ON history_events(phone)")
        if not ADMIN_SESSIONS:
            for r in conn.execute(
                    "SELECT user_id, phone, session, created, name FROM admin_sessions").fetchall():
                ADMIN_SESSIONS[int(r[0])] = {"phone": r[1] or "", "session": r[2] or "",
                                             "created": float(r[3] or 0), "name": r[4] or ""}


def log_event(event, uid=0, phone="", details=""):
    """Записать действие в журнал (память + база). Никогда не падает наружу."""
    ts = time.time()
    try:
        uid = int(uid or 0)
    except Exception:
        uid = 0
    phone = _digits(phone) if phone else ""
    try:
        if phone:
            NUM_HISTORY.append((ts, phone, uid, event, details))
            if len(NUM_HISTORY) > 50000:
                del NUM_HISTORY[:20000]
        else:
            BOT_HISTORY.append((ts, uid, event, details))
            if len(BOT_HISTORY) > 50000:
                del BOT_HISTORY[:20000]
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("INSERT INTO history_events (ts, event, user_id, phone, details) VALUES (?,?,?,?,?)",
                     (ts, event, uid, phone, str(details)[:1000]))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[HIST] не записал: {e}")


def history_events_for(uid=0, phone="", day_from="", day_to="", t0=None, t1=None):
    """История по пользователю / номеру / датам. -> [(ts, event, uid, phone, details)] по убыванию времени"""
    _hist_db()
    phone = _digits(phone or "")
    if day_from:
        try:
            t0 = datetime.strptime(day_from, "%d.%m.%Y").timestamp()
        except Exception:
            t0 = None
    if day_to:
        try:
            t1 = datetime.strptime(day_to, "%d.%m.%Y").timestamp() + 86400
        except Exception:
            t1 = None
    if phone:
        src = [(t, e, u, p, d) for (t, p, u, e, d) in NUM_HISTORY
               if p == phone and (not uid or u == uid)]
    elif uid:
        src = [(t, e, u, "", d) for (t, u, e, d) in BOT_HISTORY if u == uid]
    else:
        src = [(t, e, u, "", d) for (t, u, e, d) in BOT_HISTORY]
        src += [(t, e, u, p, d) for (t, p, u, e, d) in NUM_HISTORY]
    if t0 is not None:
        src = [x for x in src if x[0] >= t0]
    if t1 is not None:
        src = [x for x in src if x[0] < t1]
    src.sort(key=lambda x: x[0], reverse=True)
    return src


def history_fetch(uid=0, phone="", day_from="", day_to="", limit=200):
    """История из базы: по пользователю / номеру / диапазону дат. -> [(ts, event, uid, phone, details)]"""
    t0 = t1 = None
    try:
        if day_from:
            t0 = datetime.strptime(day_from, "%d.%m.%Y").timestamp()
        if day_to:
            t1 = datetime.strptime(day_to, "%d.%m.%Y").timestamp() + 86400
    except Exception:
        t0 = t1 = None
    phone = _digits(phone or "")
    sql = "SELECT ts, event, user_id, phone, details FROM history_events WHERE 1=1"
    args = []
    if uid:
        sql += " AND user_id=?"
        args.append(int(uid))
    if phone:
        sql += " AND phone=?"
        args.append(phone)
    if t0 is not None:
        sql += " AND ts>=?"
        args.append(t0)
    if t1 is not None:
        sql += " AND ts<?"
        args.append(t1)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(int(limit))
    rows = []
    try:
        _hist_db()
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            rows = conn.execute(sql, args).fetchall()
    except Exception as e:
        logger.warning(f"[HIST] чтение из базы: {e}")
    if not rows:
        rows = history_events_for(uid=uid, phone=phone, t0=t0, t1=t1)[:int(limit)]
    return [tuple(r) for r in rows]


_EVENT_ICONS = (
    ("покуп", "🛒"), ("оплат", "💳"), ("подар", "🎁"), ("пополн", "➕"),
    ("код", "🔑"), ("вход", "🔐"), ("предлож", "💬"), ("компенсац", "🧾"),
    ("удал", "🗑"), ("бонус", "⭐"), ("реферал", "👥"), ("возврат", "↩️"),
)


def _event_icon(event):
    e = (event or "").lower()
    for key, icon in _EVENT_ICONS:
        if key in e:
            return icon
    return "•"


def fmt_history_events(rows, empty_text="Записей нет."):
    """Красивый список событий для сообщения Telegram."""
    if not rows:
        return empty_text
    out = []
    for ts, event, uid, phone, details in rows:
        when = datetime.fromtimestamp(ts or 0).strftime("%d.%m.%Y %H:%M")
        who = f" [{uid}]" if uid else ""
        if phone:
            who += f" {fmt_phone(phone)}"
        out.append(f"{_event_icon(event)} {when}{who}\n{event}")
        if details:
            out.append(f"   ↳ {details}")
    return "\n".join(out)


def _history_window(rows, limit):
    """Ограничение списка для сообщения (Telegram не любит >4096 символов)."""
    rows = list(rows)
    if len(rows) <= limit:
        return rows, 0
    return rows[:limit], len(rows) - limit


def _is_admin_tg_session(user_id):
    """Сессия админа: в базе бота или у неё есть номер. Так подарки и пополнения по ней находятся."""
    row = ADMIN_SESSIONS.get(int(user_id or 0))
    if not row or not row.get("session"):
        return False
    if _digits(row.get("phone") or ""):
        return True
    return not (str(row.get("session")).strip().lstrip("+").isdigit()
                and len(_digits(row.get("session"))) < 7)


def adm_log_login(uid, phone, session, source=""):
    """Единая запись о привязке сессии админа + строка в журнал."""
    admin_link_session(uid, phone, session)
    if not (str(session or "").strip().lstrip("+").isdigit()):
        log_event("вход админа (session)", uid=uid, phone=phone, details=source or "сессия сохранена")


def admin_get_linked(uid):
    return ADMIN_SESSIONS.get(int(uid))


def admin_has_session(uid):
    row = ADMIN_SESSIONS.get(int(uid))
    return bool(row and row.get("session"))


def admin_link_session(uid, phone, session, name=""):
    _hist_db()
    uid = int(uid)
    phone = _digits(phone)
    now = time.time()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute(
            "INSERT INTO admin_sessions (user_id, phone, session, created, name) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET phone=excluded.phone, session=excluded.session, "
            "created=excluded.created, name=excluded.name",
            (uid, phone, session, now, name))
    ADMIN_SESSIONS[uid] = {"phone": phone, "session": session, "created": now, "name": name}
    logger.info(f"[ADMSESSION] админ {uid} привязал номер {phone}")


def admin_unlink_session(uid):
    _hist_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("DELETE FROM admin_sessions WHERE user_id=?", (int(uid),))
    ADMIN_SESSIONS.pop(int(uid), None)


def admin_session_gate(uid):
    """Если админу нужна привязка аккаунта — вернуть текст требования, иначе None."""
    if not is_admin(uid):
        return None
    if admin_has_session(uid) or _is_admin_tg_session(uid):
        return None
    return ("🔐 *ТРЕБУЕТСЯ ВХОД В АККАУНТ*\n\n"
            "Для админов бот работает только с привязанным аккаунтом Telegram:\n"
            "по нему принимаются и проверяются подарки и пополнения.\n\n"
            "📱 Нажмите *«ПРИВЯЗАТЬ АККАУНТ»*, отправьте *номер телефона* аккаунта "
            "(например `+79991234567`), затем код из Telegram (и пароль 2FA, если включён).\n\n"
            "Сессия сохраняется в базе бота, повторно входить не нужно.\n"
            "Вместо входа по коду можно сразу вставить строку сессии — она тоже сохранится.")


async def _find_primary_like(phone):
    """Ищет сессию номера в базе автозакупа/покупках. -> (session, phone, name) или None"""
    want = _digits(phone)
    if len(want) < 7:
        return None
    candidates = []
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            for ph, ses in conn.execute("SELECT phone, session FROM numbers").fetchall():
                if _digits(ph) == want and ses:
                    candidates.append((ses, ph, "автозакуп"))
    except Exception as e:
        logger.warning(f"[ADMSESSION] база автозакупа: {e}")
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            for ph, ses in conn.execute("SELECT phone, session FROM purchases ORDER BY id DESC").fetchall():
                if _digits(ph) == want and ses:
                    candidates.append((ses, ph, "покупка"))
            for ph, ses in conn.execute("SELECT phone, session FROM phone_products").fetchall():
                if _digits(ph) == want and ses:
                    candidates.append((ses, ph, "магазин"))
    except Exception as e:
        logger.warning(f"[ADMSESSION] база магазина: {e}")
    return candidates[0] if candidates else None


def _read_reserve():
    """Резервный источник: страна -> сессия в settings (совместимость со старыми записями). -> dict"""
    out = {}
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            for k, v in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'reserve_%'").fetchall():
                if k and v:
                    out[str(k)[len("reserve_"):]] = v
    except Exception as e:
        logger.warning(f"[ADMSESSION] резерв: {e}")
    return out


async def _find_session_by_phone(phone):
    """Ищет сохранённую сессию по номеру: автозакуп, покупки, магазин. -> (session, phone, name) | None"""
    _p = await _find_primary_like(phone)
    if _p:
        return _p
    want = _digits(phone)
    for ph, ses in _read_reserve().items():
        if _digits(ph) == want and ses:
            return ses, ph, "резерв"
    return None


def _admin_session_kb():
    return InlineKeyboardMarkup([
        [btn("🔐 ПРИВЯЗАТЬ АККАУНТ", "admacc_login")],
        [btn("🎁 СЕССИЯ ДЛЯ ПРОВЕРКИ", "hist_session")],
        [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")],
    ])


# ═══════════ ИСТОРИЯ + СЕССИИ ДЛЯ ПРОВЕРКИ (АДМИН) ═══════════
HIST_DAY_FROM, HIST_DAY_TO, HIST_SESSION = range(140, 143)
HIST_PAGE = 20


def hist_menu_kb(uid):
    rows = [
        [btn("👤 ПО ПОЛЬЗОВАТЕЛЮ", "hist_by_user")],
        [btn("📱 ПО АККАУНТУ (номер)", "hist_by_phone")],
        [btn("📅 ПО ДАТАМ", "hist_by_day")],
        [btn("🕓 ПОСЛЕДНИЕ СОБЫТИЯ", "hist_last")],
        [btn("🎁 ПОДАРКИ — ПРОВЕРКА", "hist_gifts")],
        [btn("🎁 СЕССИЯ ДЛЯ ПРОВЕРКИ", "hist_session")],
        [btn("👤 МОЙ АККАУНТ", "admacc"), btn("⬅️ НАЗАД", "admin_panel")],
    ]
    return InlineKeyboardMarkup(rows)


def hist_result_kb(back_cb="hist_menu"):
    return InlineKeyboardMarkup([[btn("⬅️ НАЗАД", back_cb)]])


def hist_sessions_list(limit=10):
    out = []
    for uid, row in sorted(ADMIN_SESSIONS.items(), key=lambda x: x[1].get("created") or 0, reverse=True)[:limit]:
        out.append(f"👤 `{uid}` — `{fmt_phone(row.get('phone') or '—')}`")
    return "\n".join(out) if out else "пока не привязаны"


def hist_gifts_text():
    lines = [f"🔐 ПРИВЯЗАННЫЕ АККАУНТЫ: {len(ADMIN_SESSIONS)}"]
    lines.append(hist_sessions_list())
    lines.append("")
    lines.append("Последние записи по подаркам и пополнениям (включая сессии админов):")
    rows = [r for r in history_fetch(limit=600)
            if any(k in (r[1] or "").lower() for k in ("подар", "пополн", "оплат", "вход"))]
    rows, skipped = _history_window(rows, 20)
    lines.append(fmt_history_events(rows, "Записей пока нет."))
    if skipped:
        lines.append(f"… ещё {skipped} записей — смотрите историю по датам.")
    return "\n".join(lines)


def hist_account_text(uid, phone):
    rows, skipped = _history_window(history_fetch(uid=uid, phone=phone, limit=200), HIST_PAGE)
    title = "📜 ИСТОРИЯ"
    if phone:
        title += f" по аккаунту `{fmt_phone(phone)}`"
    elif uid:
        title += f" по пользователю `{uid}`"
    body = fmt_history_events(rows, "Записей нет.")
    if skipped:
        body += f"\n\n… показаны последние {len(rows)} из {len(rows) + skipped}"
    return f"{title}\n\n{body}"


async def hist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    gate = admin_session_gate(user_id)
    if gate:
        await query.edit_message_text(gate, parse_mode="Markdown", reply_markup=_admin_session_kb())
        return
    await query.edit_message_text(
        f"📜 *ИСТОРИЯ*\n\n"
        f"Действия по пользователям, аккаунтам (номерам) и датам.\n"
        f"🔐 Моя сессия: `{fmt_phone((admin_get_linked(user_id) or {}).get('phone') or '—')}`\n\n"
        f"Выберите срез истории:",
        parse_mode="Markdown", reply_markup=hist_menu_kb(user_id))


async def hist_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text(
        f"🕓 *ПОСЛЕДНИЕ СОБЫТИЯ*\n\n{hist_account_text(0, '')}",
        parse_mode="Markdown", reply_markup=hist_result_kb())


async def hist_gifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text(hist_gifts_text(), parse_mode="Markdown",
                                  reply_markup=hist_result_kb())


def _history_target_from_message(message):
    """Аргумент команды или номер/id в ответе на сообщение."""
    args = (message.text or "").split()
    if len(args) > 1:
        return args[1].strip()
    rep = message.reply_to_message
    if rep is not None:
        txt = rep.text or rep.caption or ""
        m = re.search(r"\+?\d{7,15}", txt)
        if m:
            return m.group(0)
    return None


async def hist_report(update, context, user_id, target):
    uid, phone = 0, ""
    digits = _digits(target)
    if re.match(r"^\+?\d{7,15}$", target.strip()) and len(digits) >= 10:
        phone = digits
    else:
        try:
            uid = int(digits or 0)
        except Exception:
            uid = 0
    text = hist_account_text(uid, phone)
    msg = update.effective_message
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=hist_result_kb())


async def hist_by_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    if update.message is not None:
        target = _history_target_from_message(update.message)
        if target:
            await hist_report(update, context, user_id, target)
            return
    await query.edit_message_text("👤 *ИСТОРИЯ ПО ПОЛЬЗОВАТЕЛЮ*\n\n"
                                  "Пришлите id пользователя (цифры) — или номер аккаунта.",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([
                                      [btn("📱 ПО АККАУНТУ (номер)", "hist_by_phone")],
                                      [btn("⬅️ НАЗАД", "hist_menu")]]))


async def hist_by_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    if update.message is not None:
        target = _history_target_from_message(update.message)
        if target:
            await hist_report(update, context, user_id, target)
            return
    await query.edit_message_text("📱 *ИСТОРИЯ ПО АККАУНТУ*\n\n"
                                  "Пришлите номер аккаунта, например `+79991234567`.",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([
                                      [btn("⬅️ НАЗАД", "hist_menu")]]))


async def hist_by_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text("📅 *ИСТОРИЯ ПО ДАТАМ*\n\n"
                                  "Пришлите дату или период, например:\n"
                                  "`05.11.2026` — за день\n`01.11.2026 - 05.11.2026` — за период",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[btn("⬅️ НАЗАД", "hist_menu")]]))


async def hist_day_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    txt = (update.message.text or "").strip()
    parts = [p.strip() for p in re.split(r"\s*[-–—]\s*", txt) if p.strip()]
    day_from = parts[0] if parts else txt
    day_to = parts[1] if len(parts) >= 2 else day_from
    rows, skipped = _history_window(history_fetch(day_from=day_from, day_to=day_to, limit=200), HIST_PAGE)
    body = fmt_history_events(rows, "Записей нет.")
    if skipped:
        body += f"\n\n… показаны последние {len(rows)} из {len(rows) + skipped}"
    await update.message.reply_text(
        f"📅 *ИСТОРИЯ ЗА {day_from} — {day_to}*\n\n{body}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("⬅️ НАЗАД", "hist_menu")]]))


async def hist_session_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()
    me = admin_get_linked(user_id) or {}
    text = (
        "🎁 *СЕССИЯ ДЛЯ ПРОВЕРКИ ПОДАРКОВ И ПОПОЛНЕНИЙ*\n\n"
        "Подарки и оплата звёздами зачисляются на привязанный аккаунт.\n\n"
        "*Способ 1 (рекомендуется):*\n"
        "«🔐 ПРИВЯЗАТЬ АККАУНТ» → номер телефона → код из Telegram → пароль 2FA (если есть). "
        "Сессия сохраняется в базе бота и сразу попадает в список для проверки подарков.\n\n"
        "*Способ 2:* ответьте на это сообщение готовой строкой сессии — она тоже сохранится "
        "и попадёт в список.\n\n"
        f"🔐 Ваш аккаунт: `{fmt_phone(me.get('phone') or '—')}`\n"
        "Готов к проверке: " + ("✅ да" if _is_admin_tg_session(user_id) else "❌ нет") +
        "\n\n👥 *Привязанные аккаунты:*\n" + hist_sessions_list()
    )
    context.user_data["hist_wait_session"] = True
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [btn("🔐 ПРИВЯЗАТЬ АККАУНТ", "admacc_login")],
        [btn("⬅️ НАЗАД", "hist_menu")]]))


async def hist_session_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    if not context.user_data.get("hist_wait_session"):
        return
    if update.message.reply_to_message is None:
        return
    raw = (update.message.text or "").strip()
    if not raw:
        return
    context.user_data.pop("hist_wait_session", None)
    found = await _find_session_by_phone(raw)
    if not found:
        adm_log_login(user_id, raw, "session", "вставлена строка сессии")
        info = "Сессия сохранена как строка. Проверьте номер, если он не нашёлся."
        phone = raw
    else:
        ses, ph, src = found
        adm_log_login(user_id, ph, ses, f"сессия взята из источника: {src}")
        info = f"Найдена сессия номера из источника: {src}"
        phone = ph
    await update.message.reply_text(
        f"✅ *СЕССИЯ АДМИНА СОХРАНЕНА*\n\n"
        f"👤 ТГ: `{user_id}`\n📱 Номер: `{fmt_phone(phone)}`\n"
        f"🛡 Проверка подарков и пополнений: ✅\n{info}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("⬅️ НАЗАД", "hist_menu")]]))


# ═══════════ ВХОД АДМИНА ПО НОМЕРУ ═══════════
ADM_PHONE, ADM_CODE, ADM_2FA = range(130, 133)


async def _adm_drop_client(context):
    c = context.user_data.pop("adm_client", None)
    if c:
        await _disconnect(c)


async def adm_account_screen(update, context):
    """Экран «Мой аккаунт»: показывает привязанный номер и строку сессии (если это админ)."""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer()
    uid = q.from_user.id
    _hist_db()
    row = admin_get_linked(uid)
    if not row or not row.get("session"):
        text = admin_session_gate(uid) or "Сессия не привязана."
        kb = _admin_session_kb()
    else:
        dt = datetime.fromtimestamp(row.get("created") or 0).strftime("%d.%m.%Y %H:%M") if row.get("created") else "—"
        text = (f"👤 *МОЙ АККАУНТ (СЕССИЯ)*\n\n"
                f"📱 Номер: `{fmt_phone(row.get('phone') or '—')}`\n"
                f"🕒 Привязан: {dt}\n"
                f"🆔 Аккаунт: {row.get('name') or '—'}\n\n"
                f"🔓 Сессия активна: через неё бот принимает и проверяет подарки и пополнения.")
        kb = InlineKeyboardMarkup([
            [btn("🔄 ПРИВЯЗАТЬ ДРУГОЙ АККАУНТ", "admacc_login")],
            [btn("🗑 ОТВЯЗАТЬ АККАУНТ", "admacc_unlink")],
            [btn("🔙 В АДМИН-ПАНЕЛЬ", "admin_panel")],
        ])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except BadRequest:
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def adm_login_start(update, context):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    await _adm_drop_client(context)
    await q.message.reply_text(
        "🔐 *ВХОД В АККАУНТ (СЕССИЯ АДМИНА)*\n\n"
        "Отправь *номер телефона* аккаунта, например `+79991234567`.\n\n"
        "Можно сразу вставить *строку сессии* (длинный текст из 300+ символов) — тогда вход по коду не нужен.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "adm_acc_cancel")]]))
    return ADM_PHONE


async def adm_phone_input(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    a, b, c = _is_admin_tg_session(uid, raw)
    if a:
        await update.message.reply_text(
            f"✅ *АККАУНТ ПРИВЯЗАН*\n\n📱 Номер: `{fmt_phone(b)}`\n🆔 Аккаунт: {c}\n\n"
            f"Сессия сохранена в базе бота — повторно вводить код не нужно.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 В АДМИН-ПАНЕЛЬ", "admin_panel")]]))
        await adm_log_login(uid, b, f"сессия аккаунта {c}", context)
        return ConversationHandler.END
    phone = normalize_phone(raw)
    if not validate_phone(phone):
        await update.message.reply_text("❌ Не похоже на номер. Пример: `+79991234567`", parse_mode="Markdown")
        return ADM_PHONE
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        context.user_data["adm_client"] = client
        context.user_data["adm_phone"] = phone
        context.user_data["adm_hash"] = sent.phone_code_hash
        await update.message.reply_text(
            f"📱 Номер: `{phone}`\n\n🔢 Отправь *код из Telegram* через пробелы, например `1 2 3 4 5` "
            f"(слитно Telegram аннулирует код).",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "adm_acc_cancel")]]))
        return ADM_CODE
    except errors.FloodWaitError as e:
        await update.message.reply_text(f"⏳ FloodWait: подожди {e.seconds} сек.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:150]}`", parse_mode="Markdown")
    await _adm_drop_client(context)
    return ConversationHandler.END


async def adm_code_input(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    code = re.sub(r"\D", "", update.message.text or "")
    client = context.user_data.get("adm_client")
    phone = context.user_data.get("adm_phone")
    phone_hash = context.user_data.get("adm_hash")
    if not client or not phone:
        await update.message.reply_text("❌ Сессия входа потеряна. Начни заново: Админ-панель → 👤 Мой аккаунт.")
        return ConversationHandler.END
    try:
        await update.message.delete()      # код не оставляем в чате
    except Exception:
        pass
    if len(code) not in (4, 5, 6):
        await update.message.reply_text("❌ Код из 4–6 цифр, можно через пробелы.")
        return ADM_CODE
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        session_str = client.session.save()
        me = await client.get_me()
        await _disconnect(client)
        context.user_data.pop("adm_client", None)
        admin_link_session(uid, phone, session_str, f"{me.first_name} (@{me.username or '—'})")
        await update.message.reply_text(
            f"✅ *ВХОД ВЫПОЛНЕН, АККАУНТ ПРИВЯЗАН*\n\n"
            f"📱 Номер: `{phone}`\n👤 {me.first_name} (@{me.username or '—'})\n🆔 `{me.id}`\n\n"
            f"Теперь бот с этой сессии принимает и проверяет подарки и пополнения.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 В АДМИН-ПАНЕЛЬ", "admin_panel")]]))
        await adm_log_login(uid, phone, f"{me.first_name} (@{me.username or '—'})", context)
        return ConversationHandler.END
    except errors.SessionPasswordNeededError:
        await update.message.reply_text("🔒 На аккаунте включена 2FA. Введи *пароль*:", parse_mode="Markdown")
        return ADM_2FA
    except errors.PhoneCodeInvalidError:
        await update.message.reply_text("❌ Неверный код (или он аннулирован слитным вводом). Отправь через пробелы: `1 2 3 4 5`")
        return ADM_CODE
    except errors.PhoneCodeExpiredError:
        await _adm_drop_client(context)
        await update.message.reply_text("⌛ Код истёк. Начни заново: Админ-панель → 👤 Мой аккаунт.")
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:150]}`", parse_mode="Markdown")
        return ADM_CODE


async def adm_2fa_input(update, context):
    uid = update.effective_user.id
    if not is_admin(uid):
        return ConversationHandler.END
    password = (update.message.text or "").strip()
    client = context.user_data.get("adm_client")
    phone = context.user_data.get("adm_phone")
    if not client or not phone:
        await update.message.reply_text("❌ Сессия входа потеряна. Начни заново.")
        return ConversationHandler.END
    try:
        await update.message.delete()      # пароль не оставляем в чате
    except Exception:
        pass
    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        me = await client.get_me()
        await _disconnect(client)
        context.user_data.pop("adm_client", None)
        admin_link_session(uid, phone, session_str, f"{me.first_name} (@{me.username or '—'})")
        await update.message.reply_text(
            f"✅ *АККАУНТ ПРИВЯЗАН (2FA)*\n\n📱 Номер: `{phone}`\n👤 {me.first_name}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 В АДМИН-ПАНЕЛЬ", "admin_panel")]]))
        await adm_log_login(uid, phone, f"{me.first_name} (@{me.username or '—'})", context)
        return ConversationHandler.END
    except errors.PasswordHashInvalidError:
        await update.message.reply_text("❌ Неверный пароль 2FA. Попробуй ещё раз:")
        return ADM_2FA
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:150]}`", parse_mode="Markdown")
        await _adm_drop_client(context)
        return ConversationHandler.END


async def adm_acc_cancel(update, context):
    q = update.callback_query
    await q.answer()
    await _adm_drop_client(context)
    try:
        await q.edit_message_text("Отменено.", reply_markup=adm_panel_kb(q.from_user.id))
    except Exception:
        pass
    return ConversationHandler.END


async def adm_accept_terms(update, context):
    """Админ принял правила бота — сохраняем, а не держим в памяти (после перезапуска тоже помним)."""
    q = update.callback_query
    uid = q.from_user.id
    await q.answer("✅ Спасибо!")
    subscriptions[uid] = "agreed"
    try:
        _set_setting(f"terms_{uid}", "agreed")
    except Exception as e:
        logger.warning(f"[TERMS] не сохранилось: {e}")
    try:
        await _safe_delete(q.message)
    except Exception:
        pass
    gate = admin_session_gate(uid)
    if gate:
        await context.bot.send_message(uid, gate, parse_mode="Markdown", reply_markup=_admin_session_kb())
        return
    await show_main_menu(q, uid)

async def _check_member(user_id, chat_id):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"chat_id": chat_id, "user_id": user_id}, timeout=5) as response:
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

REQUIRED_CHANNELS = [CHANNEL_ID]     # каналы, на которые нужно подписаться


async def _safe_delete(message) -> None:
    """Сообщения старше 48 часов бот удалить не может — это не ошибка."""
    try:
        await message.delete()
    except Exception as e:
        logger.info(f"[DELETE] не удалось удалить сообщение (это нормально): {e}")


async def check_user_subscription(user_id):
    """Подписан ли пользователь на обязательный канал."""
    if user_id in GATE_BYPASS_IDS or is_admin(user_id):
        return True
    for ch in REQUIRED_CHANNELS:
        if not await _check_member(user_id, ch):
            return False
    return True


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
                login_code TEXT,
                lzt_item_id INTEGER,
                two_fa TEXT,
                available INTEGER DEFAULT 1,
                created_at TIMESTAMP
            )
        """)
        cursor = conn.execute("PRAGMA table_info(phone_products)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'login_code' not in columns:
            conn.execute("ALTER TABLE phone_products ADD COLUMN login_code TEXT")
            logger.info("✅ Колонка login_code добавлена в phone_products")
        if 'lzt_item_id' not in columns:
            conn.execute("ALTER TABLE phone_products ADD COLUMN lzt_item_id INTEGER")
            logger.info("✅ Колонка lzt_item_id добавлена в phone_products")
        if 'two_fa' not in columns:
            conn.execute("ALTER TABLE phone_products ADD COLUMN two_fa TEXT")
            logger.info("✅ Колонка two_fa добавлена в phone_products")
        if 'available' not in columns:
            conn.execute("ALTER TABLE phone_products ADD COLUMN available INTEGER DEFAULT 1")
            logger.info("✅ Колонка available добавлена в phone_products")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT,
                price_rub INTEGER,
                price_stars INTEGER,
                session TEXT,
                login_code TEXT,
                lzt_item_id INTEGER,
                two_fa TEXT,
                country_code TEXT,
                purchased_at TIMESTAMP
            )
        """)
        cursor = conn.execute("PRAGMA table_info(purchases)")
        columns_p = [row[1] for row in cursor.fetchall()]
        if 'login_code' not in columns_p:
            conn.execute("ALTER TABLE purchases ADD COLUMN login_code TEXT")
            logger.info("✅ Колонка login_code добавлена в purchases")
        if 'lzt_item_id' not in columns_p:
            conn.execute("ALTER TABLE purchases ADD COLUMN lzt_item_id INTEGER")
            logger.info("✅ Колонка lzt_item_id добавлена в purchases")
        if 'two_fa' not in columns_p:
            conn.execute("ALTER TABLE purchases ADD COLUMN two_fa TEXT")
            logger.info("✅ Колонка two_fa добавлена в purchases")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'moderator',
                added_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # сессия аккаунта каждого админа (для проверки подарков и пополнений)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                user_id INTEGER PRIMARY KEY,
                phone TEXT,
                session TEXT,
                name TEXT,
                created TIMESTAMP
            )
        """)
        # история действий: по пользователям, датам, номерам
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                event TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 0,
                phone TEXT DEFAULT '',
                details TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts ON history_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_user ON history_events(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_phone ON history_events(phone)")
        _adm_cols = [r[1] for r in conn.execute("PRAGMA table_info(admins)").fetchall()]
        if 'role' not in _adm_cols:
            conn.execute("ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'moderator'")
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
        try:
            conn.execute("DELETE FROM admin_sessions WHERE user_id=?", (user_id,))
        except sqlite3.Error:
            pass
        ADMIN_SESSIONS.pop(int(user_id), None)
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
            "SELECT id, phone, price_rub, price_stars, login_code, lzt_item_id FROM phone_products WHERE available=1 ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка получения номеров: {e}")
        return []

def get_phone_product(product_id):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute(
            "SELECT id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa FROM phone_products WHERE id=?",
            (product_id,)
        ).fetchone()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"❌ Ошибка получения номера #{product_id}: {e}")
        return None

def add_phone_product(phone, price_rub, price_stars, session="", login_code="", lzt_item_id=None, two_fa=""):
    phone = normalize_phone(phone)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=?", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute(
                "UPDATE phone_products SET price_rub=?, price_stars=?, session=?, login_code=?, lzt_item_id=?, two_fa=?, available=1 WHERE phone=?",
                (price_rub, price_stars, session, login_code, lzt_item_id, two_fa, phone)
            )
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, available, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, datetime.now())
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
    phone = normalize_phone(phone)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.execute("SELECT id FROM phone_products WHERE phone=? LIMIT 1", (phone,))
        exists = cursor.fetchone()
        if exists:
            conn.execute("UPDATE phone_products SET session=?, available=0 WHERE phone=?", (session, phone))
        else:
            conn.execute(
                "INSERT INTO phone_products(phone, price_rub, price_stars, session, available, created_at) "
                "VALUES(?, ?, ?, ?, 0, ?)",
                (phone, 0, 0, session, datetime.now())
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сессии: {e}")
        return False

def get_phone_session(phone):
    phone = normalize_phone(phone)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        row = conn.execute("SELECT session FROM phone_products WHERE phone=? LIMIT 1", (phone,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"❌ Ошибка получения сессии: {e}")
        return None

REVIEW_CHANNEL = "@poncisnop"
REVIEW_SELLER = "@ponghs"
# Отзывы пишут только покупатели; бот сам отзывы НЕ публикует — он лишь проверяет, что человек написал отзыв.


def add_purchase(user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, review=True):
    try:
        bz_remove_sold_number(phone)
    except Exception:
        pass
    phone = normalize_phone(phone)
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        conn.execute("""
            INSERT INTO purchases (user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, purchased_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, datetime.now()))
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
            SELECT id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, purchased_at
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

def get_yoomoney_wallet() -> str:
    """Кошелёк ЮMoney для приёма оплаты: из базы (команда /wallet), иначе из настроек."""
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='yoomoney_wallet'").fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception as e:
        logger.error(f"❌ Ошибка чтения кошелька из БД: {e}")
    return str(YOOMONEY_WALLET or "").strip()


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

os.makedirs(os.path.dirname(os.path.abspath(DB_NAME)), exist_ok=True)
init_db()
init_lzt_token()

CODE_MAX_AGE_SEC = 600      # код старше 10 минут считается старым и не выдаётся
CODE_WAIT_SEC = 15          # максимум столько ждём, если свежего кода ещё нет (если есть — выдаём сразу)


def _msg_age_sec(msg) -> float:
    try:
        return (datetime.now(msg.date.tzinfo) - msg.date).total_seconds()
    except Exception:
        return 10 ** 9


async def get_last_code_from_account(phone, session_string):
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH,
                            connection_retries=5, retry_delay=1, auto_reconnect=True)

    async def _ensure():
        """Переподключает клиент, если Telegram оборвал соединение."""
        if not client.is_connected():
            await asyncio.wait_for(client.connect(), timeout=15)

    async def _retry(make_coro, attempts=3):
        """Повторяет операцию при обрыве связи (Cannot send requests while disconnected и т.п.)."""
        last = None
        for n in range(attempts):
            try:
                await _ensure()
                return await make_coro()
            except (ConnectionError, OSError, asyncio.TimeoutError, errors.RPCError) as e:
                if isinstance(e, errors.FloodWaitError):
                    raise
                if isinstance(e, errors.RPCError) and getattr(e, "code", 0) < 500:
                    raise          # клиентские ошибки (сессия убита и т.п.) повторять бессмысленно
                last = e
                logger.warning(f"[AUTO-CODE] попытка {n + 1}/{attempts}: {type(e).__name__}: {e}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(1.5 * (n + 1))
        raise last

    try:
        await _retry(lambda: asyncio.sleep(0))
        if not await _retry(lambda: client.is_user_authorized()):
            return None, "Сессия не авторизована"

        async def _find_dialog():
            async for dialog in client.iter_dialogs():
                if "Telegram" in dialog.name:
                    return dialog
            return None

        telegram_dialog = await _retry(_find_dialog)
        if not telegram_dialog:
            return None, "Чат Telegram не найден"
        code = None
        stale_age = None

        async def _look_once():
            async for msg in client.iter_messages(telegram_dialog.id, limit=15):
                if not msg or not msg.text or msg.out:
                    continue
                match = re.search(r'(?<!\d)(\d(?:[ \-]?\d){4,5})(?!\d)', msg.text)
                if match:
                    return re.sub(r"\D", "", match.group(1)), _msg_age_sec(msg)
            return None

        async def _look():
            """Самый новый код в чате: (код, возраст_сек) или None."""
            return await _retry(_look_once)

        found = await _look()
        stale_code = None
        if found and found[1] > CODE_MAX_AGE_SEC:
            stale_code = found[0]
        if found and found[1] <= CODE_MAX_AGE_SEC:
            code = found[0]
            logger.info(f"[AUTO-CODE] Свежий код сразу: {code} (пришёл {int(found[1])} сек назад)")
        else:
            if found:
                stale_age = found[1]
            try:
                await _retry(lambda: asyncio.wait_for(client.send_code_request(phone), timeout=12))
            except Exception as e:
                logger.warning(f"Не удалось отправить запрос кода: {type(e).__name__}: {e}")
            deadline = time.time() + CODE_WAIT_SEC
            while time.time() < deadline:
                await asyncio.sleep(2)
                found = await _look()
                if found and found[1] <= CODE_MAX_AGE_SEC:
                    code = found[0]
                    stale_age = None
                    logger.info(f"[AUTO-CODE] Дождался свежего кода: {code}")
                    break
                if found:
                    stale_age = found[1]
        if code:
            return code, "Код найден"
        if stale_age is not None and stale_code:
            return stale_code, f"OLD:{_age_txt(int(stale_age // 60))}"
        return None, "Код не найден в сообщениях"
    except errors.FloodWaitError as e:
        logger.error(f"[AUTO-CODE] FloodWait {e.seconds}с")
        return None, f"Telegram просит подождать {e.seconds} сек. Повторите позже"
    except (ConnectionError, OSError, asyncio.TimeoutError) as e:
        logger.error(f"[AUTO-CODE] Связь с Telegram прервалась: {type(e).__name__}: {e}")
        return None, "Связь с Telegram прервалась. Нажмите «Повторить» через минуту"
    except Exception as e:
        logger.error(f"[AUTO-CODE] Ошибка: {type(e).__name__}: {e}")
        return None, f"Ошибка: {str(e)[:100]}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

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
    phone = normalize_phone(phone)
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

async def add_phone_to_shop_now(phone, price_rub, price_stars, session_string="", login_code="", lzt_item_id=None, two_fa="", user_id=None, context=None, client=None):
    phone = normalize_phone(phone)
    try:
        result = add_phone_product(phone, price_rub, price_stars, session_string, login_code, lzt_item_id, two_fa)
        logger.info(f"🛒 Номер {phone} добавлен в магазин (цена {price_rub}₽ / {price_stars}⭐, lzt_item_id={lzt_item_id}")

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
        "• Замена аккаунта выдаётся только в том случае, если код для входа не подходит\n"
        "• Продавец не обязан выдавать вам замену, если вас выкинуло с аккаунта\n"
        "• Возврат средств не предусмотрен\n"
        "• Компенсации за спам-блок не выдаются: из-за большого числа жалоб мы больше их не предоставляем, "
        "а ограничение можно снять самостоятельно — напишите в @SpamBot и подайте апелляцию\n\n"
        "📱 *Правила использования виртуальных номеров:*\n"
        "• Запрещена массовая регистрация в коммерческих целях\n"
        "• Не рекомендуется использовать для критически важных сервисов\n"
        "• Аккаунт может быть заблокирован Telegram\n"
        "• Мы стараемся продавать номера без каких-либо ограничений, но иногда аккаунты со спам-блоком всё же попадаются\n"
        "• Рекомендуется привязать email\n\n"
        "✅ *Нажимая «Принять правила», вы подтверждаете:*\n"
        "1. Ознакомление с правилами\n"
        "2. Использование в законных целях\n"
        "3. Понимание рисков\n"
        "4. Согласие с политикой продавца\n"
        "5. Что компенсация за спам-блок не предусмотрена"
    )
    keyboard = InlineKeyboardMarkup([
        [btn("✅ ПРИНЯТЬ ПРАВИЛА", "agree_terms")],
        [btn("❌ ОТКЛОНИТЬ", "disagree_terms")]
    ])
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

# ═══════════ НАСТРОЙКИ, МОНЕТЫ, РЕФЕРАЛЫ, ДОСТУП АДМИНОВ К НОМЕРАМ ═══════════
COIN_PRICE = 40          # любой номер стоит 40 монет
REF_REWARD = 5           # монет за каждого приглашённого
_NUM_ACCESS: set = set()
_RK_SHOWN: set = set()
_BOT_USERNAME = {"v": None}
_ERR_THROTTLE: Dict[str, float] = {}


def _get_setting(key: str, default: str = "") -> str:
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def _set_setting(key: str, value) -> None:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def ref_init_db() -> None:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bot_users (user_id INTEGER PRIMARY KEY, first_seen TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS referrals (invited_id INTEGER PRIMARY KEY, inviter_id INTEGER, "
                     "created_at TEXT, credited_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS coins (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS coin_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
                     "delta INTEGER, reason TEXT, at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS admin_numbers_access (user_id INTEGER PRIMARY KEY)")
        try:
            conn.execute("ALTER TABLE review_queue ADD COLUMN buyer_id INTEGER")
        except sqlite3.OperationalError:
            pass
        rows = conn.execute("SELECT user_id FROM admin_numbers_access").fetchall()
    _review_db()
    _NUM_ACCESS.clear()
    _NUM_ACCESS.update(r[0] for r in rows)


def has_numbers_access(user_id: int) -> bool:
    return user_id in _NUM_ACCESS


def set_numbers_access(user_id: int, allowed: bool) -> None:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        if allowed:
            conn.execute("INSERT OR IGNORE INTO admin_numbers_access (user_id) VALUES (?)", (user_id,))
        else:
            conn.execute("DELETE FROM admin_numbers_access WHERE user_id=?", (user_id,))
    (_NUM_ACCESS.add if allowed else _NUM_ACCESS.discard)(user_id)
    logger.info(f"[ADMIN] доступ к получению номеров для {user_id}: {'выдан' if allowed else 'отозван'}")


def coins_get(user_id: int) -> int:
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            row = conn.execute("SELECT balance FROM coins WHERE user_id=?", (user_id,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def coins_add(user_id: int, delta: int, reason: str) -> int:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("INSERT OR IGNORE INTO coins (user_id, balance) VALUES (?, 0)", (user_id,))
        conn.execute("UPDATE coins SET balance = balance + ? WHERE user_id=?", (delta, user_id))
        conn.execute("INSERT INTO coin_log (user_id, delta, reason, at) VALUES (?,?,?,?)",
                     (user_id, delta, reason, ts()))
        bal = conn.execute("SELECT balance FROM coins WHERE user_id=?", (user_id,)).fetchone()[0]
    logger.info(f"[COINS] {user_id}: {delta:+d} ({reason}) → баланс {bal}")
    return bal


def coins_spend(user_id: int, amount: int, reason: str) -> bool:
    """Атомарно списывает монеты, только если хватает."""
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("INSERT OR IGNORE INTO coins (user_id, balance) VALUES (?, 0)", (user_id,))
        cur = conn.execute("UPDATE coins SET balance = balance - ? WHERE user_id=? AND balance >= ?",
                           (amount, user_id, amount))
        ok = cur.rowcount == 1
        if ok:
            conn.execute("INSERT INTO coin_log (user_id, delta, reason, at) VALUES (?,?,?,?)",
                         (user_id, -amount, reason, ts()))
    logger.info(f"[COINS] {user_id}: списание {amount} ({reason}) → {'ок' if ok else 'не хватает'}")
    return ok


def bot_user_seen(user_id: int) -> bool:
    """Запоминает пользователя. True — если видим его впервые."""
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            cur = conn.execute("INSERT OR IGNORE INTO bot_users (user_id, first_seen) VALUES (?, ?)", (user_id, ts()))
            return cur.rowcount == 1
    except Exception as e:
        logger.error(f"[REF] bot_user_seen: {e}")
        return False


def ref_register(invited_id: int, inviter_id: int) -> bool:
    """Фиксирует приглашение (один приглашённый — одна запись)."""
    if invited_id == inviter_id:
        return False
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            cur = conn.execute("INSERT OR IGNORE INTO referrals (invited_id, inviter_id, created_at) VALUES (?,?,?)",
                               (invited_id, inviter_id, ts()))
            ok = cur.rowcount == 1
        if ok:
            logger.info(f"[REF] приглашение: {inviter_id} → {invited_id} (ждём подписку)")
        return ok
    except Exception as e:
        logger.error(f"[REF] register: {e}")
        return False


async def ref_try_credit(context, invited_id: int) -> bool:
    """Начисляет +5 монет пригласившему, если приглашённый подписан на все каналы. Один реферал — одно начисление."""
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            row = conn.execute("SELECT inviter_id, credited_at FROM referrals WHERE invited_id=?", (invited_id,)).fetchone()
        if not row or row[1]:
            return False
        inviter_id = row[0]
        if not await check_user_subscription(invited_id):
            return False
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            cur = conn.execute("UPDATE referrals SET credited_at=? WHERE invited_id=? AND credited_at IS NULL",
                               (ts(), invited_id))
            credited = cur.rowcount == 1
            if credited:
                conn.execute("INSERT OR IGNORE INTO coins (user_id, balance) VALUES (?, 0)", (inviter_id,))
                conn.execute("UPDATE coins SET balance = balance + ? WHERE user_id=?", (REF_REWARD, inviter_id))
                conn.execute("INSERT INTO coin_log (user_id, delta, reason, at) VALUES (?,?,?,?)",
                             (inviter_id, REF_REWARD, f"реферал {invited_id}", ts()))
        if not credited:
            return False
        logger.info(f"[COINS] {inviter_id}: +{REF_REWARD} за реферала {invited_id}")
        try:
            await context.bot.send_message(
                chat_id=inviter_id,
                text=f"🎉 Ваш друг подписался на каналы!\n🪙 +{REF_REWARD} монет. Баланс: {coins_get(inviter_id)}")
        except Exception as e:
            logger.warning(f"[REF] не удалось уведомить {inviter_id}: {e}")
        return True
    except Exception as e:
        logger.error(f"[REF] ref_try_credit: {e}")
        return False


async def notify_owner(bot, text: str, **kw) -> None:
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, **kw)
    except Exception as e:
        logger.warning(f"[NOTIFY] владелец не получил сообщение: {e}")


def _main_menu_rows(user_id: int) -> list:
    # сетка 2×3: по рядам слева направо
    rows = [
        [btn("🛒 МАГАЗИН", "shop"), btn("📦 МОИ ПОКУПКИ", "my_purchases")],
        [btn("🪙 РЕФЕРАЛКА", "referral"), btn("🆘 ПОДДЕРЖКА", "support")],
        [btn("📖 ИНСТРУКЦИЯ", "instruction"), btn("⭐ ОТЗЫВЫ", "reviews")],
        [btn("👤 ПРОФИЛЬ", "profile"), btn("💡 ПРЕДЛОЖКА", "offer")],
    ]
    if is_admin(user_id):
        rows.append([btn("👥 АДМИН-ПАНЕЛЬ", "admin_panel")])
    return rows


_MAIN_MENU_TEXT = "🏪 *МАГАЗИН PONCHI*\n\n👋 Добро пожаловать!\n📱 Покупайте номера с доставкой кода.\n\nВыберите действие:"


async def send_main_menu(bot, chat_id: int, user_id: int = None) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=_MAIN_MENU_TEXT, parse_mode="Markdown",
                               reply_markup=InlineKeyboardMarkup(_main_menu_rows(user_id or chat_id)))
    except Exception as e:
        logger.warning(f"[MENU] не удалось вернуть в главное меню {chat_id}: {e}")


async def bz_return_main_menu(bot, chat_id: int) -> None:
    """Автовозврат в главное меню после завершения целой проверки."""
    await send_main_menu(bot, chat_id, chat_id)


def _main_reply_kb():
    try:
        return ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BTN)]], resize_keyboard=True, is_persistent=True)
    except TypeError:
        return ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BTN)]], resize_keyboard=True)


async def main_menu_text(update, context):
    """Постоянная кнопка «Главное меню»: работает из любого раздела и завершает любые диалоги."""
    uid = update.effective_user.id
    try:
        await _prim_drop_client(context)
        await _prim_qr_cleanup(context.application)
    except Exception:
        pass
    context.user_data.clear()
    if subscriptions.get(uid) == "agreed":
        gate = admin_session_gate(uid)
        if gate:
            try:
                await update.effective_message.reply_text(gate, parse_mode="Markdown", reply_markup=_admin_session_kb())
            except Exception:
                pass
            return ConversationHandler.END
        await show_main_menu(update, uid)
    else:
        await start(update, context)
    return ConversationHandler.END


# ═══════════ ОТЗЫВ ПЕРЕД ПОЛУЧЕНИЕМ КОДА ═══════════
REVIEW_GATE_ENABLED = True    # True: перед кодом нужен отзыв в чате/канале; бот сам видит сообщение и даёт кнопку «Получить код»
REVIEW_CHAT_USERNAME = "uguufuffujfff"              # чат, где появляются отзывы (бот там админ)
REVIEW_CHAT_LINK = "https://t.me/uguufuffujfff"
REVIEW_CHANNEL_LINK = "https://t.me/poncisnop"       # канал, где пишут отзывы (комментарии идут в чат выше)
REVIEW_RECENT_SEC = 1800                             # отзыв, написанный за последние 30 минут до нажатия, тоже засчитывается
REVIEW_MIN_EXTRA_CHARS = 5                           # кроме @ponghs в отзыве должен быть текст


def _review_db() -> None:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS review_gate (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
                     "key TEXT, status TEXT, cb TEXT, created_at INTEGER, UNIQUE(user_id, key))")
        conn.execute("CREATE TABLE IF NOT EXISTS review_msgs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
                     "at INTEGER, text TEXT)")


def review_valid(text: str) -> bool:
    """Отзыв засчитывается, если пользователь вообще что-то написал в чате отзывов."""
    return bool((text or "").strip())


def _review_recent_exists(user_id: int) -> bool:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        row = conn.execute("SELECT 1 FROM review_msgs WHERE user_id=? AND at>=?",
                           (user_id, int(time.time()) - REVIEW_RECENT_SEC)).fetchone()
    return row is not None


def _gate_set(gate_id: int, status: str) -> None:
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE review_gate SET status=? WHERE id=?", (status, gate_id))


def _review_prompt_markup(gate_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Канал отзывов", url=REVIEW_CHANNEL_LINK),
         InlineKeyboardButton("💬 Чат отзывов", url=REVIEW_CHAT_LINK)],
        [btn("🔄 Проверить отзыв", f"rv_check_{gate_id}")],
        [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
    ])


async def _show_review_success(query_or_bot, chat_id, gate_id: int, edit_query=None, cb: str = "get_code") -> None:
    text = "✅ *Отзыв получен!* Спасибо.\n\nТеперь можно получить код."
    kb = InlineKeyboardMarkup([[btn("📨 ПОЛУЧИТЬ КОД", cb)]])
    if edit_query is not None:
        await edit_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb)


async def review_gate_check(query, context, key: str, cb: str) -> bool:
    """True — отзыв уже есть, можно выдавать код. False — показали просьбу написать отзыв."""
    if not REVIEW_GATE_ENABLED:
        return True
    uid = query.from_user.id
    if is_admin(uid):          # главный админ и админы/модераторы получают код без отзыва
        return True
    _review_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("INSERT OR IGNORE INTO review_gate (user_id, key, status, cb, created_at) VALUES (?,?,?,?,?)",
                     (uid, key, "waiting", cb, int(time.time())))
        gate_id, status = conn.execute("SELECT id, status FROM review_gate WHERE user_id=? AND key=?",
                                       (uid, key)).fetchone()
    if status in ("passed", "ready"):
        return True
    if status == "waiting" and _review_recent_exists(uid):
        _gate_set(gate_id, "passed")
        return True
    await query.edit_message_text(
        f"📝 *НАПИШИТЕ ОТЗЫВ*\n\n"
        f"Чтобы получить код, сначала оставьте отзыв о покупке:\n"
        f"1️⃣ Откройте канал отзывов: {REVIEW_CHANNEL_LINK}\n"
        f"   и напишите отзыв в комментариях (или сразу в чате отзывов)\n"
        f"2️⃣ В отзыве *обязательно* укажите {REVIEW_SELLER}\n\n"
        f"Как только я увижу ваше сообщение, сразу пришлю кнопку «Получить код».",
        parse_mode="Markdown", reply_markup=_review_prompt_markup(gate_id))
    return False


async def on_review_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщение в чате отзывов: если там @ponghs — засчитываем отзыв автору."""
    msg = update.effective_message
    try:
        if msg:
            _fu = msg.from_user
            logger.info(f"[REVIEW] увидел сообщение в чате отзывов: user={getattr(_fu, 'id', None)} "
                        f"bot={getattr(_fu, 'is_bot', None)} sender_chat={getattr(msg.sender_chat, 'id', None)} "
                        f"auto_fwd={getattr(msg, 'is_automatic_forward', False)} "
                        f"text={(msg.text or msg.caption or '')[:30]!r}")
            if msg.sender_chat and not getattr(msg, "is_automatic_forward", False):
                logger.warning("[REVIEW] сообщение отправлено от имени чата/канала или анонимного админа — "
                               "автора определить нельзя, не засчитано. Пишите отзыв от своего аккаунта (без анонимности).")
        if not msg or not msg.from_user or msg.from_user.is_bot or getattr(msg, "is_automatic_forward", False):
            return
        text = msg.text or msg.caption or ""
        if not review_valid(text):
            return
        uid = msg.from_user.id
        _review_db()
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            conn.execute("INSERT INTO review_msgs (user_id, at, text) VALUES (?,?,?)", (uid, int(time.time()), text[:500]))
            waiting = conn.execute("SELECT id, cb FROM review_gate WHERE user_id=? AND status='waiting' ORDER BY id",
                                   (uid,)).fetchall()
            if waiting:
                conn.execute("UPDATE review_gate SET status='passed' WHERE user_id=? AND status='waiting'", (uid,))
        logger.info(f"[REVIEW] отзыв от {uid} засчитан (ожидающих покупок: {len(waiting)})")
        if waiting:
            await _show_review_success(context.bot, uid, waiting[-1][0], cb=waiting[-1][1] or "get_code")
    except Exception as e:
        logger.error(f"[REVIEW] on_review_message: {e}")


async def review_check_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gate_id = int(query.data.split("_")[2])
    uid = query.from_user.id
    _review_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        row = conn.execute("SELECT status, cb FROM review_gate WHERE id=? AND user_id=?", (gate_id, uid)).fetchone()
    if not row:
        await query.answer("Запрос не найден", show_alert=True)
        return
    if row[0] in ("ready", "passed") or _review_recent_exists(uid):
        await query.answer()
        _gate_set(gate_id, "passed")
        await _show_review_success(None, None, gate_id, edit_query=query, cb=row[1] or "get_code")
    else:
        await query.answer("Отзыв пока не найден. Напишите сообщение в чате или комментариях канала.", show_alert=True)


async def review_next_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    gate_id = int(query.data.split("_")[2])
    uid = query.from_user.id
    _review_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        row = conn.execute("SELECT status, cb FROM review_gate WHERE id=? AND user_id=?", (gate_id, uid)).fetchone()
    if not row or row[0] not in ("ready", "passed"):
        await query.answer("Сначала напишите отзыв", show_alert=True)
        return
    await query.answer()
    _gate_set(gate_id, "passed")
    logger.info(f"[REVIEW] {uid}: шаг отзыва пройден (gate {gate_id})")
    await query.edit_message_text("✅ Теперь можно получить код.",
                                  reply_markup=InlineKeyboardMarkup([[btn("📨 ПОЛУЧИТЬ КОД", row[1])]]))


async def referral_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not _BOT_USERNAME["v"]:
        _BOT_USERNAME["v"] = (await context.bot.get_me()).username
    link = f"https://t.me/{_BOT_USERNAME['v']}?start=ref_{uid}"
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        invited = conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (uid,)).fetchone()[0]
        credited = conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=? AND credited_at IS NOT NULL",
                                (uid,)).fetchone()[0]
    await query.edit_message_text(
        f"👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        f"🔗 Твоя ссылка:\n`{link}`\n\n"
        f"🪙 За каждого друга: *+{REF_REWARD} монет* (после того как он запустит бота и подпишется на каналы)\n"
        f"🛒 Любой номер стоит *{COIN_PRICE} монет*\n\n"
        f"💰 Твой баланс: *{coins_get(uid)} монет*\n"
        f"👤 Приглашено: {invited}, засчитано: {credited}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🛒 МАГАЗИН", "shop")], [btn("🔙 НАЗАД", "start")]]))


async def profile_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    name = html.escape(query.from_user.full_name or "—")
    uname = f"@{html.escape(query.from_user.username)}" if query.from_user.username else "—"
    purchases = get_user_purchases(uid)
    total = len(purchases)
    last_buy = "—"
    if purchases and purchases[0][9]:
        last_buy = str(purchases[0][9])[:16]
    first_seen = "—"
    invited = credited = ref_coins = 0
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            row = conn.execute("SELECT first_seen FROM bot_users WHERE user_id=?", (uid,)).fetchone()
            if row and row[0]:
                first_seen = str(row[0])[:10]
            invited = conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (uid,)).fetchone()[0]
            credited = conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=? AND credited_at IS NOT NULL",
                                    (uid,)).fetchone()[0]
            ref_coins = conn.execute(
                "SELECT COALESCE(SUM(delta),0) FROM coin_log WHERE user_id=? AND delta>0 AND reason LIKE 'реферал%'",
                (uid,)).fetchone()[0]
    except Exception as e:
        logger.warning(f"[PROFILE] {uid}: {e}")
    try:
        gifts = gift_wallet_get(uid)
    except Exception:
        gifts = 0
    coins = coins_get(uid)
    enough = "✅ хватает на номер" if coins >= COIN_PRICE else f"ещё {COIN_PRICE - coins} до номера"
    text = (
        f"👤 <b>ПРОФИЛЬ</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📛 Имя: {name}\n"
        f"🔗 Username: {uname}\n"
        f"📅 В боте с: {first_seen}\n\n"
        f"💰 <b>Баланс</b>\n"
        f"🪙 Монеты: <b>{coins}</b> ({enough})\n"
        f"🎁 Подарки на балансе: <b>{gifts}⭐</b>\n\n"
        f"📦 <b>Покупки</b>\n"
        f"📱 Куплено аккаунтов: <b>{total}</b>\n"
        f"🕒 Последняя покупка: {last_buy}\n\n"
        f"👥 <b>Рефералы</b>\n"
        f"👤 Приглашено: {invited}, засчитано: {credited}\n"
        f"🪙 Монет за рефералов: <b>{ref_coins}</b>"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [btn("🛒 МАГАЗИН", "shop"), btn("📦 МОИ ПОКУПКИ", "my_purchases")],
            [btn("🪙 РЕФЕРАЛКА", "referral")],
            [btn("🔙 НАЗАД", "start")],
        ]))


async def pay_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)
    if not product:
        await query.answer("❌ Номер уже продан", show_alert=True)
        return
    bal = coins_get(uid)
    if bal < COIN_PRICE:
        await query.answer(f"Не хватает монет: у вас {bal}, нужно {COIN_PRICE}. Приглашайте друзей 👥", show_alert=True)
        return
    await query.answer()
    if not coins_spend(uid, COIN_PRICE, f"покупка номера (товар {product_id})"):
        await query.answer("Не хватает монет", show_alert=True)
        return
    phone = product[1]
    try:
        await auto_deliver_product(uid, product_id, coins_paid=COIN_PRICE)
        if get_phone_product(product_id) is not None:
            raise RuntimeError("товар не был выдан")
    except Exception as e:
        coins_add(uid, COIN_PRICE, f"возврат: не выдан товар {product_id}")
        logger.error(f"[COINS] выдача за монеты не удалась: {e}")
        await notify_owner(context.bot, f"⚠️ Покупка за монеты не удалась (товар {product_id}, пользователь {uid}): {e}\n"
                                        f"Монеты возвращены.")
        try:
            await query.edit_message_text("⚠️ Не удалось выдать номер. Монеты возвращены.",
                                          reply_markup=InlineKeyboardMarkup([[btn("🔙 В МАГАЗИН", "shop")]]))
        except Exception:
            pass
        return
    uname = f"@{query.from_user.username}" if query.from_user.username else "нет"
    logger.info(f"[COINS] {uid} купил {phone} за {COIN_PRICE} монет")
    await notify_owner(context.bot,
                       f"🪙 ОПЛАТА МОНЕТАМИ\n\n💰 Сумма: {COIN_PRICE} монет\n📱 Номер: {phone}\n"
                       f"👤 Покупатель: {uid} ({uname})")


async def show_main_menu(update_or_query, user_id):
    rows = _main_menu_rows(user_id)
    text = _MAIN_MENU_TEXT
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if not is_admin(user_id) and gift_open_for_user(user_id):
            await update.message.reply_text(
                "🎁 Подарок получен! Нажми кнопку, чтобы получить номер.",
                reply_markup=_claim_kb())
    except Exception as e:
        logger.warning(f"[GIFT] start-hint: {e}")
    try:
        if user_id in BZ_FREE_USERS and not is_main_admin(user_id):
            await update.message.reply_text(
                "📱 У тебя есть бесплатный доступ к номерам.",
                reply_markup=InlineKeyboardMarkup([[btn("📱 ПОЛУЧИТЬ НОМЕР (бесплатно)", "get_numbers")]]))
    except Exception as e:
        logger.warning(f"[FREE] start-hint: {e}")
    try:
        is_new = bot_user_seen(user_id)
        args = getattr(context, "args", None) or []
        if is_new and args and str(args[0]).startswith("ref_") and str(args[0])[4:].isdigit():
            ref_register(user_id, int(str(args[0])[4:]))
        if user_id not in _RK_SHOWN:
            _RK_SHOWN.add(user_id)
            await update.message.reply_text("⌨️ Внизу всегда есть кнопка «🏠 Главное меню».", reply_markup=_main_reply_kb())
        await ref_try_credit(context, user_id)
    except Exception as e:
        logger.warning(f"[REF] start: {e}")
    if subscriptions.get(user_id) != "agreed" and not is_admin(user_id) and _get_setting(f"terms_{user_id}") == "agreed":
        subscriptions[user_id] = "agreed"     # правила принял раньше — после перезапуска помним
    if subscriptions.get(user_id) == "agreed":
        gate = admin_session_gate(user_id)
        if gate:
            await update.message.reply_text(gate, parse_mode="Markdown", reply_markup=_admin_session_kb())
            return
        await show_main_menu(update, user_id)
        return
    if subscriptions.get(user_id) is True:
        await show_terms(update, user_id)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ПЕРЕЙТИ В КАНАЛ", url="https://t.me/ponchinoscaamm")],
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
    if subscriptions.get(user_id) == "agreed":
        await show_main_menu(query, user_id)
    elif subscriptions.get(user_id) is True:
        await show_terms(query, user_id)
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПЕРЕЙТИ В КАНАЛ", url="https://t.me/ponchinoscaamm")],
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
        await _safe_delete(query.message)
        subscriptions[user_id] = True
        await ref_try_credit(context, user_id)
        await show_terms(query, user_id)
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url="https://t.me/ponchinoscaamm")],
            [btn("🔍 ПРОВЕРИТЬ СНОВА", "check_sub")],
            [btn("🔙 НАЗАД", "start")]
        ])
        await query.edit_message_text(
            "❌ *ВЫ НЕ ПОДПИСАНЫ!*\n\n"
            "Для использования бота необходимо подписаться на наш канал:\n\n"
            "📢 [Best PONCHI Shop](https://t.me/ponchinoscaamm)\n\n"
            "👇 Нажмите на кнопку, чтобы подписаться,\n"
            "затем нажмите «ПРОВЕРИТЬ СНОВА».",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def agree_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Спасибо!")
    user_id = query.from_user.id
    await _safe_delete(query.message)
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
    rows = _main_menu_rows(user_id)
    text = _MAIN_MENU_TEXT
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
         btn("Отклонить", f"{CALLBACK_REJECT}:{user.id}")],
        [btn("💬 Ответить", f"reply_offer:{user.id}")]
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
    await query.edit_message_text(query.message.text + "\n\n✅ Предложение принято!",
                                  reply_markup=InlineKeyboardMarkup([[btn("💬 Ответить", f"reply_offer:{user_id}")]]))
    await context.bot.send_message(chat_id=user_id, text="✅ Ваше предложение было принято администратором!")
    return ConversationHandler.END

async def reject_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, user_id = query.data.split(":")
    user_id = int(user_id)
    await query.edit_message_text(query.message.text + "\n\n❌ Предложение отклонено!",
                                  reply_markup=InlineKeyboardMarkup([[btn("💬 Ответить", f"reply_offer:{user_id}")]]))
    await context.bot.send_message(chat_id=user_id, text="❌ Ваше предложение было отклонено администратором.")
    return ConversationHandler.END

async def reply_offer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["offer_reply_to"] = int(query.data.split(":")[1])
    await query.message.reply_text("✍️ Введите текст ответа автору заявки:",
                                   reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "offer_reply_cancel")]]))
    return OFFER_REPLY


async def reply_offer_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    target = context.user_data.pop("offer_reply_to", None)
    if not target:
        await update.message.reply_text("❌ Заявка потеряна. Нажмите «Ответить» ещё раз.")
        return ConversationHandler.END
    try:
        await context.bot.send_message(chat_id=target, text=f"💬 Ответ администратора на ваше предложение:\n\n{update.message.text}")
        await update.message.reply_text("✅ Ответ отправлен")
        logger.info(f"[OFFER] админ {update.effective_user.id} ответил на заявку пользователя {target}")
    except Exception as e:
        logger.error(f"[OFFER] не удалось отправить ответ {target}: {e}")
        await update.message.reply_text(f"❌ Не удалось отправить ответ: {str(e)[:120]}")
    return ConversationHandler.END


async def reply_offer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Отменено")
    context.user_data.pop("offer_reply_to", None)
    try:
        await query.edit_message_text("Отменено.")
    except Exception:
        pass
    return ConversationHandler.END


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🆘 ПОДДЕРЖКА\n\n👤 @ponghs\n👤 @PyM0nk",
        reply_markup=back("start")
    )

INSTRUCTION_TEXT = (
    "📖 *КАК КУПИТЬ И АКТИВИРОВАТЬ НОМЕР*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "1️⃣ *КУПИТЕ НОМЕР*\n"
    "Откройте 🛒 «МАГАЗИН» → выберите страну → выберите номер → оплатите "
    "подарками, ₽ или монетами. После оплаты бот пришлёт вам *полный номер телефона*.\n\n"

    "2️⃣ *ВВЕДИТЕ НОМЕР В TELEGRAM*\n"
    "Зайдите в Telegram → «Настройки» → «Изменить номер телефона» "
    "(или зарегистрируйте новый аккаунт) → введите купленный номер.\n\n"

    "3️⃣ *ПОЛУЧИТЕ КОД В БОТЕ*\n"
    "Вернитесь в бот → «📦 МОИ ПОКУПКИ» → выберите номер → нажмите "
    "🔑 «ПОЛУЧИТЬ КОД». Бот пришлёт код из чата Telegram.\n\n"

    "4️⃣ *ВВЕДИТЕ КОД В TELEGRAM*\n"
    "Скопируйте код и введите его в Telegram. Готово — вы в аккаунте!\n\n"

    "5️⃣ *ОБЯЗАТЕЛЬНО ЗАЩИТИТЕ АККАУНТ*\n"
    "⚠️ Сразу после входа сделайте это, иначе аккаунт могут угнать:\n\n"

    "🔐 *ДВУХФАКТОРНАЯ АУТЕНТИФИКАЦИЯ (2FA)*\n"
    "Настройки → Конфиденциальность → Облачный пароль → "
    "включите и придумайте пароль (запишите его в надёжном месте!).\n\n"

    "📧 *ПОЧТА ДЛЯ ВОССТАНОВЛЕНИЯ*\n"
    "При включении облачного пароля Telegram предложит указать почту — "
    "привяжите *свою* почту, не чужую.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "❗ *ВАЖНО*\n"
    "• Смените пароль 2FA на свой сразу после первого входа\n"
    "• Не передавайте код никому, даже «поддержке»\n"
    "• Замена номера — только если код *не подошёл*\n\n"
    "🆘 *Возникли вопросы?* Нажмите «ПОДДЕРЖКА» в главном меню — поможем."
)


async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экран «📖 Инструкция» — как купить и активировать номер."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        INSTRUCTION_TEXT,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🛡 КАК СНЯТЬ СПАМ-БЛОК", "spam_help")],
            [btn("🛒 В МАГАЗИН", "shop")],
            [btn("🔙 НАЗАД", "start")],
        ])
    )


async def spam_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инструкция для покупателей: как снять спам-блок через @SpamBot."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🛡 *КАК СНЯТЬ СПАМ-БЛОК*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Откройте в Telegram бота @SpamBot и нажмите *Start* (или отправьте `/start`).\n\n"
        "2️⃣ Бот сообщит, есть ли на аккаунте ограничения. Если они есть, выберите пункт о том, "
        "что ограничение наложено *по ошибке* (на английском — про mistake).\n\n"
        "3️⃣ Бот попросит описать ситуацию. Отправьте ему сообщение ниже "
        "*на английском* — нажмите на текст, чтобы скопировать:\n\n"
        f"```\n{SPAM_APPEAL_TEXT}\n```\n"
        "4️⃣ Дождитесь ответа. Решение принимает Telegram, сроки он не называет: "
        "иногда ответ приходит быстро, иногда нужно подождать. Позже снова отправьте `/start` "
        "в @SpamBot, чтобы проверить статус.\n\n"
        "❗ *Важно*\n"
        "• Не подавайте апелляцию много раз подряд — достаточно одной\n"
        "• Пока ограничение действует, не пишите незнакомым людям и не рассылайте сообщения\n"
        "• Компенсации за спам-блок не выдаются (см. правила)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔙 К ИНСТРУКЦИИ", "instruction")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")],
        ]))


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("start"))
        return

    gate = admin_session_gate(user_id)
    if gate:
        await query.edit_message_text(gate, parse_mode="Markdown", reply_markup=_admin_session_kb())
        return

    # частые действия — сетка 2 в ряд
    row1 = [btn("🛒 КУПИТЬ (LZT)", "lzt_buy_menu")]
    if is_super_admin(user_id):
        row1.append(btn("🤖 АВТОЗАКУП", "menu"))
    rows = [
        row1,
        [btn("📱 ДОБАВИТЬ НОМЕР", "add_phone"), btn("✏️ ЦЕНЫ", "edit_price")],
        [btn("🎁 КОМПЕНСАЦИЯ", "compensate"), btn("⚙️ НАСТРОЙКИ", "admin_settings")],
        [btn("📵 УДАЛЁННЫЙ НОМЕР", "removed_num")],
        [btn("📜 ИСТОРИЯ", "hist_menu"), btn("👤 МОЙ АККАУНТ", "admacc")],
        [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")],
    ]
    role = "👑 ГЛАВНЫЙ АДМИН" if is_super_admin(user_id) else "🛠️ МОДЕРАТОР"
    sess = admin_get_linked(user_id) or {}
    await query.edit_message_text(
        f"👥 *АДМИН-ПАНЕЛЬ*\n\nВаша роль: {role}\n"
        f"🔐 Аккаунт (сессия): `{fmt_phone(sess.get('phone') or '—')}`\n"
        f"Выберите действие:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))


async def admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вложенное меню редких настроек. Доступ к пунктам — как и раньше в админ-панели."""
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Нет доступа!", show_alert=True)
        return
    await query.answer()

    rows = [[btn("🔑 LZT ТОКЕН", "change_lzt_token")]]           # было доступно всем админам
    if is_super_admin(user_id):
        rows[0].append(btn("🗑 УДАЛИТЬ НОМЕР", "delete_phone"))
        rows.append([btn("➕ ДОБАВИТЬ АДМИНА", "add_admin"), btn("🗑 УДАЛИТЬ АДМИНА", "remove_admin")])
        rows.append([btn("📊 СПИСОК АДМИНОВ", "list_admins")])
    elif has_numbers_access(user_id):
        rows.append([btn("📱 ПОЛУЧИТЬ НОМЕРА", "get_numbers")])
    rows.append([btn("🏠 ГЛАВНОЕ МЕНЮ", "start"), btn("⬅️ НАЗАД", "admin_panel")])

    await query.edit_message_text("⚙️ *НАСТРОЙКИ И УПРАВЛЕНИЕ*\n\nЗдесь редкие функции бота.",
                                  parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

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

def _admins_panel_markup():
    rows = []
    for mod_id in MODERATORS:
        has = has_numbers_access(mod_id)
        rows.append([btn(f"👤 {mod_id}" + (" 📱" if has else ""), "adm_noop")])
        rows.append([btn("🚫 Отозвать доступ к номерам" if has else "✅ Разрешить доступ к получению номеров",
                         f"adm_num_{mod_id}"),
                     btn("🗑 Удалить", f"adm_del_{mod_id}")])
    rows.append([btn("🔙 НАЗАД", "admin_panel")])
    return InlineKeyboardMarkup(rows)


def _admins_panel_text() -> str:
    text = "📊 *СПИСОК*\n\n👑 Главный: `{}`\n".format(ADMINS[0])
    text += ("\n🛠️ Админы (📱 — есть доступ к получению номеров):" if MODERATORS else "\n🛠️ Админов нет")
    return text


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        await query.edit_message_text("❌ Только главный админ!", reply_markup=back("admin_panel"))
        return
    await query.edit_message_text(_admins_panel_text(), parse_mode="Markdown", reply_markup=_admins_panel_markup())


async def admin_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


async def admin_numbers_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_super_admin(query.from_user.id):
        await query.answer("⛔ Только владелец", show_alert=True)
        return
    target = int(query.data.split("_")[2])
    if target not in MODERATORS:
        await query.answer("Админ не найден", show_alert=True)
        return
    allow = not has_numbers_access(target)
    set_numbers_access(target, allow)
    logger.info(f"[ADMIN] владелец {query.from_user.id}: доступ к номерам для {target} → {allow}")
    await query.answer("✅ Доступ выдан" if allow else "Доступ отозван")
    try:
        await query.edit_message_text(_admins_panel_text(), parse_mode="Markdown", reply_markup=_admins_panel_markup())
    except BadRequest:
        pass


async def admin_delete_full(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_super_admin(query.from_user.id):
        await query.answer("⛔ Только владелец", show_alert=True)
        return
    target = int(query.data.split("_")[2])
    if target == ADMINS[0]:
        await query.answer("Нельзя удалить владельца", show_alert=True)
        return
    if target in MODERATORS:
        delete_admin_from_db(target)
        MODERATORS.remove(target)
        if target in ALL_ADMINS:
            ALL_ADMINS.remove(target)
        set_numbers_access(target, False)
        logger.info(f"[ADMIN] владелец {query.from_user.id} удалил админа {target} полностью")
        await query.answer("🗑 Админ удалён")
    else:
        await query.answer("Админ не найден", show_alert=True)
    try:
        await query.edit_message_text(_admins_panel_text(), parse_mode="Markdown", reply_markup=_admins_panel_markup())
    except BadRequest:
        pass


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

def find_removed_number(phone_raw):
    """Ищет сохранённую сессию/привязку для номера, которого уже нет в магазине:
    покупки, товары магазина, база автозакупа. -> dict или None."""
    want = _digits(phone_raw)
    if len(want) < 7:
        return None
    cands = []
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            for ph, pr, ps, ses, lc, lid, tfa in conn.execute(
                    "SELECT phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa "
                    "FROM purchases ORDER BY id DESC").fetchall():
                if _digits(ph) == want:
                    cands.append(dict(session=ses or "", lzt_item_id=lid, two_fa=tfa or "", login_code=lc or "",
                                      price_rub=pr, price_stars=ps))
            for ph, pr, ps, ses, lc, lid, tfa in conn.execute(
                    "SELECT phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa "
                    "FROM phone_products ORDER BY id DESC").fetchall():
                if _digits(ph) == want:
                    cands.append(dict(session=ses or "", lzt_item_id=lid, two_fa=tfa or "", login_code=lc or "",
                                      price_rub=pr, price_stars=ps))
    except Exception as e:
        logger.error(f"[REMOVED] поиск в базе магазина: {e}")
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            for ph, ses, iid in conn.execute("SELECT phone, session, item_id FROM numbers").fetchall():
                if _digits(ph) == want:
                    cands.append(dict(session=ses or "", lzt_item_id=iid, two_fa="", login_code="",
                                      price_rub=None, price_stars=None))
    except Exception as e:
        logger.error(f"[REMOVED] поиск в базе автозакупа: {e}")
    for c in cands:
        if c["session"]:
            return c
    for c in cands:
        if c["lzt_item_id"]:
            return c
    return None


async def removed_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END
    await query.edit_message_text(
        "📵 *УДАЛЁННЫЙ НОМЕР*\n\n"
        "Выдам человеку номер, которого уже нет в магазине, с кнопкой «Получить код».\n\n"
        "📝 Введите *числовой ID* пользователя:",
        parse_mode="Markdown", reply_markup=back("admin_panel"))
    return REMOVED_USER


async def removed_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.isdigit():
        await update.message.reply_text("❌ ID — только цифры. Введите ещё раз:", reply_markup=back("admin_panel"))
        return REMOVED_USER
    context.user_data["removed_target"] = int(t)
    await update.message.reply_text(
        f"👤 Пользователь: `{t}`\n\n📱 Теперь введите *номер полностью*, начиная с +\n"
        f"(например `+13258053195`):",
        parse_mode="Markdown", reply_markup=back("admin_panel"))
    return REMOVED_PHONE


async def removed_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    target = context.user_data.get("removed_target")
    if not target:
        await update.message.reply_text("❌ ID пользователя потерялся, начните заново.", reply_markup=back("admin_panel"))
        return ConversationHandler.END
    raw = update.message.text.strip()
    phone = normalize_phone(raw)
    if len(_digits(phone)) < 7:
        await update.message.reply_text("❌ Не похоже на номер. Введите полностью, например `+13258053195`:",
                                        parse_mode="Markdown", reply_markup=back("admin_panel"))
        return REMOVED_PHONE
    found = find_removed_number(phone)
    if not found:
        await update.message.reply_text(
            f"❌ Для номера `{phone}` нигде нет ни сессии, ни привязки к Market.\n"
            f"Проверьте номер или введите другой:",
            parse_mode="Markdown", reply_markup=back("admin_panel"))
        return REMOVED_PHONE

    session = found["session"]
    lzt_item_id = None if session else found["lzt_item_id"]    # есть сессия — код читаем прямо с аккаунта
    try:
        price_rub, price_stars = (found["price_rub"], found["price_stars"])
        if price_rub is None or price_stars is None:
            price_rub, price_stars = bz_shop_price(phone)
        country_code = get_country_by_phone(phone)
        already = any(_digits(r[1]) == _digits(phone) for r in get_user_purchases(target))
        if not already:
            add_purchase(target, phone, price_rub, price_stars, session, found["login_code"],
                         found["lzt_item_id"], found["two_fa"], country_code, review=False)
        awaiting_phone_confirmation[target] = {
            'phone': phone, 'product_id': None, 'session': session,
            'lzt_item_id': lzt_item_id, 'two_fa': found["two_fa"],
        }
        country = get_country_by_code(country_code) if country_code else None
        flag = country['flag'] if country else "🌍"
        name = country['name'] if country else "Неизвестно"
        await context.bot.send_message(
            chat_id=target,
            text=(
                f"📱 *ВАШ НОМЕР*\n\n"
                f"🌍 *Страна:* {flag} {name}\n"
                f"📞 *Номер:* `{phone}`\n\n"
                f"---\n"
                f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
                f"1️⃣ Смените номер телефона на свой\n"
                f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
                f"3️⃣ Установите облачный пароль\n"
                f"4️⃣ Привяжите почту для восстановления\n\n"
                f"🔑 Нажмите кнопку, чтобы получить код для входа:"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
                [btn("📖 ИНСТРУКЦИЯ", "instruction")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]]))
        await update.message.reply_text(
            f"✅ *ГОТОВО*\n\n👤 Пользователь: `{target}`\n📱 Номер: `{phone}`\n"
            + ("📦 Номер уже был в его покупках.\n" if already else "📦 Добавлен в «Мои покупки».\n")
            + "🔑 Человеку отправлена кнопка «Получить код».",
            parse_mode="Markdown", reply_markup=back("admin_panel"))
        logger.info(f"[REMOVED] админ {update.effective_user.id} выдал {phone} пользователю {target}")
    except Exception as e:
        logger.error(f"[REMOVED] не удалось выдать {phone} пользователю {target}: {e}")
        awaiting_phone_confirmation.pop(target, None)
        await update.message.reply_text(
            f"❌ Не удалось отправить номер пользователю `{target}`: {str(e)[:150]}\n"
            f"Возможно, он не запускал бота или заблокировал его.",
            parse_mode="Markdown", reply_markup=back("admin_panel"))
    context.user_data.pop("removed_target", None)
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

    context.user_data['compensate_target_user_id'] = target_user_id

    products = get_phone_products()
    if not products:
        await update.message.reply_text(
            "❌ *В МАГАЗИНЕ НЕТ НОМЕРОВ ДЛЯ ВОЗМЕЩЕНИЯ!*",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )
        return ConversationHandler.END

    rows = []
    for pid, phone, price_rub, price_stars, login_code, lzt_item_id in products:
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code)
        flag = country['flag'] if country else "🌍"
        rows.append([btn(f"{flag} {phone} ({price_stars}⭐ / {price_rub}₽)", f"comp_select_{pid}")])
    rows.append([btn("🔙 ОТМЕНА", "admin_panel")])

    await update.message.reply_text(
        f"🎁 *ВЫБЕРИТЕ НОМЕР ДЛЯ ВОЗМЕЩЕНИЯ*\n\n"
        f"Пользователь: `{target_user_id}`\n\n"
        f"Доступно номеров: {len(products)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return COMPENSATE_SELECT

async def compensate_select_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Нет доступа!", reply_markup=back("admin_panel"))
        return ConversationHandler.END

    product_id = int(query.data.replace("comp_select_", ""))
    target_user_id = context.user_data.get('compensate_target_user_id')
    if not target_user_id:
        await query.edit_message_text("❌ Ошибка: ID пользователя не найден. Попробуйте сначала.",
                                      reply_markup=back("admin_panel"))
        return ConversationHandler.END

    full_product = get_phone_product(product_id)
    if not full_product:
        await query.edit_message_text("❌ Этот номер уже был выдан или удалён.",
                                      reply_markup=back("admin_panel"))
        return ConversationHandler.END

    _, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa = full_product

    delete_phone_product(product_id)

    country_code = get_country_by_phone(phone)
    add_purchase(target_user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, review=False)

    awaiting_phone_confirmation[target_user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session,
        'lzt_item_id': lzt_item_id,
        'two_fa': two_fa
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
                [btn("📖 ИНСТРУКЦИЯ", "instruction")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
        )
        await query.edit_message_text(
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
        await query.edit_message_text(
            f"❌ *НЕ УДАЛОСЬ ОТПРАВИТЬ АККАУНТ*\n\n"
            f"Пользователь `{target_user_id}` не найден или бот заблокирован.\n\n"
            f"Номер `{phone}` удалён из магазина.",
            parse_mode="Markdown",
            reply_markup=back("admin_panel")
        )

    if 'compensate_target_user_id' in context.user_data:
        del context.user_data['compensate_target_user_id']

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

CODE_HINT_TEXT = ("📲 Введи код из Telegram/SMS *через пробелы*, например `1 2 3 4 5`.\n"
                  "⚠️ Слитно (12345) Telegram аннулирует код и скажет «неверный».")


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
        await update.message.reply_text(CODE_HINT_TEXT, parse_mode="Markdown")
        return ENTER_CODE
    else:
        await update.message.reply_text(msg)
        return PHONE_NUMBER

async def add_phone_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_code = update.message.text.strip()
    user_id = update.effective_user.id
    code = re.sub(r"\D", "", raw_code)
    if len(code) not in (5, 6):
        await update.message.reply_text("❌ Код из 5 цифр. Отправь через пробелы: `1 2 3 4 5`", parse_mode="Markdown")
        return ENTER_CODE
    context.user_data["add_code_joined"] = raw_code.isdigit()
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

        await add_phone_to_shop_now(phone, price_rub, price_stars, session_string, "", None, "", user_id, context, client=client)

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
        low = (msg or "").lower()
        if any(x in low for x in ("phone code", "confirmation code", "code has expired", "code is invalid")):
            phone = context.user_data.get('adding_phone')
            ok_new, _ = await send_code_to_phone(phone, user_id) if phone else (False, "")
            why = ("Telegram аннулирует код, если он отправлен слитно (его видит в чате). "
                   if context.user_data.get("add_code_joined") else
                   "Код неверный или уже устарел. ")
            tail = ("Я запросил НОВЫЙ код — возьми самый свежий.\n\n" + CODE_HINT_TEXT) if ok_new else \
                   "Не удалось запросить новый код, начни добавление заново."
            await update.message.reply_text("❌ " + why + tail, parse_mode="Markdown")
            return ENTER_CODE if ok_new else ConversationHandler.END
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

        await add_phone_to_shop_now(phone, price_rub, price_stars, session_string, "", None, password, user_id, context, client=client)

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
    for pid, phone, price_rub, price_stars, login_code, lzt_item_id in products:
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
    for pid, phone, price_rub, price_stars, login_code, lzt_item_id in products:
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
    _, phone, price_rub, price_stars, _, _, _, _ = product
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code)
    flag = country['flag'] if country else "🌍"
    await query.edit_message_text(
        f"⚠️ УДАЛИТЬ?\n\n📱 {flag} {phone}",
        reply_markup=InlineKeyboardMarkup([
            [btn("✅ ДА", f"del_yes_{product_id}")],
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
    for pid, phone, price_rub, price_stars, login_code, lzt_item_id in products:
        country_code = get_country_by_phone(phone)
        if country_code not in countries_data:
            countries_data[country_code] = []
        countries_data[country_code].append((pid, phone, price_rub, price_stars, login_code, lzt_item_id))
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
    for pid, phone, price_rub, price_stars, login_code, lzt_item_id in products:
        if phone.startswith(country['phone_code']):
            country_phones.append((pid, phone, price_rub, price_stars, login_code, lzt_item_id))
    if not country_phones:
        await query.edit_message_text(f"❌ Нет номеров для {country['flag']} {country['name']}",
                                      reply_markup=back("shop"))
        return
    country_phones.sort(key=lambda x: x[2])
    rows = []
    for idx, (pid, phone, price_rub, price_stars, login_code, lzt_item_id) in enumerate(country_phones, 1):
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
    _, phone, price_rub, price_stars, _, _, _, _ = product
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    hidden_phone = phone
    buttons = []
    if price_rub > 0:
        buttons.append([btn(f"💳 Оплатить {price_rub} ₽" + (" (ЛС, 8:30–21:00)" if RUB_VIA_DM else ""),
                            f"pay_rub_{product_id}")])
    buttons.append([btn(f"🪙 Купить за {COIN_PRICE} монет", f"pay_coins_{product_id}")])
    if _GIFT_ACTIONS:
        buttons.append([btn(f"🎁 Оплатить подарками ({gift_price_of(price_stars)}⭐)", f"pay_gift_{product_id}")])
    from urllib.parse import quote
    _uid = query.from_user.id
    _msg = (f"Здравствуйте! Хочу купить номер {hidden_phone}. Цена: {price_rub:g} ₽ / {price_stars}⭐. "
            f"Мой ID: {_uid}, ID товара: {product_id}")
    buttons.append([InlineKeyboardButton(f"✉️ Отправить {RUB_CONTACT}",
                                         url=f"https://t.me/{RUB_CONTACT.lstrip('@')}?text={quote(_msg)}")])
    buttons.append([InlineKeyboardButton("💬 Открыть чат", url=f"https://t.me/{RUB_CONTACT.lstrip('@')}"),
                    btn("📨 Отправить заявку на покупку", f"buyreq_{product_id}")])
    buttons.append([btn("🔙 НАЗАД", "shop")])
    await query.edit_message_text(
        f"💳 *ОПЛАТА*\n\n🌍 *Страна:* {flag} {name} ({code})\n📱 *Номер:* `{hidden_phone}`\n🎁 *Цена подарками:* {gift_price_of(price_stars)}⭐\n💰 *Цена:* {price_rub} ₽\n🪙 *Цена:* {COIN_PRICE} монет (у вас: {coins_get(query.from_user.id)})\n\n⚠️ После оплаты вы получите полный номер и код для входа.",
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
        pid, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, purchased_at = purchase
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
        "SELECT phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, purchased_at FROM purchases WHERE id=?",
        (purchase_id,)
    ).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code, purchased_at = row
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
            [btn("📖 КАК АКТИВИРОВАТЬ", "instruction")],
            [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
        ])
    )

async def purchase_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    purchase_id = int(query.data.replace("purchase_get_code_", ""))
    conn = sqlite3.connect(DB_NAME, timeout=10)
    row = conn.execute("SELECT phone, session, lzt_item_id FROM purchases WHERE id=?", (purchase_id,)).fetchone()
    conn.close()
    if not row:
        await query.edit_message_text("❌ Покупка не найдена", reply_markup=back("my_purchases"))
        return
    phone, session, lzt_item_id = row

    if not await review_gate_check(query, context, f"p:{phone}", f"purchase_get_code_{purchase_id}"):
        return

    if not lzt_item_id:
        if not session:
            await query.edit_message_text(
                f"⚠️ *НЕВОЗМОЖНО ПОЛУЧИТЬ КОД*\n\n"
                f"📞 Номер: `{phone}`\n\n"
                f"❌ Для этого номера нет сессии и нет привязки к LZT Market.\n"
                f"Пожалуйста, обратитесь в поддержку.",
                parse_mode="Markdown",
                reply_markup=back("my_purchases"),
            )
            return

        await query.edit_message_text(
            f"⏳ *ПОДКЛЮЧАЮСЬ К АККАУНТУ ЧЕРЕЗ TELEGRAM...*\n\n"
            f"📞 Номер: `{phone}`\n"
            f"Пожалуйста, подождите...",
            parse_mode="Markdown"
        )

        try:
            code_found, result = await get_last_code_from_account(phone, session)
            if code_found:
                await query.edit_message_text(
                    f"🔑 *КОД НАЙДЕН ЧЕРЕЗ TELEGRAM!*\n\n"
                    f"📞 Номер: `{phone}`\n"
                    f"🔑 Код: `{code_found}`\n\n"
                    + (f"⚠️ Это старый код (пришёл {result[4:]}). Если не подошёл — введи номер в Telegram и нажми «Новый код».\n\n"
                       if str(result).startswith("OLD:") else "")
                    + f"✅ Код подошёл для входа?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                        [btn("🔄 НОВЫЙ КОД", f"purchase_get_code_{purchase_id}")],
                        [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                    ])
                )
            else:
                await query.edit_message_text(
                    f"⚠️ *КОД НЕ НАЙДЕН*\n\n"
                    f"📞 Номер: `{phone}`\n\n"
                    f"❌ {result}\n\n"
                    f"Попробуйте повторить поиск.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [btn("🔄 ПОВТОРИТЬ", f"purchase_get_code_{purchase_id}")],
                        [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                    ])
                )
        except Exception as e:
            logger.error(f"❌ Ошибка получения кода через Telethon: {e}")
            await query.edit_message_text(
                f"❌ *ОШИБКА ПРИ ПОЛУЧЕНИИ КОДА*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"```\n{str(e)[:200]}\n```\n\n"
                f"Попробуйте ещё раз.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🔄 ПОВТОРИТЬ", f"purchase_get_code_{purchase_id}")],
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
            )
        return

    if session:
        try:
            fresh_code = await read_fresh_code_only(session)
        except Exception:
            fresh_code = None
        if fresh_code:
            await query.edit_message_text(
                f"🔑 *КОД НАЙДЕН!*\n\n📞 Номер: `{phone}`\n🔑 Код: `{fresh_code}`\n\n"
                f"✅ Код подошёл для входа?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                    [btn("🔄 НОВЫЙ КОД", f"purchase_get_code_{purchase_id}")],
                    [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                ])
            )
            return

    await query.edit_message_text(
        f"⏳ *ЗАПРАШИВАЮ КОД ЧЕРЕЗ API...*\n\n"
        f"📞 Номер: `{phone}`\n"
        f"Пожалуйста, подождите...",
        parse_mode="Markdown"
    )

    try:
        token = get_lzt_token()
        market = _lzt_market_cls(token=token)
        if LZT_PROXY:
            market.settings.proxy = LZT_PROXY

        def _get_code():
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            return _lzt_fetch_verification_code(market, lzt_item_id)

        lzt_code = await asyncio.get_running_loop().run_in_executor(None, _get_code)

        if lzt_code:
            await query.edit_message_text(
                f"🔑 *КОД ПОЛУЧЕН ЧЕРЕЗ API!*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"🔑 Код: `{lzt_code}`\n\n"
                f"✅ Код подошёл для входа?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [btn("✅ КОД ПОДОШЁЛ", f"purchase_ok_{purchase_id}")],
                    [btn("🔄 НОВЫЙ КОД", f"purchase_get_code_{purchase_id}")],
                    [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                ])
            )
        else:
            await query.edit_message_text(
                f"⚠️ *КОД НЕ ПОЛУЧЕН*\n\n"
                f"📞 Номер: `{phone}`\n\n"
                + _code_fail_text(),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [btn("🔄 ПОВТОРИТЬ", f"purchase_get_code_{purchase_id}")],
                    [btn("🔙 К МОИМ ПОКУПКАМ", "my_purchases")]
                ])
            )
    except Exception as e:
        logger.error(f"❌ Ошибка получения кода через LZT: {e}")
        await query.edit_message_text(
            f"❌ *ОШИБКА ПРИ ПОЛУЧЕНИИ КОДА*\n\n"
            f"📞 Номер: `{phone}`\n"
            f"```\n{str(e)[:200]}\n```\n\n"
            f"Попробуйте ещё раз.",
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
    # Оплата Stars напрямую боту отключена — только подарками
    query = update.callback_query
    await query.answer("⭐ Оплата Stars отключена. Оплатите подарками 🎁", show_alert=True)

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=False, error_message="Оплата Stars отключена. Оплатите подарками.")

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    parts = payload.split("_")
    product_id = int(parts[1])
    user_id = update.effective_user.id

    product = get_phone_product(product_id)
    if not product:
        await update.message.reply_text("❌ Номер не найден")
        return

    _, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa = product
    delete_phone_product(product_id)

    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code)

    awaiting_phone_confirmation[user_id] = {
        "phone": phone,
        "product_id": product_id,
        "session": session,
        "lzt_item_id": lzt_item_id,
        "two_fa": two_fa
    }

    username = update.effective_user.username if update.effective_user else None
    await send_stars_notification_to_telegram(context, user_id, username, phone, price_stars, price_rub,
                                              product_id)

    await update.message.reply_text(
        generate_product_message(phone, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("📖 ИНСТРУКЦИЯ", "instruction")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

# ═══════════ ОПЛАТА РУБЛЯМИ ЧЕРЕЗ ЛС ═══════════
RUB_VIA_DM = True                       # True: рубли принимаются в личке, False: старая оплата через ЮMoney
RUB_CONTACT = "@ponghs"                 # кому писать
RUB_OPEN_MIN = 8 * 60 + 30              # приём с 08:30
RUB_CLOSE_MIN = 21 * 60                 # до 21:00
RUB_TZ = timezone(timedelta(hours=3))   # МСК


def rub_dm_open(now=None) -> bool:
    now = now or datetime.now(RUB_TZ)
    t = now.hour * 60 + now.minute
    return RUB_OPEN_MIN <= t < RUB_CLOSE_MIN


_BUYREQ_LAST = {}


async def buy_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупатель нажал «Отправить заявку на покупку»: заявка уходит админам."""
    query = update.callback_query
    product_id = int(query.data.split("_")[1])
    product = get_phone_product(product_id)
    if not product:
        await query.answer("Номер больше не доступен", show_alert=True)
        return
    user = query.from_user
    key = (user.id, product_id)
    if time.time() - _BUYREQ_LAST.get(key, 0) < 300:
        await query.answer("Заявка уже отправлена, ожидайте ответ", show_alert=True)
        return
    _BUYREQ_LAST[key] = time.time()
    await query.answer()
    _, phone, price_rub, price_stars, _, _, _, _ = product
    uname = f"@{user.username}" if user.username else "нет username"
    await notify_admins(
        context.bot,
        f"📨 ЗАЯВКА НА ПОКУПКУ\n\n👤 {user.full_name} ({uname})\n🆔 ID: {user.id}\n"
        f"📱 Номер: {phone}\n💰 Цена: {price_rub:g} ₽ / {gift_price_of(price_stars)}⭐\n🔢 Товар: {product_id}")
    await query.edit_message_text(
        "📨 *ЗАЯВКА ОТПРАВЛЕНА*\n\n"
        f"📱 Номер: `{phone}`\n\n"
        f"⏳ Ваша заявка рассматривается, ожидайте ответ в течение 5 минут либо напишите {RUB_CONTACT}.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Открыть чат", url=f"https://t.me/{RUB_CONTACT.lstrip('@')}")],
            [btn("🔙 НАЗАД", f"select_phone_{product_id}")]]))


async def pay_rub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    product = get_phone_product(product_id)

    if not product:
        await query.edit_message_text("❌ Номер больше не доступен!")
        return

    _, phone, price_rub, price_stars, _, _, _, _ = product
    user_id = query.from_user.id

    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    country_flag = country['flag'] if country else "🌍"
    country_name = country['name'] if country else "Неизвестно"
    phone_code = country['phone_code'] if country else ""

    hidden_phone = phone

    if RUB_VIA_DM:
        from urllib.parse import quote
        pending_rub.pop(user_id, None)
        head = (f"💳 *ОПЛАТА РУБЛЯМИ*\n\n🌍 *Страна:* {country_flag} {country_name} ({phone_code})\n"
                f"📱 *Номер:* `{hidden_phone}`\n💰 *Сумма:* {price_rub} ₽\n\n")
        if rub_dm_open():
            msg_text = (f"Здравствуйте! Хочу оплатить номер {hidden_phone} ({price_rub} ₽). "
                        f"Мой ID: {user_id}, ID товара: {product_id}")
            link = f"https://t.me/{RUB_CONTACT.lstrip('@')}?text={quote(msg_text)}"
            await query.edit_message_text(
                head + f"📩 Оплата рублями принимается *в личных сообщениях* с 8:30 до 21:00 (МСК).\n"
                       f"Напишите {RUB_CONTACT} — отвечаю сразу. После оплаты номер выдам вручную.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"✉️ НАПИСАТЬ {RUB_CONTACT}", url=link)],
                    [btn("🔙 НАЗАД", f"select_phone_{product_id}")],
                ]))
        else:
            await query.edit_message_text(
                head + f"⏰ Сейчас оплата рублями не принимается.\n"
                       f"Рубли принимаются *в личных сообщениях {RUB_CONTACT} с 8:30 до 21:00 (МСК)*.\n\n"
                       f"Пока можно оплатить монетами или подарками.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", f"select_phone_{product_id}")]]))
        return

    label = f"rub_{product_id}_{user_id}_{int(time.time())}"

    pending_rub[user_id] = {
        'product_id': product_id,
        'phone': phone,
        'label': label,
        'message_id': query.message.message_id,
        'chat_id': query.message.chat_id
    }

    wallet = get_yoomoney_wallet()
    if not wallet:
        pending_rub.pop(user_id, None)
        logger.error("❌ Не задан кошелёк ЮMoney (команда /wallet НОМЕР)")
        await query.edit_message_text(
            "⚠️ Оплата рублями сейчас недоступна. Попробуйте оплату звёздами или напишите в поддержку.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 НАЗАД", "shop")]]))
        for admin_id in ADMINS:
            try:
                await context.bot.send_message(
                    admin_id, "⚠️ Покупатель пытался оплатить рублями, но не задан кошелёк ЮMoney.\n"
                              "Отправь боту: /wallet НОМЕР_КОШЕЛЬКА (например /wallet 4100123456789012)")
            except Exception:
                pass
        return
    payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={wallet}&quickpay-form=small&sum={price_rub}&label={label}"

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

    _, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa = product

    delete_phone_product(product_id)
    country_code = get_country_by_phone(phone)
    add_purchase(user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code)

    awaiting_phone_confirmation[user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session,
        'lzt_item_id': lzt_item_id,
        'two_fa': two_fa
    }

    del pending_rub[user_id]

    try:
        username = query.from_user.username if query.from_user else None
        await send_rub_notification_to_telegram(context, user_id, username, phone, price_rub, price_stars, product_id)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления о покупке: {e}")

    await query.edit_message_text(
        generate_product_message(phone, price_rub, price_stars),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
            [btn("📖 ИНСТРУКЦИЯ", "instruction")],
            [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
        ])
    )

async def _edit_or_send(query, text, **kw):
    """Правит сообщение; если не вышло (сеть, сообщение устарело) — присылает новым, чтобы код точно дошёл."""
    try:
        await query.edit_message_text(text, **kw)
        return
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        logger.warning(f"[CODE] edit не удался ({type(e).__name__}: {e}), отправляю новым сообщением")
    for attempt in range(3):
        try:
            await query.get_bot().send_message(chat_id=query.from_user.id, text=text, **kw)
            logger.info(f"[CODE] сообщение отправлено пользователю {query.from_user.id} новым сообщением")
            return
        except Exception as e2:
            logger.error(f"[CODE] send_message попытка {attempt + 1}/3: {type(e2).__name__}: {e2}")
            await asyncio.sleep(2)


async def get_code_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔴🔴🔴 get_code_button ВЫЗВАНА! 🔴🔴🔴")
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in awaiting_phone_confirmation:
        logger.error(f"❌ НЕТ ДАННЫХ ДЛЯ {user_id}")
        await _edit_or_send(query, "❌ Нет номеров для получения кода! Оплатите номер сначала.")
        return

    data = awaiting_phone_confirmation[user_id]
    phone = data['phone']
    lzt_item_id = data.get('lzt_item_id')
    session = data.get('session', '')

    if not await review_gate_check(query, context, f"p:{phone}", "get_code"):
        return

    if not lzt_item_id:
        if not session:
            await _edit_or_send(query,
                f"⚠️ *НЕВОЗМОЖНО ПОЛУЧИТЬ КОД*\n\n"
                f"📞 Номер: `{phone}`\n\n"
                f"❌ Для этого номера нет сессии и нет привязки к Market.\n"
                f"Пожалуйста, обратитесь в поддержку.",
                parse_mode="Markdown"
            )
            return

        await _edit_or_send(query,
            f"⏳ *ПОДКЛЮЧАЮСЬ К АККАУНТУ ЧЕРЕЗ TELEGRAM...*\n\n"
            f"📞 Номер: `{phone}`\n"
            f"Пожалуйста, подождите...",
            parse_mode="Markdown"
        )

        try:
            code_found, result = await get_last_code_from_account(phone, session)
            if code_found:
                keyboard = InlineKeyboardMarkup([
                    [btn("✅ КОД ПОДОШЁЛ", "code_ok")],
                    [btn("🔄 НОВЫЙ КОД", "get_code")],
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
                await _edit_or_send(query,
                    f"🔑 *КОД НАЙДЕН ЧЕРЕЗ TELEGRAM!*\n\n"
                    f"📞 Номер: `{phone}`\n"
                    f"🔑 Код: `{code_found}`\n\n"
                    + (f"⚠️ Это старый код (пришёл {result[4:]}). Если не подошёл — введи номер в Telegram и нажми «Новый код».\n\n"
                       if str(result).startswith("OLD:") else "")
                    + f"✅ Код подошёл для входа?",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            else:
                keyboard = InlineKeyboardMarkup([
                    [btn("🔄 ПОВТОРИТЬ", "get_code")],
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
                await _edit_or_send(query,
                    f"⚠️ *КОД НЕ НАЙДЕН*\n\n"
                    f"📞 Номер: `{phone}`\n\n"
                    f"❌ {result}\n\n"
                    f"Попробуйте повторить поиск.",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        except Exception as e:
            logger.error(f"❌ Ошибка получения кода через Telethon: {e}")
            await _edit_or_send(query,
                f"❌ *ОШИБКА ПРИ ПОЛУЧЕНИИ КОДА*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"```\n{str(e)[:200]}\n```\n\n"
                f"Попробуйте ещё раз.",
                parse_mode="Markdown"
            )
        return

    if session:
        try:
            fresh_code = await read_fresh_code_only(session)
        except Exception:
            fresh_code = None
        if fresh_code:
            await _edit_or_send(query,
                f"🔑 *КОД НАЙДЕН!*\n\n📞 Номер: `{phone}`\n🔑 Код: `{fresh_code}`\n\n"
                f"✅ Код подошёл для входа?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [btn("✅ КОД ПОДОШЁЛ", "code_ok")],
                    [btn("🔄 НОВЫЙ КОД", "get_code")],
                    [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
                ])
            )
            return

    await _edit_or_send(query,
        f"⏳ *ЗАПРАШИВАЮ КОД ЧЕРЕЗ API...*\n\n"
        f"📞 Номер: `{phone}`\n"
        f"Пожалуйста, подождите...",
        parse_mode="Markdown"
    )

    try:
        token = get_lzt_token()
        market = _lzt_market_cls(token=token)
        if LZT_PROXY:
            market.settings.proxy = LZT_PROXY

        def _get_code():
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            return _lzt_fetch_verification_code(market, lzt_item_id)

        lzt_code = await asyncio.get_running_loop().run_in_executor(None, _get_code)

        if lzt_code:
            keyboard = InlineKeyboardMarkup([
                [btn("✅ КОД ПОДОШЁЛ", "code_ok")],
                [btn("🔄 НОВЫЙ КОД", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
            await _edit_or_send(query,
                f"🔑 *КОД ПОЛУЧЕН ЧЕРЕЗ API!*\n\n"
                f"📞 Номер: `{phone}`\n"
                f"🔑 Код: `{lzt_code}`\n\n"
                f"✅ Код подошёл для входа?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [btn("🔄 ПОВТОРИТЬ", "get_code")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
            await _edit_or_send(query,
                f"⚠️ *КОД НЕ ПОЛУЧЕН*\n\n"
                f"📞 Номер: `{phone}`\n\n"
                + _code_fail_text(),
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"❌ Ошибка получения кода через LZT: {e}")
        await _edit_or_send(query,
            f"❌ *ОШИБКА ПРИ ПОЛУЧЕНИИ КОДА*\n\n"
            f"📞 Номер: `{phone}`\n"
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

LZT_MAX_PRICE = 20
LZT_SPAM_FILTER = "no"
LZT_ALLOW_GEO_SPAMBLOCK = "false"   # галочка «Разрешить ГЕО спамблок» снята
LZT_EXCLUDE_COUNTRIES = {}
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

_LZT_CODE_LAST = {"status": None, "msg": ""}


def _code_fail_text() -> str:
    """Текст, когда код не найден."""
    return ("Бот не нашёл код, и причина этому:\n"
            "1. Вы не ввели номер и не запросили код\n"
            "2. Если не помогло, обратитесь в поддержку @ponghs или @PyM0nk")


def _lzt_fetch_verification_code(market, item_id: int) -> Optional[str]:
    endpoint = f"/{item_id}/telegram-login-code"
    _LZT_CODE_LAST.update(status=None, msg="")
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
            _LZT_CODE_LAST.update(status=resp.status_code, msg=resp.text[:300])
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
    phone = normalize_phone(phone)
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

        test_client = TelegramClient(StringSession(new_session), API_ID, API_HASH)
        try:
            await asyncio.wait_for(test_client.connect(), timeout=10)
            if not await test_client.is_user_authorized():
                logger.error(f"[LZT-SESSION] ❌ Созданная сессия НЕ РАБОТАЕТ (не авторизована)")
                return None, "session_invalid"
            await test_client.disconnect()
            logger.info(f"[LZT-SESSION] ✅ Сессия проверена и работает!")
        except Exception as e:
            logger.error(f"[LZT-SESSION] ❌ Ошибка проверки сессии: {e}")
            return None, f"session_verification_failed:{str(e)[:50]}"

        return new_session, "ok"
    except errors.SessionPasswordNeededError:
        return None, "2fa"
    except errors.PhoneCodeInvalidError:
        return None, "invalid_code"
    except errors.FloodWaitError as e:
        return None, f"flood:{e.seconds}"
    except Exception as e:
        logger.error(f"[LZT-SESSION] Ошибка: {e}")
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
                match = re.search(r'\b(\d{5})\b', msg.text)
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
    logger.info("[SEARCH] Ищу один подходящий аккаунт (до 5 страниц)...")
    balance, balance_id = _lzt_fetch_balance_and_account_id(market)
    if balance is not None:
        logger.info(f"[BALANCE] Доступно: {balance:.2f} ₽ (balance_id: {balance_id})")

    for page in range(1, 11):
        query = (
            f"/telegram?"
            f"pmax={LZT_MAX_PRICE}"
            f"&spam={LZT_SPAM_FILTER}"
            f"&allow_geo_spamblock={LZT_ALLOW_GEO_SPAMBLOCK}"
            f"&order_by={LZT_ORDER_BY}"
            f"&page={page}"
            f"&show=true"
        )
        try:
            response = market.request("GET", query)
            _lzt_log_raw(f"SEARCH_PAGE_{page}", response)
            data = response.json()
        except Exception as e:
            logger.error(f"[SEARCH] Ошибка запроса страницы {page}: {e}")
            continue

        items = data.get("items", [])
        if not items:
            items = data.get("accounts", [])
        if not items and isinstance(data, list):
            items = data

        if not items:
            logger.info(f"[SEARCH] Страница {page} пуста.")
            continue

        logger.info(f"[SEARCH] Страница {page}: найдено {len(items)} лотов.")

        if target_country:
            filtered = []
            for item in items:
                c = _lzt_get_country(item)
                if c and target_country.lower() in c.lower():
                    filtered.append(item)
            if not filtered:
                logger.info(f"[SEARCH] На странице {page} нет лотов для страны {target_country}, переходим дальше.")
                continue
            items = filtered
            logger.info(f"[SEARCH] На странице {page} найдено {len(items)} лотов для страны {target_country}.")

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
            _sr = lzt_item_spam_reason(item)
            if _sr:
                logger.info(f"[SKIP] ID:{item_id} — спам-блок: {_sr}")
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

    logger.info("[RESULT] Подходящих лотов не найдено ни на одной из 5 страниц.")
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
                price_rub_shop, price_stars_shop = bz_shop_price(normalize_phone(phone))

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
                    await add_phone_to_shop_now(phone, price_rub_shop, price_stars_shop, used_session, "", item_id, "", user_id, context)
                else:
                    add_phone_product(phone, price_rub_shop, price_stars_shop, "", "", item_id)
            else:
                queue_text = "❌ Номер телефона не найден — не удалось добавить в магазин."

            safe_phone = html.escape(str(phone_display))
            safe_country = html.escape(str(country or "N/A"))
            safe_price = html.escape(f"{price:.2f}")

            await query.edit_message_text(
                f"✅ <b>НОМЕР УСПЕШНО КУПЛЕН!</b>\n\n"
                f"📱 Номер: <code>{safe_phone}</code>\n"
                f"🌍 Страна: {safe_country}\n"
                f"💰 Цена покупки: {safe_price} ₽\n\n"
                f"{queue_text}\n"
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
                price_rub_shop, price_stars_shop = bz_shop_price(normalize_phone(phone))

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
                    await add_phone_to_shop_now(phone, price_rub_shop, price_stars_shop, used_session, "", item_id, "", user_id, context)
                else:
                    add_phone_product(phone, price_rub_shop, price_stars_shop, "", "", item_id)
            else:
                queue_text = "❌ Номер телефона не найден — не удалось добавить в магазин."

            safe_phone2 = html.escape(str(phone_display))
            safe_country2 = html.escape(str(country or "N/A"))
            safe_price2 = html.escape(f"{price:.2f}")

            await query.edit_message_text(
                f"✅ <b>НОМЕР УСПЕШНО КУПЛЕН!</b>\n\n"
                f"🌍 Страна: {safe_country2}\n"
                f"📱 Номер: <code>{safe_phone2}</code>\n"
                f"💰 Цена покупки: {safe_price2} ₽\n\n"
                f"{queue_text}\n"
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


# ═══════════════════════════════════════════════════════════
#  АВТОЗАКУП АККАУНТОВ (LZT) — закупка, очистка, получение
#  Перенесено из «закуп_номеров». Своя база (BZ_DB_NAME), админы — общие
#  с магазином (только главные админы), токен LZT — тот же (get_lzt_token()).
# ═══════════════════════════════════════════════════════════
try:
    from config import BUYER_DB_NAME as BZ_DB_NAME
except ImportError:
    BZ_DB_NAME = "/storage/emulated/0/Download/Автопокупка и парсер аков/lzt_numbers.db"
if not os.path.isdir(os.path.dirname(BZ_DB_NAME) or "."):
    BZ_DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lzt_numbers.db")
try:
    from config import BUYER_AVATAR_DIR as AVATAR_DIR
except ImportError:
    AVATAR_DIR = "/storage/emulated/0/Download/Автопокупка и парсер аков/avatars"
try:
    from config import BUYER_START_PHONE as START_PHONE
except ImportError:
    START_PHONE = "+2349122611201"

warnings.filterwarnings("ignore", message=".*per_message.*")
for _n in ("httpx", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)

GIFT_ALLOWED_STARS = None   # None = любой подарок; или набор цен, например {15, 25, 50}
WIPE_ON_LOGIN = True
KEEP_CHAT_ID = 777000
WIPE_BLOCK_BOTS = True
WIPE_BLOCK_USERS = True
BUY_DELAY = 3
CODE_ATTEMPTS = 8
CODE_ROUNDS = 3
CODE_DELAY = 5
MIN_PRICE = 1
ALLOW_GEO_SPAMBLOCK = "false"   # без гео-спамблока
SPAM_FILTER = "no"          # серверный фильтр LZT: только лоты без спам-блока
NO_LOTS_RETRIES = 40
NO_LOTS_DELAY = 10

BUY_COUNT, BUY_PRICE = range(110, 112)
MANUAL_PHONE, MANUAL_CODE, MANUAL_2FA = range(112, 115)
DELETE_NUMBER_INPUT = 115
PRIM_PHONE, PRIM_CODE, PRIM_2FA = range(116, 119)
QR_2FA_PW = 119
BUY_COUNTRY = 120


def ts(dt=None) -> str:
    return (dt or datetime.now()).isoformat(sep=" ", timespec="seconds")


STOP_KB = InlineKeyboardMarkup([[InlineKeyboardButton("⛔ СТОП", callback_data="buy_stop")]])


def esc(text: str) -> str:
    for ch in ["_", "*", "`", "[", "]"]:
        text = str(text).replace(ch, "\\" + ch)
    return text


def is_main_admin(user_id: int) -> bool:
    return is_super_admin(user_id)


def _bz_admin_ids() -> List[int]:
    ids = list(ADMINS) if ADMINS else []
    if ADMIN_ID not in ids:
        ids.insert(0, ADMIN_ID)
    return ids


# ═══════════ БАЗА ДАННЫХ ═══════════
def bz_init_db():
    os.makedirs(os.path.dirname(os.path.abspath(BZ_DB_NAME)), exist_ok=True)
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                phone TEXT UNIQUE,
                price REAL,
                country TEXT,
                session TEXT,
                status TEXT DEFAULT 'active',
                is_primary INTEGER DEFAULT 0,
                bought_at TIMESTAMP,
                next_check_at TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('stopped', '0')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gift_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_id INTEGER UNIQUE,
                user_id INTEGER,
                gift_title TEXT,
                stars INTEGER,
                number_id INTEGER,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP
            )
        """)
        try:
            conn.execute("ALTER TABLE numbers ADD COLUMN wiped_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # колонка уже есть
        try:
            conn.execute("ALTER TABLE numbers ADD COLUMN shop_listed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # колонка уже есть
        conn.execute("CREATE TABLE IF NOT EXISTS account_decisions (phone TEXT PRIMARY KEY, decision TEXT, reason TEXT, at TEXT)")
        for _col, _typ in (("tg_id", "INTEGER"), ("tg_username", "TEXT"), ("created_est", "TEXT"),
                           ("created_src", "TEXT"), ("spam_status", "TEXT"), ("spam_note", "TEXT"),
                           ("inspected_at", "TIMESTAMP")):
            try:
                conn.execute(f"ALTER TABLE numbers ADD COLUMN {_col} {_typ}")
            except sqlite3.OperationalError:
                pass  # колонка уже есть
        conn.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_bought', 0)")
        conn.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_dead', 0)")
        conn.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_spent', 0)")
    logger.info("✅ База данных готова")


def is_stopped() -> bool:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='stopped'").fetchone()
    return bool(row and row[0] == "1")


def set_stopped(value: bool):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE settings SET value=? WHERE key='stopped'",
                     ("1" if value else "0",))


async def notify_admins(bot, text, **kwargs):
    for admin_id in _bz_admin_ids():
        try:
            await bot.send_message(chat_id=admin_id, text=text, **kwargs)
        except BadRequest:
            # сломалась Markdown-разметка — шлём простым текстом
            plain = {k: v for k, v in kwargs.items() if k != "parse_mode"}
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=text.replace("*", "").replace("`", ""), **plain)
            except Exception as e:
                logger.warning(f"[NOTIFY] Не доставлено {admin_id}: {e}")
        except Exception as e:
            logger.warning(f"[NOTIFY] Не доставлено {admin_id}: {e}")


async def safe_edit(bot, chat_id, message_id, text, **kwargs):
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=text, **kwargs)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        kwargs.pop("parse_mode", None)
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text.replace("*", "").replace("`", ""), **kwargs)
        except Exception as e2:
            logger.warning(f"[EDIT] Не удалось обновить сообщение: {e2}")
    except Exception as e:
        logger.warning(f"[EDIT] Не удалось обновить сообщение: {e}")


BACKGROUND_TASKS: set = set()

ACTIVE_OPERATION: Optional[str] = None  # "buy" | "import" | None, защита от двойного запуска


def try_start_operation(name: str) -> bool:
    global ACTIVE_OPERATION
    if ACTIVE_OPERATION is not None:
        return False
    ACTIVE_OPERATION = name
    return True


def finish_operation():
    global ACTIVE_OPERATION
    ACTIVE_OPERATION = None


def get_active_operation() -> Optional[str]:
    return ACTIVE_OPERATION


def spawn(coro):
    """create_task с хранением ссылки (иначе задачу может собрать GC)."""
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task


def stats_increment(key: str, amount: int = 1):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE stats SET value = value + ? WHERE key=?", (amount, key))


def stats_get_all() -> dict:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        total_bought = conn.execute(
            "SELECT value FROM stats WHERE key='total_bought'"
        ).fetchone()
        total_dead = conn.execute(
            "SELECT value FROM stats WHERE key='total_dead'"
        ).fetchone()
        total_spent = conn.execute(
            "SELECT value FROM stats WHERE key='total_spent'"
        ).fetchone()
        alive = conn.execute(
            "SELECT COUNT(*) FROM numbers WHERE is_primary=0 "
            "AND status IN ('active','alive','secured')"
        ).fetchone()
    return {
        "total_bought": total_bought[0] if total_bought else 0,
        "total_dead": total_dead[0] if total_dead else 0,
        "total_spent_kop": total_spent[0] if total_spent else 0,
        "alive": alive[0] if alive else 0,
    }


BZ_DEFAULT_SHOP_RUB = SHOP_PRICE_RUB
BZ_DEFAULT_SHOP_STARS = 40   # используется только если цены ещё ни разу не задавались
BZ_LIVE_STATUSES = ("active", "alive", "secured")


def bz_shop_price(phone):
    """Цена в магазине: из настроек страны (COUNTRIES), иначе значения по умолчанию."""
    cfg = get_country_by_code(get_country_by_phone(phone)) or {}
    rub = cfg.get("price_rub") or BZ_DEFAULT_SHOP_RUB
    stars = cfg.get("price_stars") or BZ_DEFAULT_SHOP_STARS
    try:                                    # рубли и звёзды, заданные владельцем, действуют независимо друг от друга
        saved_rub = _get_setting("shop_price_rub")
        if saved_rub:
            rub = float(saved_rub)
    except ValueError:
        pass
    try:
        saved_stars = _get_setting("shop_price_stars")
        if saved_stars:
            stars = int(float(saved_stars))
    except ValueError:
        pass
    return rub, stars


def bz_publish_to_shop(phone, item_id, session, two_fa="") -> bool:
    """Выкладывает номер в магазин. Страна/флаг определяются по коду номера.
    Уже существующий в магазине (в продаже или проданный) повторно не добавляется."""
    try:
        phone_n = normalize_phone(phone)
        if not validate_phone(phone_n):
            logger.warning(f"[SHOP] {phone}: неверный формат, не выложен")
            return False
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            exists = conn.execute("SELECT id FROM phone_products WHERE phone=?", (phone_n,)).fetchone()
        if exists:
            # номер уже лежит в магазине (мог попасть туда со старой ценой) — выравниваем по заданной цене
            rub, stars = bz_shop_price(phone_n)
            with sqlite3.connect(DB_NAME, timeout=10) as conn:
                conn.execute("UPDATE phone_products SET price_rub=?, price_stars=? WHERE phone=? AND available=1",
                             (rub, stars, phone_n))
        else:
            rub, stars = bz_shop_price(phone_n)
            if not add_phone_product(phone_n, rub, stars, session or "", "", item_id or None, two_fa or ""):
                return False
            cc = get_country_by_code(get_country_by_phone(phone_n))
            logger.info(f"[SHOP] {phone_n} выложен: {(cc or {}).get('flag', '🌍')} "
                        f"{(cc or {}).get('name', 'страна не определена')}, {rub}₽ / {stars}⭐")
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            conn.execute("UPDATE numbers SET shop_listed=1 WHERE phone=?", (phone,))
        return True
    except Exception as e:
        logger.error(f"[SHOP] publish {phone}: {e}")
        return False


def bz_unpublish_from_shop(phone) -> None:
    """Снимает с продажи (только непроданные) — номер ушёл из базы автозакупа."""
    try:
        phone_n = normalize_phone(phone)
        with sqlite3.connect(DB_NAME, timeout=10) as conn:
            conn.execute("DELETE FROM phone_products WHERE phone=? AND available=1", (phone_n,))
    except Exception as e:
        logger.error(f"[SHOP] unpublish {phone}: {e}")


def bz_remove_sold_number(phone) -> None:
    """Магазин продал номер — убираем его из базы автозакупа (чтобы не подарить/не проверять)."""
    try:
        want = _digits(phone)
        if len(want) < 7:
            return
        removed = False
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            for nid, ph in conn.execute("SELECT id, phone FROM numbers WHERE is_primary=0").fetchall():
                if _digits(ph) == want:
                    conn.execute("DELETE FROM numbers WHERE id=?", (nid,))
                    removed = True
        if removed:
            bz_remember(phone, "deleted", "продан в магазине")
    except Exception as e:
        logger.error(f"[SHOP] remove sold {phone}: {e}")


def bz_publish_ready() -> List[str]:
    """Выкладывает в магазин номера, прошедшие 25-часовую проверку: аккаунт жив и все чужие сеансы завершены."""
    threshold = datetime.now() - timedelta(hours=25)
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT phone, item_id, session FROM numbers "
            "WHERE is_primary=0 AND status='secured' AND COALESCE(shop_listed,0)=0 "
            "AND (bought_at IS NULL OR bought_at <= ?)", (ts(threshold),)).fetchall()
    added = []
    for phone, item_id, session in rows:
        if bz_publish_to_shop(phone, item_id, session):
            added.append(phone)
    return added


def bz_waiting_count() -> int:
    """Сколько номеров ещё ждут 25-часовой проверки."""
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            return conn.execute("SELECT COUNT(*) FROM numbers WHERE is_primary=0 AND COALESCE(shop_listed,0)=0 "
                                "AND status IN ('active','alive','secured')").fetchone()[0]
    except Exception:
        return 0


def bz_sync_shop() -> Tuple[int, int]:
    """Выкладывает прошедшие проверку номера. -> (выложено, ещё ждут проверки)"""
    added = bz_publish_ready()
    return len(added), bz_waiting_count()


def bz_pending_all() -> List[Tuple[str, int, str]]:
    """Все купленные номера, ещё не выложенные в магазин (кроме помеченных спамом/заморозкой)."""
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        return conn.execute(
            "SELECT phone, item_id, session FROM numbers "
            "WHERE is_primary=0 AND status IN ('active','alive','secured') "
            "AND COALESCE(shop_listed,0)=0 AND COALESCE(spam_status,'')!='spam'").fetchall()


def bz_publish_all_now() -> Tuple[int, int]:
    """Выкладывает в магазин ВСЕ купленные номера сразу, не дожидаясь 25-часовой проверки. -> (выложено, не вышло)"""
    added = failed = 0
    for phone, item_id, session in bz_pending_all():
        if bz_publish_to_shop(phone, item_id, session):
            added += 1
        else:
            failed += 1
    return added, failed


def add_number(item_id, phone, price, country, session, is_primary=0, two_fa=""):
    now = datetime.now()
    next_check = None if is_primary else now + timedelta(hours=24)
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO numbers "
            "(item_id, phone, price, country, session, status, is_primary, bought_at, next_check_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
            (item_id, phone, price, country, session, is_primary, ts(now),
             ts(next_check) if next_check else None),
        )
    if not is_primary:
        stats_increment("total_bought", 1)
        stats_increment("total_spent", int(round((price or 0) * 100)))
        bz_schedule_inspect(phone, session)     # в магазин — только после 25-часовой проверки


def delete_number(number_id):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute(
            "SELECT is_primary, phone FROM numbers WHERE id=?", (number_id,)
        ).fetchone()
        if row and row[0] == 0:
            bz_unpublish_from_shop(row[1])
            bz_remember(row[1], "deleted", "удалён вручную")
        conn.execute("DELETE FROM numbers WHERE id=?", (number_id,))
    if row and row[0] == 0:
        stats_increment("total_dead", 1)


def _digits(text: str) -> str:
    return "".join(ch for ch in str(text) if ch.isdigit())


def delete_number_by_phone(user_input: str) -> Optional[str]:
    """Удаляет купленный номер из базы по введённому номеру.
    Возвращает номер как он хранился в базе или None, если не найден.
    Статистику «мёртвых» не трогает (это ручное удаление)."""
    want = _digits(user_input)
    if len(want) < 7:
        return None
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, phone FROM numbers WHERE is_primary=0"
        ).fetchall()
        found = None
        for nid, phone in rows:
            have = _digits(phone)
            if have == want or (len(want) >= 10 and have[-10:] == want[-10:]):
                found = (nid, phone)
                break
        if not found:
            return None
        conn.execute("DELETE FROM numbers WHERE id=?", (found[0],))
    bz_unpublish_from_shop(found[1])
    bz_remember(found[1], "deleted", "удалён по номеру")
    return found[1]


def mark_wiped(number_id=None, phone=None):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        if number_id is not None:
            conn.execute("UPDATE numbers SET wiped_at=? WHERE id=?", (ts(), number_id))
        elif phone is not None:
            conn.execute("UPDATE numbers SET wiped_at=? WHERE phone=?", (ts(), phone))


def is_wiped(number_id: int) -> bool:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute(
            "SELECT wiped_at FROM numbers WHERE id=?", (number_id,)).fetchone()
    return bool(row and row[0])


def get_unwiped() -> List[Tuple[int, str, str]]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        return conn.execute(
            "SELECT id, phone, session FROM numbers "
            "WHERE is_primary=0 AND wiped_at IS NULL AND status != 'dead' "
            "ORDER BY id").fetchall()


def gift_add(msg_id, user_id, title, stars) -> Optional[int]:
    """Записывает полученный подарок. None — если он уже был записан."""
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            cur = conn.execute(
                "INSERT INTO gift_access (msg_id, user_id, gift_title, stars, status, created_at) "
                "VALUES (?, ?, ?, ?, 'new', ?)",
                (msg_id, user_id, title, stars, ts()))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def gift_open_for_user(user_id: int):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        return conn.execute(
            "SELECT id, number_id FROM gift_access "
            "WHERE user_id=? AND status IN ('new','assigned') ORDER BY id",
            (user_id,)).fetchall()


def gift_get(gid: int):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        return conn.execute(
            "SELECT id, user_id, number_id, status FROM gift_access WHERE id=?",
            (gid,)).fetchone()


def gift_assign_number(gid: int):
    """Закрепляет за подарком один свободный номер. -> (id, phone, session) или None."""
    conn = sqlite3.connect(BZ_DB_NAME, timeout=10, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        g = conn.execute(
            "SELECT number_id, status FROM gift_access WHERE id=?", (gid,)).fetchone()
        if not g or g[1] not in ("new", "assigned"):
            conn.execute("ROLLBACK")
            return None
        if g[0]:
            row = conn.execute(
                "SELECT id, phone, session FROM numbers WHERE id=?", (g[0],)).fetchone()
            if row:
                conn.execute("COMMIT")
                return row
        row = conn.execute(
            "SELECT id, phone, session FROM numbers "
            "WHERE is_primary=0 AND status IN ('active','alive','secured') "
            "AND id NOT IN (SELECT number_id FROM gift_access "
            "               WHERE number_id IS NOT NULL AND status='assigned') "
            "ORDER BY id LIMIT 1").fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return None
        conn.execute(
            "UPDATE gift_access SET number_id=?, status='assigned' WHERE id=?",
            (row[0], gid))
        conn.execute("COMMIT")
        bz_unpublish_from_shop(row[1])
        return row
    except Exception as e:
        logger.error(f"[GIFT] assign error: {e}")
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return None
    finally:
        conn.close()


def gift_finish(gid: int) -> Optional[str]:
    """Код подошёл: удаляем номер из базы, подарок закрываем. -> номер или None."""
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        g = conn.execute(
            "SELECT number_id FROM gift_access WHERE id=? AND status='assigned'",
            (gid,)).fetchone()
        if not g:
            return None
        row = conn.execute(
            "SELECT phone FROM numbers WHERE id=?", (g[0],)).fetchone()
        conn.execute("DELETE FROM numbers WHERE id=?", (g[0],))
        conn.execute("UPDATE gift_access SET status='done' WHERE id=?", (gid,))
    if row:
        bz_unpublish_from_shop(row[0])
        bz_remember(row[0], "deleted", "выдан по подарку")
    return row[0] if row else "?"


def set_number_status(number_id, status):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE numbers SET status=? WHERE id=?", (status, number_id))
        row = conn.execute("SELECT phone, is_primary FROM numbers WHERE id=?", (number_id,)).fetchone()
    if row and not row[1] and status not in BZ_LIVE_STATUSES:
        bz_unpublish_from_shop(row[0])


def postpone_check(number_id, hours: float = 1):
    """Отложить следующую проверку (чтобы не спамить при ошибках)."""
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE numbers SET next_check_at=? WHERE id=?",
                     (ts(datetime.now() + timedelta(hours=hours)), number_id))


def get_active_sessions() -> List[Tuple[int, str, str]]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, phone, session FROM numbers "
            "WHERE status IN ('active', 'alive', 'secured') AND is_primary=0"
        ).fetchall()
    return rows


def get_due_numbers() -> List[Tuple[int, int, str, str]]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, item_id, phone, session FROM numbers "
            "WHERE status='active' AND next_check_at <= ? AND is_primary=0",
            (ts(),),
        ).fetchall()
    return rows


def get_ready_to_secure() -> List[Tuple[int, str, str]]:
    threshold = datetime.now() - timedelta(hours=25)
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, phone, session FROM numbers "
            "WHERE is_primary=0 AND status='alive' AND bought_at <= ? "
            "AND (next_check_at IS NULL OR next_check_at <= ?)",
            (ts(threshold), ts()),
        ).fetchall()
    return rows


def get_all_bought() -> List[Tuple[int, int, str, str]]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, item_id, phone, session FROM numbers WHERE is_primary=0"
        ).fetchall()
    return rows


def get_stats():
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM numbers WHERE is_primary=0 GROUP BY status"
        ).fetchall()
        recent = conn.execute(
            "SELECT phone, price, status, bought_at FROM numbers "
            "WHERE is_primary=0 ORDER BY id DESC LIMIT 10"
        ).fetchall()
    return dict(rows), recent


def get_primary_session() -> Optional[str]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute(
            "SELECT session FROM numbers WHERE is_primary=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def get_bought_list() -> List[Tuple[int, str, str]]:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT id, phone, status FROM numbers "
            "WHERE is_primary=0 ORDER BY id ASC"
        ).fetchall()
    return rows


def get_known_item_ids() -> set:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute(
            "SELECT item_id FROM numbers WHERE item_id IS NOT NULL AND item_id != 0"
        ).fetchall()
    return {r[0] for r in rows}


def get_number_by_id(number_id: int):
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute(
            "SELECT id, item_id, phone, session, status FROM numbers WHERE id=?",
            (number_id,)
        ).fetchone()
    return row

# ═══════════ LZT API (для автозакупа) ═══════════
def make_market():
    if not _lzt_available:
        raise RuntimeError("LOLZTEAM не установлен: pip install LOLZTEAM")
    market = _lzt_market_cls(token=get_lzt_token())
    if LZT_PROXY:
        market.settings.proxy = LZT_PROXY
    return market


async def lzt_get_balance(market) -> Tuple[Optional[float], Optional[int]]:
    """Баланс LZT в рублях и id баланса для оплаты (разные валюты НЕ суммируем)."""
    try:
        resp = await market.request("GET", "/balance/exchange")
        data = resp.json()
        cands = []
        for key, val in (data.get("to") or {}).items():
            if isinstance(val, dict) and val.get("balance") is not None:
                try:
                    cands.append((str(key).lower(), val.get("type"), float(val["balance"]), val.get("balance_id")))
                except (ValueError, TypeError):
                    pass
        if not cands:
            logger.warning(f"[BALANCE] неожиданный ответ: {str(data)[:300]}")
            return None, None
        logger.info(f"[BALANCE] варианты: {[(k, t, round(b_, 2)) for k, t, b_, _ in cands]}")
        # платим с того баланса, где больше всего денег (а не с первого попавшегося «account» на 1 ₽)
        pick = next((c for c in cands if c[0] in ("rub", "₽", "руб", "rur")), None)
        if pick is None:
            pick = max(cands, key=lambda c: c[2])
        return pick[2], pick[3]
    except Exception as e:
        logger.warning(f"[BALANCE] Ошибка: {e}")
        return None, None


def lzt_get_country(item) -> str:
    return str(item.get("telegram_country") or item.get("country") or "")


async def lzt_fetch_code(market, item_id: int, attempts: int = 1) -> Optional[str]:
    code_keys = {"code", "email_code", "sms_code", "otp", "telegram_code", "login_code"}
    text_keys = {"message", "text", "data", "msg"}

    def walk(d, depth=8):
        if depth <= 0:
            return
        if isinstance(d, dict):
            for k, v in d.items():
                yield k, v
                if isinstance(v, (dict, list)):
                    yield from walk(v, depth - 1)
        elif isinstance(d, list):
            for x in d:
                yield from walk(x, depth - 1)

    for i in range(attempts):
        try:
            resp = await market.request("GET", f"/{item_id}/telegram-login-code")
            if resp.status_code == 200:
                pairs = list(walk(resp.json()))
                for k, v in pairs:
                    if isinstance(k, str) and k.lower() in code_keys and v is not None:
                        s = str(v).strip()
                        if s.isdigit() and 4 <= len(s) <= 8:
                            return s
                for k, v in pairs:
                    if isinstance(k, str) and k.lower() in text_keys and isinstance(v, str):
                        m = re.search(r"\b(\d{5})\b", v)
                        if m:
                            return m.group(1)
            elif resp.status_code == 429:
                logger.warning("[CODE] 429 — слишком часто")
        except Exception as e:
            logger.error(f"[CODE] Ошибка: {e}")
        if i < attempts - 1:
            await asyncio.sleep(CODE_DELAY)
    return None


def lzt_extract_phone(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"(\+\d[\d\s\-]{7,20})", text)
    if m:
        phone = re.sub(r"[\s\-]", "", m.group(1))
        if len(phone) >= 10:
            return phone
    m = re.search(r"\b(\d{11,13})\b", text)
    if m:
        return m.group(1)
    return None


def lzt_extract_login_data(data) -> dict:
    result = {}
    root = data
    for wrapper in ("data", "item", "account", "response"):
        if isinstance(data, dict) and isinstance(data.get(wrapper), dict):
            root = data[wrapper]
            break

    def walk(d, depth=8):
        if depth <= 0 or not isinstance(d, (dict, list)):
            return
        items = d.items() if isinstance(d, dict) else enumerate(d)
        for k, v in items:
            if isinstance(k, str) and k not in result and v is not None:
                result[k] = v
            walk(v, depth - 1)

    walk(root)
    for key in ("loginData", "login_data", "json", "data"):
        v = result.get(key)
        if isinstance(v, str) and len(v) > 5:
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    for k2, v2 in parsed.items():
                        if k2 not in result and v2 is not None:
                            result[k2] = v2
            except json.JSONDecodeError:
                pass
    return result


PURCHASES_LOG_SAMPLE_SHOWN = False


async def lzt_list_purchases(market) -> List[dict]:
    """
    Список уже купленных лотов (раздел «Мои покупки» на LZT).
    Эндпоинт /user/items — предположение по документации LZT Market API,
    сам я его не вызывал (нет доступа к интернету), поэтому структура
    ответа подтверждается только логом первой страницы (см. ниже).
    Если эндпоинт окажется другим — пришли мне строку лога
    "[IMPORT] сырой ответ:" целиком, поправлю парсинг.
    """
    global PURCHASES_LOG_SAMPLE_SHOWN
    result = []
    for page in range(1, 21):
        try:
            resp = await market.request("GET", f"/user/items?page={page}")
            data = resp.json()
        except Exception as e:
            logger.error(f"[IMPORT] Ошибка запроса страницы {page}: {e}")
            break

        if not PURCHASES_LOG_SAMPLE_SHOWN:
            logger.info(f"[IMPORT] сырой ответ: {json.dumps(data, ensure_ascii=False)[:1500]}")
            PURCHASES_LOG_SAMPLE_SHOWN = True

        items = None
        if isinstance(data, dict):
            for key in ("items", "data", "purchases", "accounts"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
        elif isinstance(data, list):
            items = data
        if not items:
            break
        result.extend(items)
    return result


def lzt_is_telegram_item(item: dict) -> bool:
    for key in ("category", "category_id", "item_origin", "title", "item_type"):
        v = item.get(key)
        if v is not None and "telegram" in str(v).lower():
            return True
    return bool(item.get("telegram_id") or item.get("telegram_country"))


async def lzt_get_item_login_data(market, item_id: int) -> dict:
    """Данные для входа уже купленного лота (раздел «Данные для входа» на LZT)."""
    try:
        resp = await market.request("GET", f"/{item_id}")
        return lzt_extract_login_data(resp.json())
    except Exception as e:
        logger.warning(f"[IMPORT] Не удалось получить данные лота {item_id}: {e}")
        return {}


def _lzt_country_ok(item, ccode: str, cname: str) -> bool:
    """Страна лота совпадает с выбранной (точное совпадение кода или названия)."""
    c = lzt_get_country(item).strip().lower()
    return bool(c) and (c == ccode.lower() or (cname and c == cname.lower()))


async def _lzt_fast_buy(market, item_id: int, payload: dict):
    resp = await market.request("POST", f"/{item_id}/fast-buy", json=payload)
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code not in (200, 201) and payload.get("balance_id") is not None:
        txt = str(data.get("errors") if isinstance(data, dict) else data).lower()
        if "средств" in txt or "insufficient" in txt:
            logger.info("[BUY] недостаточно средств на выбранном балансе — пробую без balance_id")
            p2 = {k: v for k, v in payload.items() if k != "balance_id"}
            resp2 = await market.request("POST", f"/{item_id}/fast-buy", json=p2)
            try:
                data2 = resp2.json()
            except Exception:
                data2 = {}
            return resp2, data2
    return resp, data


_LZT_COUNTRY_STYLE = {"v": None}      # None — не определено, "lower"/"upper" — серверный фильтр работает, "none" — нет


async def _lzt_detect_country_filter(market, max_price) -> str:
    """Проверяет на живых лотах, работает ли фильтр country[] у LZT и в каком регистре."""
    if _LZT_COUNTRY_STYLE["v"] is not None:
        return _LZT_COUNTRY_STYLE["v"]
    style = "none"
    determined = False
    try:
        r = await market.request("GET", f"/telegram?pmax={max_price}&page=1")
        data = r.json()
        items = data.get("items") or data.get("accounts") or (data if isinstance(data, list) else [])
        logger.info(f"[SEARCH] примеры стран в лотах: {[lzt_get_country(i) for i in items[:10]]}")
        sample = next((lzt_get_country(i) for i in items if lzt_get_country(i)), "")
        if sample:
            determined = True
            for st, val in (("lower", sample.lower()), ("upper", sample.upper())):
                rr = await market.request("GET", f"/telegram?pmax={max_price}&country[]={val}&page=1")
                d2 = rr.json()
                its = d2.get("items") or d2.get("accounts") or []
                if its and all(lzt_get_country(i).lower() == sample.lower() for i in its[:10]):
                    style = st
                    break
    except Exception as e:
        logger.warning(f"[SEARCH] не удалось проверить фильтр страны: {e}")
    if determined:
        _LZT_COUNTRY_STYLE["v"] = style
    logger.info(f"[SEARCH] серверный фильтр страны: {style}")
    return style


# ====== ЖЁСТКИЙ ФИЛЬТР СПАМ-БЛОКА (в т.ч. гео) — проверка данных лота ПЕРЕД покупкой ======
STRICT_SPAM_FILTER = True
SPAM_SKIP_UNKNOWN = False    # False: лоты без информации о спам-блоке (нет поля или -1) покупаем; True: пропускаем такие
_SPAM_OK_VALUES = {"", "0", "no", "none", "null", "false", "clean", "ok", "nomatter", "нет", "чистый"}
_SPAM_TEXT_RE = re.compile(r"(спам[\s\-_]*блок|spam[\s\-_]*block|spambot|гео[\s\-_]*спам|geo[\s\-_]*spam|"
                           r"ограничен\w*\s+(?:по\s+)?гео|limited)", re.IGNORECASE)
_NEGATION_RE = re.compile(r"(без|нет|no|not|free|clean|отсутств\w*|чист\w*)\W{0,12}$", re.IGNORECASE)

def lzt_item_spam_reason(item) -> Optional[str]:
    """Возвращает причину, если по данным лота есть спам-блок (или это нельзя исключить), иначе None."""
    if not STRICT_SPAM_FILTER or not isinstance(item, dict):
        return None

    def walk(obj, path="", depth=0):
        if depth > 4:
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if isinstance(v, (dict, list)):
                    r = walk(v, f"{path}{k}.", depth + 1)
                    if r:
                        return r
                    continue
                if ("spam" in key or "geo_block" in key or "geoblock" in key) and "filter" not in key:
                    sv = str(v).strip().lower()
                    if sv in ("-1", "-1.0"):
                        if SPAM_SKIP_UNKNOWN:
                            return f"поле {path}{k}=-1 (спам-блок не проверен)"
                        continue
                    if sv not in _SPAM_OK_VALUES:
                        return f"поле {path}{k}={v}"
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:50]):
                r = walk(v, f"{path}{i}.", depth + 1)
                if r:
                    return r
        return None

    r = walk(item)
    if r:
        return r
    for fld in ("title", "title_en", "description", "description_en", "note_text"):
        txt = str(item.get(fld) or "")
        for m in _SPAM_TEXT_RE.finditer(txt):
            if not _NEGATION_RE.search(txt[max(0, m.start() - 16):m.start()]):
                return f"в тексте лота ({fld}): «{txt[max(0, m.start() - 10):m.end() + 10]}»"
    return None
# ====== КОНЕЦ ФИЛЬТРА ======

async def lzt_buy_one(market, max_price: float, balance_id=None, balance=None,
                      skip_ids: set = None, country=None):
    """Ищет и покупает ОДИН лот. skip_ids — проданные/битые лоты. country — словарь страны, код или None."""
    if skip_ids is None:
        skip_ids = set()

    # устойчивый разбор country: словарь / строка-код / None
    if isinstance(country, dict):
        ccode = str(country.get("code", "") or "")
        cname = str(country.get("name", "") or "")
    elif country:
        ccode = str(country).strip()
        cname = ""
    else:
        ccode = ""
        cname = ""

    use_server = False
    cval = ccode.lower()
    if ccode:
        style = await _lzt_detect_country_filter(market, max_price)
        if style in ("lower", "upper"):
            use_server = True
            cval = ccode.lower() if style == "lower" else ccode.upper()
    max_pages = 25 if (ccode and not use_server) else 10

    for page in range(1, max_pages + 1):
        query = f"/telegram?pmax={max_price}&order_by=price_to_up&page={page}"
        if use_server:
            query += f"&country[]={cval}"
        if MIN_PRICE and MIN_PRICE > 0:
            query += f"&pmin={min(MIN_PRICE, max_price)}"
        query += f"&spam={SPAM_FILTER or 'no'}"   # всегда: без спам-блока
        query += f"&allow_geo_spamblock={ALLOW_GEO_SPAMBLOCK}"   # и без гео-спамблока
        try:
            resp = await market.request("GET", query)
            data = resp.json()
        except Exception as e:
            logger.error(f"[SEARCH] Ошибка страницы {page}: {e}")
            continue

        items = data.get("items") or data.get("accounts") or (data if isinstance(data, list) else [])
        logger.info(f"[SEARCH] стр.{page}: найдено лотов {len(items) if items else 0}")
        if not items:
            break

        if ccode and not use_server:
            items = [it for it in items if _lzt_country_ok(it, ccode, cname)]
            if not items:
                continue

        for item in items:
            item_id = item.get("item_id") or item.get("id")
            if item_id is None:
                continue
            item_id = int(item_id)

            if item_id in skip_ids:
                continue

            price = float(item.get("price") or 0)
            price_total = float(item.get("priceWithSellerFee") or price * 1.03)
            lot_country = lzt_get_country(item)

            if price > max_price:
                continue
            _sr = lzt_item_spam_reason(item)
            if _sr:
                logger.info(f"[SKIP] лот {item_id} — спам-блок: {_sr}")
                skip_ids.add(item_id)
                continue
            if balance is not None and balance < price_total:
                return False, None, None, None, None, {}, "no_money"

            logger.info(f"[BUY] лот {item_id} | {price}₽ | {lot_country or 'N/A'}")
            payload = {"price": price}
            if balance_id is not None:
                payload["balance_id"] = balance_id
            try:
                buy_resp, buy_data = await _lzt_fast_buy(market, item_id, payload)

                if buy_resp.status_code in (200, 201):
                    logger.info(f"✅ Куплен лот {item_id}")
                    login_data = lzt_extract_login_data(buy_data)
                    phone = None
                    for key in ("phone", "phone_number", "number", "telegram_phone"):
                        if login_data.get(key):
                            phone = str(login_data[key]).strip()
                            break
                    if not phone:
                        for field in (str(item.get("title") or ""),
                                      str(item.get("description") or "")):
                            phone = lzt_extract_phone(field)
                            if phone:
                                break
                    if not phone and login_data:
                        phone = lzt_extract_phone(json.dumps(login_data, ensure_ascii=False))
                    return True, item_id, phone, price, lot_country, login_data, None
                else:
                    logger.warning(f"❌ fast-buy HTTP {buy_resp.status_code} "
                                   f"лот {item_id}: {str(buy_data)[:150]}")
                    err_txt = str(buy_data.get("errors") if isinstance(buy_data, dict)
                                  else buy_data).lower()
                    if "средств" in err_txt or "insufficient" in err_txt:
                        return False, None, None, None, None, {}, "no_money"
                    if buy_resp.status_code == 429:
                        await asyncio.sleep(3)
                        continue
                    skip_ids.add(item_id)
                    continue
            except Exception as e:
                logger.error(f"❌ Ошибка покупки {item_id}: {e}")
                skip_ids.add(item_id)
                continue

    return False, None, None, None, None, {}, "no_lots"


AVATAR_DIR = "/storage/emulated/0/Download/Автопокупка и парсер аков/avatars"

START_PHONE = "+2349122611201"


async def terminal_login() -> Optional[str]:
    print("\n" + "=" * 60)
    print("  🔐 ВХОД В СТАРТОВЫЙ АККАУНТ")
    print("=" * 60)

    existing = get_primary_session()
    if existing:
        print("  ✅ Найдена сохранённая сессия. Проверяю...")
        try:
            client = TelegramClient(StringSession(existing), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                await client.disconnect()
                print(f"  ✅ Сессия активна: {me.first_name} (@{me.username or '—'})")
                return existing
            await client.disconnect()
        except Exception as e:
            print(f"  ⚠️ Сессия не работает: {e}")
        print("  ⏳ Нужен новый вход.")

    if not (sys.stdin and sys.stdin.isatty()):
        print("  ℹ️ Нет консоли — вход в стартовый аккаунт сделаешь в чате бота (кнопка 🔑).")
        return None

    print(f"\n  Шаг 1/3. Номер: {START_PHONE}")
    phone = START_PHONE

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        print(f"  ✅ Код отправлен на {phone}")

        print("\n  Шаг 2/3. Введи код из Telegram:")
        code = (await asyncio.to_thread(input, "  🔢 Код: ")).strip().replace(" ", "")

        try:
            await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
        except errors.SessionPasswordNeededError:
            print("\n  🔒 Шаг 3/3. Двухфакторная аутентификация.")
            password = (await asyncio.to_thread(input, "  🔑 Пароль 2FA: ")).strip()
            await client.sign_in(password=password)

        session_str = client.session.save()
        me = await client.get_me()
        await client.disconnect()

        add_number(0, phone, 0.0, "primary", session_str, is_primary=1)
        print(f"\n  ✅ ВХОД ВЫПОЛНЕН: {me.first_name} (@{me.username or '—'})")
        print("=" * 60 + "\n")
        return session_str

    except errors.PhoneCodeInvalidError:
        print("  ❌ Неверный код. Запусти заново.")
        await client.disconnect()
        return None
    except errors.PasswordHashInvalidError:
        print("  ❌ Неверный пароль 2FA. Запусти заново.")
        await client.disconnect()
        return None
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        await client.disconnect()
        return None


def fmt_phone(phone) -> str:
    """Номер для показа: всегда с + в начале."""
    p = str(phone or "").strip()
    return p if p.startswith("+") or not p else "+" + p


_APP = None  # заполняется в on_startup, нужен для уведомлений из фоновых задач


WIPE_CONCURRENCY = 8        # параллельных операций внутри одного аккаунта
WIPE_ACCOUNTS_PARALLEL = 3  # сколько аккаунтов чистится одновременно


async def wipe_account(client, progress=None, should_stop=None) -> dict:
    """Выходит из всех групп/каналов, удаляет все диалоги (только у этого
    аккаунта), блокирует ботов/людей, чистит контакты, истории и папки.
    Чат 777000 не трогает. Всё делается параллельно."""
    st = {"channels": 0, "groups": 0, "users": 0, "contacts": 0, "errors": 0,
          "aborted": False, "total": 0, "seen": 0, "blocked": 0,
          "stories": 0, "folders": 0}
    loop = asyncio.get_event_loop()
    pause = {"until": 0.0}

    async def _wait_pause():
        delay = pause["until"] - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)

    def _flood(e) -> bool:
        """True — можно продолжать после паузы, False — слишком долго, прерываем."""
        if e.seconds > 120:
            st["aborted"] = True
            return False
        pause["until"] = max(pause["until"], loop.time() + e.seconds + 1)
        return True

    dialogs = [d async for d in client.iter_dialogs()]  # все папки, включая архив
    st["total"] = len(dialogs)
    logger.info(f"[WIPE] найдено диалогов: {len(dialogs)}")
    if progress:
        await progress(st)

    sem = asyncio.Semaphore(WIPE_CONCURRENCY)

    async def _one(d):
        async with sem:
            if st["aborted"]:
                return
            if should_stop and should_stop():
                st["aborted"] = True
                return
            ent = d.entity
            if getattr(ent, "id", None) == KEEP_CHAT_ID:
                st["seen"] += 1
                return
            if (isinstance(ent, types.User) and not getattr(ent, "is_self", False)
                    and ((ent.bot and WIPE_BLOCK_BOTS)
                         or (not ent.bot and WIPE_BLOCK_USERS))):
                for _ in range(2):
                    await _wait_pause()
                    try:
                        await client(functions.contacts.BlockRequest(id=ent))
                        st["blocked"] += 1
                        break
                    except errors.FloodWaitError as e:
                        if not _flood(e):
                            return
                    except Exception as e:
                        logger.warning(f"[WIPE] блок {getattr(ent, 'id', '?')}: {str(e)[:60]}")
                        break
            for _ in range(3):
                if st["aborted"]:
                    return
                await _wait_pause()
                try:
                    await client.delete_dialog(ent, revoke=False)
                    if d.is_channel and not d.is_group:
                        st["channels"] += 1
                    elif d.is_group or d.is_channel:
                        st["groups"] += 1
                    else:
                        st["users"] += 1
                    break
                except errors.FloodWaitError as e:
                    if not _flood(e):
                        st["errors"] += 1
                        return
                except Exception as e:
                    logger.warning(f"[WIPE] {getattr(ent, 'id', '?')}: {str(e)[:80]}")
                    st["errors"] += 1
                    break
            st["seen"] += 1
            if st["seen"] % 20 == 0:
                logger.info(f"[WIPE] {st['seen']}/{st['total']}")
            if progress and st["seen"] % 5 == 0:
                await progress(st)

    async def _extras():
        # контакты
        try:
            res = await client(functions.contacts.GetContactsRequest(hash=0))
            users = [u for u in getattr(res, "users", []) if u.id != KEEP_CHAT_ID]
            for i in range(0, len(users), 100):
                chunk = users[i:i + 100]
                await client(functions.contacts.DeleteContactsRequest(id=chunk))
                st["contacts"] += len(chunk)
        except Exception as e:
            logger.warning(f"[WIPE] контакты: {str(e)[:80]}")
            st["errors"] += 1
        # истории: скрыть чужие, удалить свои
        try:
            await client(functions.stories.ToggleAllStoriesHiddenRequest(hidden=True))
        except Exception as e:
            logger.warning(f"[WIPE] скрытие историй: {str(e)[:80]}")
        try:
            me = await client.get_me()
            ids = set()
            try:
                r = await client(functions.stories.GetPinnedStoriesRequest(
                    peer=me, offset_id=0, limit=100))
                ids |= {x.id for x in r.stories if hasattr(x, "id")}
            except Exception:
                pass
            try:
                r = await client(functions.stories.GetPeerStoriesRequest(peer=me))
                ids |= {x.id for x in r.stories.stories if hasattr(x, "id")}
            except Exception:
                pass
            if ids:
                await client(functions.stories.DeleteStoriesRequest(peer=me, id=list(ids)))
                st["stories"] = len(ids)
        except Exception as e:
            logger.warning(f"[WIPE] свои истории: {str(e)[:80]}")
        # папки чатов
        try:
            res = await client(functions.messages.GetDialogFiltersRequest())
            for f in getattr(res, "filters", res):
                fid = getattr(f, "id", None)
                if fid and fid != 0:
                    await client(functions.messages.UpdateDialogFilterRequest(id=fid))
                    st["folders"] += 1
        except Exception as e:
            logger.warning(f"[WIPE] папки: {str(e)[:80]}")

    await asyncio.gather(_extras(), *[_one(d) for d in dialogs],
                         return_exceptions=True)
    logger.info(f"[WIPE] готово: {st}")
    return st


async def do_wipe(session: str, progress=None, should_stop=None) -> Optional[dict]:
    """Входит по сессии и чистит аккаунт. None — сессия мертва."""
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        if not await client.is_user_authorized():
            return None
        return await asyncio.wait_for(wipe_account(client, progress, should_stop), timeout=1800)
    finally:
        await _disconnect(client)


def wipe_summary(st: dict) -> str:
    return (f"📢 Каналов: {st['channels']}\n👥 Групп: {st['groups']}\n"
            f"💬 Личных чатов: {st['users']}\n📇 Контактов: {st['contacts']}\n"
            f"🚫 Заблокировано: {st['blocked']}\n📸 Историй удалено: {st['stories']}\n"
            f"🗂 Папок удалено: {st['folders']}\n"
            f"⚠️ Ошибок: {st['errors']}")


async def wipe_session_task(session: str, phone: str):
    """Фоновая очистка свежевошедшего аккаунта (покупка не ждёт)."""
    if not WIPE_ON_LOGIN:
        return
    try:
        st = await do_wipe(session)
        if st is None:
            return
        if not st.get("aborted"):
            mark_wiped(phone=phone)
        logger.info(f"[WIPE] {phone}: {st}")
        if _APP is not None:
            await notify_admins(
                _APP.bot, f"🧹 АККАУНТ ОЧИЩЕН\n\n📱 {phone}\n{wipe_summary(st)}")
    except Exception as e:
        logger.error(f"[WIPE] {phone}: {e}")


async def set_random_avatar(client) -> Tuple[bool, str]:
    if not os.path.isdir(AVATAR_DIR):
        return False, "no_avatar_dir"
    files = [f for f in os.listdir(AVATAR_DIR)
             if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not files:
        return False, "no_avatars"
    path = os.path.join(AVATAR_DIR, random.choice(files))
    try:
        await client(UploadProfilePhotoRequest(
            file=await client.upload_file(path)
        ))
        return True, path
    except errors.FloodWaitError as e:
        return False, f"flood_{e.seconds}"
    except Exception as e:
        return False, f"error:{str(e)[:80]}"


DEAD_REASONS = [
    (errors.AuthKeyUnregisteredError, "Сессия аннулирована"),
    (errors.UserDeactivatedBanError, "Аккаунт забанен"),
    (errors.UserDeactivatedError, "Аккаунт деактивирован"),
    (errors.SessionRevokedError, "Сессия отозвана"),
]


def dead_reason(exc) -> Optional[str]:
    for cls, text in DEAD_REASONS:
        if isinstance(exc, cls):
            return text
    return None


async def _disconnect(client):
    try:
        await client.disconnect()
    except Exception:
        pass


async def verify_alive(number_id: int, item_id: int, phone: str,
                       session: str, market, app) -> None:
    report = f"🔍 *ПРОВЕРКА*\n\n📱 `{phone}`\n"
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        me = await asyncio.wait_for(client.get_me(), timeout=15)

        if me is None:
            delete_number(number_id)
            report += "\n❌ Сессия мертва.\n🗑 Удалён из базы."
        else:
            set_number_status(number_id, "alive")
            uname = f"@{me.username}" if me.username else "—"
            report += (f"\n✅ Аккаунт жив\n"
                       f"👤 `{me.first_name}` {uname}\n"
                       f"🆔 `{me.id}`\n"
                       f"📌 Статус: *АКТИВЕН*")
    except asyncio.TimeoutError:
        postpone_check(number_id)
        report += "\n⚠️ Таймаут.\n📌 Статус: *НЕИЗВЕСТЕН*"
    except Exception as e:
        reason = dead_reason(e)
        if reason:
            delete_number(number_id)
            report += f"\n❌ {reason}.\n🗑 Удалён из базы."
        else:
            logger.error(f"[CHECK] Ошибка проверки {phone}: {e}")
            postpone_check(number_id)
            report += f"\n⚠️ Ошибка: `{str(e)[:150]}`\n📌 Статус: *НЕИЗВЕСТЕН*"
    finally:
        await _disconnect(client)

    await notify_admins(app.bot, report, parse_mode="Markdown")


async def verify_and_secure(number_id: int, item_id: int, phone: str,
                            session: str, market, app) -> str:
    report = f"🔍🔒 *ПРОВЕРКА + ЗАВЕРШЕНИЕ*\n\n📱 `{phone}`\n"
    result = "unknown"
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        me = await asyncio.wait_for(client.get_me(), timeout=15)

        if me is None:
            delete_number(number_id)
            report += "\n❌ Сессия мертва.\n🗑 Удалён из базы."
            result = "dead"
        else:
            uname = f"@{me.username}" if me.username else "—"
            try:
                await client(ResetAuthorizationsRequest())
                set_number_status(number_id, "secured")
                report += (f"\n✅ Все чужие сессии завершены\n"
                           f"👤 `{me.first_name}` {uname}\n"
                           f"🆔 `{me.id}`\n"
                           f"📌 Статус: *ЗАЩИЩЁН*")
                result = "secured"
            except errors.FloodWaitError as e:
                set_number_status(number_id, "alive")
                postpone_check(number_id)
                report += (f"\n⚠️ FloodWait {e.seconds} сек.\n"
                           f"👤 `{me.first_name}`\n"
                           f"📌 Статус: *АКТИВЕН*")
                result = "alive"
            except Exception as e:
                set_number_status(number_id, "alive")
                if _is_frozen_error(e):
                    bz_mark_frozen(number_id, phone)
                    report += ("\n⛔ Аккаунт ЗАМОРОЖЕН Telegram — завершить сеансы невозможно.\n"
                               "📌 Помечен как СПАМ, в магазин не выставляется.")
                else:
                    postpone_check(number_id)
                    report += (f"\n⚠️ Не удалось завершить сессии: `{str(e)[:100]}`\n"
                               f"📌 Статус: *АКТИВЕН*")
                result = "alive"
    except asyncio.TimeoutError:
        postpone_check(number_id)
        report += "\n⚠️ Таймаут."
    except Exception as e:
        reason = dead_reason(e)
        if reason:
            delete_number(number_id)
            report += f"\n❌ {reason}.\n🗑 Удалён из базы."
            result = "dead"
        else:
            logger.error(f"[CHECK+SECURE] Ошибка {phone}: {e}")
            postpone_check(number_id)
            report += f"\n⚠️ Ошибка: `{str(e)[:150]}`"
    finally:
        await _disconnect(client)

    await notify_admins(app.bot, report, parse_mode="Markdown")
    return result


FROZEN_NOTE = "аккаунт заморожен Telegram (FROZEN_METHOD_INVALID): завершить сеансы нельзя"


def _is_frozen_error(e) -> bool:
    return "FROZEN" in str(e).upper() or "FROZEN" in type(e).__name__.upper()


def bz_mark_frozen(number_id: int, phone: str) -> None:
    """Замороженный аккаунт: сеансы завершить нельзя → помечаем СПАМ, в магазин не выставляем, повторных попыток нет."""
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            conn.execute("UPDATE numbers SET spam_status='spam', spam_note=?, inspected_at=?, next_check_at=? WHERE id=?",
                         (FROZEN_NOTE, ts(), ts(datetime.now() + timedelta(days=3650)), number_id))
        logger.warning(f"[FROZEN] {phone}: {FROZEN_NOTE}")
    except Exception as e:
        logger.error(f"[FROZEN] не удалось пометить {phone}: {e}")


async def secure_account(number_id: int, phone: str, session: str, app) -> None:
    report = f"🔒 *ЗАВЕРШЕНИЕ СЕССИЙ (25Ч)*\n\n📱 `{phone}`\n"
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)

        if not await client.is_user_authorized():
            delete_number(number_id)
            report += "\n❌ Сессия мертва.\n🗑 Удалён из базы."
        else:
            await client(ResetAuthorizationsRequest())
            me = await client.get_me()
            set_number_status(number_id, "secured")
            uname = f"@{me.username}" if me.username else "—"
            report += (f"\n✅ Все чужие сессии завершены\n"
                       f"👤 `{me.first_name}` {uname}\n"
                       f"📌 Статус: *ЗАЩИЩЁН*")
    except Exception as e:
        if _is_frozen_error(e):
            bz_mark_frozen(number_id, phone)
            report += ("\n⛔ Аккаунт ЗАМОРОЖЕН Telegram — завершить сеансы невозможно.\n"
                       "📌 Помечен как СПАМ, в магазин не выставляется, повторных попыток не будет.")
        else:
            logger.error(f"[SECURE] Ошибка {phone}: {e}")
            postpone_check(number_id)  # повтор через час, а не каждую минуту
            report += f"\n⚠️ Ошибка: `{str(e)[:150]}`"
    finally:
        await _disconnect(client)

    await notify_admins(app.bot, report, parse_mode="Markdown")


async def scheduler_loop(app):
    await asyncio.sleep(10)
    while True:
        try:
            due = get_due_numbers()
            if due:
                market = make_market() if _lzt_available else None
                logger.info(f"[SCHED] Проверка {len(due)} номеров")
                for number_id, item_id, phone, session in due:
                    await verify_alive(number_id, item_id, phone, session, market, app)
                    await asyncio.sleep(5)

            ready = get_ready_to_secure()
            if ready:
                logger.info(f"[SCHED] Завершаю сессии у {len(ready)} аккаунтов (25ч)")
                for number_id, phone, session in ready:
                    await secure_account(number_id, phone, session, app)
                    await asyncio.sleep(5)

            added = await asyncio.to_thread(bz_publish_ready)
            if added:
                await notify_owner(app.bot, "✅ Номера добавлены в магазин: " + str(len(added)) + " шт.\n"
                                   + "\n".join(f"• {fmt_phone(x)}" for x in added[:20]))
            if ready or added:
                await bz_return_main_menu(app.bot, ADMIN_ID)

        except Exception as e:
            logger.error(f"[SCHED] Ошибка: {e}")
        await asyncio.sleep(60)


async def add_bought_account(phone: str, item_id: int, market,
                             password: Optional[str] = None) -> Tuple[Optional[str], str]:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        sent = await asyncio.wait_for(client.send_code_request(phone), timeout=15)
        logger.info(f"[ADD] Код запрошен для {phone}")

        tried = set()
        signed = False
        for round_no in range(CODE_ROUNDS):
            if round_no > 0:
                logger.info(f"[ADD] Код не пришёл, запрашиваю заново ({round_no + 1}/{CODE_ROUNDS})")
                sent = await asyncio.wait_for(client.send_code_request(phone), timeout=15)
            for _ in range(CODE_ATTEMPTS):
                await asyncio.sleep(CODE_DELAY)
                code = await lzt_fetch_code(market, item_id)
                if not code or code in tried:
                    continue
                tried.add(code)
                try:
                    await asyncio.wait_for(
                        client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash),
                        timeout=15,
                    )
                    signed = True
                except errors.PhoneCodeInvalidError:
                    continue  # возможно старый код — ждём свежий
                except errors.SessionPasswordNeededError:
                    if not password:
                        return None, "needs_2fa"
                    try:
                        await asyncio.wait_for(client.sign_in(password=password), timeout=15)
                        signed = True
                    except errors.PasswordHashInvalidError:
                        # пароль из ответа покупки мог устареть — берём свежий
                        # из карточки лота (как в разделе «Данные для входа» на LZT)
                        logger.info(f"[ADD] Пароль неверный, пробую получить свежий "
                                   f"для лота {item_id}")
                        fresh = await lzt_get_item_login_data(market, item_id)
                        if fresh:
                            logger.info(f"[ADD] Свежие данные лота {item_id}, "
                                       f"поля: {sorted(fresh.keys())}")
                        fresh_pw = None
                        for key in ("telegram_password", "password", "twofa", "2fa",
                                    "two_fa", "cloud_password"):
                            if fresh.get(key):
                                fresh_pw = str(fresh[key])
                                break
                        if fresh_pw and fresh_pw != password:
                            await asyncio.wait_for(client.sign_in(password=fresh_pw), timeout=15)
                            signed = True
                        else:
                            raise
                break
            if signed:
                break

        if not signed:
            return None, ("invalid_code" if tried else "no_code_from_market")

        session_str = client.session.save()

        ok_ava, ava_info = await set_random_avatar(client)
        if ok_ava:
            logger.info(f"[ADD] Аватарка установлена: {ava_info}")
        else:
            logger.warning(f"[ADD] Аватарка не установлена: {ava_info}")

        test = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        try:
            await asyncio.wait_for(test.connect(), timeout=10)
            if not await test.is_user_authorized():
                return None, "session_invalid"
        finally:
            await _disconnect(test)

        logger.info(f"[ADD] ✅ Купленный аккаунт {phone} добавлен")
        spawn(wipe_session_task(session_str, phone))
        return session_str, "ok"
    except asyncio.TimeoutError:
        return None, "timeout"
    except errors.SessionPasswordNeededError:
        return None, "needs_2fa"
    except errors.PasswordHashInvalidError:
        return None, "bad_2fa_password"
    except errors.PhoneCodeInvalidError:
        return None, "invalid_code"
    except errors.PhoneCodeExpiredError:
        return None, "code_expired"
    except errors.FloodWaitError as e:
        return None, f"flood_{e.seconds}"
    except Exception as e:
        return None, f"error:{str(e)[:80]}"
    finally:
        await _disconnect(client)


async def bulk_buy_task(context, count, max_price, progress_chat, progress_msg_id, country=None):
    try:
        await _bulk_buy_task(context, count, max_price, progress_chat, progress_msg_id, country)
    except Exception as e:
        logger.exception("[BUY] Необработанная ошибка закупки")
        await notify_admins(context.bot, f"❌ Ошибка закупки: {str(e)[:200]}")
    finally:
        finish_operation()


async def _bulk_buy_task(context, count, max_price, progress_chat, progress_msg_id, country=None):
    set_stopped(False)
    if not _lzt_available:
        await safe_edit(context.bot, progress_chat, progress_msg_id,
                        "❌ LOLZTEAM не установлен: pip install LOLZTEAM")
        return
    market = make_market()
    balance, balance_id = await lzt_get_balance(market)

    primary = get_primary_session()
    if not primary:
        await context.bot.edit_message_text(
            chat_id=progress_chat, message_id=progress_msg_id,
            text="❌ *НЕТ СТАРТОВОЙ СЕССИИ*\n\nВойди в аккаунт при запуске.",
            parse_mode="Markdown")
        return

    if balance is not None and balance < MIN_PRICE * 1.03:
        await context.bot.edit_message_text(
            chat_id=progress_chat, message_id=progress_msg_id,
            text=f"❌ *НЕДОСТАТОЧНО СРЕДСТВ*\n\nБаланс: `{balance:.2f} ₽`\nМинимальный лот: `{MIN_PRICE} ₽`",
            parse_mode="Markdown")
        return
    if balance is not None and balance < max_price * 1.03:
        capped = int(balance / 1.03 * 100) / 100
        logger.info(f"[BUY] баланс {balance:.2f} < лимит {max_price}: покупаю лоты до {capped}")
        max_price = max(float(MIN_PRICE), capped)

    # ВАЖНО: страна-фильтр хранится отдельно и НЕ перезаписывается результатом покупки
    target_country = country

    country_title = (f"{target_country.get('flag', '')} {target_country.get('name', target_country.get('code'))}"
                     if isinstance(target_country, dict) and target_country else "любая")
    ok_count, fail_count = 0, 0
    attempts = 0
    max_attempts = count * 10
    skip_ids: set = set()
    empty_rounds = 0
    report_lines = []

    while ok_count < count and attempts < max_attempts and not is_stopped():
        attempts += 1

        status_text = (f"🛒 *ЗАКУПКА И ДОБАВЛЕНИЕ*\n\n"
                       f"🌍 Страна: {country_title}   💰 до {max_price:g} ₽\n"
                       f"✅ Куплено: {ok_count}/{count}\n"
                       f"❌ Неудачно: {fail_count}\n"
                       f"🔁 Попытка: {attempts}/{max_attempts}\n"
                       f"⛔ Пропущено лотов: {len(skip_ids)}\n"
                       f"🔎 Пустых поисков подряд: {empty_rounds}/{NO_LOTS_RETRIES}\n")
        if balance is not None:
            status_text += f"\n💰 `{balance:.2f} ₽`"
        await safe_edit(context.bot, progress_chat, progress_msg_id, status_text,
                        parse_mode="Markdown", reply_markup=STOP_KB)

        ok, item_id, phone, price, item_country, login_data, err = await lzt_buy_one(
            market, max_price, balance_id, balance, skip_ids=skip_ids, country=target_country)

        if not ok:
            if err == "no_money":
                left = f"{balance:.2f} ₽" if balance is not None else "неизвестно"
                report_lines.append(f"💸 LZT ответил «недостаточно средств», закупка завершена. Бот видел баланс: {left}")
                await notify_admins(context.bot,
                    f"💸 *БАЛАНСА НЕ ХВАТИЛО — ЗАКУПКА ЗАВЕРШЕНА*\n\nКуплено: {ok_count}/{count}\nОстаток: {left}",
                    parse_mode="Markdown")
                break
            if err == "no_lots":
                empty_rounds += 1
                if empty_rounds <= NO_LOTS_RETRIES:
                    attempts -= 1
                    logger.info(f"[BUY] Лотов нет, повтор поиска {empty_rounds}/{NO_LOTS_RETRIES}")
                    await asyncio.sleep(NO_LOTS_DELAY)
                    continue
                logger.warning(f"[BUY] Лоты закончились после {attempts} попыток")
                report_lines.append(f"📭 Лоты закончились на попытке {attempts}")
                await notify_admins(context.bot,
                    f"📭 *ЛОТЫ ЗАКОНЧИЛИСЬ*\n\nКуплено: {ok_count}/{count}\n"
                    f"Пропущено битых: {len(skip_ids)}",
                    parse_mode="Markdown")
                break
            fail_count += 1
            await asyncio.sleep(BUY_DELAY)
            continue

        empty_rounds = 0
        new_balance, _bid = await lzt_get_balance(market)
        if new_balance is not None:
            balance = new_balance
        elif balance is not None:
            balance -= float(price or 0) * 1.03

        password = None
        for key in ("telegram_password", "password", "twofa", "2fa",
                    "two_fa", "cloud_password"):
            v = (login_data or {}).get(key)
            if v:
                password = str(v)
                break

        if phone:
            session_str, status = await add_bought_account(
                phone, item_id, market, password=password)
        else:
            session_str, status = None, "phone_not_found"

        if session_str:
            add_number(item_id, phone, price, item_country, session_str, two_fa=password or "")
            ok_count += 1
            report_lines.append(f"{ok_count}️⃣ ✅ `{phone}` ({price}₽)")
            await notify_admins(context.bot,
                f"✅ *АККАУНТ ДОБАВЛЕН И АКТИВЕН*\n\n📱 `{phone}`\n💰 {price} ₽\n"
                f"🌍 {country_label(item_country, phone)}\n🆔 `{item_id}`\n"
                f"📊 Прогресс: {ok_count}/{count}",
                parse_mode="Markdown")
        else:
            fail_count += 1
            skip_ids.add(item_id)
            report_lines.append(f"⚠️ `{phone or '?'}` ({price}₽), вход: `{status}`")
            logger.warning(f"[BUY] Лот {item_id} куплен, но вход: {status}")
            await notify_admins(context.bot,
                f"⚠️ *КУПЛЕН, НО ВХОД НЕ УДАЛСЯ*\n\n📱 `{phone or '?'}`\n"
                f"🆔 лот `{item_id}`\n❓ причина: `{status}`\n\n"
                f"Попробуй войти вручную: меню → ➕ НОМЕР ВРУЧНУЮ.",
                parse_mode="Markdown")

        await asyncio.sleep(BUY_DELAY)

    if is_stopped():
        report_lines.append("⏹ Остановлено кнопкой СТОП")
    summary = "\n".join(report_lines) if report_lines else "—"

    if ok_count >= count:
        header = f"📊 *ЗАКУПКА ЗАВЕРШЕНА* ({country_title})\n\n✅ Добавлено: {ok_count}/{count}"
    else:
        header = (f"⚠️ *ЗАКУПКА ОСТАНОВЛЕНА* ({country_title})\n\n"
                  f"✅ Добавлено: {ok_count}/{count}\n"
                  f"🔁 Попыток: {attempts}")

    await safe_edit(
        context.bot, progress_chat, progress_msg_id,
        f"{header}\n❌ Неудачно: {fail_count}\n\n*Детали:*\n{summary[:3500]}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🚀 ВЫГРУЗИТЬ ВСЁ В МАГАЗИН", "bz_shop_all")]]))

# ═══════════ КНОПКА «ПОЛУЧИТЬ НОМЕРА» ═══════════
NUMBERS_PER_PAGE = 16
_STOP_FLAGS = {"check": False, "wipe": False}


def _back_numbers(context) -> str:
    return f"numpage_{context.user_data.get('num_page', 0)}"


def numbers_list_kb(page: int = 0, admin: bool = True):
    rows = get_bought_list()
    spam = _spam_map()
    decisions = bz_decisions_map()
    pages = max(1, (len(rows) + NUMBERS_PER_PAGE - 1) // NUMBERS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = rows[page * NUMBERS_PER_PAGE:(page + 1) * NUMBERS_PER_PAGE]
    kb_rows = []
    row_buf = []
    for nid, phone, status in chunk:
        emoji = "🟢" if status == "secured" else "🔴"
        mark = ("⛔СПАМ " if spam.get(nid) == "spam" else "") + ("📌" if decisions.get(_digits(phone)) == "kept" else "")
        row_buf.append(btn(f"{emoji} {mark}{fmt_phone(phone)}", f"num_{nid}"))
        if len(row_buf) == 2:
            kb_rows.append(row_buf)
            row_buf = []
    if row_buf:
        kb_rows.append(row_buf)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(btn("◀️", f"numpage_{page - 1}"))
        nav.append(btn(f"{page + 1}/{pages}", f"numpage_{page}"))
        if page < pages - 1:
            nav.append(btn("▶️", f"numpage_{page + 1}"))
        kb_rows.append(nav)
    if admin:
        kb_rows.append([btn("🗑 УДАЛИТЬ НОМЕР", "delete_number_start")])
    kb_rows.append([btn("🔙 МЕНЮ", "menu")])
    return InlineKeyboardMarkup(kb_rows), page, pages, len(rows)


async def get_numbers(update, context):
    q = update.callback_query
    await q.answer()
    if not bz_can_get(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return

    page = 0
    if q.data.startswith("numpage_"):
        page = int(q.data.split("_")[1])

    if not get_bought_list():
        await q.edit_message_text(
            "📭 Купленных номеров пока нет.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 МЕНЮ", "menu")]]))
        return

    kb, page, pages, total = numbers_list_kb(page, is_main_admin(q.from_user.id))
    context.user_data["num_page"] = page
    try:
        await q.edit_message_text(
            f"📱 *КУПЛЕННЫЕ НОМЕРА*\n\nВсего: *{total}*  •  стр. {page + 1}/{pages}\n"
            f"🟢 сессии завершены   🔴 не завершены   ⛔ спам-блок\n\nВыбери номер:",
            parse_mode="Markdown", reply_markup=kb)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def delete_number_start(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await q.edit_message_text(
        "🗑 *УДАЛИТЬ НОМЕР*\n\nОтправь мне номер, который хочешь удалить из базы.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "get_numbers")]]))
    return DELETE_NUMBER_INPUT


async def delete_number_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    phone = delete_number_by_phone(update.message.text.strip())
    if phone is None:
        await update.message.reply_text(
            "❌ Такого номера в базе нет. Отправь номер ещё раз или нажми отмену:",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "get_numbers")]]))
        return DELETE_NUMBER_INPUT
    await update.message.reply_text(
        f"✅ Номер `{phone}` удалён из базы.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🗑 УДАЛИТЬ ЕЩЁ", "delete_number_start")],
            [btn("📱 К НОМЕРАМ", "get_numbers")],
        ]))
    return ConversationHandler.END


async def delete_cancel(update, context):
    await get_numbers(update, context)
    return ConversationHandler.END


async def _render_detail(q, context, nid: int, note: str = ""):
    row = get_number_by_id(nid)
    if not row:
        await q.edit_message_text(
            "❌ Номер не найден.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙", _back_numbers(context))]]))
        return
    _, item_id, phone, session, status = row
    phone = fmt_phone(phone)
    sess_txt = "🟢 завершены" if status == "secured" else "🔴 не завершены"
    wiped_txt = "да" if is_wiped(nid) else "нет"
    text = (
        f"📱 *НОМЕР*\n\n"
        f"`{phone}`\n\n"
        f"📌 Статус: `{status}`\n"
        f"🔒 Чужие сессии: {sess_txt}\n"
        f"🧹 Очищен: {wiped_txt}\n"
        f"🆔 Лот: `{item_id}`\n"
        f"{_extra_text(nid)}\n"
        f"👉 Введи этот номер в Telegram.\n"
        f"Когда придёт СМС с кодом — нажми *«Получить код»*.\n"
        f"Бот сам прочитает код из переписки этой сессии."
    )
    if note:
        text += f"\n\n{note}"
    if is_main_admin(q.from_user.id):
        kb = InlineKeyboardMarkup([
            [btn("📨 ПОЛУЧИТЬ КОД", f"getcode_{nid}")],
            [btn("✅ КОД ПОДОШЁЛ", f"codeok_{nid}")],
            [btn("🛡 ПРОВЕРИТЬ СПАМ-БЛОК", f"inspect_{nid}")],
            [btn("↩️ СНЯТЬ ПОМЕТКУ «ОСТАВЛЕН»", f"unkeep_{nid}") if bz_decisions_map().get(_digits(phone)) == "kept"
             else btn("📌 ОСТАВИТЬ (запомнить)", f"keep_{nid}")],
            [btn("🔒 ЗАВЕРШИТЬ ВСЕ СЕССИИ", f"secure_{nid}")],
            [btn("🧹 ОЧИСТИТЬ АККАУНТ", f"wipe_{nid}")],
            [btn("🔙 К НОМЕРАМ", _back_numbers(context))],
        ])
    else:
        kb = InlineKeyboardMarkup([
            [btn("📨 ПОЛУЧИТЬ КОД", f"getcode_{nid}")],
            [btn("✅ КОД ПОДОШЁЛ", f"codeok_{nid}")],
            [btn("🔙 К НОМЕРАМ", _back_numbers(context))],
        ])
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        await q.edit_message_text(text.replace("*", "").replace("`", ""),
                                  reply_markup=kb)


async def number_detail(update, context):
    q = update.callback_query
    await q.answer()
    if not bz_can_get(q.from_user.id):
        return
    await _render_detail(q, context, int(q.data.split("_")[1]))


async def secure_one(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer("⏳ Завершаю сессии...")
    nid = int(q.data.split("_")[1])
    row = get_number_by_id(nid)
    if not row:
        await _render_detail(q, context, nid)
        return
    session = row[3]
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            note = "❌ Сессия мертва."
        else:
            await client(ResetAuthorizationsRequest())
            set_number_status(nid, "secured")
            note = "✅ Все чужие сессии завершены."
    except errors.FloodWaitError as e:
        note = f"⚠️ FloodWait {e.seconds} сек. Попробуй позже."
    except Exception as e:
        if _is_frozen_error(e):
            bz_mark_frozen(nid, row[2])
            note = "⛔ Аккаунт заморожен Telegram — сеансы завершить нельзя. Помечен как СПАМ."
        else:
            note = f"⚠️ Ошибка: {str(e)[:100]}"
    finally:
        await _disconnect(client)
    await _render_detail(q, context, nid, note)


async def wipe_one(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer("🧹 Очищаю...")
    nid = int(q.data.split("_")[1])
    row = get_number_by_id(nid)
    if not row:
        await _render_detail(q, context, nid)
        return
    try:
        await q.edit_message_text(
            "🧹 Очищаю аккаунт... Это может занять несколько минут.")
    except BadRequest:
        pass
    try:
        st = await do_wipe(row[3])
        if st is None:
            note = "❌ Сессия мертва."
        else:
            if not st.get("aborted"):
                mark_wiped(number_id=nid)
            note = "🧹 Очищено:\n" + wipe_summary(st)
    except Exception as e:
        note = f"⚠️ Ошибка: {str(e)[:100]}"
    await _render_detail(q, context, nid, note)


async def wipe_all(update, context):
    """Чистит только те аккаунты, которые бот ещё не очищал (несколько сразу)."""
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    rows = get_unwiped()
    if not rows:
        await q.edit_message_text(
            "✅ Все аккаунты уже очищены.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
        return

    _STOP_FLAGS["wipe"] = False
    stop_kb = InlineKeyboardMarkup([[btn("⏹ ЗАВЕРШИТЬ ОЧИСТКУ", "stop_wipe")]])
    msg = await q.edit_message_text(
        f"🧹 Очищаю {len(rows)} аккаунтов...", reply_markup=stop_kb)

    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(WIPE_ACCOUNTS_PARALLEL)
    current = {}          # nid -> [phone, seen, total]
    cnt = {"done": 0, "failed": 0, "skipped": 0}
    last = [0.0]

    async def render(force=False):
        now = loop.time()
        if not force and now - last[0] < 3:
            return
        last[0] = now
        lines = "\n".join(
            f"• {fmt_phone(v[0])}: {v[1]}/{v[2]}" for v in list(current.values()))
        try:
            await context.bot.edit_message_text(
                chat_id=msg.chat_id, message_id=msg.message_id,
                text=(f"🧹 Очистка: {cnt['done'] + cnt['failed']}/{len(rows)}\n\n"
                      f"{lines}\n\n"
                      f"✅ Очищено: {cnt['done']}\n⚠️ Не удалось: {cnt['failed']}"),
                reply_markup=stop_kb)
        except Exception:
            pass

    async def _acc(nid, phone, session):
        async with sem:
            if _STOP_FLAGS["wipe"]:
                cnt["skipped"] += 1
                return
            current[nid] = [phone, 0, 0]

            async def _progress(st):
                current[nid][1] = st["seen"]
                current[nid][2] = st["total"]
                await render()

            try:
                st = await do_wipe(session, _progress,
                                   should_stop=lambda: _STOP_FLAGS["wipe"])
                if st is None or st.get("aborted"):
                    cnt["failed"] += 1
                else:
                    mark_wiped(number_id=nid)
                    cnt["done"] += 1
            except Exception as e:
                logger.error(f"[WIPE-ALL] {phone}: {e}")
                cnt["failed"] += 1
            finally:
                current.pop(nid, None)
            await render(force=True)

    await asyncio.gather(*[_acc(*r) for r in rows], return_exceptions=True)

    stopped = _STOP_FLAGS["wipe"]
    try:
        await context.bot.edit_message_text(
            chat_id=msg.chat_id, message_id=msg.message_id,
            text=(("⏹ ОЧИСТКА ОСТАНОВЛЕНА\n\n" if stopped else "📊 ОЧИСТКА ЗАВЕРШЕНА\n\n")
                  + f"✅ Очищено: {cnt['done']}\n⚠️ Не удалось/прервано: {cnt['failed']}\n"
                  f"⏳ Осталось: {len(get_unwiped())}"),
            reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
    except Exception:
        pass


async def stop_batch(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    key = q.data.split("_")[1]
    _STOP_FLAGS[key] = True
    await q.answer("⏹ Останавливаю после текущего аккаунта...", show_alert=False)


def _age_txt(age_min) -> str:
    if age_min is None:
        return ""
    if age_min < 1:
        return "только что"
    if age_min < 60:
        return f"{age_min} мин назад"
    return f"{age_min // 60} ч назад"


async def get_code_for_number(update, context):
    """Читает последний код прямо из Telegram-переписки сессии (777000)."""
    q = update.callback_query
    await q.answer("⏳ Читаю переписку...")
    if not bz_can_get(q.from_user.id):
        return

    nid = int(q.data.split("_")[1])
    row = get_number_by_id(nid)
    if not row:
        await q.edit_message_text("❌ Номер не найден.")
        return

    _, item_id, phone, session, status = row
    phone = fmt_phone(phone)

    r = await read_login_code_ex(session)
    if r["err"]:
        if r["err"] == "session_dead":
            text = (f"📱 {phone}\n\n❌ Сессия этого номера больше не активна.\n\n"
                    f"Telegram разлогинил аккаунт: из него вышли (например, покупатель завершил все сеансы), "
                    f"либо аккаунт заблокирован или удалён. Код через эту сессию прочитать нельзя, "
                    f"повторная попытка не поможет.\n\n"
                    f"Если код нужен — войди в аккаунт заново и сохрани новую сессию.")
        else:
            text = (f"📱 {phone}\n\n❌ Ошибка сессии: {r['err']}\n\nПопробуй ещё раз.")
    elif not r["code"]:
        last = r["last"] or "—"
        recent = "\n".join(f"• {t}" for t in r.get("recent", [])) or f"• {last}"
        text = (f"📱 {phone}\n\n📭 В чате Telegram этого аккаунта нет сообщения с кодом входа\n\n"
                f"Сообщений в чате: {r['count']}. Последние:\n{recent}\n\n"
                f"Код приходит сюда, только когда ты вводишь этот номер в Telegram "
                f"(вход на новом устройстве, способ «код в приложение», не SMS). "
                f"Сделай это и нажми кнопку ещё раз — я сразу покажу самый последний код.")
    else:
        age = _age_txt(r["age_min"])
        text = (f"📱 {phone}\n\n🔑 КОД:  {r['code']}\n"
                + (f"🕒 Пришёл: {age}\n" if age else "")
                + ("\n⚠️ Это старый код. Если нужен новый — введи номер в Telegram "
                   "и нажми «Получить код ещё».\n" if r["old"] else "\nВведи его в Telegram."))

    kb = InlineKeyboardMarkup([
        [btn("📨 ПОЛУЧИТЬ КОД ЕЩЁ", f"getcode_{nid}")],
        [btn("✅ КОД ПОДОШЁЛ", f"codeok_{nid}")],
        [btn("🔙 К НОМЕРАМ", _back_numbers(context))],
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            # то же сообщение — обновим отметкой времени, чтобы было видно, что бот проверил
            await q.edit_message_text(
                text + f"\n\n🔄 Проверено {datetime.now().strftime('%H:%M:%S')}",
                reply_markup=kb)
        else:
            raise


async def code_ok(update, context):
    q = update.callback_query
    await q.answer("✅ Ок")
    if not bz_can_get(q.from_user.id):
        return

    nid = int(q.data.split("_")[1])
    row = get_number_by_id(nid)
    phone = fmt_phone(row[2]) if row else "?"

    if not bz_owner_like(q.from_user.id):
        # бесплатный пользователь забрал номер — убираем его из базы и магазина
        who = f"{q.from_user.id}" + (f" (@{q.from_user.username})" if q.from_user.username else "")
        delete_number_row(nid)
        await notify_admins(
            context.bot, f"🎁 *БЕСПЛАТНЫЙ НОМЕР ЗАБРАН*\n\n📱 `{phone}`\n👤 {who}",
            parse_mode="Markdown")
        try:
            await q.edit_message_text(
                f"✅ Код подошёл\n\n📱 {phone}\n\nНомер твой, из базы он убран.",
                reply_markup=InlineKeyboardMarkup([[btn("📱 К НОМЕРАМ", "get_numbers")]]))
        except BadRequest:
            pass
        return

    await notify_admins(
        context.bot,
        f"✅ *КОД ПОДОШЁЛ*\n\n📱 `{phone}`",
        parse_mode="Markdown")

    kb = InlineKeyboardMarkup([
        [btn("🗑 УДАЛИТЬ АККАУНТ", f"delacc_{nid}")],
        [btn("🔙 К НОМЕРАМ", _back_numbers(context))],
    ])
    try:
        await q.edit_message_text(
            f"✅ Код подошёл\n\n📱 {phone}\n\n"
            f"Можно удалить этот аккаунт из базы.", reply_markup=kb)
    except BadRequest:
        pass


def delete_number_row(number_id: int) -> Optional[str]:
    """Полностью удаляет аккаунт из базы (статистику «мёртвых» не трогает)."""
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        row = conn.execute(
            "SELECT phone FROM numbers WHERE id=? AND is_primary=0",
            (number_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM numbers WHERE id=?", (number_id,))
    bz_unpublish_from_shop(row[0])
    bz_remember(row[0], "deleted", "удалён кнопкой")
    return row[0]


async def delete_account(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    nid = int(q.data.split("_")[1])
    phone = delete_number_row(nid)
    await q.answer("🗑 Удалено" if phone else "Уже удалён")
    text = (f"🗑 Аккаунт {fmt_phone(phone)} полностью удалён из базы."
            if phone else "Этого аккаунта уже нет в базе.")
    await q.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(
            [[btn("🔙 К НОМЕРАМ", _back_numbers(context))]]))


# ═══════════ ДОСТУП К НОМЕРУ ЗА ПОДАРОК ═══════════
_ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def extract_code(text: str) -> Optional[str]:
    """Достаёт код входа из сообщения 777000 на любом языке."""
    t = (text or "").translate(_ZW)
    # «Login code: 12345», «Código: 12345», «Код: 1 2 3 4 5», «123-45»
    m = re.search(r"(?<!\d)(\d(?:[ \-\u00a0]?\d){4,5})(?!\d)", t)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return digits if len(digits) in (5, 6) else None


async def read_login_code_ex(session: str, max_age: int = CODE_MAX_AGE_SEC, wait: int = 0, on_wait=None) -> dict:
    """Читает ПОСЛЕДНИЙ код входа из чата 777000 и отдаёт сразу, ничего не ждёт.
    Если код старше max_age — всё равно отдаёт, но ставит old=True (чтобы показать предупреждение).
    wait > 0 — подождать более свежий, если найденный старый.
    -> {code, err, age_min, old, count, last}"""
    out = {"code": None, "err": None, "age_min": None, "old": False, "count": 0, "last": "", "recent": []}
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await client.is_user_authorized():
            out["err"] = "session_dead"
            return out
        peer = None
        try:
            peer = await client.get_input_entity(777000)
        except Exception:
            try:
                async for d in client.iter_dialogs(limit=100):
                    if d.id == 777000:
                        peer = d.entity
                        break
            except Exception:
                peer = None
        if peer is None:
            peer = types.InputPeerUser(777000, 0)
        deadline = time.time() + wait
        first = True
        while True:
            count = 0
            found = None
            async for msg in client.iter_messages(peer, limit=30):
                text = msg.message or ""
                count += 1
                if first and count <= 3:
                    out["recent"].append(text.replace("\n", " ")[:90])
                if count == 1 and first:
                    out["last"] = text.replace("\n", " ")[:80]
                code = extract_code(text)
                if code:
                    found = (code, _msg_age_sec(msg))
                    break          # сообщения идут от новых к старым → это самый свежий код
            if first:
                out["count"] = count
                first = False
            if found:
                out["code"] = found[0]
                out["age_min"] = int(found[1] // 60)
                out["old"] = found[1] > max_age
            if (found and not out["old"]) or wait <= 0 or time.time() >= deadline:
                break
            if on_wait:
                try:
                    await on_wait(int(wait - (deadline - time.time())), wait)
                except Exception:
                    pass
            await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"[CODE] Ошибка чтения кода: {e}")
        out["err"] = str(e)[:120]
    finally:
        await _disconnect(client)
    logger.info(f"[CODE] последний код: {out['code']} (пришёл {out['age_min']} мин назад, старый={out['old']})")
    return out


async def read_fresh_code_only(session: str) -> Optional[str]:
    """Свежий код из чата 777000 аккаунта (не старше 10 минут), ждём до 20 сек. Новый код НЕ запрашивает."""
    r = await read_login_code_ex(session)
    return r["code"] if (not r["err"] and not r["old"]) else None


async def read_login_code(session: str):
    """-> (code, err)"""
    r = await read_login_code_ex(session)
    return r["code"], r["err"]


def _claim_kb():
    return InlineKeyboardMarkup([[btn("📱 ПОЛУЧИТЬ НОМЕР", "gift_claim")]])


async def gift_claim(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    rows = gift_open_for_user(uid)
    if not rows:
        await q.edit_message_text("📭 Нет неиспользованных подарков.")
        return
    rows.sort(key=lambda r: 0 if r[1] else 1)  # сначала уже выданный номер
    gid = rows[0][0]
    res = gift_assign_number(gid)
    if not res:
        await q.edit_message_text(
            "⏳ Свободных номеров сейчас нет. Подарок сохранён — попробуй чуть позже.",
            reply_markup=_claim_kb())
        await notify_admins(
            context.bot,
            f"⚠️ Нет свободных номеров для подарка (юзер `{uid}`).",
            parse_mode="Markdown")
        return
    _, phone, _ = res
    phone = fmt_phone(phone)
    await q.edit_message_text(
        f"📱 *ТВОЙ НОМЕР*\n\n`{phone}`\n\n"
        f"👉 Введи этот номер в Telegram.\n"
        f"Когда придёт код — нажми *«Получить код»*.\n"
        f"Когда войдёшь — нажми *«Код подошёл»*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("📨 ПОЛУЧИТЬ КОД", f"gcode_{gid}")],
            [btn("✅ КОД ПОДОШЁЛ", f"gok_{gid}")],
        ]))


async def gift_code(update, context):
    q = update.callback_query
    await q.answer("⏳ Читаю код...")
    gid = int(q.data.split("_")[1])
    g = gift_get(gid)
    if not g or g[1] != q.from_user.id or g[3] != "assigned":
        await q.answer("❌ Недоступно", show_alert=True)
        return
    row = get_number_by_id(g[2])
    if not row:
        await q.edit_message_text("❌ Номер не найден.")
        return
    _, _, phone, session, _ = row
    phone = fmt_phone(phone)
    rr = await read_login_code_ex(session)
    code, err = rr["code"], rr["err"]
    if err:
        body = f"❌ Ошибка: `{err}`\n\nПопробуй ещё раз."
    elif not code:
        body = ("📭 *Кодов в чате Telegram нет*\n\nВведи номер в Telegram, дождись кода "
                "и нажми кнопку ещё раз.")
    else:
        body = (f"🔑 *КОД:*  `{code}`\n\n"
                + ("⚠️ Это старый код — введи номер в Telegram и нажми «Получить код ещё».\n"
                   if rr["old"] else "Введи его в Telegram."))
    kb = InlineKeyboardMarkup([
        [btn("📨 ПОЛУЧИТЬ КОД ЕЩЁ", f"gcode_{gid}")],
        [btn("✅ КОД ПОДОШЁЛ", f"gok_{gid}")],
    ])
    try:
        await q.edit_message_text(f"📱 `{phone}`\n\n{body}",
                                  parse_mode="Markdown", reply_markup=kb)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def gift_ok(update, context):
    q = update.callback_query
    await q.answer("✅ Ок")
    gid = int(q.data.split("_")[1])
    g = gift_get(gid)
    if not g or g[1] != q.from_user.id:
        await q.answer("❌ Недоступно", show_alert=True)
        return
    phone = gift_finish(gid)
    if phone is None:
        await q.edit_message_text("✅ Уже завершено.")
        return
    await q.edit_message_text("✅ Готово! Номер выдан и удалён из базы.")
    await notify_admins(
        context.bot,
        f"✅ *КОД ПОДОШЁЛ (подарок)*\n\n📱 `{phone}`\n👤 `{q.from_user.id}`\n"
        f"Номер удалён из базы.",
        parse_mode="Markdown")


# ═══════════ ОПЛАТА ПОДАРКАМИ ═══════════
GIFT_PRICE_STARS = 50          # запасная цена в ⭐, если у номера цена в звёздах не задана (обычно берётся цена самого номера)
GIFT_ORDER_TTL = 60 * 60       # сколько живёт заказ после нажатия «Оплатить подарками», сек
GIFT_LEGACY_CLAIM = False      # True: старый режим — любой подарок открывает «ПОЛУЧИТЬ НОМЕР» из автозакупа
GIFT_ACCOUNT: Dict[str, Any] = {}   # аккаунт, который принимает подарки (заполняется при старте)


def gift_price_of(price_stars) -> int:
    """Цена номера в ⭐ при оплате подарками = цена в звёздах, которую ты задал номеру."""
    try:
        v = int(price_stars)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else GIFT_PRICE_STARS


def _gift_pay_db():
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS gift_wallet (
            user_id INTEGER PRIMARY KEY, stars INTEGER NOT NULL DEFAULT 0)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS gift_payments (
            user_id INTEGER, msg_id INTEGER, title TEXT, stars INTEGER, created REAL,
            PRIMARY KEY (user_id, msg_id))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS gift_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER,
            need INTEGER, status TEXT DEFAULT 'pending', created REAL)""")


def gift_wallet_get(uid: int) -> int:
    _gift_pay_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        row = conn.execute("SELECT stars FROM gift_wallet WHERE user_id=?", (uid,)).fetchone()
    return row[0] if row else 0


def gift_wallet_add(msg_id: int, uid: int, title: str, stars: int) -> Optional[int]:
    """Зачисляет подарок на баланс. -> новый баланс, None — если подарок уже был учтён."""
    _gift_pay_db()
    conn = sqlite3.connect(DB_NAME, timeout=10, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO gift_payments (user_id, msg_id, title, stars, created) VALUES (?,?,?,?,?)",
                         (uid, msg_id, title, stars, time.time()))
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return None
        conn.execute("INSERT INTO gift_wallet (user_id, stars) VALUES (?, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET stars = stars + ?", (uid, stars, stars))
        bal = conn.execute("SELECT stars FROM gift_wallet WHERE user_id=?", (uid,)).fetchone()[0]
        conn.execute("COMMIT")
        return bal
    except Exception as e:
        logger.error(f"[GIFTPAY] wallet_add: {e}")
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return None
    finally:
        conn.close()


def gift_order_create(uid: int, product_id: int, need: int) -> int:
    _gift_pay_db()
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("UPDATE gift_orders SET status='cancelled' WHERE user_id=? AND status='pending'", (uid,))
        cur = conn.execute("INSERT INTO gift_orders (user_id, product_id, need, status, created) "
                           "VALUES (?,?,?, 'pending', ?)", (uid, product_id, need, time.time()))
        return cur.lastrowid


def gift_try_deliver(uid: int) -> Dict[str, Any]:
    """Если у пользователя есть активный заказ и на балансе хватает — списывает цену и закрывает заказ."""
    _gift_pay_db()
    conn = sqlite3.connect(DB_NAME, timeout=10, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT stars FROM gift_wallet WHERE user_id=?", (uid,)).fetchone()
        bal = row[0] if row else 0
        o = conn.execute("SELECT id, product_id, need, created FROM gift_orders "
                         "WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        if not o:
            conn.execute("ROLLBACK")
            return {"state": "no_order", "balance": bal}
        oid, pid, need, created = o
        if time.time() - created > GIFT_ORDER_TTL:
            conn.execute("UPDATE gift_orders SET status='expired' WHERE id=?", (oid,))
            conn.execute("COMMIT")
            return {"state": "expired", "balance": bal}
        if bal < need:
            conn.execute("ROLLBACK")
            return {"state": "need_more", "balance": bal, "need": need, "product_id": pid}
        if not get_phone_product(pid):
            conn.execute("UPDATE gift_orders SET status='cancelled' WHERE id=?", (oid,))
            conn.execute("COMMIT")
            return {"state": "gone", "balance": bal}
        conn.execute("UPDATE gift_wallet SET stars = stars - ? WHERE user_id=?", (need, uid))
        conn.execute("UPDATE gift_orders SET status='done' WHERE id=?", (oid,))
        conn.execute("COMMIT")
        return {"state": "done", "product_id": pid, "need": need, "balance": bal - need}
    except Exception as e:
        logger.error(f"[GIFTPAY] try_deliver: {e}")
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return {"state": "error", "balance": 0}
    finally:
        conn.close()


def _gift_set_account(me):
    if not me:
        return
    uname = getattr(me, "username", None)
    name = getattr(me, "first_name", None) or "аккаунт"
    GIFT_ACCOUNT["id"] = getattr(me, "id", None)
    GIFT_ACCOUNT["label"] = f"@{uname}" if uname else f"{name} (id {GIFT_ACCOUNT['id']})"


async def gift_account_label() -> Optional[str]:
    if GIFT_ACCOUNT.get("label"):
        return GIFT_ACCOUNT["label"]
    session = get_primary_session()
    if not session:
        return None
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), 20)
        if not await client.is_user_authorized():
            return None
        _gift_set_account(await client.get_me())
        return GIFT_ACCOUNT.get("label")
    except Exception as e:
        logger.warning(f"[GIFTPAY] не узнал аккаунт для подарков: {e}")
        return None
    finally:
        await _disconnect(client)


def _md_escape(t: str) -> str:
    return t.replace("_", "\\_")


async def _gift_tell(application, client, uid, text, reply_markup=None):
    try:
        await application.bot.send_message(uid, text, parse_mode="Markdown", reply_markup=reply_markup)
        return
    except Exception as e:
        logger.warning(f"[GIFTPAY] бот не смог написать {uid}: {e}")
    if client is not None:
        try:
            await client.send_message(uid, f"🎁 Подарок получен! Откройте бота @{application.bot.username} "
                                           f"и нажмите /start — номер выдадим там.")
        except Exception as e:
            logger.warning(f"[GIFTPAY] и аккаунт не смог написать {uid}: {e}")


async def _gift_deliver(application, uid: int, res: Dict[str, Any]):
    """Выдаёт номер после успешной оплаты подарками."""
    pid, need = res["product_id"], res["need"]
    _p = get_phone_product(pid)
    phone_full = _p[1] if _p else "?"
    await auto_deliver_product(uid, pid, paid_text=f"🎁 Оплачено подарками: {need}⭐")
    logger.info(f"[GIFTPAY] {uid}: номер выдан за подарки ({need}⭐), остаток {res['balance']}⭐")
    await notify_admins(application.bot,
                        f"✅ *ПРОДАЖА ЗА ПОДАРКИ*\n\n👤 `{uid}`\n📱 Номер: `{phone_full}`\n🆔 товар {pid}\n⭐ {need}",
                        parse_mode="Markdown")


async def _gift_pay_on_gift(application, client, msg_id: int, uid: int, title: str, stars: int):
    bal = gift_wallet_add(msg_id, uid, title, stars)
    if bal is None:
        return
    logger.info(f"[GIFTPAY] {uid}: подарок «{title}» {stars}⭐, баланс {bal}⭐")
    phone_line = ""
    try:
        with sqlite3.connect(DB_NAME, timeout=10) as _c:
            _o = _c.execute("SELECT product_id FROM gift_orders WHERE user_id=? AND status='pending' "
                            "ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        _p = get_phone_product(_o[0]) if _o else None
        if _p:
            phone_line = f"\n📱 Номер: `{_p[1]}`"
    except Exception as e:
        logger.warning(f"[GIFTPAY] не удалось узнать номер для уведомления: {e}")
    await notify_admins(application.bot,
                        f"🎁 *ПОДАРОК (оплата)*\n\n👤 `{uid}`{phone_line}\n{title}, ⭐ {stars}\nБаланс подарков: {bal}⭐",
                        parse_mode="Markdown")
    res = gift_try_deliver(uid)
    st = res["state"]
    if st == "done":
        await _gift_deliver(application, uid, res)
    elif st == "need_more":
        left = res["need"] - res["balance"]
        await _gift_tell(application, client, uid,
                         f"🎁 Подарок получен: {stars}⭐\n"
                         f"Накоплено: *{res['balance']}⭐* из *{res['need']}⭐*.\n"
                         f"Отправьте ещё подарки на *{left}⭐* — и номер придёт автоматически.")
    elif st == "gone":
        await _gift_tell(application, client, uid,
                         f"⚠️ Номер, который вы выбрали, уже продан. Подарки не потеряны: на балансе "
                         f"*{res['balance']}⭐*. Выберите другой номер и нажмите «Оплатить подарками».")
    elif st == "expired":
        await _gift_tell(application, client, uid,
                         f"⌛ Заказ устарел, но подарок засчитан: на балансе *{res['balance']}⭐*. "
                         f"Выберите номер в магазине и нажмите «Оплатить подарками» — баланс зачтётся.")
    else:  # нет заказа
        await _gift_tell(application, client, uid,
                         f"🎁 Подарок получен: {stars}⭐. На балансе *{bal}⭐*.\n"
                         f"Выберите номер в магазине и нажмите «Оплатить подарками» — баланс зачтётся.")


# цена подарка в ⭐ -> какие подарки столько стоят (для подсказок покупателю; правь под свои цены)
GIFT_CATALOG = {
    100: ["💍 кольцо", "💎 кристалл"],
    50: ["🚀 ракета"],
    25: ["🌹 роза", "🍾 шампанское", "🎂 торт", "🎁 подарок"],
    15: ["❤️ сердечко"],
}


def gift_breakdowns(total: int, max_options: int = 4):
    """Варианты, из каких подарков набрать сумму. Возвращает (сумма, [строки]).
    Если ровно набрать нельзя — берёт ближайшую большую сумму."""
    prices = sorted(GIFT_CATALOG, reverse=True)

    def combos(target):
        out = []

        def rec(i, left, cur):
            if i == len(prices):
                if left == 0:
                    out.append(dict(cur))
                return
            pr = prices[i]
            for n in range(left // pr + 1):
                cur[pr] = n
                rec(i + 1, left - n * pr, cur)
            cur[pr] = 0

        rec(0, target, {})
        return out

    total = max(int(total), 1)
    target, found = total, []
    for t in range(total, total + 100):
        found = combos(t)
        if found:
            target = t
            break
    # меньше подарков — выше; при равенстве — разнообразнее (ракета/роза/сердечко)
    found.sort(key=lambda c: (sum(c.values()), -max(k for k, v in c.items() if v)))
    lines = []
    for c in found[:max_options]:
        parts = []
        for pr in prices:
            n = c.get(pr, 0)
            if n:
                name = GIFT_CATALOG[pr][0]
                parts.append(f"{n} × {name} ({pr}⭐)" if n > 1 else f"{name} ({pr}⭐)")
        lines.append("• " + " + ".join(parts))
    return target, lines


def gift_hint_text(left: int) -> str:
    """Текст-подсказка «чем заплатить» на сумму left ⭐."""
    target, lines = gift_breakdowns(left)
    extra = ""
    if target != left:
        extra = f"\n_(ровно {left}⭐ набрать нельзя, ближайшая сумма — {target}⭐; остаток сохранится на балансе)_"
    any_lines = []
    for pr in sorted(GIFT_CATALOG, reverse=True):
        names = GIFT_CATALOG[pr]
        if len(names) > 1 and f"({pr}⭐)" in "".join(lines):
            any_lines.append(f"за {pr}⭐ подойдёт любой: " + ", ".join(names))
    return ("Варианты на *" + str(target) + "⭐*:\n" + "\n".join(lines) + extra
            + ("\n\n" + "\n".join(any_lines) if any_lines else ""))


async def pay_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    product_id = int(q.data.split("_")[2])
    if not _GIFT_ACTIONS:
        await q.edit_message_text("❌ Оплата подарками сейчас недоступна. Выберите другой способ.",
                                  reply_markup=back(f"select_phone_{product_id}"))
        return
    product = get_phone_product(product_id)
    if not product:
        await q.edit_message_text("❌ Номер уже продан или удалён", reply_markup=back("shop"))
        return
    acc = await gift_account_label()
    if not acc:
        await q.edit_message_text("❌ Приём подарков временно недоступен. Попробуйте позже или выберите другой способ.",
                                  reply_markup=back(f"select_phone_{product_id}"))
        return
    need_stars = gift_price_of(product[3])
    gift_order_create(uid, product_id, need_stars)
    res = gift_try_deliver(uid)          # вдруг подарки уже были отправлены раньше
    if res["state"] == "done":
        await q.edit_message_text("✅ Подарки найдены — выдаю номер…")
        await _gift_deliver(context.application, uid, res)
        return
    phone = product[1]
    hidden = phone
    bal = res.get("balance", 0)
    left = max(need_stars - bal, 0)
    await q.edit_message_text(
        f"🎁 *ОПЛАТА ПОДАРКАМИ*\n\n📱 Номер: `{hidden}`\n💰 Цена: *{need_stars}⭐*\n"
        + (f"✅ Уже на балансе: {bal}⭐\n" if bal else "") +
        f"\nОтправьте подарки аккаунту *{_md_escape(acc)}* на сумму не меньше *{left}⭐*.\n\n"
        f"{gift_hint_text(left)}\n\n"
        f"Бот сам увидит подарок от вашего аккаунта и сразу выдаст номер. "
        f"Заказ действует {GIFT_ORDER_TTL // 60} минут.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("🔄 ПРОВЕРИТЬ ОПЛАТУ", "gpay_check")],
            [btn("🔙 НАЗАД", f"select_phone_{product_id}")],
        ]))


async def gift_pay_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    res = gift_try_deliver(uid)
    st = res["state"]
    if st == "done":
        await q.answer("✅ Оплачено!")
        await _gift_deliver(context.application, uid, res)
    elif st == "need_more":
        await q.answer(f"Пока получено {res['balance']}⭐ из {res['need']}⭐. "
                       f"Отправьте ещё на {res['need'] - res['balance']}⭐.", show_alert=True)
    elif st == "gone":
        await q.answer("Этот номер уже продан. Баланс подарков сохранён — выберите другой.", show_alert=True)
    elif st == "expired":
        await q.answer("Заказ устарел. Выберите номер заново — баланс подарков сохранён.", show_alert=True)
    else:
        await q.answer("Активного заказа нет. Выберите номер и нажмите «Оплатить подарками».", show_alert=True)


_GIFT_ACTIONS = tuple(
    getattr(types, n) for n in ("MessageActionStarGift", "MessageActionStarGiftUnique")
    if hasattr(types, n))


async def _handle_gift_update(update, client, application):
    msg = getattr(update, "message", None)
    action = getattr(msg, "action", None)
    if action is None or not isinstance(action, _GIFT_ACTIONS):
        return
    if getattr(msg, "out", False):
        return
    uid = getattr(getattr(msg, "peer_id", None), "user_id", None)
    if not uid:
        return
    gift = getattr(action, "gift", None)
    stars = getattr(gift, "stars", None)
    title = getattr(gift, "title", None) or f"id {getattr(gift, 'id', '?')}"

    # оплата подарками: звёзды идут на баланс пользователя, выдача — автоматически
    if isinstance(stars, int) and stars > 0:
        await _gift_pay_on_gift(application, client, msg.id, uid, str(title), stars)
    else:
        await notify_admins(application.bot,
                            f"🎁 Подарок от `{uid}` не засчитан (нет цены в ⭐, возможно улучшенный): {title}",
                            parse_mode="Markdown")
    if not GIFT_LEGACY_CLAIM:
        return

    if GIFT_ALLOWED_STARS is not None and stars not in GIFT_ALLOWED_STARS:
        await notify_admins(
            application.bot,
            f"🎁 Подарок от `{uid}` проигнорирован (не из списка): "
            f"{title}, ⭐ {stars}", parse_mode="Markdown")
        return

    gid = gift_add(msg.id, uid, str(title), stars)
    if gid is None:
        return
    await notify_admins(
        application.bot,
        f"🎁 *ПОДАРОК*\n\n👤 `{uid}`\n{title}, ⭐ {stars}\nДоступ к номеру открыт.",
        parse_mode="Markdown")
    try:
        await application.bot.send_message(
            uid, "🎁 Подарок получен! Нажми кнопку, чтобы получить номер.",
            reply_markup=_claim_kb())
    except Exception:
        # человек ещё не запускал бота — пишем ему с аккаунта и даём ссылку
        try:
            await client.send_message(
                uid, f"🎁 Спасибо за подарок! Напиши боту @{application.bot.username} "
                     f"и нажми /start — там получишь номер.")
        except Exception as e:
            logger.warning(f"[GIFT] Не удалось уведомить {uid}: {e}")


async def gift_listener(application):
    """Слушает личные сообщения стартовой сессии и ловит подарки."""
    if not _GIFT_ACTIONS:
        logger.info("[GIFT] приём подарков выключен (старый Telethon). Чтобы включить: pip install -U telethon")
        return
    while True:
        session = get_primary_session()
        if not session:
            await asyncio.sleep(60)
            continue
        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.error("[GIFT] Стартовая сессия не авторизована")
                await asyncio.sleep(300)
                continue

            @client.on(events.Raw(types.UpdateNewMessage))
            async def _on_raw(update):
                try:
                    await _handle_gift_update(update, client, application)
                except Exception as e:
                    logger.error(f"[GIFT] handler error: {e}")

            try:
                _gift_set_account(await client.get_me())
            except Exception as e:
                logger.warning(f"[GIFT] get_me: {e}")
            logger.info("🎁 Слушаю подарки")
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[GIFT] listener error: {e}")
        finally:
            await _disconnect(client)
        await asyncio.sleep(30)


# ═══════════ ПРОВЕРКИ ИЗ МЕНЮ ═══════════
async def run_check_now(update, context):
    q = update.callback_query
    await q.answer("⏳...")
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    due = get_due_numbers()
    if not due:
        await q.edit_message_text(
            "✅ Нет просроченных.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
        return
    await q.edit_message_text(
        f"⏳ Проверяю {len(due)}...",
        reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
    market = make_market() if _lzt_available else None
    app = context.application
    for number_id, item_id, phone, session in due:
        await verify_alive(number_id, item_id, phone, session, market, app)
        await asyncio.sleep(5)
    await bz_return_main_menu(context.bot, q.message.chat_id)


async def check_all_now(update, context):
    q = update.callback_query
    await q.answer("⏳...")
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return

    rows = get_all_bought()
    if not rows:
        await q.edit_message_text(
            "📭 Купленных аккаунтов нет.",
            reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
        return

    _STOP_FLAGS["check"] = False
    stop_kb = InlineKeyboardMarkup([[btn("⏹ ЗАВЕРШИТЬ ПРОВЕРКУ", "stop_check")]])
    msg = await q.edit_message_text(
        f"🔍🔒 Проверяю и завершаю сессии у {len(rows)} аккаунтов...",
        reply_markup=stop_kb)
    stopped = False

    market = make_market() if _lzt_available else None
    app = context.application
    secured, alive, dead, unknown = 0, 0, 0, 0

    for i, (nid, item_id, phone, sess) in enumerate(rows, 1):
        if _STOP_FLAGS["check"]:
            stopped = True
            break
        try:
            await context.bot.edit_message_text(
                chat_id=msg.chat_id, message_id=msg.message_id,
                text=(f"🔍🔒 Проверка {i}/{len(rows)}\n\n"
                      f"📱 {phone}\n\n"
                      f"🔒 Защищено: {secured}\n"
                      f"✅ Живых: {alive}\n"
                      f"❌ Мёртвых: {dead}\n"
                      f"⚠️ Неизвестно: {unknown}"),
                reply_markup=stop_kb)
        except Exception:
            pass

        result = await verify_and_secure(nid, item_id, phone, sess, market, app)

        if result == "secured":
            secured += 1
        elif result == "alive":
            alive += 1
        elif result == "dead":
            dead += 1
        else:
            unknown += 1

        await asyncio.sleep(1)

    try:
        await context.bot.edit_message_text(
            chat_id=msg.chat_id, message_id=msg.message_id,
            text=(("⏹ ПРОВЕРКА ОСТАНОВЛЕНА\n\n" if stopped else
                   "📊 ПРОВЕРКА + ЗАВЕРШЕНИЕ СЕССИЙ\n\n") +
                  f"🔒 Защищено (чужие сессии убиты): {secured}\n"
                  f"✅ Живых (завершить не удалось): {alive}\n"
                  f"❌ Мёртвых (удалено): {dead}\n"
                  f"⚠️ Неизвестно: {unknown}"),
            reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))
    except Exception:
        pass
    await bz_return_main_menu(context.bot, msg.chat_id)


SPAM_APPEAL_TEXT = (
    "Hello,\n\n"
    "I am writing to appeal the spam-related restriction placed on my account. "
    "I believe this restriction was applied in error. I have not violated the platform rules "
    "and do not violate them. I did not use my account for spam, unsolicited messages, "
    "or any prohibited automated activity.\n\n"
    "If my account was flagged automatically, please review this decision manually.\n\n"
    "Please reconsider the spam block and remove the restrictions from my account as soon as possible.\n\n"
    "Thank you for your time and assistance."
)


async def bz_appeal(update, context):
    """Присылает текст апелляции для @SpamBot (в моноширинном блоке — копируется нажатием)."""
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer()
    await q.message.reply_text(
        "📝 *АПЕЛЛЯЦИЯ ПРОТИВ СПАМ-БЛОКА*\n\n"
        "Откройте @SpamBot → `/start` → выберите пункт «это ошибка» и отправьте текст ниже "
        "(нажмите на него, чтобы скопировать):\n\n"
        f"```\n{SPAM_APPEAL_TEXT}\n```",
        parse_mode="Markdown")


def bz_menu_kb():
    return InlineKeyboardMarkup([
        [btn("🛒 ЗАКУПИТЬ", "buy_start"), btn("📱 ПОЛУЧИТЬ НОМЕРА", "get_numbers")],
        [btn("📊 СТАТИСТИКА", "stats_show"), btn("📋 НОМЕРА", "list_numbers")],
        [btn("🔍 24Ч", "run_check"), btn("🔎 ВСЕ", "check_all")],
        [btn("➕ НОМЕР ВРУЧНУЮ", "manual_add"), btn("🧹 ОЧИСТКА АККАУНТОВ", "wipe_all")],
        [btn("🛡 ПРОВЕРИТЬ СПАМ-БЛОК", "bz_spamcheck"), btn("📜 ИСТОРИЯ", "bz_history")],
        [btn("📝 АПЕЛЛЯЦИЯ ДЛЯ @SpamBot", "bz_appeal")],
        [btn("📤 ЗАГРУЗИТЬ БАЗУ (.db)", "bz_db_upload"), btn("🏪 В МАГАЗИН", "bz_shop_sync")],
        [btn("🚀 ВЫГРУЗИТЬ ВСЁ В МАГАЗИН", "bz_shop_all")],
        [btn("🔑 ВХОД В СТАРТОВЫЙ АККАУНТ", "bz_primary_login")],
        [btn("📲 ВХОД ПО ССЫЛКЕ (без кода)", "bz_primary_qr")],
        [btn("🔙 В АДМИН-ПАНЕЛЬ", "admin_panel")],
    ])


def _db_counts(path: str) -> str:
    """Краткая сводка по sqlite-файлу: какие таблицы и сколько строк."""
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as c:
            tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            parts = []
            for t in tabs:
                if t.startswith("sqlite_"):
                    continue
                n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                if t in ("phone_products", "numbers", "purchases", "gift_access", "admins"):
                    parts.append(f"{t}={n}")
            return ", ".join(parts) or "нужных таблиц нет"
    except Exception as e:
        return f"не открылся ({str(e)[:40]})"


async def dbinfo_cmd(update, context):
    if not is_main_admin(update.effective_user.id):
        return
    lines = ["🩺 ДИАГНОСТИКА БАЗ", "",
             f"Магазин: {DB_NAME}", f"  {_db_counts(DB_NAME)}",
             f"Автозакуп: {BZ_DB_NAME}", f"  {_db_counts(BZ_DB_NAME)}"]
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as c:
            st = c.execute("SELECT status, COUNT(*) FROM numbers WHERE is_primary=0 GROUP BY status").fetchall()
            unl = c.execute("SELECT COUNT(*) FROM numbers WHERE is_primary=0 AND COALESCE(shop_listed,0)=0").fetchone()[0]
        lines.append("  статусы номеров: " + (", ".join(f"{a}={b}" for a, b in st) or "пусто"))
        lines.append(f"  ещё не выложено в магазин: {unl}")
    except Exception as e:
        lines.append(f"  ошибка чтения: {e}")
    seen = {os.path.abspath(DB_NAME), os.path.abspath(BZ_DB_NAME)}
    dirs = {os.path.dirname(os.path.abspath(DB_NAME)), os.path.dirname(os.path.abspath(BZ_DB_NAME)),
            os.path.dirname(os.path.abspath(__file__)), os.getcwd()}
    others = []
    for d in dirs:
        try:
            for f in sorted(os.listdir(d)):
                fp = os.path.join(d, f)
                if f.endswith((".db", ".sqlite", ".sqlite3")) and os.path.abspath(fp) not in seen:
                    seen.add(os.path.abspath(fp))
                    others.append(f"{fp}\n  {_db_counts(fp)}")
        except Exception:
            pass
    lines.append("")
    lines.append("Другие базы рядом:" if others else "Других баз рядом нет.")
    lines.extend(others)
    if others:
        lines.append("")
        lines.append("Перенести номера из другой базы: /import_db ПОЛНЫЙ_ПУТЬ")
    await update.message.reply_text("\n".join(lines)[:4000])


def _import_db_sync(src: str) -> List[str]:
    """Копирует номера магазина, номера автозакупа и покупки из файла базы src. Возвращает строки отчёта."""
    report = []
    deleted_keys = {k for k, d in bz_decisions_map().items() if d == "deleted"}
    plan = [(DB_NAME, "phone_products", "phone"), (DB_NAME, "purchases", None), (BZ_DB_NAME, "numbers", "phone")]
    for dst, table, key in plan:
        try:
            with sqlite3.connect(dst, timeout=10) as c:
                c.create_function("bz_is_deleted", 1, lambda ph: 1 if _digits(ph or "") in deleted_keys else 0)
                c.execute("ATTACH DATABASE ? AS src", (src,))
                have = c.execute("SELECT name FROM src.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not have:
                    report.append(f"{table}: в файле нет")
                    continue
                dcols = [r[1] for r in c.execute(f'PRAGMA main.table_info("{table}")').fetchall()]
                scols = [r[1] for r in c.execute(f'PRAGMA src.table_info("{table}")').fetchall()]
                cols = [x for x in dcols if x in scols and x != "id"]
                if not cols:
                    report.append(f"{table}: колонки не совпали")
                    continue
                cl = ", ".join(f'"{x}"' for x in cols)
                before = c.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
                if key:
                    c.execute(f'INSERT INTO main."{table}" ({cl}) SELECT {cl} FROM src."{table}" s '
                              f'WHERE NOT bz_is_deleted(s."{key}") AND '
                              f'NOT EXISTS (SELECT 1 FROM main."{table}" m WHERE m."{key}" = s."{key}")')
                elif "user_id" in cols and "phone" in cols:
                    c.execute(f'INSERT INTO main."{table}" ({cl}) SELECT {cl} FROM src."{table}" s '
                              f'WHERE NOT EXISTS (SELECT 1 FROM main."{table}" m '
                              f'WHERE m.user_id = s.user_id AND m.phone = s.phone)')
                else:
                    c.execute(f'INSERT INTO main."{table}" ({cl}) SELECT {cl} FROM src."{table}"')
                after = c.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
                c.commit()
                c.execute("DETACH DATABASE src")
                report.append(f"{table}: добавлено {after - before}")
        except Exception as e:
            report.append(f"{table}: ошибка {str(e)[:80]}")
    try:
        _mark_ts = ts(datetime.now() - timedelta(hours=26))
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            conn.execute("UPDATE numbers SET bought_at=COALESCE(bought_at, ?), next_check_at=COALESCE(next_check_at, ?) "
                         "WHERE is_primary=0 AND status IN ('active','alive')", (_mark_ts, ts()))
    except Exception as e:
        logger.error(f"[IMPORT] метки проверки: {e}")
    try:
        added, failed = bz_sync_shop()
        report.append(f"выложено в магазин: {added} (ещё ждут 25-часовой проверки: {failed})")
    except Exception as e:
        report.append(f"выкладка: ошибка {str(e)[:60]}")
    return report


async def import_db_cmd(update, context):
    """/import_db путь — то же, что отправка файла .db боту, но по пути на сервере."""
    if not is_main_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Проще: отправь мне файл .db прямо в чат.\nИли: /import_db /полный/путь/к/базе.db\nСписок баз: /dbinfo")
        return
    src = " ".join(context.args).strip().strip('"')
    if not os.path.isfile(src):
        await update.message.reply_text(f"❌ Файл не найден: {src}")
        return
    if os.path.abspath(src) in (os.path.abspath(DB_NAME), os.path.abspath(BZ_DB_NAME)):
        await update.message.reply_text("Это текущая база, переносить нечего.")
        return
    report = await asyncio.to_thread(_import_db_sync, src)
    await update.message.reply_text("📥 Импорт из " + src + "\n" + "\n".join(report))


async def bz_db_upload_prompt(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        return
    await q.message.reply_text(
        "📤 *ЗАГРУЗКА БАЗЫ*\n\n"
        "Отправь мне сюда файл базы с номерами (например `lzt_numbers.db`) как документ. "
        "Я перенесу из него номера в базу бота, выложу их в магазин по странам и верну отчёт.\n\n"
        "Дубли не добавляются, текущие данные не стираются.",
        parse_mode="Markdown")


async def db_file_received(update, context):
    """Админ прислал файл .db → импорт номеров и выкладка в магазин."""
    msg = update.message
    if not msg or not msg.document or not is_main_admin(update.effective_user.id):
        return
    doc = msg.document
    name = (doc.file_name or "").lower()
    if not name.endswith((".db", ".sqlite", ".sqlite3")):
        return
    if (doc.file_size or 0) > 19 * 1024 * 1024:
        await msg.reply_text("❌ Файл больше 19 МБ — Telegram не даёт боту его скачать. "
                             "Загрузи на хостинг вручную и используй /import_db путь.")
        return
    tmp = os.path.join(os.path.dirname(os.path.abspath(BZ_DB_NAME)), "_incoming_import.db")
    status = await msg.reply_text("⏳ Скачиваю и импортирую базу…")
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(tmp)
        with open(tmp, "rb") as f:
            if not f.read(16).startswith(b"SQLite format 3"):
                await status.edit_text("❌ Это не файл базы SQLite.")
                return
        report = await asyncio.to_thread(_import_db_sync, tmp)
        await status.edit_text("📥 *БАЗА ЗАГРУЖЕНА*\n\n" + "\n".join(report)
                               + "\n\nПроверь: /dbinfo", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"[DBFILE] {e}")
        await status.edit_text(f"❌ Ошибка импорта: {str(e)[:200]}")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


async def webtest_cmd(update, context):
    """/webtest — бот сам отправляет тестовое уведомление на публичную ссылку вебхука и смотрит, дошло ли оно."""
    if not is_main_admin(update.effective_user.id):
        return
    url = context.args[0] if context.args else YOOMONEY_WEBHOOK_URL
    payload = {"notification_type": "card-incoming", "operation_id": "test-notification",
               "amount": "50.00", "currency": "643", "datetime": "2026-01-01T00:00:00Z",
               "sender": "", "codepro": "false", "label": "", "test_notification": "true",
               "sha1_hash": "selftest"}
    before = _REQ_COUNT["post"]
    wait_msg = await update.message.reply_text("⏳ Отправляю тестовый запрос на публичную ссылку…")

    def _post():
        r = requests.post(url, data=payload, timeout=20)
        return r.status_code, (r.text or "")[:150].replace("\n", " ")

    try:
        status, body = await asyncio.to_thread(_post)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ссылка не отвечает: {str(e)[:200]}\n\nХостинг не принимает запросы по этому адресу.")
        return
    await asyncio.sleep(2)
    arrived = _REQ_COUNT["post"] > before
    if status == 200 and arrived:
        verdict = "✅ Запрос дошёл до бота. Если сообщения о тесте нет — смотри логи на «❌ Ошибка отправки»."
    elif status == 200:
        verdict = ("⚠️ Шлюз хостинга ответил 200, но боту запрос НЕ передал: он отправляет его не на порты бота. "
                   "Спроси у поддержки хостинга, куда он пересылает webhook p50.")
    elif status in (401, 403):
        verdict = "⚠️ Шлюз отверг запрос (доступ). Проверь секрет/ссылку в панели хостинга."
    elif status in (404, 405):
        verdict = "⚠️ Шлюз не принимает такой запрос по этому адресу (ссылка не подключена или неверный путь)."
    elif status >= 500:
        verdict = "⚠️ Шлюз получил запрос, но бот/порт не отвечает (5xx). Бот должен слушать порт, на который идёт webhook."
    else:
        verdict = f"⚠️ Неожиданный ответ шлюза: {status}."
    await wait_msg.edit_text(f"🧪 Самопроверка вебхука\nURL: {url}\nОтвет шлюза: {status} {body}\n"
                             f"Дошло до бота: {'да' if arrived else 'нет'}\n\n{verdict}")


async def web_cmd(update, context):
    """/web — показывает, дошли ли до бота запросы от ЮMoney (без чтения логов хостинга)."""
    if not is_main_admin(update.effective_user.id):
        return
    last = "\n".join(_RECENT_REQUESTS) or "ни одного запроса ещё не приходило"
    await update.message.reply_text(
        f"🌐 Веб-сервер оплаты\nПорты: {', '.join(map(str, _WEB_PORTS_OPEN)) or 'не запущен'}\n\n"
        f"Последние входящие запросы:\n{last}\n\n"
        "Нажми в ЮMoney «Протестировать» и снова отправь /web: если список пустой, "
        "хостинг не доставляет вебхук боту.")


async def wallet_cmd(update, context):
    """/wallet НОМЕР — задать кошелёк ЮMoney для приёма оплаты (хранится в базе)."""
    if not is_main_admin(update.effective_user.id):
        return
    cur = get_yoomoney_wallet()
    if not context.args:
        await update.message.reply_text(
            f"💳 Кошелёк ЮMoney сейчас: {cur or 'не задан'}\n\n"
            "Задать: /wallet 4100123456789012\n(номер кошелька — в приложении ЮMoney, обычно начинается с 4100)")
        return
    num = "".join(ch for ch in context.args[0] if ch.isdigit())
    if not (11 <= len(num) <= 20):
        await update.message.reply_text("❌ Номер кошелька — это 11–20 цифр, например 4100123456789012.")
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('yoomoney_wallet', ?)", (num,))
    await context.bot.send_message(update.effective_chat.id,
        f"✅ Кошелёк ЮMoney сохранён: {num}\nОплата рублями теперь идёт на него.")


# ═══════════ ПАМЯТЬ: какие аккаунты удалены, какие оставлены ═══════════
def bz_remember(phone, decision: str, reason: str = "") -> None:
    """Запоминает решение по аккаунту: 'deleted' (удалён/продан/выдан) или 'kept' (оставлен)."""
    try:
        key = _digits(phone)
        if len(key) < 7:
            return
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS account_decisions (phone TEXT PRIMARY KEY, decision TEXT, reason TEXT, at TEXT)")
            conn.execute("INSERT OR REPLACE INTO account_decisions (phone, decision, reason, at) VALUES (?,?,?,?)",
                         (key, decision, reason, ts()))
    except Exception as e:
        logger.error(f"[MEMORY] {phone}: {e}")


def bz_forget(phone) -> None:
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            conn.execute("DELETE FROM account_decisions WHERE phone=?", (_digits(phone),))
    except Exception as e:
        logger.error(f"[MEMORY] forget {phone}: {e}")


def bz_decisions_map() -> Dict[str, str]:
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            return {p: d for p, d in conn.execute("SELECT phone, decision FROM account_decisions").fetchall()}
    except Exception:
        return {}


# ═══════════ ПРОВЕРКА АККАУНТА ПОСЛЕ ВХОДА: спам-блок, дата создания, username, ID ═══════════
BZ_SPAMCHECK_USER = "ponghs"      # кому бот пишет с купленного аккаунта для проверки на спам-блок
BZ_SPAMCHECK_TEXT = "Привет"
BZ_SPAMCHECK_ENABLED = False      # False — с купленных аккаунтов НИЧЕГО не отправляется, бот только заходит и читает
BZ_FREE_USERS = {6003847704}      # пользователи с бесплатным доступом к «Получить номера»
BZ_INSPECT_OLD = False            # старые номера при запуске НЕ проверяются (только при покупке или по кнопке)
_INSPECT_SEM = None
_TARGET_WARNED = False

# опорные точки «Telegram ID → дата регистрации» (приблизительно)
_ID_ANCHORS = [
    (2768409, 1383264000), (7679610, 1388448000), (11538514, 1391212000), (15835244, 1392940000),
    (23646077, 1393459000), (38015510, 1393632000), (44634663, 1399334000), (46145305, 1400198000),
    (54845238, 1411257000), (63263518, 1414454000), (101260938, 1425600000), (111220210, 1429574000),
    (103258382, 1432771000), (116812045, 1437696000), (124872445, 1439856000), (130029930, 1441324000),
    (143445125, 1448928000), (148670295, 1452211000), (171295414, 1457481000), (181783990, 1460246000),
    (222021370, 1465344000), (278941742, 1473465000), (294851037, 1479600000), (328594461, 1482969000),
    (352940995, 1487894000), (369669043, 1490918000), (400169472, 1501459000), (805158066, 1563208000),
    (1974255900, 1634000000),
]


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d.%m.%Y")


def _est_reg_date(uid: int) -> str:
    """Очень приблизительная дата регистрации по Telegram ID."""
    if uid < _ID_ANCHORS[0][0]:
        return "до конца 2013"
    if uid > _ID_ANCHORS[-1][0]:
        return "после октября 2021 (точнее по ID не определить)"
    for (i1, t1), (i2, t2) in zip(_ID_ANCHORS, _ID_ANCHORS[1:]):
        if i1 <= uid <= i2:
            ts = t1 + (t2 - t1) * (uid - i1) / max(1, (i2 - i1))
            return "≈ " + datetime.fromtimestamp(ts, timezone.utc).strftime("%m.%Y")
    return "не определить"


def _classify_send_error(e) -> Tuple[str, str]:
    """Результат неудачной отправки -> (spam_status, note)."""
    name = type(e).__name__
    msg = str(e).upper()
    if isinstance(e, ValueError) or "USERNAME" in name.upper() and ("NOTOCCUPIED" in name.upper() or "INVALID" in name.upper()):
        return "target_missing", f"не нашёл @{BZ_SPAMCHECK_USER}"
    if "PEERFLOOD" in name.upper() or "PEER_FLOOD" in msg:
        return "spam", "PeerFlood: Telegram запретил писать"
    if any(k in name.upper() for k in ("USERBANNEDINCHANNEL", "CHATWRITEFORBIDDEN", "USERRESTRICTED")) or "USER_RESTRICTED" in msg:
        return "spam", f"ограничение отправки ({name})"
    if "FLOODWAIT" in name.upper() or "FLOOD_WAIT" in msg:
        return "unknown", "FloodWait: слишком частые запросы, проверка отложена"
    return "unknown", f"не удалось проверить ({name})"


async def _resolve_777000(client):
    try:
        return await client.get_input_entity(777000)
    except Exception:
        return types.InputPeerUser(777000, 0)


async def bz_inspect_account(phone: str, session: str) -> dict:
    """Заходит в аккаунт и собирает ID/username/дату создания. Писать с аккаунта (проверка на спам-блок) можно только при BZ_SPAMCHECK_ENABLED=True."""
    res = {"err": None, "tg_id": None, "username": None, "created_est": None, "created_src": None,
           "spam_status": "unknown", "spam_note": ""}
    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=12)
        if not await client.is_user_authorized():
            res["err"] = "session_dead"
            res["spam_note"] = "сессия не активна"
            return res
        me = await client.get_me()
        res["tg_id"] = me.id
        res["username"] = me.username

        async def _created():
            try:
                peer = await _resolve_777000(client)
                async for m in client.iter_messages(peer, limit=1, reverse=True):
                    res["created_est"] = _fmt_ts(m.date.timestamp())
                    res["created_src"] = "по первому сообщению Telegram"
            except Exception as e:
                logger.info(f"[INSPECT] {phone}: дата по чату не получена: {e}")

        async def _spam():
            if not BZ_SPAMCHECK_ENABLED:
                res["spam_status"] = "unknown"
                res["spam_note"] = "проверка на спам отключена"
                return
            try:
                await asyncio.wait_for(client.send_message(BZ_SPAMCHECK_USER, BZ_SPAMCHECK_TEXT), timeout=12)
                res["spam_status"] = "ok"
                res["spam_note"] = f"сообщение @{BZ_SPAMCHECK_USER} отправлено"
            except Exception as e:
                st, note = _classify_send_error(e)
                res["spam_status"], res["spam_note"] = st, note

        await asyncio.gather(_created(), _spam())
        if not res["created_est"]:
            res["created_est"] = _est_reg_date(me.id)
            res["created_src"] = "по ID, приблизительно"
    except Exception as e:
        logger.error(f"[INSPECT] {phone}: {e}")
        res["err"] = str(e)[:100]
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    return res


def _store_inspection(phone: str, res: dict) -> None:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        conn.execute(
            "UPDATE numbers SET tg_id=?, tg_username=?, created_est=?, created_src=?, "
            "spam_status=?, spam_note=?, inspected_at=? WHERE phone=?",
            (res.get("tg_id"), res.get("username"), res.get("created_est"), res.get("created_src"),
             res.get("spam_status"), res.get("spam_note"), ts(), phone))


async def bz_inspect_and_store(phone: str, session: str) -> dict:
    global _INSPECT_SEM, _TARGET_WARNED
    if _INSPECT_SEM is None:
        _INSPECT_SEM = asyncio.Semaphore(6)
    async with _INSPECT_SEM:
        res = await bz_inspect_account(phone, session)
    if res["err"] and res["err"] != "session_dead":
        return res      # сетевая ошибка — не отмечаем как проверенный, повторим позже
    try:
        _store_inspection(phone, res)
    except Exception as e:
        logger.error(f"[INSPECT] не сохранилось {phone}: {e}")
    logger.info(f"[INSPECT] {phone}: id={res['tg_id']} @{res['username']} создан {res['created_est']} "
                f"({res['created_src']}) спам={res['spam_status']} ({res['spam_note']})")
    bot_ = getattr(_APP, "bot", None) if _APP is not None else None
    try:
        if bot_ and res["spam_status"] == "spam":
            await notify_admins(bot_, f"⛔ *СПАМ-БЛОК*\n\n`{fmt_phone(phone)}`\n{res['spam_note']}\n"
                                      f"Помечен в «Получить номера».", parse_mode="Markdown")
        elif bot_ and res["spam_status"] == "target_missing" and not _TARGET_WARNED:
            _TARGET_WARNED = True
            await notify_admins(bot_, f"⚠️ Не нашёл в Telegram @{BZ_SPAMCHECK_USER} — проверку на спам-блок "
                                      f"сделать не могу. Проверь имя.", parse_mode="Markdown")
    except Exception:
        pass
    return res


def bz_schedule_inspect(phone: str, session: str) -> None:
    """Запускает проверку нового аккаунта в фоне (из синхронного add_number)."""
    try:
        asyncio.get_running_loop()
        spawn(bz_inspect_and_store(phone, session))
    except RuntimeError:
        if BOT_LOOP is not None:
            asyncio.run_coroutine_threadsafe(bz_inspect_and_store(phone, session), BOT_LOOP)


async def bz_inspect_backlog():
    """При запуске проверяет номера, которые ещё не проверялись (по одному, с паузой)."""
    await asyncio.sleep(20)
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute("SELECT phone, session FROM numbers WHERE is_primary=0 AND inspected_at IS NULL "
                            "AND status IN ('active','alive','secured')").fetchall()
    if rows:
        logger.info(f"[INSPECT] непроверенных номеров: {len(rows)}")
    for phone, session in rows:
        try:
            await bz_inspect_and_store(phone, session)
        except Exception as e:
            logger.error(f"[INSPECT] backlog {phone}: {e}")
        await asyncio.sleep(6)


def get_number_extra(nid: int) -> dict:
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        r = conn.execute("SELECT tg_id, tg_username, created_est, created_src, spam_status, spam_note, inspected_at "
                         "FROM numbers WHERE id=?", (nid,)).fetchone()
    keys = ("tg_id", "username", "created_est", "created_src", "spam_status", "spam_note", "inspected_at")
    return dict(zip(keys, r)) if r else {}


def _spam_map() -> Dict[int, str]:
    try:
        with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
            return {i: st for i, st in conn.execute("SELECT id, spam_status FROM numbers").fetchall()}
    except Exception:
        return {}


def bz_can_get(user_id: int) -> bool:
    return is_main_admin(user_id) or user_id in BZ_FREE_USERS or has_numbers_access(user_id)


def bz_owner_like(user_id: int) -> bool:
    """Права владельца при получении номеров (без расхода номера «бесплатного» пользователя)."""
    return is_main_admin(user_id) or has_numbers_access(user_id)


def _extra_text(nid: int) -> str:
    x = get_number_extra(nid)
    if not x or not x.get("inspected_at"):
        return "\n🔎 Аккаунт ещё не проверен (ID, дата создания, спам-блок)"
    st = x["spam_status"]
    spam_line = {"ok": "✅ нет (написать получилось)",
                 "spam": f"⛔ ЕСТЬ — {x['spam_note']}",
                 "target_missing": f"❔ не проверен — {x['spam_note']}"}.get(st, f"❔ не проверен — {x['spam_note']}")
    return (f"\n🆔 ID аккаунта: `{x['tg_id']}`\n"
            f"👤 Username: {'@' + x['username'] if x['username'] else 'нет'}\n"
            f"🗓 Создан: {x['created_est']} ({x['created_src']})\n"
            f"🛡 Спам-блок: {spam_line}\n")


async def spamcheck_bulk(update, context):
    """Кнопка «Проверить спам-блок»: проверяет только ещё не проверенные номера, пропуская «оставленные»."""
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer()
    kept = {k for k, d in bz_decisions_map().items() if d == "kept"}
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        rows = conn.execute("SELECT phone, session FROM numbers WHERE is_primary=0 AND inspected_at IS NULL "
                            "AND status IN ('active','alive','secured')").fetchall()
    rows = [(p_, s_) for p_, s_ in rows if _digits(p_) not in kept]
    if not rows:
        await q.message.reply_text("✅ Все номера уже проверены (или оставлены). Одиночную проверку делай в карточке номера.",
                                   reply_markup=bz_menu_kb())
        return
    msg = await q.message.reply_text(f"🛡 Проверяю спам-блок: 0/{len(rows)}…")
    ok = spam = unk = 0
    spam_list: List[str] = []
    done = 0
    for i in range(0, len(rows), 6):
        batch = rows[i:i + 6]
        results = await asyncio.gather(*(bz_inspect_and_store(p_, s_) for p_, s_ in batch), return_exceptions=True)
        for (p_, _), r in zip(batch, results):
            done += 1
            if isinstance(r, Exception):
                unk += 1
            elif r.get("spam_status") == "ok":
                ok += 1
            elif r.get("spam_status") == "spam":
                spam += 1
                spam_list.append(fmt_phone(p_))
            else:
                unk += 1
        try:
            await msg.edit_text(f"🛡 Проверяю спам-блок: {done}/{len(rows)}…")
        except Exception:
            pass
    text = f"🛡 *ПРОВЕРКА ЗАВЕРШЕНА*\n\n✅ Чистые: {ok}\n⛔ Спам-блок: {spam}\n❔ Не проверены: {unk}"
    if spam_list:
        text += "\n\nСпам-блок:\n" + "\n".join(f"• `{x}`" for x in spam_list[:30])
        text += "\n\nРешай в «Получить номера»: удалить или 📌 оставить — я запомню."
        text += "\nТекст апелляции для @SpamBot — кнопка «📝 АПЕЛЛЯЦИЯ ДЛЯ @SpamBot» в меню."
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=bz_menu_kb())
    await bz_return_main_menu(context.bot, q.message.chat_id)


async def keep_toggle(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    action, nid_s = q.data.split("_")
    nid = int(nid_s)
    row = get_number_by_id(nid)
    if not row:
        await q.answer("Номер не найден", show_alert=True)
        return
    if action == "keep":
        bz_remember(row[2], "kept", "оставлен админом")
        await q.answer("📌 Запомнил: оставлен")
    else:
        bz_forget(row[2])
        await q.answer("Пометка снята")
    await _render_detail(q, context, nid)


async def history_cmd(update, context):
    """История решений: что удалено, что оставлено."""
    q = getattr(update, "callback_query", None)
    uid = q.from_user.id if q else update.effective_user.id
    if not is_main_admin(uid):
        return
    if q:
        await q.answer()
    with sqlite3.connect(BZ_DB_NAME, timeout=10) as conn:
        dele = conn.execute("SELECT phone, reason, at FROM account_decisions WHERE decision='deleted' ORDER BY at DESC").fetchall()
        kept = conn.execute("SELECT phone, reason, at FROM account_decisions WHERE decision='kept' ORDER BY at DESC").fetchall()
    lines = [f"📜 ИСТОРИЯ РЕШЕНИЙ", "", f"🗑 Удалено/продано/выдано: {len(dele)}"]
    lines += [f"  +{p_} — {r_} ({a_[:10]})" for p_, r_, a_ in dele[:15]]
    lines += ["", f"📌 Оставлено: {len(kept)}"]
    lines += [f"  +{p_} ({a_[:10]})" for p_, r_, a_ in kept[:15]]
    text = "\n".join(lines)[:4000]
    if q:
        await q.message.reply_text(text, reply_markup=bz_menu_kb())
    else:
        await update.message.reply_text(text)


async def inspect_now(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    nid = int(q.data.split("_")[1])
    row = get_number_by_id(nid)
    if not row:
        await q.answer("Номер не найден", show_alert=True)
        return
    await q.answer("🔎 Проверяю аккаунт…")
    res = await bz_inspect_and_store(row[2], row[3])
    note = "" if not res.get("err") or res["err"] == "session_dead" else f"⚠️ Проверка не удалась: {res['err']}"
    await _render_detail(q, context, nid, note)


async def bz_shop_sync_cb(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        return
    added, waiting = await asyncio.to_thread(bz_sync_shop)
    await q.edit_message_text(
        f"🏪 *МАГАЗИН*\n\nВыложено сейчас: {added}\nЖдут 25-часовой проверки: {waiting}\n\n"
        f"В магазин попадают только номера, у которых прошло 25 часов, аккаунт жив и все чужие сеансы завершены.",
        parse_mode="Markdown", reply_markup=bz_menu_kb())


async def bz_shop_all_ask(update, context):
    """Шаг 1: показать, сколько номеров будет выложено, и попросить подтверждение."""
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    n = len(await asyncio.to_thread(bz_pending_all))
    if n == 0:
        await q.edit_message_text("🚀 Выкладывать нечего: все купленные номера уже в магазине "
                                  "(или помечены как спам/заморожены).", reply_markup=bz_menu_kb())
        return
    await q.edit_message_text(
        f"🚀 *ВЫГРУЗИТЬ ВСЁ В МАГАЗИН*\n\nБудет выложено номеров: *{n}*\n\n"
        f"⚠️ Они попадут в продажу сразу, не дожидаясь 25-часовой проверки и завершения чужих сеансов. "
        f"Номера со спам-меткой и замороженные не выкладываются.\n\nПодтвердить?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("✅ ДА, ВЫЛОЖИТЬ", "bz_shop_all_do")],
            [btn("❌ ОТМЕНА", "menu")],
        ]))


async def bz_shop_all_do(update, context):
    """Шаг 2: выложить все."""
    q = update.callback_query
    await q.answer("⏳ Выкладываю…")
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    added, failed = await asyncio.to_thread(bz_publish_all_now)
    logger.info(f"[SHOP] выгрузка всех по кнопке: выложено {added}, не вышло {failed}")
    await q.edit_message_text(
        f"🚀 *ГОТОВО*\n\n✅ Выложено в магазин: {added}\n"
        + (f"⚠️ Не удалось: {failed} (смотри лог `[SHOP]`)\n" if failed else ""),
        parse_mode="Markdown", reply_markup=bz_menu_kb())


async def show_menu(q):
    text = ("🤖 *АВТОЗАКУП АККАУНТОВ*\n\n"
            "• 🛒 — закупка с автовходом\n"
            "• 📱 — получить номера и коды\n"
            "• 📊 — статистика\n"
            "• 📋 — база сессий\n"
            "• 🔍 — проверка просроченных\n"
            "• 🔎 — проверить + завершить сессии\n"
            "• ➕ — добавить номер вручную\n"
            "• 📤 — отправить боту файл базы с номерами, он добавит их и выложит в магазин\n"
            "• 🔑 — войти в аккаунт, который принимает подарки\n"
            "• 🏪 — выложить в магазин всё, что ещё не выложено (новые покупки выкладываются сами)\n"
            "• 🧹 — очистить аккаунты от чатов (только ещё не очищенные)")
    try:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=bz_menu_kb())
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# ═══════════ СТАТИСТИКА ═══════════
async def stats_show(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return

    s = stats_get_all()
    total_bought = s["total_bought"]
    alive = s["alive"]
    total_dead = s["total_dead"]
    spent_rub = s["total_spent_kop"] / 100
    avg = (spent_rub / total_bought) if total_bought else 0

    text = (
        f"📊 *СТАТИСТИКА*\n\n"
        f"🛒 Всего куплено: *{total_bought}*\n"
        f"✅ Сейчас живо: *{alive}*\n"
        f"❌ Мёртвых удалено: *{total_dead}*\n"
        f"💸 Всего потрачено: *{spent_rub:.2f} ₽*\n"
        f"📉 Средняя цена: *{avg:.2f} ₽*"
    )
    await q.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 МЕНЮ", "menu")]]))


# ═══════════ ЗАКУПКА ═══════════
def _buy_country_kb(page: int = 0):
    items = sorted(COUNTRIES, key=lambda c: str(c.get("name", "")))
    per = 16
    pages = max(1, (len(items) + per - 1) // per)
    page = max(0, min(page, pages - 1))
    rows = [[btn("🌍 ЛЮБАЯ СТРАНА", "bc_ANY")]]
    buf = []
    for c in items[page * per:(page + 1) * per]:
        buf.append(btn(f"{c.get('flag', '')} {c.get('name', c.get('code'))}", f"bc_{c['code']}"))
        if len(buf) == 2:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(btn("◀️", f"bcp_{page - 1}"))
        nav.append(btn(f"{page + 1}/{pages}", f"bcp_{page}"))
        if page < pages - 1:
            nav.append(btn("▶️", f"bcp_{page + 1}"))
        rows.append(nav)
    rows.append([btn("🔙 ОТМЕНА", "menu")])
    return InlineKeyboardMarkup(rows)


_BUY_COUNTRY_TEXT = ("🛒 *ЗАКУПКА*\n\n🌍 *Какую страну закупаем?*\n"
                     "Выбери кнопкой или напиши название/код страны (например `Индия` или `IN`).")


async def buy_start(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    context.user_data.pop("buy_country", None)
    context.user_data.pop("buy_price", None)
    await q.edit_message_text(_BUY_COUNTRY_TEXT, parse_mode="Markdown", reply_markup=_buy_country_kb(0))
    return BUY_COUNTRY


async def buy_country_page(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        return ConversationHandler.END
    page = int(q.data.split("_")[1])
    try:
        await q.edit_message_text(_BUY_COUNTRY_TEXT, parse_mode="Markdown", reply_markup=_buy_country_kb(page))
    except BadRequest:
        pass
    return BUY_COUNTRY


async def _buy_country_chosen(chat_reply, context, country):
    context.user_data["buy_country"] = country
    label = f"{country.get('flag', '')} {country.get('name', country.get('code'))}" if country else "🌍 любая страна"
    context.user_data.pop("price_mode", None)
    context.user_data.pop("shop_stars", None)
    await chat_reply(
        f"🌍 Страна: *{label}*\n\n💰 *Какую цену в магазине установить перед закупкой?*",
        parse_mode="Markdown", reply_markup=_buy_pmode_kb())
    return BUY_PMODE


async def buy_country_pick(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        return ConversationHandler.END
    code = q.data[3:]
    country = None if code == "ANY" else get_country_by_code(code)
    if code != "ANY" and not country:
        await q.answer("Страна не найдена", show_alert=True)
        return BUY_COUNTRY
    return await _buy_country_chosen(q.edit_message_text, context, country)


async def buy_country_text(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip().lower()
    found = None
    for c in COUNTRIES:
        if t == str(c.get("code", "")).lower() or t == str(c.get("name", "")).lower():
            found = c
            break
    if not found:
        for c in COUNTRIES:
            if t and t in str(c.get("name", "")).lower():
                found = c
                break
    if not found:
        await update.message.reply_text("❌ Не нашёл такую страну. Выбери кнопкой или напиши иначе (название или код).")
        return BUY_COUNTRY
    return await _buy_country_chosen(update.message.reply_text, context, found)


def _buy_pmode_kb():
    return InlineKeyboardMarkup([
        [btn("⭐ Цена в звёздах", "bpm_stars"), btn("💳 Цена в рублях", "bpm_rub")],
        [btn("⭐💳 Обе цены вместе", "bpm_both")],
        [btn("⏭ Не менять цены", "bpm_keep")],
        [btn("🔙 ОТМЕНА", "menu")],
    ])


_ASK_MAX_PRICE = "💰 Теперь введи *максимальную цену закупки* одного номера на LZT в ₽:"


def _apply_shop_price(stars=None, rub=None) -> str:
    """Сохраняет цену(ы) магазина и применяет к выставленным номерам. -> строка для сообщения."""
    with sqlite3.connect(DB_NAME, timeout=10) as conn:
        if stars is not None:
            _set_setting("shop_price_stars", stars)
            conn.execute("UPDATE phone_products SET price_stars=? WHERE available=1", (stars,))
        if rub is not None:
            _set_setting("shop_price_rub", rub)
            conn.execute("UPDATE phone_products SET price_rub=? WHERE available=1", (rub,))
    parts = []
    if stars is not None:
        parts.append(f"{stars} ⭐")
    if rub is not None:
        parts.append(f"{rub:g} ₽")
    logger.info(f"[PRICE] владелец задал цены магазина: {' / '.join(parts)} (применены ко всем выставленным номерам)")
    return " / ".join(parts)


async def buy_pmode_pick(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        return ConversationHandler.END
    mode = q.data.split("_", 1)[1]
    context.user_data["price_mode"] = mode
    kb = InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]])
    if mode == "keep":
        await q.edit_message_text("⏭ Цены остаются прежними.\n\n" + _ASK_MAX_PRICE, parse_mode="Markdown", reply_markup=kb)
        return BUY_PRICE
    if mode == "rub":
        await q.edit_message_text("💳 Введи *цену в рублях* (в магазине):", parse_mode="Markdown", reply_markup=kb)
        return BUY_PRUB
    await q.edit_message_text("⭐ Введи *цену в звёздах* (в магазине) для номеров:", parse_mode="Markdown", reply_markup=kb)
    return BUY_PSTARS


async def buy_pstars_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip().replace(",", ".")
    try:
        stars = int(float(t))
        if stars <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Цена в звёздах — целое число, например 40:")
        return BUY_PSTARS
    context.user_data["shop_stars"] = stars
    kb = InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]])
    if context.user_data.get("price_mode") == "stars":
        try:
            shown = _apply_shop_price(stars=stars)
        except Exception as e:
            logger.error(f"[PRICE] не удалось сохранить цену в звёздах: {e}")
            await notify_owner(context.bot, f"⚠️ Не удалось сохранить цену: {e}")
            await update.message.reply_text(f"❌ Не удалось сохранить цену: {str(e)[:120]}")
            return ConversationHandler.END
        await update.message.reply_text(f"✅ Цена в звёздах сохранена: {shown}\n(применена ко всем номерам в магазине)\n\n"
                                        + _ASK_MAX_PRICE, parse_mode="Markdown", reply_markup=kb)
        return BUY_PRICE
    await update.message.reply_text(
        f"⭐ Цена в звёздах: *{stars}*\n\n💳 Теперь введи *цену в рублях* (в магазине):",
        parse_mode="Markdown", reply_markup=kb)
    return BUY_PRUB


async def buy_prub_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip().replace(",", ".")
    try:
        rub = float(t)
        if rub <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Цена в рублях — число, например 65 или 64.9:")
        return BUY_PRUB
    only_rub = context.user_data.get("price_mode") == "rub"
    stars = None if only_rub else context.user_data.get("shop_stars")
    if not only_rub and not stars:
        await update.message.reply_text("❌ Цена в звёздах потерялась, начни заново: меню → 🛒 ЗАКУПИТЬ.")
        return ConversationHandler.END
    try:
        shown = _apply_shop_price(stars=stars, rub=rub)
    except Exception as e:
        logger.error(f"[PRICE] не удалось сохранить цены: {e}")
        await notify_owner(context.bot, f"⚠️ Не удалось сохранить цены: {e}")
        await update.message.reply_text(f"❌ Не удалось сохранить цены: {str(e)[:120]}")
        return ConversationHandler.END
    await update.message.reply_text(
        f"✅ Цена успешно сохранена: {shown}\n(применена ко всем номерам в магазине)\n\n" + _ASK_MAX_PRICE,
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]]))
    return BUY_PRICE


async def buy_price_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip().replace(",", ".")
    try:
        max_price = float(t)
        if max_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Цена числом, например 30 или 25.5:")
        return BUY_PRICE
    context.user_data["buy_price"] = max_price
    await update.message.reply_text(
        f"💰 Макс. цена: *{max_price:g} ₽*\n\n🔢 Сколько номеров купить? (1–100)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]]))
    return BUY_COUNT


async def buy_count_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.isdigit() or not (1 <= int(t) <= 100):
        await update.message.reply_text("❌ Число от 1 до 100:")
        return BUY_COUNT
    count = int(t)
    max_price = context.user_data.get("buy_price")
    country = context.user_data.get("buy_country")
    if not max_price:
        await update.message.reply_text("❌ Цена потерялась, начни заново: меню → 🛒 ЗАКУПИТЬ.")
        return ConversationHandler.END
    if not try_start_operation("buy"):
        await update.message.reply_text(
            f"⚠️ Уже выполняется: *{get_active_operation()}*.\n"
            "Дождись завершения или нажми ⛔ СТОП в том сообщении.",
            parse_mode="Markdown")
        return ConversationHandler.END
    msg = await update.message.reply_text("⏳ Запускаю...")
    spawn(bulk_buy_task(context, count, max_price, msg.chat_id, msg.message_id, country))
    return ConversationHandler.END


# ═══════════ ИМПОРТ УЖЕ КУПЛЕННЫХ ЛОТОВ ═══════════
async def import_purchases_start(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    msg_text = (
        "📥 *ИМПОРТ КУПЛЕННЫХ ЛОТОВ*\n\n"
        "Найду на LZT все купленные Telegram-аккаунты, которых ещё нет "
        "в базе бота, и попробую войти в каждый.\n\n⏳ Запускаю..."
    )
    if not try_start_operation("import"):
        await q.answer(f"⚠️ Уже выполняется: {get_active_operation()}", show_alert=True)
        return
    await q.edit_message_text(msg_text, parse_mode="Markdown", reply_markup=STOP_KB)
    spawn(import_purchases_task(context, q.message.chat_id, q.message.message_id))


async def import_purchases_task(context, progress_chat, progress_msg_id):
    try:
        await _import_purchases_task(context, progress_chat, progress_msg_id)
    except Exception as e:
        logger.exception("[IMPORT] Необработанная ошибка импорта")
        await notify_admins(context.bot, f"❌ Ошибка импорта: {str(e)[:200]}")
    finally:
        finish_operation()


async def _import_purchases_task(context, progress_chat, progress_msg_id):
    set_stopped(False)
    if not _lzt_available:
        await safe_edit(context.bot, progress_chat, progress_msg_id,
                        "❌ LOLZTEAM не установлен: pip install LOLZTEAM")
        return
    market = make_market()

    all_items = await lzt_list_purchases(market)
    known = get_known_item_ids()
    todo = []
    for item in all_items:
        item_id = item.get("item_id") or item.get("id")
        if item_id is None:
            continue
        item_id = int(item_id)
        if item_id in known:
            continue
        if not lzt_is_telegram_item(item):
            continue
        todo.append((item_id, item))

    if not all_items:
        await safe_edit(context.bot, progress_chat, progress_msg_id,
            "📭 LZT не вернул ни одной покупки.\n\n"
            "Либо покупок правда нет, либо эндпоинт /user/items для "
            "«Моих покупок» на вашем аккаунте называется иначе — "
            "посмотри лог строку `[IMPORT]` и пришли её мне.")
        return

    if not todo:
        await safe_edit(context.bot, progress_chat, progress_msg_id,
            f"✅ Новых лотов нет.\n\nВсего покупок на LZT: {len(all_items)}\n"
            f"Уже в базе бота: {len(known)}")
        return

    ok_count, fail_count = 0, 0
    report_lines = []

    for i, (item_id, item) in enumerate(todo, 1):
        if is_stopped():
            report_lines.append("⏹ Остановлено кнопкой СТОП")
            break

        await safe_edit(context.bot, progress_chat, progress_msg_id,
            f"📥 *ИМПОРТ*\n\n🔁 {i}/{len(todo)}\n✅ Вошёл: {ok_count}\n❌ Не удалось: {fail_count}",
            parse_mode="Markdown", reply_markup=STOP_KB)

        login_data = await lzt_get_item_login_data(market, item_id)
        phone = None
        for key in ("phone", "phone_number", "number", "telegram_phone"):
            if login_data.get(key):
                phone = str(login_data[key]).strip()
                break
        if not phone:
            phone = lzt_extract_phone(str(item.get("title") or "") +
                                      " " + str(item.get("description") or ""))
        if not phone and login_data:
            phone = lzt_extract_phone(json.dumps(login_data, ensure_ascii=False))

        if not phone:
            fail_count += 1
            report_lines.append(f"⚠️ лот `{item_id}`: номер не найден")
            logger.warning(f"[IMPORT] Номер не найден для лота {item_id}")
            continue

        password = None
        for key in ("telegram_password", "password", "twofa", "2fa",
                    "two_fa", "cloud_password"):
            if login_data.get(key):
                password = str(login_data[key])
                break

        session_str, status = await add_bought_account(phone, item_id, market, password=password)
        if session_str:
            add_number(item_id, phone, 0.0, lzt_get_country(item), session_str, two_fa=password or "")
            ok_count += 1
            report_lines.append(f"✅ `{phone}` (лот {item_id})")
        else:
            fail_count += 1
            report_lines.append(f"⚠️ `{phone}` (лот {item_id}): `{status}`")

        await asyncio.sleep(BUY_DELAY)

    summary = "\n".join(report_lines) if report_lines else "—"
    await safe_edit(context.bot, progress_chat, progress_msg_id,
        f"📊 *ИМПОРТ ЗАВЕРШЁН*\n\n✅ Вошёл: {ok_count}\n❌ Не удалось: {fail_count}\n\n"
        f"*Детали:*\n{summary[:3500]}", parse_mode="Markdown")


# ═══════════ РУЧНОЕ ДОБАВЛЕНИЕ ═══════════
async def manual_add_start(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.edit_message_text(
        "➕ *ДОБАВИТЬ НОМЕР ВРУЧНУЮ*\n\n"
        "Шаг 1/3. Введи номер телефона в формате `+79991234567`:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]]))
    return MANUAL_PHONE


async def manual_phone_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    phone = update.message.text.strip()
    if not phone.startswith("+") or len(phone) < 10:
        await update.message.reply_text("❌ Неверный формат. Пример: `+79991234567`",
                                        parse_mode="Markdown")
        return MANUAL_PHONE

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        context.user_data["manual_client"] = client
        context.user_data["manual_phone"] = phone
        context.user_data["manual_hash"] = sent.phone_code_hash

        await update.message.reply_text(
            f"📱 Номер: `{phone}`\n\n"
            f"Шаг 2/3. Введи *код из Telegram* через пробелы, например `1 2 3 4 5` "
            f"(слитно Telegram аннулирует код):",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "menu")]]))
        return MANUAL_CODE
    except errors.FloodWaitError as e:
        await update.message.reply_text(f"⏳ FloodWait: подожди {e.seconds} сек.")
        await client.disconnect()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:120]}`",
                                        parse_mode="Markdown")
        await client.disconnect()
        return ConversationHandler.END


async def manual_code_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    code = update.message.text.strip().replace(" ", "")
    client = context.user_data.get("manual_client")
    phone = context.user_data.get("manual_phone")
    phone_hash = context.user_data.get("manual_hash")

    if not client:
        await update.message.reply_text("❌ Сессия потеряна. Начни заново /start")
        return ConversationHandler.END

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        session_str = client.session.save()

        ok_ava, ava_info = await set_random_avatar(client)
        await client.disconnect()

        add_number(0, phone, 0.0, "manual", session_str)
        spawn(wipe_session_task(session_str, phone))
        ava_status = "✅ установлена" if ok_ava else f"⚠️ {ava_info}"

        await update.message.reply_text(
            f"✅ *НОМЕР ДОБАВЛЕН ВРУЧНУЮ*\n\n"
            f"📱 `{phone}`\n"
            f"🖼 Аватарка: {ava_status}\n"
            f"🔑 Сессия сохранена",
            parse_mode="Markdown",
            reply_markup=bz_menu_kb())
        return ConversationHandler.END
    except errors.SessionPasswordNeededError:
        context.user_data["manual_client"] = client
        await update.message.reply_text(
            "🔒 *Шаг 3/3. Двухфакторная аутентификация*\n\nВведи пароль 2FA:",
            parse_mode="Markdown")
        return MANUAL_2FA
    except errors.PhoneCodeInvalidError:
        await update.message.reply_text("❌ Неверный код или он аннулирован (слитный код Telegram блокирует). "
                                        "Если ввёл слитно — нажми ОТМЕНА и начни заново: придёт новый код. "
                                        "Отправляй цифры через пробелы: `1 2 3 4 5`", parse_mode="Markdown")
        return MANUAL_CODE
    except errors.PhoneCodeExpiredError:
        await update.message.reply_text("❌ Код истёк. Начни заново /start")
        await client.disconnect()
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:120]}`",
                                        parse_mode="Markdown")
        await client.disconnect()
        return ConversationHandler.END


async def manual_2fa_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    password = update.message.text.strip()
    client = context.user_data.get("manual_client")
    phone = context.user_data.get("manual_phone")

    if not client:
        await update.message.reply_text("❌ Сессия потеряна. Начни заново /start")
        return ConversationHandler.END

    try:
        await client.sign_in(password=password)
        session_str = client.session.save()

        ok_ava, ava_info = await set_random_avatar(client)
        await client.disconnect()

        add_number(0, phone, 0.0, "manual", session_str)
        spawn(wipe_session_task(session_str, phone))
        ava_status = "✅ установлена" if ok_ava else f"⚠️ {ava_info}"

        await update.message.reply_text(
            f"✅ *НОМЕР ДОБАВЛЕН ВРУЧНУЮ*\n\n"
            f"📱 `{phone}`\n"
            f"🔒 2FA пройдена\n"
            f"🖼 Аватарка: {ava_status}",
            parse_mode="Markdown",
            reply_markup=bz_menu_kb())
        return ConversationHandler.END
    except errors.PasswordHashInvalidError:
        await update.message.reply_text("❌ Неверный пароль 2FA. Попробуй ещё раз:")
        return MANUAL_2FA
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:120]}`",
                                        parse_mode="Markdown")
        await client.disconnect()
        return ConversationHandler.END


async def _prim_drop_client(context):
    client = context.user_data.pop("prim_client", None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass


async def prim_login_start(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await _prim_drop_client(context)
    await q.message.reply_text(
        "🔑 *ВХОД В СТАРТОВЫЙ АККАУНТ*\n\n"
        "Этот аккаунт принимает подарки.\n"
        f"Отправь номер в формате `+79991234567` или `-`, чтобы взять `{START_PHONE}`:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "prim_cancel")]]))
    return PRIM_PHONE


def _prim_keypad(buf: str, length: int):
    return InlineKeyboardMarkup([
        [btn("📲 ВОЙТИ ПО ССЫЛКЕ (без кода)", "bz_primary_qr")],
        [btn("🔄 НОВЫЙ КОД", "pk_resend"), btn("🔙 ОТМЕНА", "prim_cancel")]])


def _prim_code_text(phone: str, buf: str, length: int) -> str:
    return (f"📱 `{phone}`\n\n🔢 Отправь мне код из чата «Telegram» *через пробелы*, "
            f"например `1 8 2 0 7`.\n\n"
            f"⚠️ Слитно (`18207`) не пиши: Telegram сразу аннулирует такой код.")


async def prim_phone_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    phone = update.message.text.strip()
    if phone == "-":
        phone = START_PHONE
    if not phone.startswith("+") or len(phone) < 10:
        await update.message.reply_text("❌ Неверный формат. Пример: `+79991234567`", parse_mode="Markdown")
        return PRIM_PHONE
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        length = int(getattr(getattr(sent, "type", None), "length", 5) or 5)
        context.user_data.update(prim_client=client, prim_phone=phone,
                                 prim_hash=sent.phone_code_hash, prim_len=length, prim_buf="")
        msg = await update.message.reply_text(
            _prim_code_text(phone, "", length), parse_mode="Markdown",
            reply_markup=_prim_keypad("", length))
        context.user_data["prim_msg"] = msg.message_id
        return PRIM_CODE
    except errors.FloodWaitError as e:
        await update.message.reply_text(f"⏳ FloodWait: подожди {e.seconds} сек.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: `{str(e)[:150]}`", parse_mode="Markdown")
    try:
        await client.disconnect()
    except Exception:
        pass
    return ConversationHandler.END


async def _prim_finish(context, chat_id, client, phone):
    session_str = client.session.save()
    me = await client.get_me()
    await client.disconnect()
    context.user_data.pop("prim_client", None)
    add_number(0, phone, 0.0, "primary", session_str, is_primary=1)
    _prim_backup_save(session_str)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(f"✅ *СТАРТОВЫЙ АККАУНТ ПОДКЛЮЧЁН*\n\n"
              f"👤 {me.first_name} (@{me.username or '—'})\n📱 `{phone}`\n\n"
              f"Сессия сохранена, повторно вводить код не нужно. "
              f"Подарки начнут приниматься в течение минуты."),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [btn("💾 СТРОКА СЕССИИ (на случай потери диска)", "prim_export")],
            [btn("🔙 В МЕНЮ", "menu")]]))
    return ConversationHandler.END


async def _prim_resend(context, chat_id, note: str):
    client = context.user_data.get("prim_client")
    phone = context.user_data.get("prim_phone")
    if not client or not phone:
        return False
    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Не удалось запросить код: {str(e)[:150]}")
        return False
    length = int(getattr(getattr(sent, "type", None), "length", 5) or 5)
    context.user_data.update(prim_hash=sent.phone_code_hash, prim_len=length, prim_buf="")
    msg = await context.bot.send_message(
        chat_id=chat_id, text=note + "\n\n" + _prim_code_text(phone, "", length),
        parse_mode="Markdown", reply_markup=_prim_keypad("", length))
    context.user_data["prim_msg"] = msg.message_id
    return True


async def _prim_submit(context, chat_id, code: str):
    client = context.user_data.get("prim_client")
    phone = context.user_data.get("prim_phone")
    phone_hash = context.user_data.get("prim_hash")
    if not client or not phone:
        await context.bot.send_message(chat_id=chat_id, text="❌ Сессия потеряна. Нажми кнопку входа заново.")
        return ConversationHandler.END
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        return await _prim_finish(context, chat_id, client, phone)
    except errors.SessionPasswordNeededError:
        await context.bot.send_message(
            chat_id=chat_id, text="🔒 Включена двухфакторная защита. Введи *пароль 2FA*:",
            parse_mode="Markdown")
        return PRIM_2FA
    except errors.PhoneCodeInvalidError:
        context.user_data["prim_buf"] = ""
        if code == context.user_data.get("prim_dead_code"):
            text = ("❌ Это старый код, он уже аннулирован. Возьми НОВЫЙ из чата «Telegram» "
                    "(он пришёл после моего последнего сообщения) и отправь через пробелы: `1 8 2 0 7`.")
        else:
            text = "❌ Неверный код. Проверь цифры и отправь ещё раз через пробелы."
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return PRIM_CODE
    except errors.PhoneCodeExpiredError:
        context.user_data["prim_dead_code"] = code
        if context.user_data.pop("prim_via_text", False):
            note = ("⌛ Telegram аннулировал код, потому что он был написан слитно. "
                    "Я запросил НОВЫЙ код — открой чат «Telegram» и возьми свежий (старый больше не подойдёт). "
                    "Отправь его через пробелы, например `1 8 2 0 7`.")
        else:
            note = "⌛ Код истёк, отправил новый."
        if await _prim_resend(context, chat_id, note):
            return PRIM_CODE
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: {str(e)[:150]}")
    await _prim_drop_client(context)
    return ConversationHandler.END


async def prim_code_press(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    action = q.data[3:]
    buf = context.user_data.get("prim_buf", "")
    length = context.user_data.get("prim_len", 5)
    phone = context.user_data.get("prim_phone", "")
    if not context.user_data.get("prim_client"):
        await q.message.reply_text("❌ Сессия потеряна. Нажми кнопку входа заново.")
        return ConversationHandler.END
    if action == "resend":
        await _prim_resend(context, q.message.chat_id, "🔄 Запросил новый код.")
        return PRIM_CODE
    if action == "del":
        buf = buf[:-1]
    elif action == "ok":
        if len(buf) < 4:
            await q.answer("Введи код полностью", show_alert=True)
            return PRIM_CODE
        return await _prim_submit(context, q.message.chat_id, buf)
    elif action.isdigit() and len(buf) < 8:
        buf += action
    context.user_data["prim_buf"] = buf
    try:
        await q.edit_message_text(_prim_code_text(phone, buf, length), parse_mode="Markdown",
                                  reply_markup=_prim_keypad(buf, length))
    except BadRequest:
        pass
    if action.isdigit() and len(buf) >= length:
        return await _prim_submit(context, q.message.chat_id, buf)
    return PRIM_CODE


async def prim_code_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    code = "".join(ch for ch in update.message.text if ch.isdigit())
    if len(code) < 4:
        await update.message.reply_text("❌ Отправь цифры кода, например 18207.")
        return PRIM_CODE
    context.user_data["prim_via_text"] = True
    try:
        await update.message.delete()   # код не оставляем в чате
    except Exception:
        pass
    return await _prim_submit(context, update.effective_chat.id, code)


async def prim_2fa_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    password = update.message.text.strip()
    client = context.user_data.get("prim_client")
    phone = context.user_data.get("prim_phone")
    chat_id = update.effective_chat.id
    if not client or not phone:
        await update.message.reply_text("❌ Сессия потеряна. Нажми кнопку входа заново.")
        return ConversationHandler.END
    try:
        await update.message.delete()   # пароль не оставляем в чате
    except Exception:
        pass
    try:
        await client.sign_in(password=password)
        return await _prim_finish(context, chat_id, client, phone)
    except errors.PasswordHashInvalidError:
        await context.bot.send_message(chat_id=chat_id, text="❌ Неверный пароль 2FA. Попробуй ещё раз:")
        return PRIM_2FA
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: {str(e)[:150]}")
    await _prim_drop_client(context)
    return ConversationHandler.END


async def prim_cancel(update, context):
    await _prim_drop_client(context)
    await _prim_qr_cleanup(context.application)
    q = update.callback_query
    await q.answer()
    try:
        await q.edit_message_text("Отменено.", reply_markup=bz_menu_kb())
    except Exception:
        pass
    return ConversationHandler.END


async def prim_export(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await q.answer()
    sess = get_primary_session()
    if not sess:
        await q.message.reply_text("❌ Сессии нет.")
        return
    await q.message.reply_text(
        "💾 *Строка сессии стартового аккаунта*\n\n"
        f"`{sess}`\n\n"
        "Сохрани её в переменную окружения `PRIMARY_SESSION` на хостинге — тогда бот "
        "войдёт сам, даже если диск очистится. ⚠️ Это полный доступ к аккаунту: "
        "никому не показывай и удали это сообщение после сохранения.",
        parse_mode="Markdown")


class _CtxShim:
    """Мини-контекст для завершения входа из фоновой задачи (без модуля types: он занят telethon)."""
    def __init__(self, bot):
        self.user_data = {}
        self.bot = bot


async def _prim_qr_cleanup(app):
    data = app.bot_data.pop("prim_qr", None)
    if data and data.get("client"):
        try:
            await data["client"].disconnect()
        except Exception:
            pass


def _prim_qr_text(url: str) -> str:
    return ("📲 <b>ВХОД ПО ССЫЛКЕ</b>\n\n"
            "Код вводить не нужно.\n"
            f"👉 <a href=\"{html.escape(url)}\">Нажми сюда</a> — откроется Telegram, "
            "подтверди вход (аккаунт, который должен стать стартовым).\n\n"
            "Ссылка живёт около 30 секунд, я сам обновлю её ниже.")


async def _prim_qr_task(app, qr, client, chat_id, msg_id):
    bot_ = app.bot
    deadline = time.time() + 240
    try:
        while time.time() < deadline:
            cur = app.bot_data.get("prim_qr")
            if not cur or cur.get("client") is not client:
                return   # отменили
            try:
                await qr.wait(timeout=20)
                break
            except asyncio.TimeoutError:
                try:
                    await qr.recreate()
                    await bot_.edit_message_text(
                        chat_id=chat_id, message_id=msg_id, text=_prim_qr_text(qr.url),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "prim_cancel")]]))
                except BadRequest:
                    pass
                except Exception as e:
                    logger.warning(f"[PRIMARY-QR] recreate: {e}")
            except errors.SessionPasswordNeededError:
                await bot_.send_message(
                    chat_id=chat_id,
                    text="🔒 На аккаунте включена двухфакторная защита.",
                    reply_markup=InlineKeyboardMarkup([[btn("🔑 ВВЕСТИ ПАРОЛЬ 2FA", "qr_2fa")]]))
                return
        else:
            await bot_.send_message(chat_id=chat_id, text="⌛ Время ожидания вышло. Попробуй ещё раз.",
                                    reply_markup=bz_menu_kb())
            await _prim_qr_cleanup(app)
            return
        me = await client.get_me()
        phone = "+" + str(me.phone).lstrip("+")
        shim = _CtxShim(bot_)
        await _prim_finish(shim, chat_id, client, phone)
        app.bot_data.pop("prim_qr", None)
    except Exception as e:
        logger.error(f"[PRIMARY-QR] {e}")
        try:
            await bot_.send_message(chat_id=chat_id, text=f"❌ Ошибка входа по ссылке: {str(e)[:150]}")
        except Exception:
            pass
        await _prim_qr_cleanup(app)


async def prim_qr_start(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    await _prim_drop_client(context)
    await _prim_qr_cleanup(context.application)
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        qr = await client.qr_login()
    except Exception as e:
        await q.message.reply_text(f"❌ Не удалось начать вход по ссылке: {str(e)[:150]}")
        try:
            await client.disconnect()
        except Exception:
            pass
        return ConversationHandler.END
    context.application.bot_data["prim_qr"] = {"client": client}
    msg = await q.message.reply_text(
        _prim_qr_text(qr.url), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[btn("🔙 ОТМЕНА", "prim_cancel")]]))
    spawn(_prim_qr_task(context.application, qr, client, q.message.chat_id, msg.message_id))
    return ConversationHandler.END


async def qr_2fa_start(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    if not context.application.bot_data.get("prim_qr"):
        await q.message.reply_text("❌ Сессия входа потеряна. Начни заново.")
        return ConversationHandler.END
    await q.message.reply_text("Введи *пароль 2FA* (сообщение я сразу удалю):", parse_mode="Markdown")
    return QR_2FA_PW


async def qr_2fa_input(update, context):
    if not is_main_admin(update.effective_user.id):
        return ConversationHandler.END
    data = context.application.bot_data.get("prim_qr")
    chat_id = update.effective_chat.id
    if not data:
        await update.message.reply_text("❌ Сессия входа потеряна. Начни заново.")
        return ConversationHandler.END
    client = data["client"]
    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        phone = "+" + str(me.phone).lstrip("+")
        shim = _CtxShim(context.bot)
        await _prim_finish(shim, chat_id, client, phone)
        context.application.bot_data.pop("prim_qr", None)
        return ConversationHandler.END
    except errors.PasswordHashInvalidError:
        await context.bot.send_message(chat_id=chat_id, text="❌ Неверный пароль 2FA. Попробуй ещё раз:")
        return QR_2FA_PW
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка: {str(e)[:150]}")
    await _prim_qr_cleanup(context.application)
    return ConversationHandler.END


def _prim_backup_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(BZ_DB_NAME)), "primary_session.txt")


def _prim_backup_save(session_str: str) -> None:
    try:
        with open(_prim_backup_path(), "w", encoding="utf-8") as f:
            f.write(session_str)
    except Exception as e:
        logger.warning(f"[PRIMARY] не удалось сохранить резервную копию: {e}")


def _prim_backup_load() -> str:
    try:
        with open(_prim_backup_path(), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


async def manual_cancel(update, context):
    client = context.user_data.pop("manual_client", None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    await update.callback_query.answer()
    await show_menu(update.callback_query)
    return ConversationHandler.END


# ═══════════ БАЗА ═══════════
async def list_numbers(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    stats, recent = get_stats()
    if not stats:
        text = "📋 База пуста."
    else:
        lines = [f"• {s}: {c}" for s, c in stats.items()]
        recent_txt = "\n".join(f"{p} — {pr}₽ [{s}]" for p, pr, s, _ in recent)
        text = f"📋 БАЗА (купленные)\n\n" + "\n".join(lines) + f"\n\nПоследние:\n{recent_txt}"
    await q.edit_message_text(text, parse_mode=None,
                              reply_markup=InlineKeyboardMarkup([[btn("🔙", "menu")]]))


async def menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    if not is_main_admin(q.from_user.id):
        if q.from_user.id in BZ_FREE_USERS or has_numbers_access(q.from_user.id):
            try:
                await q.edit_message_text(
                    "📱 У тебя есть доступ к получению номеров.",
                    reply_markup=InlineKeyboardMarkup([
                        [btn("📱 ПОЛУЧИТЬ НОМЕР", "get_numbers")],
                        [btn("🏠 В МАГАЗИН", "start")]]))
            except BadRequest:
                pass
            return
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    await show_menu(q)


async def cancel_conv(update, context):
    await update.callback_query.answer()
    await show_menu(update.callback_query)
    return ConversationHandler.END


async def conv_start(update, context):
    """/start внутри диалога: закрыть незавершённый вход и выйти из диалога."""
    client = context.user_data.pop("manual_client", None)
    if client:
        await _disconnect(client)
    await start(update, context)
    return ConversationHandler.END


async def buy_stop(update, context):
    q = update.callback_query
    if not is_main_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True)
        return
    set_stopped(True)
    await q.answer("⏹ Останавливаю после текущего шага...", show_alert=True)


async def force_reset_stuck(update, context):
    """На случай зависшего флага после сбоя/перезапуска без штатного завершения."""
    if not is_main_admin(update.effective_user.id):
        return
    finish_operation()
    set_stopped(False)
    await update.message.reply_text("🔧 Флаги сброшены.")



async def bz_on_startup(application):
    global _APP
    _APP = application
    finish_operation()
    set_stopped(False)

    if not get_yoomoney_wallet():
        await notify_admins(application.bot,
            "⚠️ *НЕ ЗАДАН КОШЕЛЁК ЮMONEY*\n\nБез него оплата рублями не работает "
            "(ЮMoney пишет «Перевести не получится»).\n"
            "Отправь боту: `/wallet НОМЕР_КОШЕЛЬКА`, например `/wallet 4100123456789012`.",
            parse_mode="Markdown")
    try:
        import config as _config_mod
        if getattr(_config_mod, "_DB_FALLBACK", False):
            msg = ("⚠️ *БАЗА С НОМЕРАМИ НЕ НАЙДЕНА*\n\n"
                   "Папки `/storage/emulated/0/Download/Автопокупка и парсер аков/` здесь нет "
                   "(бот запущен не на телефоне), поэтому создана новая пустая база:\n"
                   f"`{BZ_DB_NAME}`\n\n"
                   "Загрузи свой `lzt_numbers.db` в эту папку на хостинге и перезапусти бота, "
                   "либо отправь /import_db ПУТЬ_К_ФАЙЛУ. Список баз: /dbinfo")
            await notify_admins(application.bot, msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"[DB] предупреждение о базе: {e}")

    primary = get_primary_session()
    env_session = os.getenv("PRIMARY_SESSION", "").strip() or _prim_backup_load()
    if not primary and env_session:
        add_number(0, START_PHONE, 0.0, "primary", env_session, is_primary=1)
        primary = env_session
        logger.info("[PRIMARY] стартовая сессия восстановлена (PRIMARY_SESSION или резервный файл)")
    if primary and not os.path.isfile(_prim_backup_path()):
        _prim_backup_save(primary)
    if not primary:
        await notify_admins(application.bot,
            "⚠️ *АВТОЗАКУП: НЕТ СТАРТОВОЙ СЕССИИ*\n\nОна нужна для приёма подарков. "
            "Нажми кнопку и войди прямо здесь, в чате.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("📲 ВОЙТИ ПО ССЫЛКЕ (без кода)", "bz_primary_qr")],
                [btn("🔑 ВОЙТИ ПО КОДУ", "bz_primary_login")]]))
    else:
        await notify_admins(application.bot,
            f"🚀 *АВТОЗАКУП ЗАПУЩЕН*\n\nСтартовая сессия активна.\n"
            f"Купленных аккаунтов: {len(get_all_bought())}",
            parse_mode="Markdown")
    try:
        added, waiting = await asyncio.to_thread(bz_sync_shop)
        if added:
            await notify_owner(application.bot, f"✅ Номера добавлены в магазин: {added} шт.")
    except Exception as e:
        logger.error(f"[SHOP] sync при старте: {e}")
    spawn(scheduler_loop(application))
    spawn(gift_listener(application))
    if BZ_INSPECT_OLD:
        spawn(bz_inspect_backlog())


def register_buyer_handlers(app):
    """Подключает хендлеры автозакупа. Вызывать ДО общих хендлеров магазина."""
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_start, pattern="^buy_start$")],
        states={
            BUY_COUNTRY: [CallbackQueryHandler(buy_country_page, pattern=r"^bcp_\d+$"),
                          CallbackQueryHandler(buy_country_pick, pattern=r"^bc_"),
                          MessageHandler(TXT_INPUT, buy_country_text)],
            BUY_PMODE: [CallbackQueryHandler(buy_pmode_pick, pattern=r"^bpm_(stars|rub|both|keep)$")],
            BUY_PSTARS: [MessageHandler(TXT_INPUT, buy_pstars_input)],
            BUY_PRUB: [MessageHandler(TXT_INPUT, buy_prub_input)],
            BUY_PRICE: [MessageHandler(TXT_INPUT, buy_price_input)],
            BUY_COUNT: [MessageHandler(TXT_INPUT, buy_count_input)],
        },
        fallbacks=[CommandHandler("start", conv_start),
                   CallbackQueryHandler(cancel_conv, pattern="^menu$")],
        allow_reentry=True,
        per_message=False,
    )
    manual_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(manual_add_start, pattern="^manual_add$")],
        states={
            MANUAL_PHONE: [MessageHandler(TXT_INPUT, manual_phone_input)],
            MANUAL_CODE: [MessageHandler(TXT_INPUT, manual_code_input)],
            MANUAL_2FA: [MessageHandler(TXT_INPUT, manual_2fa_input)],
        },
        fallbacks=[CommandHandler("start", conv_start),
                   CallbackQueryHandler(manual_cancel, pattern="^menu$")],
        allow_reentry=True,
        per_message=False,
    )
    delete_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_number_start, pattern="^delete_number_start$")],
        states={
            DELETE_NUMBER_INPUT: [MessageHandler(TXT_INPUT, delete_number_input)],
        },
        fallbacks=[CallbackQueryHandler(delete_cancel, pattern="^get_numbers$"),
                   CallbackQueryHandler(cancel_conv, pattern="^menu$"),
                   CommandHandler("start", conv_start)],
        allow_reentry=True,
        per_message=False,
    )
    prim_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(prim_login_start, pattern="^bz_primary_login$")],
        states={
            PRIM_PHONE: [MessageHandler(TXT_INPUT, prim_phone_input)],
            PRIM_CODE: [CallbackQueryHandler(prim_code_press, pattern=r"^pk_"),
                        MessageHandler(TXT_INPUT, prim_code_input)],
            PRIM_2FA: [MessageHandler(TXT_INPUT, prim_2fa_input)],
        },
        fallbacks=[CallbackQueryHandler(prim_cancel, pattern="^prim_cancel$"),
                   CallbackQueryHandler(prim_qr_start, pattern="^bz_primary_qr$"),
                   CommandHandler("start", conv_start)],
        allow_reentry=True,
        per_message=False,
    )
    qr2fa_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(qr_2fa_start, pattern="^qr_2fa$")],
        states={QR_2FA_PW: [MessageHandler(TXT_INPUT, qr_2fa_input)]},
        fallbacks=[CallbackQueryHandler(prim_cancel, pattern="^prim_cancel$"),
                   CommandHandler("start", conv_start)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(prim_conv)
    app.add_handler(qr2fa_conv)
    app.add_handler(CallbackQueryHandler(prim_qr_start, pattern="^bz_primary_qr$", block=False))
    app.add_handler(CallbackQueryHandler(prim_export, pattern="^prim_export$"))
    app.add_handler(buy_conv)
    app.add_handler(manual_conv)
    app.add_handler(delete_conv)

    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(list_numbers, pattern="^list_numbers$"))
    app.add_handler(CallbackQueryHandler(stats_show, pattern="^stats_show$"))
    app.add_handler(CallbackQueryHandler(run_check_now, pattern="^run_check$", block=False))
    app.add_handler(CallbackQueryHandler(check_all_now, pattern="^check_all$", block=False))
    app.add_handler(CallbackQueryHandler(get_numbers, pattern=r"^(get_numbers|numpage_\d+)$"))
    app.add_handler(CallbackQueryHandler(secure_one, pattern=r"^secure_\d+$", block=False))
    app.add_handler(CallbackQueryHandler(wipe_one, pattern=r"^wipe_\d+$", block=False))
    app.add_handler(CallbackQueryHandler(wipe_all, pattern="^wipe_all$", block=False))
    app.add_handler(CallbackQueryHandler(stop_batch, pattern="^stop_(check|wipe)$"))
    app.add_handler(CallbackQueryHandler(number_detail, pattern=r"^num_\d+$"))
    app.add_handler(CallbackQueryHandler(get_code_for_number, pattern=r"^getcode_\d+$"))
    app.add_handler(CallbackQueryHandler(code_ok, pattern=r"^codeok_\d+$"))
    app.add_handler(CallbackQueryHandler(gift_claim, pattern="^gift_claim$"))
    app.add_handler(CallbackQueryHandler(gift_code, pattern=r"^gcode_\d+$"))
    app.add_handler(CallbackQueryHandler(gift_ok, pattern=r"^gok_\d+$"))
    app.add_handler(CallbackQueryHandler(delete_account, pattern=r"^delacc_\d+$"))
    app.add_handler(CallbackQueryHandler(buy_stop, pattern="^buy_stop$"))
    app.add_handler(CallbackQueryHandler(inspect_now, pattern=r"^inspect_\d+$", block=False))
    app.add_handler(CallbackQueryHandler(spamcheck_bulk, pattern="^bz_spamcheck$", block=False))
    app.add_handler(CallbackQueryHandler(bz_appeal, pattern="^bz_appeal$"))
    app.add_handler(CallbackQueryHandler(keep_toggle, pattern=r"^(keep|unkeep)_\d+$"))
    app.add_handler(CallbackQueryHandler(history_cmd, pattern="^bz_history$"))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CallbackQueryHandler(bz_shop_sync_cb, pattern="^bz_shop_sync$"))
    app.add_handler(CallbackQueryHandler(bz_shop_all_ask, pattern="^bz_shop_all$"))
    app.add_handler(CallbackQueryHandler(bz_shop_all_do, pattern="^bz_shop_all_do$"))
    app.add_handler(CommandHandler("reset", force_reset_stuck))
    app.add_handler(CallbackQueryHandler(bz_db_upload_prompt, pattern="^bz_db_upload$"))
    app.add_handler(MessageHandler(filters.Document.ALL, db_file_received), group=5)
    app.add_handler(CommandHandler("dbinfo", dbinfo_cmd))
    app.add_handler(CommandHandler("wallet", wallet_cmd))
    app.add_handler(CommandHandler("web", web_cmd))
    app.add_handler(CommandHandler("webtest", webtest_cmd))
    app.add_handler(CommandHandler("import_db", import_db_cmd))


from flask import Flask, request
flask_app = Flask(__name__)

def _webhook_ports() -> List[int]:
    """Порты, на которых слушает веб-сервер оплаты. Хостинг может пробрасывать вебхук на любой из них,
    поэтому слушаем сразу несколько. Можно задать свои: WEBHOOK_PORTS=10000,8080."""
    ports: List[int] = []
    for name in ("PORT", "SERVER_PORT", "WEBHOOK_PORT"):
        v = os.getenv(name)
        if v and v.isdigit():
            ports.append(int(v))
    extra = os.getenv("WEBHOOK_PORTS", "")
    ports += [int(x) for x in extra.replace(" ", "").split(",") if x.isdigit()]
    ports += [10000, 8080, 8000, 5000, 3000, 8443, 80, 50, 5050, 9000, 4000, 7860, 8888, 50000]
    return list(dict.fromkeys(ports))


_RECENT_REQUESTS: List[str] = []
_REQ_COUNT = {"post": 0}
YOOMONEY_WEBHOOK_URL = os.getenv("YOOMONEY_WEBHOOK_URL") or "https://pabliss-hosting.duckdns.org/webhooks/p50/d3ec22851259eec7d4503c6ad7baac1b"
_WEB_PORTS_OPEN: List[int] = []


@flask_app.before_request
def _log_every_request():
    if request.method == "POST":
        _REQ_COUNT["post"] += 1
    _RECENT_REQUESTS.append(f"{time.strftime('%H:%M:%S')} {request.method} {request.path} (порт {request.environ.get('SERVER_PORT')}, "
                            f"{request.content_type or 'без типа'}, {request.content_length or 0} байт)")
    del _RECENT_REQUESTS[:-10]
    logger.info(f"🌐 Входящий запрос: {request.method} {request.path} "
                f"(порт {request.environ.get('SERVER_PORT')}, от {request.headers.get('X-Forwarded-For') or request.remote_addr})")


def start_flask():
    from werkzeug.serving import make_server
    started = []
    for port in _webhook_ports():
        try:
            srv = make_server("0.0.0.0", port, flask_app, threaded=True)
        except Exception as e:
            logger.info(f"[WEB] порт {port} недоступен: {str(e)[:60]}")
            continue
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(port)
    _WEB_PORTS_OPEN[:] = started
    logger.info(f"✅ Веб-сервер оплаты слушает порты: {started}")
    env_ports = {k: v for k, v in os.environ.items() if "PORT" in k.upper() or "WEBHOOK" in k.upper()}
    if env_ports:
        logger.info(f"[WEB] переменные окружения хостинга про порты: { {k: ('***' if 'SECRET' in k.upper() or 'TOKEN' in k.upper() else v) for k, v in env_ports.items()} }")
    while True:
        time.sleep(3600)

def _yoomoney_signature_ok(data) -> bool:
    """Проверка подлинности уведомления ЮMoney по секрету (YOOMONEY_SECRET в config.py или переменной окружения).
    Если секрет не задан — проверка отключена (как раньше)."""
    secret = os.getenv("YOOMONEY_SECRET") or ""
    if not secret:
        try:
            import config as _c
            secret = getattr(_c, "YOOMONEY_SECRET", "") or ""
        except Exception:
            secret = ""
    if not secret:
        return True
    import hashlib, hmac
    parts = [data.get(k, "") for k in ("notification_type", "operation_id", "amount", "currency",
                                       "datetime", "sender", "codepro")]
    parts += [secret, data.get("label", "")]
    expected = hashlib.sha1("&".join(parts).encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, data.get("sha1_hash", ""))


@flask_app.route('/', defaults={'subpath': ''}, methods=['POST'])
@flask_app.route('/<path:subpath>', methods=['POST'])
def yoomoney_webhook(subpath=''):
    data = request.form if request.form else (request.get_json(silent=True) or {})
    if not _yoomoney_signature_ok(data):
        logger.warning(f"⛔ Вебхук с неверной подписью отклонён (путь /{subpath})")
        return "forbidden", 403
    logger.info(f"📨 Получен вебхук на /{subpath}: {data}")
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

@flask_app.route('/', defaults={'subpath': ''}, methods=['GET'])
@flask_app.route('/<path:subpath>', methods=['GET'])
def webhook_test(subpath=''):
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
                    _, phone, price_rub, price_stars, _, _, _, _ = product
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
        admin_chat = ADMIN_CHAT_ID if ADMIN_CHAT_ID else ADMIN_ID
        for chat_id in dict.fromkeys((admin_chat, HELPER_ID)):
            sent = False
            try:
                response = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                    timeout=8
                )
                sent = response.status_code == 200
                if not sent:
                    logger.error(f"❌ Ошибка отправки в {chat_id}: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"❌ requests не смог отправить в {chat_id}: {e} — пробую через бота")
            if not sent and BOT_LOOP is not None and globals().get("application") is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        application.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML"),
                        BOT_LOOP).result(timeout=15)
                    sent = True
                except Exception as e:
                    logger.error(f"❌ Через бота тоже не вышло ({chat_id}): {e}")
            if not sent:
                all_ok = False
        if all_ok:
            logger.info("✅ Уведомление отправлено в Telegram")
        else:
            logger.error("❌ Ошибка отправки уведомления в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}")

async def send_rub_notification_to_telegram(context, user_id, username, phone, price_rub, price_stars, product_id):
    try:
        safe_username = html.escape(username) if username else "Нет"
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code) if country_code else None
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        safe_country_name = html.escape(country_name)
        hidden_phone = phone
        safe_hidden_phone = html.escape(hidden_phone)
        datetime_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        message = (
            f"💳 <b>ОПЛАТА РУБЛЯМИ</b>\n\n"
            f"📌 Тип: Оплата рублями (ручная проверка)\n"
            f"💰 Сумма: {price_rub} ₽\n"
            f"💵 Эквивалент: {price_stars} ⭐\n"
            f"👤 Покупатель: <code>{user_id}</code>\n"
            f"🆔 Username: @{safe_username}\n"
            f"🌍 Страна: {country_flag} {safe_country_name}\n"
            f"📱 Номер: <code>{safe_hidden_phone}</code>\n"
            f"🏷️ Товар ID: <code>{product_id}</code>\n"
            f"📅 Дата: {datetime_str}\n\n"
            f"✅ Статус: ОПЛАЧЕНО"
        )
        admin_chat = ADMIN_CHAT_ID if ADMIN_CHAT_ID else ADMIN_ID
        await context.bot.send_message(chat_id=admin_chat, text=message, parse_mode="HTML")
        await context.bot.send_message(chat_id=HELPER_ID, text=message, parse_mode="HTML")
        logger.info("✅ Уведомление об оплате рублями отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления об оплате рублями: {e}")

async def send_stars_notification_to_telegram(context, user_id, username, phone, price_stars, price_rub, product_id):
    try:
        safe_username = html.escape(username) if username else "Нет"
        country_code = get_country_by_phone(phone)
        country = get_country_by_code(country_code) if country_code else None
        country_flag = country['flag'] if country else "🌍"
        country_name = country['name'] if country else "Неизвестно"
        safe_country_name = html.escape(country_name)
        safe_hidden_phone = html.escape(phone)     # владельцу — полный номер, без маскировки
        datetime_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        message = (
            f"⭐ <b>ОПЛАТА ЗВЁЗДАМИ</b>\n\n"
            f"📌 Тип: Оплата Telegram Stars\n"
            f"💰 Сумма: {price_stars} ⭐\n"
            f"💵 Эквивалент: {price_rub} ₽\n"
            f"👤 Покупатель: <code>{user_id}</code>\n"
            f"🆔 Username: @{safe_username}\n"
            f"🌍 Страна: {country_flag} {safe_country_name}\n"
            f"📱 Номер (полный): <code>{safe_hidden_phone}</code>\n"
            f"🏷️ Товар ID: <code>{product_id}</code>\n"
            f"📅 Дата: {datetime_str}\n\n"
            f"✅ Статус: ОПЛАЧЕНО"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode="HTML")
        await context.bot.send_message(chat_id=HELPER_ID, text=message, parse_mode="HTML")
        logger.info("✅ Уведомление об оплате звёздами отправлено в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления об оплате звёздами: {e}")

async def auto_deliver_product(user_id, product_id, coins_paid=None, paid_text=None):
    logger.info(f"🎁 АВТОМАТИЧЕСКАЯ ВЫДАЧА ТОВАРА ДЛЯ {user_id}")
    product = get_phone_product(product_id)
    if not product:
        logger.error(f"❌ Товар {product_id} не найден в БД!")
        return
    _, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa = product
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
        purchase_result = add_purchase(user_id, phone, price_rub, price_stars, session, login_code, lzt_item_id, two_fa, country_code)
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
    awaiting_phone_confirmation[user_id] = {
        'phone': phone,
        'product_id': product_id,
        'session': session,
        'lzt_item_id': lzt_item_id,
        'two_fa': two_fa
    }
    logger.info(f"✅ Данные сохранены для получения кода")
    if user_id in pending_rub:
        del pending_rub[user_id]
        logger.info(f"✅ pending_rub очищен для {user_id}")
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=generate_product_message(phone, price_rub, price_stars, coins=coins_paid, paid_text=paid_text),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [btn("🔑 ПОЛУЧИТЬ КОД", "get_code")],
                [btn("📖 ИНСТРУКЦИЯ", "instruction")],
                [btn("🏠 ГЛАВНОЕ МЕНЮ", "start")]
            ])
        )
        logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            message = generate_product_message(phone, price_rub, price_stars, coins=coins_paid, paid_text=paid_text)
            keyboard = {"inline_keyboard": [[{"text": "🔑 ПОЛУЧИТЬ КОД", "callback_data": "get_code"}], [{"text": "📖 ИНСТРУКЦИЯ", "callback_data": "instruction"}]]}
            requests.post(url, json={"chat_id": user_id, "text": message, "parse_mode": "Markdown", "reply_markup": keyboard}, timeout=5)
            logger.info(f"✅ Сообщение отправлено через requests")
        except Exception as e2:
            logger.error(f"❌ Ошибка через requests: {e2}")

def generate_product_message(phone, price_rub, price_stars, two_fa="", coins=None, paid_text=None):
    country_code = get_country_by_phone(phone)
    country = get_country_by_code(country_code) if country_code else None
    flag = country['flag'] if country else "🌍"
    name = country['name'] if country else "Неизвестно"
    code = country['phone_code'] if country else ""
    two_fa_text = f"🔐 2FA ПАРОЛЬ: `{two_fa}`\n\n" if two_fa else ""
    return (
        f"✅ *ОПЛАЧЕНО!*\n\n"
        f"🌍 *Страна:* {flag} {name} ({code})\n"
        f"📱 *ВАШ НОМЕР:* `{phone}`\n"
        + (f"{paid_text}\n\n" if paid_text else
           f"🪙 Оплачено: {coins} монет\n\n" if coins else f"💰 {price_rub} ₽ / {price_stars}⭐\n\n") +
        f"----\n"
        f"⚠️ *ПОСЛЕ ВХОДА В АККАУНТ ОБЯЗАТЕЛЬНО:*\n"
        f"1️⃣ Смените номер телефона на свой\n"
        f"2️⃣ Поставьте двухфакторную аутентификацию (2FA)\n"
        f"3️⃣ Установите облачный пароль\n"
        f"4️⃣ Привяжите почту для восстановления\n\n"
        f"🔑 Нажмите кнопку, чтобы получить код для входа:"
    )

_HARMLESS_ERRORS = ("message is not modified", "message can't be deleted", "query is too old",
                    "message to edit not found", "message to delete not found", "query id is invalid")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # сетевые сбои (обрыв связи, таймаут) — не баг бота: тихо логируем, без уведомлений и ответов
    from telegram.error import NetworkError, TimedOut, Forbidden
    if isinstance(context.error, Forbidden):
        # пользователь заблокировал бота / удалил чат — это штатная ситуация, писать ему больше нельзя
        logger.warning(f"[BLOCKED] не могу написать пользователю: {context.error}")
        return
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning(f"[NET] сетевая ошибка, пропускаю: {type(context.error).__name__}: {context.error}")
        return
    err_text = str(context.error).lower()
    if any(k in err_text for k in _HARMLESS_ERRORS):
        # безвредно: нажали кнопку, которая ничего не меняет / сообщение устарело — не шум и не ошибка
        logger.info(f"[BOT] пропущено безвредное: {context.error}")
        return
    logger.error(f"❌ Ошибка: {context.error}")
    try:
        key = f"{type(context.error).__name__}:{str(context.error)[:80]}"
        now_t = time.time()
        if now_t - _ERR_THROTTLE.get(key, 0) > 300:       # не чаще раза в 5 минут на одну и ту же ошибку
            _ERR_THROTTLE[key] = now_t
            who = update.effective_user.id if update and getattr(update, "effective_user", None) else "—"
            await notify_owner(context.bot, f"⚠️ Ошибка в боте\n\n{type(context.error).__name__}: {str(context.error)[:300]}\n"
                                            f"Пользователь: {who}")
    except Exception:
        pass
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

    try:
        ref_init_db()
    except Exception as e:
        logger.error(f"❌ Реферальная система: ошибка инициализации БД: {e}")

    logger.info("[VERSION] цены магазина: заданные владельцем (fix-3)")
    try:
        # цены, которые владелец задал в «ЗАКУПИТЬ», применяем к номерам, выложенным со старой ценой (один раз на каждое значение)
        _sr, _ss = _get_setting("shop_price_rub"), _get_setting("shop_price_stars")
        _sig = f"{_sr}/{_ss}"
        if (_sr or _ss) and _get_setting("shop_price_synced") != _sig:
            with sqlite3.connect(DB_NAME, timeout=10) as _conn:
                if _sr:
                    _conn.execute("UPDATE phone_products SET price_rub=? WHERE available=1", (float(_sr),))
                if _ss:
                    _conn.execute("UPDATE phone_products SET price_stars=? WHERE available=1", (int(float(_ss)),))
            _set_setting("shop_price_synced", _sig)
            logger.info(f"[PRICE] номера в магазине приведены к заданной цене: {_ss or '—'}⭐ / {_sr or '—'}₽")
    except Exception as e:
        logger.error(f"❌ Не удалось применить заданную цену к номерам: {e}")

    try:
        bz_init_db()
        logger.info(f"💾 База магазина: {DB_NAME}")
        logger.info(f"💾 База автозакупа: {BZ_DB_NAME}")
        logger.info(f"💾 В базах: магазин [{_db_counts(DB_NAME)}], автозакуп [{_db_counts(BZ_DB_NAME)}]")
    except Exception as e:
        logger.error(f"❌ Автозакуп: ошибка инициализации БД: {e}")

    try:
        await terminal_login()
    except Exception as e:
        logger.error(f"❌ Автозакуп: вход в стартовый аккаунт: {e}")

    # увеличенные таймауты: на мобильной сети/VPN дефолтных 5 сек не хватает (Timed out / ReadError / ConnectError)
    app = (Application.builder().token(BOT_TOKEN)
           .connect_timeout(30).read_timeout(30).write_timeout(30).pool_timeout(30)
           .get_updates_connect_timeout(30).get_updates_read_timeout(45)
           .get_updates_write_timeout(30).get_updates_pool_timeout(30)
           .build())
    global application
    application = app

    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={ADD_ADMIN: [MessageHandler(TXT_INPUT, add_admin_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )

    add_phone_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_phone_start, pattern="^add_phone$")],
        states={
            PHONE_PRICE: [MessageHandler(TXT_INPUT, add_phone_price)],
            PHONE_STARS: [MessageHandler(TXT_INPUT, add_phone_stars)],
            PHONE_NUMBER: [MessageHandler(TXT_INPUT, add_phone_number)],
            ENTER_CODE: [MessageHandler(TXT_INPUT, add_phone_code)],
            ENTER_2FA: [MessageHandler(TXT_INPUT, add_phone_2fa)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    edit_rub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_rub_start, pattern="^edit_rub$")],
        states={EDIT_PRICE: [MessageHandler(TXT_INPUT, edit_rub_input)]},
        fallbacks=[CommandHandler("start", start)]
    )

    edit_stars_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_stars_start, pattern="^edit_stars$")],
        states={EDIT_STARS: [MessageHandler(TXT_INPUT, edit_stars_input)]},
        fallbacks=[CommandHandler("start", start)]
    )

    reply_offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reply_offer_start, pattern=r"^reply_offer:\d+$")],
        states={OFFER_REPLY: [MessageHandler(TXT_INPUT, reply_offer_send)]},
        fallbacks=[CommandHandler("start", start),
                   CallbackQueryHandler(reply_offer_cancel, pattern="^offer_reply_cancel$")]
    )

    offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(make_offer, pattern="^make_offer$")],
        states={AWAITING_OFFER: [MessageHandler(TXT_INPUT, receive_offer)]},
        fallbacks=[CommandHandler("start", start)]
    )

    change_lzt_token_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(change_lzt_token_start, pattern="^change_lzt_token$")],
        states={EDIT_LZT_TOKEN: [MessageHandler(TXT_INPUT, change_lzt_token_confirm)]},
        fallbacks=[CommandHandler("start", start)]
    )

    compensate_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(compensate_start, pattern="^compensate$")],
        states={
            COMPENSATE_USER: [MessageHandler(TXT_INPUT, compensate_confirm)],
            COMPENSATE_SELECT: [CallbackQueryHandler(compensate_select_phone, pattern="^comp_select_")],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    removed_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(removed_start, pattern="^removed_num$")],
        states={
            REMOVED_USER: [MessageHandler(TXT_INPUT, removed_user_input)],
            REMOVED_PHONE: [MessageHandler(TXT_INPUT, removed_phone_input)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    register_buyer_handlers(app)

    app.add_handler(add_admin_conv)
    app.add_handler(add_phone_conv)
    app.add_handler(edit_rub_conv)
    app.add_handler(edit_stars_conv)
    app.add_handler(offer_conv)
    app.add_handler(reply_offer_conv)
    app.add_handler(change_lzt_token_conv)
    app.add_handler(compensate_conv)
    app.add_handler(removed_conv)

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
    app.add_handler(CallbackQueryHandler(instruction, pattern="^instruction$"))
    app.add_handler(CallbackQueryHandler(spam_help, pattern="^spam_help$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_settings_menu, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(remove_admin, pattern="^remove_admin$"))
    app.add_handler(CallbackQueryHandler(remove_admin_confirm, pattern=r"^remove_admin_\d+$"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="^list_admins$"))
    app.add_handler(CallbackQueryHandler(admin_noop, pattern="^adm_noop$"))
    app.add_handler(CallbackQueryHandler(admin_numbers_toggle, pattern=r"^adm_num_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_delete_full, pattern=r"^adm_del_\d+$"))
    app.add_handler(CallbackQueryHandler(review_check_cb, pattern=r"^rv_check_\d+$"))
    app.add_handler(CallbackQueryHandler(review_next_cb, pattern=r"^rv_next_\d+$"))
    app.add_handler(MessageHandler(filters.Chat(username=REVIEW_CHAT_USERNAME) & (filters.TEXT | filters.CAPTION)
                                   & ~filters.COMMAND, on_review_message), group=7)
    app.add_handler(CallbackQueryHandler(referral_screen, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(profile_screen, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(pay_coins, pattern=r"^pay_coins_\d+$"))
    app.add_handler(CallbackQueryHandler(pay_gift, pattern=r"^pay_gift_\d+$"))
    app.add_handler(CallbackQueryHandler(gift_pay_check, pattern=r"^gpay_check$"))

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
    app.add_handler(CallbackQueryHandler(buy_request, pattern=r"^buyreq_\d+$"))
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

    # постоянная кнопка «Главное меню» — из любого раздела, включая активные диалоги
    _menu_btn_handler = MessageHandler(filters.Regex(r"^🏠 Главное меню$"), main_menu_text)
    try:
        for _hs in app.handlers.values():
            for _h in _hs:
                if isinstance(_h, ConversationHandler):
                    _h.fallbacks.append(_menu_btn_handler)
    except Exception as e:
        logger.warning(f"[MENU] не удалось добавить кнопку «Главное меню» в диалоги: {e}")
    app.add_handler(_menu_btn_handler)

    app.add_error_handler(error_handler)

    logger.info("=" * 60)
    logger.info("✅ БОТ ГОТОВ К РАБОТЕ!")
    logger.info("👑 ГЛАВНЫЙ АДМИН: " + str(ADMINS[0]))
    logger.info("🛠️ МОДЕРАТОРЫ: " + str(MODERATORS if MODERATORS else "Нет"))
    logger.info("=" * 60)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(timeout=30, bootstrap_retries=-1, drop_pending_updates=False)

    global BOT_LOOP
    BOT_LOOP = asyncio.get_running_loop()
    logger.info(f"🔄 BOT_LOOP установлен: {BOT_LOOP}")

    try:
        await bz_on_startup(app)
    except Exception as e:
        logger.error(f"❌ Автозакуп: ошибка запуска фоновых задач: {e}")

    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask-сервер запускается (порты смотри в строке «Веб-сервер оплаты слушает порты»)")
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()
