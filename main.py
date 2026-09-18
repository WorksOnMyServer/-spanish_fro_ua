import asyncio
import os
import logging
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from database.connection import init_db
from bot.handlers import router as bot_router
from bot.scheduler import start_scheduler  # <--- Оновлено назву імпорту

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def main():
    print("=== Spanish Learning Bot Ecosystem Starting ===")

    # 1. Ініціалізація бази даних
    await init_db()
    print("[1/3] База даних проініціалізована.")

    # 2. Ініціалізація Telegram Бота
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        print("[Error] BOT_TOKEN не вказано у файлі .env!")
        return

    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(bot_router)

    # 3. Запуск Планувальника та Long Polling
    start_scheduler(bot)  # <--- Викликаємо start_scheduler замість setup_scheduler
    print("[2/3] Планувальник автопостингу запущено.")
    print("[3/3] Бот успішно запущений і готовий до роботи!")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
