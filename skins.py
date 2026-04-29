import random
import time
import traceback
import shutil
import os
from datetime import datetime
from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import get_db, Skin, SkinRepeat, SkinUser, SkinInventory, SkinLog, RARITY_PRICES, Hero
from handlers.admin_system import is_admin, log_action

def is_command(text: str, *variants) -> bool:
    if not text:
        return False
    text_lower = text.lower().strip()
    for variant in variants:
        variant_lower = variant.lower()
        if text_lower == variant_lower:
            return True
        if text_lower == f"/{variant_lower}":
            return True
        if text_lower == f".{variant_lower}":
            return True
    return False

def extract_args(text: str) -> str:
    if not text:
        return ""
    parts = text.strip().split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""

def get_cooldown_seconds(vip_level: int) -> int:
    if vip_level == 1:
        return 50 * 60
    elif vip_level == 2:
        return 40 * 60
    elif vip_level == 3:
        return 30 * 60
    return 60 * 60

def get_vip_name(level: int) -> str:
    return ["Обычный", "Легендарный VIP", "Мифический VIP", "VIP Бессмертного"][level]

def normalize_rarity(text: str) -> str:
    r = text.lower()
    if "обычн" in r:
        return "🟢 Обычный"
    if "исключительн" in r:
        return "🔵 Исключительный"
    if "роскошн" in r:
        return "🟣 Роскошный"
    if "изысканн" in r:
        return "🟡 Изысканный"
    if "изящн" in r:
        return "🟠 Изящный"
    if "легендарн" in r:
        return "🔴 Легендарный"
    return None

def parse_skin_description(text: str):
    parts = [p.strip() for p in text.split(',')]
    if len(parts) < 5:
        return None, None, None, None
    skin_name = f"{parts[0]}, {parts[1]}"
    rarity = normalize_rarity(parts[2])
    role = parts[3]
    lane = parts[4]
    return skin_name, rarity, role, lane

def format_skin_message(skin_name, hero_role, hero_lane, rarity, price, user_name, user_id, is_repeat=False):
    user_link = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    if is_repeat:
        title = "<b>ты получил повторный облик!</b>"
    else:
        title = "<b>ты получил новый облик!</b>"
    
    return (f"{user_link}, {title}\n\n"
            f"<blockquote><i><b>{skin_name}</b></i></blockquote>\n"
            f"<blockquote><i><b>Роль: {hero_role}</b></i></blockquote>\n"
            f"<blockquote><i><b>Линия: {hero_lane}</b></i></blockquote>\n\n"
            f"<b>{rarity}</b>\n"
            f"<i>🪙 (+{price} очков коллекционера)</i>")

async def unknown_command(message: types.Message):
    text = message.text or ""
    await message.reply(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Доступные команды:\n"
        "• help — помощь\n"
        "• skin — получить облик\n"
        "• catalog — каталог обликов\n"
        "• inventory — инвентарь\n"
        "• profile — мой профиль\n\n"
        "Все команды работают с / или . или без них",
        parse_mode="HTML"
    )

