import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from config import BOT_TOKEN
from handlers.skins import register_handlers_skins
from handlers.templates import register_handlers_templates
from handlers.admin_system import register_handlers_admin

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

register_handlers_skins(dp)
register_handlers_templates(dp)
register_handlers_admin(dp)

async def set_commands():
    commands = [
        types.BotCommand(command="help", description="📖 Помощь"),
        types.BotCommand(command="skin", description="🎲 Получить случайный облик"),
        types.BotCommand(command="catalog", description="📋 Каталог обликов"),
        types.BotCommand(command="inventory", description="📦 Мой инвентарь"),
        types.BotCommand(command="profile", description="👤 Мой профиль"),
    ]
    await bot.set_my_commands(commands)

if __name__ == '__main__':
    from aiogram import executor
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_commands())
    executor.start_polling(dp, skip_updates=True)
