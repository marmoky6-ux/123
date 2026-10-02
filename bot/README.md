# Структура проекта

```
artifacts/
  run_bot.py          # запуск
  miniapp/
    index.html        # Telegram Mini App (установка userbot)
  bot/
    __init__.py
    config.py         # токен, OWNER_ID, канал, MINI_APP_URL
    loader.py         # bot, dp
    db.py             # SQLite
    utils.py          # esc, media, view-once
    main.py           # main(), автоочистка
    userbot_manager.py# Telethon «передумал писать»
    handlers/
      __init__.py     # setup_routers()
      subscription.py # подписка + middleware
      start.py        # /start
      admin.py        # админ-команды
      log.py          # /log, /logcsv
      referral.py     # /ref, /toprefs
      user_commands.py# /help, /love, /type, .команды
      business.py     # business messages / delete / edit
      userbot.py      # /userbot + Mini App web_app_data
```

## Mini App

1. Залей папку `miniapp/` на свой HTTPS-сайт.
2. В `bot/config.py` укажи:
   ```python
   MINI_APP_URL = "https://твой-домен.com/miniapp/index.html"
   ```
3. В @BotFather → Bot Settings → Menu Button / Configure Mini App — можно привязать тот же URL.
4. В боте: `/userbot` → кнопка «Открыть Mini App».

## Запуск

```bash
cd artifacts
python run_bot.py
```