async def auto_add_skin(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    if not message.photo:
        return
    
    caption = message.caption or ""
    lines = [line.strip() for line in caption.strip().split('\n') if line.strip()]
    photos = message.photo
    
    for line in lines:
        if not line:
            continue
        
        if line.lower().startswith("чистое фото для"):
            skin_name = line[15:].strip()
            if not skin_name:
                await message.reply("❌ Не указано имя скина после 'чистое фото для'")
                continue
            
            photo_file_id = photos[0].file_id if photos else None
            
            with next(get_db()) as db:
                skin = db.query(Skin).filter_by(name=skin_name).first()
                if not skin:
                    await message.reply(f"❌ Скин '{skin_name}' не найден в каталоге.")
                    continue
                
                skin.clean_image_file_id = photo_file_id
                db.commit()
                await log_action(message.from_user.id, 'add_clean_photo', skin.id, skin_name)
            
            await message.reply(f"✅ Чистое фото для скина <b>{skin_name}</b> добавлено!", parse_mode="HTML")
        
        elif line.lower().startswith("повторка для"):
            skin_name = line[12:].strip()
            if not skin_name:
                await message.reply("❌ Не указано имя скина после 'повторка для'")
                continue
            
            photo_file_id = photos[0].file_id if photos else None
            
            with next(get_db()) as db:
                skin = db.query(Skin).filter_by(name=skin_name).first()
                if not skin:
                    await message.reply(f"❌ Скин '{skin_name}' не найден в каталоге.")
                    continue
                
                repeat = db.query(SkinRepeat).filter_by(skin_id=skin.id).first()
                if not repeat:
                    repeat = SkinRepeat(skin_id=skin.id, repeat_image_file_id=photo_file_id)
                    db.add(repeat)
                else:
                    repeat.repeat_image_file_id = photo_file_id
                db.commit()
                await log_action(message.from_user.id, 'add_repeat', skin.id, skin.name)
            
            await message.reply(f"✅ Повторка для скина <b>{skin_name}</b> добавлена!", parse_mode="HTML")
        
        else:
            skin_name, rarity, role, lane = parse_skin_description(line)
            if not skin_name:
                await message.reply(f"❌ Неверный формат: '{line}'\nНужно: Герой, Название, редкость, роль, линия")
                continue
            
            if not rarity:
                rarity = "🟢 Обычный"
            
            photo_file_id = photos[0].file_id if photos else None
            
            with next(get_db()) as db:
                hero_name = skin_name.split(',')[0].strip()
                hero = db.query(Hero).filter_by(name=hero_name).first()
                if not hero:
                    hero = Hero(name=hero_name, role=role, lane=lane)
                    db.add(hero)
                    db.commit()
                else:
                    hero.role = role
                    hero.lane = lane
                    db.commit()
                
                existing = db.query(Skin).filter_by(name=skin_name).first()
                if existing:
                    await message.reply(f"ℹ️ Скин '{skin_name}' уже существует.")
                    continue
                
                new_skin = Skin(hero_id=hero.id, name=skin_name, rarity=rarity, image_file_id=photo_file_id, clean_image_file_id=None)
                db.add(new_skin)
                db.commit()
                await log_action(message.from_user.id, 'add_skin', new_skin.id, skin_name)
            
            await message.reply(f"✅ Скин <b>{skin_name}</b> добавлен в каталог!\nРедкость: {rarity}\nРоль: {role}\nЛиния: {lane}", parse_mode="HTML")

async def cmd_help(message: types.Message):
    await message.reply(
        "🎮 <b>Команды бота скинов Mobile Legends</b>\n\n"
        "Все команды работают с / или . или без них\n\n"
        "<b>Помощь</b> — help, хелп, помощь\n"
        "<b>Случайный облик</b> — skin, скин, хочу скин\n"
        "<b>Каталог обликов</b> — catalog, каталог\n"
        "<b>Мой инвентарь</b> — inventory, инвентарь, inv, инв\n"
        "<b>Мой профиль</b> — profile, профиль, проф",
        parse_mode="HTML"
    )

async def cmd_adminhelp(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администратора.")
        return
    await message.reply(
        "👑 <b>Админ-команды</b>\n\n"
        "<b>Добавление обликов (админ/создатель):</b>\n"
        "• Отправь фото с подписью: Герой, Название, редкость, роль, линия\n"
        "<b>Добавление повторки (админ/создатель):</b>\n"
        "• Отправь фото с подписью: повторка для Герой, Название\n"
        "<b>Добавление чистого фото для профиля (админ/создатель):</b>\n"
        "• Отправь фото с подписью: чистое фото для Герой, Название\n\n"
        "<b>Замена фото (админ/создатель):</b>\n"
        "• /заменить Герой, Название, редкость — замена фото выпадения\n"
        "• /заменить повторку для Герой, Название — замена фото повторки\n"
        "• /заменить чистое фото для Герой, Название — замена чистого фото\n\n"
        "<b>Управление своим инвентарём (админ/создатель):</b>\n"
        "• take, взять, выдать — выдать себе облик\n"
        "• remove, удалить, убрать — удалить свой облик\n"
        "<b>Управление каталогом (админ/создатель):</b>\n"
        "• del_skin, удали скин, удалискин — удалить скин из каталога\n\n"
        "<b>Только для создателя:</b>\n"
        "• reset_profile, сбросить профиль — сбросить профиль пользователя\n"
        "• reset_cooldown, сбросить кд, сброс — сбросить КД (по ответу, ID или @username)\n"
        "• set_vip, вип — выдать VIP (1-3) или снять (0)\n"
        "• savecode, сохранить код — резервная копия кода\n\n"
        "<b>Управление администраторами (только создатель):</b>\n"
        "• add_admin, дать админку / дать админку ID — назначить администратора\n"
        "• remove_admin, забрать админку / забрать админку ID — удалить администратора\n"
        "• admins, админы, список админов — список администраторов\n"
        "• admin_logs, логи, админлоги — логи действий (с пагинацией)",
        parse_mode="HTML"
    )

async def cmd_catalog(message: types.Message):
    with next(get_db()) as db:
        all_skins = db.query(Skin).all()
        if not all_skins:
            await message.reply("📭 Каталог пуст.")
            return

        by_rarity = {}
        for skin in all_skins:
            by_rarity.setdefault(skin.rarity, []).append(skin.name)

    rarity_order = [
        ("🔴 Легендарный", "Легендарные"),
        ("🟠 Изящный", "Изящные"),
        ("🟡 Изысканный", "Изысканные"),
        ("🟣 Роскошный", "Роскошные"),
        ("🔵 Исключительный", "Исключительные"),
        ("🟢 Обычный", "Обычные")
    ]

    text = "📋 <b>Каталог обликов</b>\n\n"
    for rarity_key, rarity_name in rarity_order:
        if rarity_key in by_rarity:
            skins_list = by_rarity[rarity_key]
            price = RARITY_PRICES.get(rarity_key, 100)
            emoji = rarity_key.split()[0]
            text += f"<b>{emoji} {rarity_name} ({len(skins_list)}) — {price} очков</b>\n"
            for skin_name in sorted(skins_list, key=str.lower):
                text += f"<blockquote><i><b>{skin_name}</b></i></blockquote>\n"
            text += "\n"

    await message.reply(text[:4090], parse_mode="HTML")

last_skin_use = {}

async def get_random_skin(message: types.Message):
    user_id = message.from_user.id
    now = int(time.time())

    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=user_id).first()
        if not user:
            user = SkinUser(user_id=user_id)
            db.add(user)
            db.commit()

        last_time = user.last_skin_time if user.last_skin_time else 0
        cooldown = get_cooldown_seconds(user.vip_level)
        remaining = (last_time + cooldown) - now
        
        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            user_link = f"<a href='tg://user?id={user_id}'>{message.from_user.full_name}</a>"
            await message.reply(f"{user_link}, ты сможешь получить следующий облик через {minutes} мин {seconds} сек! ⏳", parse_mode="HTML")
            return

        all_skins = db.query(Skin).join(Hero).all()
        if not all_skins:
            await message.reply("❌ Нет скинов. Добавь их через фото.")
            return

        skin = random.choice(all_skins)
        skin_id = skin.id
        skin_name = skin.name
        skin_rarity = skin.rarity
        skin_price = skin.price
        skin_image = skin.image_file_id
        hero_role = skin.hero.role if skin.hero else "❓ Не указана"
        hero_lane = skin.hero.lane if skin.hero else "❓ Не указана"
        
        owned = db.query(SkinInventory).filter_by(user_id=user_id, skin_id=skin_id).first()
        is_repeat = owned is not None

        user.last_skin_time = now
        
        if not is_repeat:
            user.collector_points += skin_price
            db.add(SkinInventory(user_id=user_id, skin_id=skin_id))
            db.commit()
        else:
            db.commit()

        db.add(SkinLog(user_id=user_id, skin_id=skin_id, timestamp=now, is_repeat=1 if is_repeat else 0))
        db.commit()

    last_skin_use[user_id] = now

    caption = format_skin_message(skin_name, hero_role, hero_lane, skin_rarity, skin_price, message.from_user.full_name, user_id, is_repeat)

    photo_file_id = skin_image
    if is_repeat:
        with next(get_db()) as db:
            repeat_photo = db.query(SkinRepeat).filter_by(skin_id=skin_id).first()
            if repeat_photo:
                photo_file_id = repeat_photo.repeat_image_file_id

    if photo_file_id:
        await message.reply_photo(photo=photo_file_id, caption=caption, parse_mode="HTML")
    else:
        await message.reply(caption, parse_mode="HTML")

async def cmd_inventory(message: types.Message):
    user_id = message.from_user.id
    
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=user_id).first()
        points = user.collector_points if user else 0
        
        inventory = db.query(SkinInventory).filter_by(user_id=user_id).all()
        if not inventory:
            await message.reply("📭 У тебя пока нет обликов. Используй /skin")
            return
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton(text="🎨 Установить облик на профиль", callback_data=f"equip_skin_menu_{user_id}"))
        
        skin_names = [f"🎽 {item.skin.name}" for item in inventory]
        text = "📦 Твой инвентарь:\n" + "\n".join(skin_names[:30])
        if len(skin_names) > 30:
            text += f"\n... и ещё {len(skin_names)-30}"
        text += f"\n\n🏆 Очков коллекционера: {points}"
        
        await message.reply(text, reply_markup=keyboard, parse_mode="HTML")

