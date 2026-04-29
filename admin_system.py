from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import get_db, Admin, AdminLog
import time

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
async def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    with next(get_db()) as db:
        admin = db.query(Admin).filter_by(user_id=user_id).first()
        return admin is not None

async def get_target_user_id(message: types.Message) -> int:
    """Универсальное получение ID цели из команды (ответ, ID, @username)"""
    # 1. Если есть ответ на сообщение
    if message.reply_to_message:
        return message.reply_to_message.from_user.id
    
    # 2. Парсим текст команды
    text = message.text or ""
    # Убираем префиксы / и .
    for prefix in ['/', '.']:
        if text.startswith(prefix):
            text = text[1:]
            break
    
    # Ищем аргументы после команды
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    
    arg = parts[1].strip()
    
    # 2.1 Если аргумент — число (ID)
    if arg.isdigit():
        return int(arg)
    
    # 2.2 Если аргумент — @username
    if arg.startswith('@'):
        try:
            chat = await message.bot.get_chat(arg)
            return chat.id
        except Exception:
            return None
    
    return None

async def get_user_display_name(bot, user_id: int) -> str:
    with next(get_db()) as db:
        admin_record = db.query(Admin).filter_by(user_id=user_id).first()
        if admin_record and admin_record.cached_name:
            return admin_record.cached_name
    
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            display_name = f"@{chat.username}"
        elif chat.full_name:
            display_name = chat.full_name
        else:
            display_name = str(user_id)
    except Exception:
        display_name = str(user_id)
    
    with next(get_db()) as db:
        admin_record = db.query(Admin).filter_by(user_id=user_id).first()
        if admin_record:
            admin_record.cached_name = display_name
            db.commit()
    
    return display_name

async def log_action(admin_id: int, action: str, target_id: int = None, target_name: str = None):
    with next(get_db()) as db:
        log = AdminLog(
            admin_id=admin_id,
            action=action,
            target_id=target_id,
            target_name=target_name,
            timestamp=int(time.time())
        )
        db.add(log)
        db.commit()

async def send_logs_page(message: types.Message, page: int = 0):
    items_per_page = 10
    with next(get_db()) as db:
        total_logs = db.query(AdminLog).count()
        if total_logs == 0:
            await message.reply("📭 Логов пока нет.")
            return
        
        logs = db.query(AdminLog).order_by(AdminLog.timestamp.desc()).offset(page * items_per_page).limit(items_per_page).all()
        total_pages = (total_logs + items_per_page - 1) // items_per_page
        
        action_names = {
            'add_admin': '➕ Назначил администратора',
            'remove_admin': '➖ Удалил администратора',
            'add_skin': '🆕 Добавил скин',
            'delete_skin': '🗑 Удалил скин',
            'add_repeat': '🔄 Добавил повторку',
            'add_clean_photo': '🖼 Добавил чистое изображение'
        }
        
        text = f"📋 <b>Логи действий</b>\n\n"
        for log in logs:
            action_text = action_names.get(log.action, log.action)
            admin_info = await get_user_display_name(message.bot, log.admin_id)
            if log.target_name:
                text += f"• {admin_info} {action_text}: {log.target_name}\n"
            elif log.target_id:
                text += f"• {admin_info} {action_text}: <code>{log.target_id}</code>\n"
            else:
                text += f"• {admin_info} {action_text}\n"
        
        text += f"\n📄 Страница {page + 1} из {total_pages}"
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"logs_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперед ▶", callback_data=f"logs_page_{page+1}"))
        if nav_buttons:
            keyboard.row(*nav_buttons)
        keyboard.add(InlineKeyboardButton(text="🗑 Очистить всё", callback_data="clear_all_logs"))
        keyboard.add(InlineKeyboardButton(text="❌ Закрыть", callback_data="close_logs"))
        
        await message.reply(text, parse_mode="HTML", reply_markup=keyboard)

# ---------- НАВИГАЦИЯ ПО ЛОГАМ ----------
async def logs_page_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("Только для создателя!", show_alert=True)
        return
    page = int(callback_query.data.split("_")[-1])
    await callback_query.message.delete()
    await send_logs_page(callback_query.message, page)
    await callback_query.answer()

async def clear_all_logs_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("Только для создателя!", show_alert=True)
        return
    with next(get_db()) as db:
        db.query(AdminLog).delete()
        db.commit()
    await callback_query.message.edit_text("✅ Все логи успешно очищены!")
    await callback_query.answer()

