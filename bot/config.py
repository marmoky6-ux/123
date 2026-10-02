"""Конфигурация бота."""
API_TOKEN = "7671253575:AAFGKbHVlqfX1Lezwfe2y1-T1HIvdyRR1I8"
INSTRUCTION_IMAGE = "instruction.png"
OWNER_ID = 867995626  # Главный владелец

# Обязательная подписка на канал
REQUIRED_CHANNEL_USERNAME = "attackrating_news"  # без @ и без https://t.me/
REQUIRED_CHANNEL_LINK = "https://t.me/attackrating_news"
REQUIRED_CHANNEL_CHAT_ID = f"@{REQUIRED_CHANNEL_USERNAME}"

DB_PATH = "business_bot.db"

# Telethon (userbot). Получить на https://my.telegram.org
# Можно оставить общие для всех или каждый пользователь укажет свои через /userbot_api
TELETHON_API_ID = 0  # например 12345678
TELETHON_API_HASH = ""  # например "0123456789abcdef0123456789abcdef"

# Сколько секунд без нового typing-события считать, что человек перестал печатать
TYPING_STOP_TIMEOUT = 6

# Telegram Mini App (userbot setup). Залей папку miniapp/ на свой сайт и укажи URL.
# Пример: "https://example.com/miniapp/index.html"
MINI_APP_URL = "https://fee-structure-cache-planet.trycloudflare.com/"  # ← вставь ссылку на свой сайт
