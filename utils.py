from aiogram import types
from config import OWNER_ID

async def is_admin(message: types.Message) -> bool:
    if message.from_user.id == OWNER_ID:
        return True
    member = await message.chat.get_member(message.from_user.id)
    return member.is_chat_admin()

async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def extract_command_args(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""