async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user_link = f"<a href='tg://user?id={user_id}'>{message.from_user.full_name}</a>"
    
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=user_id).first()
        if not user:
            user = SkinUser(user_id=user_id)
            db.add(user)
            db.commit()
        
        vip_level = user.vip_level
        points = user.collector_points
        equipped_skin_id = user.equipped_skin_id
        inventory_count = db.query(SkinInventory).filter_by(user_id=user_id).count()
        
        equipped_skin = None
        if equipped_skin_id:
            equipped_skin = db.query(Skin).filter_by(id=equipped_skin_id).first()
    
    text = f"<b>👤 Профиль пользователя {user_link}</b>\n\n"
    text += f"<b>👑 VIP статус:</b> {get_vip_name(vip_level)}\n"
    text += f"<b>📦 Скинов в коллекции:</b> {inventory_count}\n"
    text += f"<b>🏆 Очков коллекционера:</b> {points}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text="📦 Инвентарь", callback_data=f"inventory_from_profile_{user_id}"))
    
    if equipped_skin:
        text += f"<b>✨ Установленный облик:</b>\n<blockquote><i><b>{equipped_skin.name}</b></i></blockquote>\n"
        photo_id = equipped_skin.clean_image_file_id if equipped_skin.clean_image_file_id else equipped_skin.image_file_id
        if photo_id:
            await message.reply_photo(photo=photo_id, caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.reply(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        text += "<b>✨ Установленный облик:</b> ❌ не установлен\n"
        await message.reply(text, parse_mode="HTML", reply_markup=keyboard)

# ---------- ОБРАБОТЧИКИ КНОПОК ----------
async def inventory_from_profile_callback(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split("_")[-1])
    if callback_query.from_user.id != user_id:
        await callback_query.answer("Это не твой профиль!", show_alert=True)
        return
    
    await callback_query.answer()
    
    try:
        await callback_query.message.delete()
    except:
        pass
    
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=user_id).first()
        points = user.collector_points if user else 0
        inventory = db.query(SkinInventory).filter_by(user_id=user_id).all()
        
        if not inventory:
            text = "📭 У тебя пока нет обликов. Используй /skin"
            await callback_query.message.answer(text, parse_mode="HTML")
            return
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton(text="🎨 Установить облик на профиль", callback_data=f"equip_skin_menu_{user_id}"))
        
        skin_names = [f"🎽 {item.skin.name}" for item in inventory]
        text = "📦 Твой инвентарь:\n" + "\n".join(skin_names[:30])
        if len(skin_names) > 30:
            text += f"\n... и ещё {len(skin_names)-30}"
        text += f"\n\n🏆 Очков коллекционера: {points}"
    
    await callback_query.message.answer(text, parse_mode="HTML", reply_markup=keyboard)

