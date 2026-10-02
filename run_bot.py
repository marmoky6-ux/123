#!/usr/bin/env python3
"""Запуск: python run_bot.py  (из папки artifacts, рядом с пакетом bot/)."""
import asyncio
from bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
