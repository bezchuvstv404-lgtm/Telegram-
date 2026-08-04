# ==========================================
# КОНФИГУРАЦИЯ (ЛИЧНЫЕ ДАННЫЕ)
# ==========================================

<<<<<<< HEAD
BOT_TOKEN = "8254882046:AAFfPJjPGafPs2Me_ApykXj1yoWG4rrJSbY"
ADMIN_ID = 5451203188
API_ID = 37929729
API_HASH = "a9b0048cb977e7efe52c0e9ebef901e1"
YOOMONEY_WALLET = "4100119486619208"
=======
BOT_TOKEN = ""
ADMIN_ID = 
API_ID = 
API_HASH = ""
YOOMONEY_WALLET = ""
>>>>>>> 1c00839 (Clear sensitive data in config.py)
DB_NAME = 'shop.db'
CHANNEL_ID = 
ADMIN_CHAT_ID = 
ADMINS = []

# ==========================================
# БАЗА СТРАН (100+ САМЫХ ПОПУЛЯРНЫХ)
# ==========================================
COUNTRIES = [
    # === ВАШИ СТРАНЫ ===
    {"code": "US", "name": "США", "flag": "🇺🇸", "phone_code": "+1"},
    {"code": "IN", "name": "Индия", "flag": "🇮🇳", "phone_code": "+91"},
    {"code": "MM", "name": "Мьянма (Бирма)", "flag": "🇲🇲", "phone_code": "+95"},
    {"code": "MY", "name": "Малайзия", "flag": "🇲🇾", "phone_code": "+60"},
    {"code": "ES", "name": "Испания", "flag": "🇪🇸", "phone_code": "+34"},
    {"code": "IR", "name": "Иран", "flag": "🇮🇷", "phone_code": "+98"},
    {"code": "TH", "name": "Таиланд", "flag": "🇹🇭", "phone_code": "+66"},
    {"code": "PH", "name": "Филиппины", "flag": "🇵🇭", "phone_code": "+63"},

    # === АЗИЯ (25 стран) ===
    {"code": "CN", "name": "Китай", "flag": "🇨🇳", "phone_code": "+86"},
    {"code": "JP", "name": "Япония", "flag": "🇯🇵", "phone_code": "+81"},
    {"code": "KR", "name": "Южная Корея", "flag": "🇰🇷", "phone_code": "+82"},
    {"code": "ID", "name": "Индонезия", "flag": "🇮🇩", "phone_code": "+62"},
    {"code": "VN", "name": "Вьетнам", "flag": "🇻🇳", "phone_code": "+84"},
    {"code": "SG", "name": "Сингапур", "flag": "🇸🇬", "phone_code": "+65"},
    {"code": "IL", "name": "Израиль", "flag": "🇮🇱", "phone_code": "+972"},
    {"code": "AE", "name": "ОАЭ", "flag": "🇦🇪", "phone_code": "+971"},
    {"code": "SA", "name": "Саудовская Аравия", "flag": "🇸🇦", "phone_code": "+966"},
    {"code": "TR", "name": "Турция", "flag": "🇹🇷", "phone_code": "+90"},
    {"code": "PK", "name": "Пакистан", "flag": "🇵🇰", "phone_code": "+92"},
    {"code": "BD", "name": "Бангладеш", "flag": "🇧🇩", "phone_code": "+880"},
    {"code": "LK", "name": "Шри-Ланка", "flag": "🇱🇰", "phone_code": "+94"},
    {"code": "KH", "name": "Камбоджа", "flag": "🇰🇭", "phone_code": "+855"},
    {"code": "LA", "name": "Лаос", "flag": "🇱🇦", "phone_code": "+856"},
    {"code": "MN", "name": "Монголия", "flag": "🇲🇳", "phone_code": "+976"},
    {"code": "NP", "name": "Непал", "flag": "🇳🇵", "phone_code": "+977"},
    {"code": "AF", "name": "Афганистан", "flag": "🇦🇫", "phone_code": "+93"},
    {"code": "IQ", "name": "Ирак", "flag": "🇮🇶", "phone_code": "+964"},
    {"code": "SY", "name": "Сирия", "flag": "🇸🇾", "phone_code": "+963"},
    {"code": "JO", "name": "Иордания", "flag": "🇯🇴", "phone_code": "+962"},
    {"code": "LB", "name": "Ливан", "flag": "🇱🇧", "phone_code": "+961"},
    {"code": "KW", "name": "Кувейт", "flag": "🇰🇼", "phone_code": "+965"},
    {"code": "QA", "name": "Катар", "flag": "🇶🇦", "phone_code": "+974"},
    {"code": "BH", "name": "Бахрейн", "flag": "🇧🇭", "phone_code": "+973"},
    {"code": "OM", "name": "Оман", "flag": "🇴🇲", "phone_code": "+968"},
    {"code": "YE", "name": "Йемен", "flag": "🇾🇪", "phone_code": "+967"},

    # === ЕВРОПА (35 стран) ===
    {"code": "RU", "name": "Россия", "flag": "🇷🇺", "phone_code": "+7"},
    {"code": "GB", "name": "Великобритания", "flag": "🇬🇧", "phone_code": "+44"},
    {"code": "DE", "name": "Германия", "flag": "🇩🇪", "phone_code": "+49"},
    {"code": "FR", "name": "Франция", "flag": "🇫🇷", "phone_code": "+33"},
    {"code": "IT", "name": "Италия", "flag": "🇮🇹", "phone_code": "+39"},
    {"code": "PT", "name": "Португалия", "flag": "🇵🇹", "phone_code": "+351"},
    {"code": "NL", "name": "Нидерланды", "flag": "🇳🇱", "phone_code": "+31"},
    {"code": "BE", "name": "Бельгия", "flag": "🇧🇪", "phone_code": "+32"},
    {"code": "CH", "name": "Швейцария", "flag": "🇨🇭", "phone_code": "+41"},
    {"code": "AT", "name": "Австрия", "flag": "🇦🇹", "phone_code": "+43"},
    {"code": "SE", "name": "Швеция", "flag": "🇸🇪", "phone_code": "+46"},
    {"code": "NO", "name": "Норвегия", "flag": "🇳🇴", "phone_code": "+47"},
    {"code": "DK", "name": "Дания", "flag": "🇩🇰", "phone_code": "+45"},
    {"code": "FI", "name": "Финляндия", "flag": "🇫🇮", "phone_code": "+358"},
    {"code": "PL", "name": "Польша", "flag": "🇵🇱", "phone_code": "+48"},
    {"code": "UA", "name": "Украина", "flag": "🇺🇦", "phone_code": "+380"},
    {"code": "KZ", "name": "Казахстан", "flag": "🇰🇿", "phone_code": "+7"},
    {"code": "BY", "name": "Беларусь", "flag": "🇧🇾", "phone_code": "+375"},
    {"code": "GR", "name": "Греция", "flag": "🇬🇷", "phone_code": "+30"},
    {"code": "CZ", "name": "Чехия", "flag": "🇨🇿", "phone_code": "+420"},
    {"code": "HU", "name": "Венгрия", "flag": "🇭🇺", "phone_code": "+36"},
    {"code": "RO", "name": "Румыния", "flag": "🇷🇴", "phone_code": "+40"},
    {"code": "BG", "name": "Болгария", "flag": "🇧🇬", "phone_code": "+359"},
    {"code": "HR", "name": "Хорватия", "flag": "🇭🇷", "phone_code": "+385"},
    {"code": "RS", "name": "Сербия", "flag": "🇷🇸", "phone_code": "+381"},
    {"code": "LT", "name": "Литва", "flag": "🇱🇹", "phone_code": "+370"},
    {"code": "LV", "name": "Латвия", "flag": "🇱🇻", "phone_code": "+371"},
    {"code": "EE", "name": "Эстония", "flag": "🇪🇪", "phone_code": "+372"},
    {"code": "SK", "name": "Словакия", "flag": "🇸🇰", "phone_code": "+421"},
    {"code": "SI", "name": "Словения", "flag": "🇸🇮", "phone_code": "+386"},
    {"code": "IE", "name": "Ирландия", "flag": "🇮🇪", "phone_code": "+353"},
    {"code": "AL", "name": "Албания", "flag": "🇦🇱", "phone_code": "+355"},
    {"code": "MD", "name": "Молдова", "flag": "🇲🇩", "phone_code": "+373"},
    {"code": "AM", "name": "Армения", "flag": "🇦🇲", "phone_code": "+374"},
    {"code": "GE", "name": "Грузия", "flag": "🇬🇪", "phone_code": "+995"},

    # === СЕВЕРНАЯ АМЕРИКА (10 стран) ===
    {"code": "CA", "name": "Канада", "flag": "🇨🇦", "phone_code": "+1"},
    {"code": "MX", "name": "Мексика", "flag": "🇲🇽", "phone_code": "+52"},
    {"code": "CU", "name": "Куба", "flag": "🇨🇺", "phone_code": "+53"},
    {"code": "DO", "name": "Доминикана", "flag": "🇩🇴", "phone_code": "+1"},
    {"code": "JM", "name": "Ямайка", "flag": "🇯🇲", "phone_code": "+1"},
    {"code": "BB", "name": "Барбадос", "flag": "🇧🇧", "phone_code": "+1"},
    {"code": "HT", "name": "Гаити", "flag": "🇭🇹", "phone_code": "+509"},
    {"code": "TT", "name": "Тринидад и Тобаго", "flag": "🇹🇹", "phone_code": "+1"},
    {"code": "BS", "name": "Багамы", "flag": "🇧🇸", "phone_code": "+1"},
    {"code": "BZ", "name": "Белиз", "flag": "🇧🇿", "phone_code": "+501"},

    # === ЮЖНАЯ АМЕРИКА (15 стран) ===
    {"code": "BR", "name": "Бразилия", "flag": "🇧🇷", "phone_code": "+55"},
    {"code": "AR", "name": "Аргентина", "flag": "🇦🇷", "phone_code": "+54"},
    {"code": "CO", "name": "Колумбия", "flag": "🇨🇴", "phone_code": "+57"},
    {"code": "PE", "name": "Перу", "flag": "🇵🇪", "phone_code": "+51"},
    {"code": "CL", "name": "Чили", "flag": "🇨🇱", "phone_code": "+56"},
    {"code": "VE", "name": "Венесуэла", "flag": "🇻🇪", "phone_code": "+58"},
    {"code": "EC", "name": "Эквадор", "flag": "🇪🇨", "phone_code": "+593"},
    {"code": "BO", "name": "Боливия", "flag": "🇧🇴", "phone_code": "+591"},
    {"code": "PY", "name": "Парагвай", "flag": "🇵🇾", "phone_code": "+595"},
    {"code": "UY", "name": "Уругвай", "flag": "🇺🇾", "phone_code": "+598"},
    {"code": "GT", "name": "Гватемала", "flag": "🇬🇹", "phone_code": "+502"},
    {"code": "CR", "name": "Коста-Рика", "flag": "🇨🇷", "phone_code": "+506"},
    {"code": "PA", "name": "Панама", "flag": "🇵🇦", "phone_code": "+507"},
    {"code": "SV", "name": "Сальвадор", "flag": "🇸🇻", "phone_code": "+503"},
    {"code": "HN", "name": "Гондурас", "flag": "🇭🇳", "phone_code": "+504"},
    {"code": "NI", "name": "Никарагуа", "flag": "🇳🇮", "phone_code": "+505"},

    # === АФРИКА (25 стран) ===
    {"code": "NG", "name": "Нигерия", "flag": "🇳🇬", "phone_code": "+234"},
    {"code": "ZA", "name": "ЮАР", "flag": "🇿🇦", "phone_code": "+27"},
    {"code": "EG", "name": "Египет", "flag": "🇪🇬", "phone_code": "+20"},
    {"code": "KE", "name": "Кения", "flag": "🇰🇪", "phone_code": "+254"},
    {"code": "MA", "name": "Марокко", "flag": "🇲🇦", "phone_code": "+212"},
    {"code": "DZ", "name": "Алжир", "flag": "🇩🇿", "phone_code": "+213"},
    {"code": "TN", "name": "Тунис", "flag": "🇹🇳", "phone_code": "+216"},
    {"code": "GH", "name": "Гана", "flag": "🇬🇭", "phone_code": "+233"},
    {"code": "UG", "name": "Уганда", "flag": "🇺🇬", "phone_code": "+256"},
    {"code": "TZ", "name": "Танзания", "flag": "🇹🇿", "phone_code": "+255"},
    {"code": "AO", "name": "Ангола", "flag": "🇦🇴", "phone_code": "+244"},
    {"code": "CM", "name": "Камерун", "flag": "🇨🇲", "phone_code": "+237"},
    {"code": "ZM", "name": "Замбия", "flag": "🇿🇲", "phone_code": "+260"},
    {"code": "ZW", "name": "Зимбабве", "flag": "🇿🇼", "phone_code": "+263"},
    {"code": "SN", "name": "Сенегал", "flag": "🇸🇳", "phone_code": "+221"},
    {"code": "CI", "name": "Кот-д'Ивуар", "flag": "🇨🇮", "phone_code": "+225"},
    {"code": "ML", "name": "Мали", "flag": "🇲🇱", "phone_code": "+223"},
    {"code": "BF", "name": "Буркина-Фасо", "flag": "🇧🇫", "phone_code": "+226"},
    {"code": "NE", "name": "Нигер", "flag": "🇳🇪", "phone_code": "+227"},
    {"code": "Tg", "name": "Того", "flag": "🇹🇬", "phone_code": "+228"},
    {"code": "BJ", "name": "Бенин", "flag": "🇧🇯", "phone_code": "+229"},
    {"code": "MZ", "name": "Мозамбик", "flag": "🇲🇿", "phone_code": "+258"},
    {"code": "MW", "name": "Малави", "flag": "🇲🇼", "phone_code": "+265"},
    {"code": "ZM", "name": "Замбия", "flag": "🇿🇲", "phone_code": "+260"},
    {"code": "ZW", "name": "Зимбабве", "flag": "🇿🇼", "phone_code": "+263"},

    # === ОКЕАНИЯ (10 стран) ===
    {"code": "AU", "name": "Австралия", "flag": "🇦🇺", "phone_code": "+61"},
    {"code": "NZ", "name": "Новая Зеландия", "flag": "🇳🇿", "phone_code": "+64"},
    {"code": "FJ", "name": "Фиджи", "flag": "🇫🇯", "phone_code": "+679"},
    {"code": "PG", "name": "Папуа-Новая Гвинея", "flag": "🇵🇬", "phone_code": "+675"},
    {"code": "SB", "name": "Соломоновы Острова", "flag": "🇸🇧", "phone_code": "+677"},
    {"code": "VU", "name": "Вануату", "flag": "🇻🇺", "phone_code": "+678"},
    {"code": "WS", "name": "Самоа", "flag": "🇼🇸", "phone_code": "+685"},
    {"code": "TO", "name": "Тонга", "flag": "🇹🇴", "phone_code": "+676"},
    {"code": "FM", "name": "Микронезия", "flag": "🇫🇲", "phone_code": "+691"},
    {"code": "MH", "name": "Маршалловы Острова", "flag": "🇲🇭", "phone_code": "+692"},
]
