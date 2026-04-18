from pyrogram import Client, filters, enums 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant
from config import Config
from helper.database import jishubotz



async def not_subscribed(_, client, message):
    await jishubotz.add_user(client, message)
    if not Config.FORCE_SUB:
        return False
    try:             
        user = await client.get_chat_member(Config.FORCE_SUB, message.from_user.id) 
        if user.status == enums.ChatMemberStatus.BANNED:
            return True 
        else:
            return False                
    except UserNotParticipant:
        pass
    return True


@Client.on_message(filters.private & filters.create(not_subscribed))
async def forces_sub(client, message):
    buttons = [[InlineKeyboardButton(text="🔺 Join Our Cool Channel 🔺", url=f"https://telegram.me/{Config.FORCE_SUB}")]]
    text = f"""<b>Hey there, {message.from_user.mention}! 😘

Before we can have fun, you gotta join my awesome channel first! 

Pretty please, don’t keep me waiting~ 💖</b>"""
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    try:
        user = await client.get_chat_member(Config.FORCE_SUB, message.from_user.id)    
        if user.status == enums.ChatMemberStatus.BANNED:                                   
            return await client.send_message(
    message.from_user.id, 
    text="Oopsie! You're currently banned from using me. If you think this is a mistake, please contact @Suh0_Kang to get it sorted out!"
)
    except UserNotParticipant:                       
        return await message.reply_text(text=text,quote=True, reply_markup=InlineKeyboardMarkup(buttons))
    return await message.reply_text(text=text,quote=True, reply_markup=InlineKeyboardMarkup(buttons))





# Jishu Developer 
# Don't Remove Credit 🥺
# Telegram Channel @JishuBotz
# Developer @JishuDeveloper