async def equip_skin_menu_callback(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split("_")[-1])
    if callback_query.from_user.id != user_id:
        await callback_query.answer("Это не твой профиль!", show_alert=True)
        return
    
    with next(get_db()) as db:
        inventory = db.query(SkinInventory).filter_by(user_id=user_id).all()
        if not inventory:
            await callback_query.answer("У тебя нет скинов для установки!", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        for item in inventory:
            skin_id = item.skin.id
            skin_name = item.skin.name
            keyboard.add(InlineKeyboardButton(text=skin_name, callback_data=f"equip_skin_{user_id}_{skin_id}"))
        keyboard.add(InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_equip_{user_id}"))
    
    await callback_query.message.edit_text("🎨 <b>Выбери облик, который хочешь установить на профиль:</b>", parse_mode="HTML", reply_markup=keyboard)
    await callback_query.answer()

async def equip_skin_callback(callback_query: types.CallbackQuery):
    parts = callback_query.data.split("_")
    if len(parts) < 4:
        await callback_query.answer("Ошибка")
        return
    
    target_user_id = int(parts[2])
    skin_id = int(parts[3])
    
    if callback_query.from_user.id != target_user_id:
        await callback_query.answer("Это не твой профиль!", show_alert=True)
        return
    
    skin_name = None
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=target_user_id).first()
        if not user:
            user = SkinUser(user_id=target_user_id)
            db.add(user)
        
        has_skin = db.query(SkinInventory).filter_by(user_id=target_user_id, skin_id=skin_id).first()
        if not has_skin:
            await callback_query.answer("У тебя нет этого скина!", show_alert=True)
            return
        
        skin = db.query(Skin).filter_by(id=skin_id).first()
        if not skin:
            await callback_query.answer("Скин не найден", show_alert=True)
            return
        
        skin_name = skin.name
        user.equipped_skin_id = skin_id
        db.commit()
    
    await callback_query.answer(f"✅ Скин {skin_name} установлен на профиль!")
    
    try:
        await callback_query.message.delete()
    except:
        pass
    
    user_id = target_user_id
    user_link = f"<a href='tg://user?id={user_id}'>{callback_query.from_user.full_name}</a>"
    
    with next(get_db()) as db:
        user_data = db.query(SkinUser).filter_by(user_id=user_id).first()
        if not user_data:
            user_data = SkinUser(user_id=user_id)
            db.add(user_data)
            db.commit()
        
        vip_level = user_data.vip_level
        points = user_data.collector_points
        equipped_skin_id = user_data.equipped_skin_id
        inventory_count = db.query(SkinInventory).filter_by(user_id=user_id).count()
        
        equipped_skin_obj = None
        if equipped_skin_id:
            equipped_skin_obj = db.query(Skin).filter_by(id=equipped_skin_id).first()
    
    text = f"<b>👤 Профиль пользователя {user_link}</b>\n\n"
    text += f"<b>👑 VIP статус:</b> {get_vip_name(vip_level)}\n"
    text += f"<b>📦 Скинов в коллекции:</b> {inventory_count}\n"
    text += f"<b>🏆 Очков коллекционера:</b> {points}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text="📦 Инвентарь", callback_data=f"inventory_from_profile_{user_id}"))
    
    if equipped_skin_obj:
        text += f"<b>✨ Установленный облик:</b>\n<blockquote><i><b>{equipped_skin_obj.name}</b></i></blockquote>\n"
        photo_id = equipped_skin_obj.clean_image_file_id if equipped_skin_obj.clean_image_file_id else equipped_skin_obj.image_file_id
        if photo_id:
            await callback_query.bot.send_photo(chat_id=callback_query.message.chat.id, photo=photo_id, caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await callback_query.bot.send_message(chat_id=callback_query.message.chat.id, text=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        text += "<b>✨ Установленный облик:</b> ❌ не установлен\n"
        await callback_query.bot.send_message(chat_id=callback_query.message.chat.id, text=text, parse_mode="HTML", reply_markup=keyboard)

async def cancel_equip_callback(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split("_")[-1])
    if callback_query.from_user.id != user_id:
        await callback_query.answer("Это не твой профиль!", show_alert=True)
        return
    
    await callback_query.message.delete()
    await callback_query.answer("❌ Установка облика отменена")
    
    await cmd_profile(callback_query.message)

# ---------- ЗАМЕНА ФОТО ----------
async def replace_skin_photo(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администраторов.")
        return
    if not message.photo:
        await message.reply("❌ Отправь фото с подписью:\n• заменить чистое фото для Герой, Название\n• заменить повторку для Герой, Название\n• заменить Герой, Название, редкость")
        return
    
    caption = message.caption or ""
    text = caption.strip()
    photo_file_id = message.photo[-1].file_id
    
    if text.lower().startswith(("заменить чистое фото для")):
        skin_name = text[22:].strip()
        if not skin_name:
            await message.reply("❌ Не указано имя скина")
            return
        
        with next(get_db()) as db:
            skin = db.query(Skin).filter_by(name=skin_name).first()
            if not skin:
                await message.reply(f"❌ Скин '{skin_name}' не найден")
                return
            skin.clean_image_file_id = photo_file_id
            db.commit()
            await log_action(message.from_user.id, 'add_clean_photo', skin.id, skin_name)
        
        await message.reply(f"✅ Чистое фото для <b>{skin_name}</b> заменено!", parse_mode="HTML")
        return
    
    if text.lower().startswith(("заменить повторку для")):
        skin_name = text[17:].strip()
        if not skin_name:
            await message.reply("❌ Не указано имя скина")
            return
        
        with next(get_db()) as db:
            skin = db.query(Skin).filter_by(name=skin_name).first()
            if not skin:
                await message.reply(f"❌ Скин '{skin_name}' не найден")
                return
            
            repeat = db.query(SkinRepeat).filter_by(skin_id=skin.id).first()
            if not repeat:
                repeat = SkinRepeat(skin_id=skin.id, repeat_image_file_id=photo_file_id)
                db.add(repeat)
            else:
                repeat.repeat_image_file_id = photo_file_id
            db.commit()
            await log_action(message.from_user.id, 'add_repeat', skin.id, skin_name)
        
        await message.reply(f"✅ Повторка для <b>{skin_name}</b> заменена!", parse_mode="HTML")
        return
    
    if text.lower().startswith(("заменить")):
        line = text[8:].strip()
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 3:
            await message.reply("❌ Неверный формат. Пример: заменить Фрейя, Покорительница галактики, легендарный")
            return
        
        skin_name = f"{parts[0]}, {parts[1]}"
        
        with next(get_db()) as db:
            skin = db.query(Skin).filter_by(name=skin_name).first()
            if not skin:
                await message.reply(f"❌ Скин '{skin_name}' не найден")
                return
            skin.image_file_id = photo_file_id
            db.commit()
            await log_action(message.from_user.id, 'add_skin', skin.id, skin_name)
        
        await message.reply(f"✅ Фото выпадения для <b>{skin_name}</b> заменено!", parse_mode="HTML")
        return
    
    await message.reply("❌ Неверный формат.")

# ---------- АДМИНСКИЕ КОМАНДЫ ----------
async def del_skin_command(message: types.Message, page: int = 0):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администраторов.")
        return
    
    with next(get_db()) as db:
        all_skins = db.query(Skin).order_by(Skin.name).all()
        if not all_skins:
            await message.reply("📭 Каталог пуст.")
            return
    
    items_per_page = 10
    total_pages = (len(all_skins) + items_per_page - 1) // items_per_page
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    start = page * items_per_page
    end = start + items_per_page
    skins_on_page = all_skins[start:end]
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for skin in skins_on_page:
        keyboard.add(InlineKeyboardButton(text=f"🗑 {skin.name}", callback_data=f"delete_skin_{skin.id}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"del_skin_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶", callback_data=f"del_skin_page_{page+1}"))
    if nav_buttons:
        keyboard.row(*nav_buttons)
    
    keyboard.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_skin"))
    
    await message.reply(f"🗑 <b>Выбери скин для удаления</b> (страница {page+1}/{total_pages}):", reply_markup=keyboard, parse_mode="HTML")

async def process_del_skin_page(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нельзя", show_alert=True)
        return
    page = int(callback_query.data.split("_")[-1])
    class FakeMessage:
        from_user = callback_query.from_user
        chat = callback_query.message.chat
        async def reply(self, text, **kwargs):
            await callback_query.message.reply(text, **kwargs)
    await del_skin_command(FakeMessage(), page)
    await callback_query.message.delete()
    await callback_query.answer()

async def process_delete_skin(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нельзя", show_alert=True)
        return
    skin_id = int(callback_query.data.split("_")[-1])
    
    with next(get_db()) as db:
        skin = db.query(Skin).filter_by(id=skin_id).first()
        if not skin:
            await callback_query.answer("Скин не найден")
            return
        skin_name = skin.name
        db.query(SkinRepeat).filter_by(skin_id=skin_id).delete()
        db.query(SkinInventory).filter_by(skin_id=skin_id).delete()
        db.query(SkinLog).filter_by(skin_id=skin_id).delete()
        db.delete(skin)
        db.commit()
        await log_action(callback_query.from_user.id, 'delete_skin', skin_id, skin_name)
    
    await callback_query.message.edit_text(f"✅ Скин <b>{skin_name}</b> удалён из каталога!", parse_mode="HTML")
    await callback_query.answer()

async def cancel_delete_skin(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нельзя", show_alert=True)
        return
    await callback_query.message.edit_text("❌ Удаление отменено.")
    await callback_query.answer()

async def take_skin_command(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администраторов.")
        return
    from keyboards.inline import skins_choose_keyboard
    await message.reply("Выбери скин:", reply_markup=skins_choose_keyboard())

async def process_take_skin(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нельзя", show_alert=True)
        return
    
    try:
        skin_id = int(callback_query.data.replace("take_skin_", ""))
    except:
        await callback_query.answer("Ошибка формата", show_alert=True)
        return
    
    with next(get_db()) as db:
        skin = db.query(Skin).filter_by(id=skin_id).first()
        if not skin:
            await callback_query.answer("Скин не найден", show_alert=True)
            return
        
        skin_id_val = skin.id
        skin_name_val = skin.name
        skin_rarity = skin.rarity
        skin_price = skin.price
        skin_image = skin.image_file_id
        hero_role = skin.hero.role if skin.hero else "❓ Не указана"
        hero_lane = skin.hero.lane if skin.hero else "❓ Не указана"
        
        user_id = callback_query.from_user.id
        
        existing = db.query(SkinInventory).filter_by(user_id=user_id, skin_id=skin_id_val).first()
        is_repeat = existing is not None
        
        user = db.query(SkinUser).filter_by(user_id=user_id).first()
        if not user:
            user = SkinUser(user_id=user_id)
            db.add(user)
        
        if not is_repeat:
            user.collector_points += skin_price
            db.add(SkinInventory(user_id=user_id, skin_id=skin_id_val))
            db.commit()
        else:
            db.commit()
    
    caption = format_skin_message(skin_name_val, hero_role, hero_lane, skin_rarity, skin_price, callback_query.from_user.full_name, user_id, is_repeat)
    
    photo_file_id = skin_image
    if is_repeat:
        with next(get_db()) as db:
            repeat_photo = db.query(SkinRepeat).filter_by(skin_id=skin_id_val).first()
            if repeat_photo:
                photo_file_id = repeat_photo.repeat_image_file_id
    
    await callback_query.message.delete()
    if photo_file_id:
        await callback_query.message.answer_photo(photo=photo_file_id, caption=caption, parse_mode="HTML")
    else:
        await callback_query.message.answer(caption, parse_mode="HTML")
    await callback_query.answer("✅ Выдано!" if not is_repeat else "✅ Повторка выдана!")

async def remove_skin_start(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только для администраторов.")
        return
    user_id = message.from_user.id
    with next(get_db()) as db:
        inventory = db.query(SkinInventory).filter_by(user_id=user_id).all()
        if not inventory:
            await message.reply("📭 В твоём инвентаре нет скинов.")
            return
        skin_list = [(item.skin.id, item.skin.name) for item in inventory]
    
    from keyboards.inline import inventory_remove_keyboard
    await message.reply("Выбери скин для удаления:", reply_markup=inventory_remove_keyboard(user_id, skin_list))

async def process_remove_skin(callback_query: types.CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        await callback_query.answer("Нельзя", show_alert=True)
        return
    
    data = callback_query.data
    prefix = "remove_skin_"
    if not data.startswith(prefix):
        await callback_query.answer("Ошибка формата")
        return
    
    parts = data.split("_")
    if len(parts) < 4:
        await callback_query.answer("Ошибка формата")
        return
    
    try:
        target_user_id = int(parts[2])
        skin_id = int(parts[3])
    except:
        await callback_query.answer("Ошибка данных")
        return
    
    with next(get_db()) as db:
        skin = db.query(Skin).filter_by(id=skin_id).first()
        if not skin:
            await callback_query.answer("Скин не найден", show_alert=True)
            return
        
        inv = db.query(SkinInventory).filter_by(user_id=target_user_id, skin_id=skin_id).first()
        if not inv:
            await callback_query.answer("Нет в инвентаре", show_alert=True)
            return
        
        skin_name = skin.name
        skin_price = skin.price
        
        db.delete(inv)
        
        user = db.query(SkinUser).filter_by(user_id=target_user_id).first()
        if user:
            user.collector_points -= skin_price
            if user.collector_points < 0:
                user.collector_points = 0
            db.commit()
        else:
            db.commit()
    
    await callback_query.message.delete()
    await callback_query.message.answer(f"✅ {skin_name} удалён из инвентаря!\n🏆 {skin_price} очков вычтено из коллекции.", parse_mode="HTML")
    await callback_query.answer()

async def reset_cooldown(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    
    target_id = None
    
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    else:
        text = message.text or ""
        for prefix in ['/', '.']:
            if text.startswith(prefix):
                text = text[1:]
                break
        words = text.split()
        if len(words) > 1:
            arg = words[1]
            if arg.isdigit():
                target_id = int(arg)
            elif arg.startswith('@'):
                try:
                    chat = await message.bot.get_chat(arg)
                    target_id = chat.id
                except:
                    await message.reply(f"❌ Пользователь {arg} не найден.")
                    return
            else:
                await message.reply("❌ Укажи пользователя:\n• Ответь на его сообщение\n• Укажи ID: /сбросить кд 123456789\n• Укажи @username: /сбросить кд @username")
                return
    
    if not target_id:
        await message.reply("❌ Укажи пользователя:\n• Ответь на его сообщение\n• Укажи ID: /сбросить кд 123456789\n• Укажи @username: /сбросить кд @username")
        return
    
    global last_skin_use
    last_skin_use[target_id] = 0
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=target_id).first()
        if user:
            user.last_skin_time = 0
            db.commit()
    
    await message.reply(f"✅ КД пользователя сброшена!")

async def set_vip(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только для создателя бота.")
        return
    if not message.reply_to_message:
        await message.reply("❌ Ответь на сообщение пользователя.\nПример: вип (1-3) — выдать VIP, вип 0 — снять VIP")
        return
    
    text = message.text.strip()
    for prefix in ['/', '.']:
        if text.startswith(prefix):
            text = text[1:]
    
    parts = text.split()
    if len(parts) < 2:
        await message.reply("❌ Укажи уровень: 0, 1, 2 или 3\n0 — снять VIP, 1-3 — выдать VIP")
        return
    
    try:
        level = int(parts[1])
        if level not in (0, 1, 2, 3):
            await message.reply("❌ Уровень должен быть 0, 1, 2 или 3")
            return
    except:
        await message.reply("❌ Уровень должен быть числом (0, 1, 2 или 3)")
        return
    
    target_id = message.reply_to_message.from_user.id
    
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=target_id).first()
        if not user:
            user = SkinUser(user_id=target_id)
            db.add(user)
        user.vip_level = level
        db.commit()
    
    if level == 0:
        await message.reply(f"✅ VIP статус пользователя сброшен (теперь {get_vip_name(0)})")
    else:
        await message.reply(f"✅ Пользователю выдан VIP: {get_vip_name(level)}")

async def reset_profile_command(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только для создателя бота.")
        return
    
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user.id
    else:
        args = extract_args(message.text)
        if args and args.isdigit():
            target = int(args)
    
    if not target:
        await message.reply("❌ Укажи пользователя: ответь на его сообщение или укажи ID.")
        return
    
    with next(get_db()) as db:
        user = db.query(SkinUser).filter_by(user_id=target).first()
        if user:
            user.collector_points = 0
            user.vip_level = 0
            user.last_skin_time = 0
            user.equipped_skin_id = None
            db.query(SkinInventory).filter_by(user_id=target).delete()
            db.commit()
            await message.reply(f"✅ Профиль пользователя {target} полностью сброшен.")
        else:
            await message.reply(f"❌ Пользователь {target} не найден в базе.")

async def save_code_backup(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только для создателя бота.")
        return
    
    await message.reply("🔄 Создаю резервную копию проекта...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder = f"/data/data/com.termux/files/home/mlbb_bot_backup_{timestamp}"
    
    os.makedirs(backup_folder, exist_ok=True)
    
    source_folder = "/data/data/com.termux/files/home/mlbb_bot"
    
    try:
        for item in os.listdir(source_folder):
            s = os.path.join(source_folder, item)
            d = os.path.join(backup_folder, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, ignore_dangling_symlinks=True, ignore=shutil.ignore_patterns('__pycache__'))
            else:
                if item != 'mlbb_bot.db':
                    shutil.copy2(s, d)
        
        archive_name = f"/data/data/com.termux/files/home/mlbb_bot_backup_{timestamp}.tar.gz"
        shutil.make_archive(archive_name.replace('.tar.gz', ''), 'gztar', backup_folder)
        
        with open(archive_name, 'rb') as f:
            await message.reply_document(
                document=types.InputFile(f, filename=f"mlbb_bot_backup_{timestamp}.tar.gz"),
                caption=f"✅ Резервная копия сохранена!\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
        
        shutil.rmtree(backup_folder)
        os.remove(archive_name)
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

# ---------- РЕГИСТРАЦИЯ ----------
def register_handlers_skins(dp: Dispatcher):
    dp.register_message_handler(cmd_help, lambda m: is_command(m.text, 'help', 'хелп', 'помощь'))
    dp.register_message_handler(cmd_adminhelp, lambda m: is_command(m.text, 'adminhelp', 'хелп админу', 'помощь админу'))
    dp.register_message_handler(cmd_catalog, lambda m: is_command(m.text, 'catalog', 'каталог'))
    dp.register_message_handler(get_random_skin, lambda m: is_command(m.text, 'skin', 'скин'))
    dp.register_message_handler(get_random_skin, lambda m: m.text and m.text.lower().strip() in ['хочу скин', 'хочускин'])
    dp.register_message_handler(cmd_inventory, lambda m: is_command(m.text, 'inventory', 'инвентарь', 'inv', 'инв'))
    dp.register_message_handler(cmd_profile, lambda m: is_command(m.text, 'profile', 'профиль', 'проф'))
    
    dp.register_message_handler(reset_profile_command, lambda m: is_command(m.text, 'reset_profile', 'сбросить профиль', 'сброситьпрофиль'))
    dp.register_message_handler(del_skin_command, lambda m: is_command(m.text, 'del_skin', 'удали скин', 'удалискин'))
    dp.register_message_handler(take_skin_command, lambda m: is_command(m.text, 'take', 'взять', 'выдать'))
    dp.register_message_handler(remove_skin_start, lambda m: is_command(m.text, 'remove', 'удалить', 'убрать'))
    dp.register_message_handler(reset_cooldown, lambda m: is_command(m.text, 'reset_cooldown', 'сбросить кд', 'сброскд', 'сброситькд', 'сброс', 'сброс кд', 'resetcd'))
    dp.register_message_handler(set_vip, lambda m: m.text and any(m.text.startswith(cmd) for cmd in ['/set_vip', '.set_vip', 'set_vip', '/установитьвип', '.установитьвип', 'установитьвип', '/вип', '.вип', 'вип', '/vip', '.vip', 'vip']))
    dp.register_message_handler(save_code_backup, lambda m: is_command(m.text, 'savecode', 'сохранить код', 'сохранитькод', 'backupcode', 'бэкап кода', 'бэкапкода', 'save', 'сохранить'))
    dp.register_message_handler(replace_skin_photo, lambda m: is_command(m.text, 'заменить', 'replace'))
    
    dp.register_callback_query_handler(process_take_skin, lambda c: c.data and c.data.startswith('take_skin_'))
    dp.register_callback_query_handler(process_remove_skin, lambda c: c.data and c.data.startswith('remove_skin_'))
    dp.register_callback_query_handler(process_del_skin_page, lambda c: c.data and c.data.startswith('del_skin_page_'))
    dp.register_callback_query_handler(process_delete_skin, lambda c: c.data and c.data.startswith('delete_skin_'))
    dp.register_callback_query_handler(cancel_delete_skin, lambda c: c.data == 'cancel_delete_skin')
    
    dp.register_callback_query_handler(inventory_from_profile_callback, lambda c: c.data and c.data.startswith('inventory_from_profile_'))
    dp.register_callback_query_handler(equip_skin_menu_callback, lambda c: c.data and c.data.startswith('equip_skin_menu_'))
    dp.register_callback_query_handler(equip_skin_callback, lambda c: c.data and c.data.startswith('equip_skin_'))
    dp.register_callback_query_handler(cancel_equip_callback, lambda c: c.data and c.data.startswith('cancel_equip_'))
    
    dp.register_message_handler(auto_add_skin, content_types=['photo'])
    dp.register_message_handler(unknown_command, lambda m: m.text and (m.text.startswith('/') or m.text.startswith('.')))