async def close_logs_callback(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

# ---------- ОСНОВНЫЕ КОМАНДЫ ----------
async def cmd_admin_logs(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только для создателя бота.")
        return
    await send_logs_page(message, 0)

async def cmd_add_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только создатель бота может назначать администраторов.")
        return
    
    target_id = await get_target_user_id(message)
    if not target_id:
        await message.reply("❌ Укажи пользователя:\n• Ответь на его сообщение\n• Напиши ID: /дать админку 123456789\n• Напиши @username: /дать админку @username")
        return
    
    if target_id == OWNER_ID:
        await message.reply("👑 Создатель бота и так имеет все права.")
        return
    
    with next(get_db()) as db:
        existing = db.query(Admin).filter_by(user_id=target_id).first()
        if existing:
            user_info = await get_user_display_name(message.bot, target_id)
            await message.reply(f"⚠️ Пользователь {user_info} уже является администратором.")
            return
        
        new_admin = Admin(user_id=target_id, cached_name=None)
        db.add(new_admin)
        db.commit()
    
    user_info = await get_user_display_name(message.bot, target_id)
    await log_action(message.from_user.id, 'add_admin', target_id, user_info)
    await message.reply(f"✅ Пользователь {user_info} назначен администратором бота!", parse_mode="HTML")

async def cmd_remove_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только создатель бота может удалять администраторов.")
        return
    
    target_id = await get_target_user_id(message)
    if not target_id:
        await message.reply("❌ Укажи пользователя:\n• Ответь на его сообщение\n• Напиши ID: /забрать админку 123456789\n• Напиши @username: /забрать админку @username")
        return
    
    if target_id == OWNER_ID:
        await message.reply("👑 Создатель бота не может быть удалён из администраторов.")
        return
    
    with next(get_db()) as db:
        admin = db.query(Admin).filter_by(user_id=target_id).first()
        if not admin:
            user_info = await get_user_display_name(message.bot, target_id)
            await message.reply(f"⚠️ Пользователь {user_info} не является администратором.")
            return
        
        db.delete(admin)
        db.commit()
    
    user_info = await get_user_display_name(message.bot, target_id)
    await log_action(message.from_user.id, 'remove_admin', target_id, user_info)
    await message.reply(f"✅ Пользователь {user_info} лишён прав администратора.", parse_mode="HTML")

async def cmd_list_admins(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администраторов.")
        return
    
    with next(get_db()) as db:
        admins = db.query(Admin).all()
    
    text = "👑 <b>Список администраторов бота:</b>\n\n"
    creator_info = await get_user_display_name(message.bot, OWNER_ID)
    text += f"• <b>Создатель:</b> {creator_info}\n"
    
    if admins:
        text += "\n<b>Администраторы:</b>\n"
        for admin in admins:
            user_info = await get_user_display_name(message.bot, admin.user_id)
            text += f"• {user_info}\n"
    else:
        text += "\n❌ Нет назначенных администраторов."
    
    await message.reply(text, parse_mode="HTML")

# ---------- РЕГИСТРАЦИЯ ----------
def register_handlers_admin(dp: Dispatcher):
    add_admin_variants = [
        'add_admin', '.add_admin', '/add_admin',
        'датьадминку', 'дать админку', '.датьадминку', '.дать админку', '/датьадминку', '/дать админку'
    ]
    remove_admin_variants = [
        'remove_admin', '.remove_admin', '/remove_admin',
        'забратьадминку', 'забрать админку', '.забратьадминку', '.забрать админку', '/забратьадминку', '/забрать админку'
    ]
    list_admins_variants = [
        'admins', '.admins', '/admins',
        'админы', '.админы', '/админы',
        'список админов', '.список админов', '/список админов'
    ]
    admin_logs_variants = [
        'admin_logs', '.admin_logs', '/admin_logs',
        'логи', '.логи', '/логи',
        'админлоги', '.админлоги', '/админлоги'
    ]
    
    dp.register_message_handler(cmd_add_admin, lambda m: m.text and any(m.text.startswith(v) for v in add_admin_variants))
    dp.register_message_handler(cmd_remove_admin, lambda m: m.text and any(m.text.startswith(v) for v in remove_admin_variants))
    dp.register_message_handler(cmd_list_admins, lambda m: m.text and any(m.text.startswith(v) for v in list_admins_variants))
    dp.register_message_handler(cmd_admin_logs, lambda m: m.text and any(m.text.startswith(v) for v in admin_logs_variants))
    
    dp.register_callback_query_handler(logs_page_callback, lambda c: c.data and c.data.startswith('logs_page_'))
    dp.register_callback_query_handler(clear_all_logs_callback, lambda c: c.data == 'clear_all_logs')
    dp.register_callback_query_handler(close_logs_callback, lambda c: c.data == 'close_logs')
