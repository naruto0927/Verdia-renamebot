from pyrogram import Client, filters 
from helper.database import jishubotz

@Client.on_message(filters.private & filters.command('set_caption'))
async def add_caption(client, message):
    if len(message.command) == 1:
       return await message.reply_text(
    "**🌿 Whisper to me your desired caption...\n\n"
    "✨ Example:\n"
    "`/set_caption 📕 Name ➠ : {filename}\n\n🔗 Size ➠ : {filesize}\n\n⏰ Duration ➠ : {duration}`**"
)
    caption = message.text.split(" ", 1)[1]
    await jishubotz.set_caption(message.from_user.id, caption=caption)
    await message.reply_text("**🌸 Your caption has been gently woven into place ✅**")
   
@Client.on_message(filters.private & filters.command('del_caption'))
async def delete_caption(client, message):
    caption = await jishubotz.get_caption(message.from_user.id)  
    if not caption:
       return await message.reply_text("**🌿 Looks like you haven’t set a caption yet ❌**")
    await jishubotz.set_caption(message.from_user.id, caption=None)
    await message.reply_text("**✨ Your caption has been gracefully deleted 🗑️**")
                                       
@Client.on_message(filters.private & filters.command('see_caption'))
async def see_caption(client, message):
    caption = await jishubotz.get_caption(message.from_user.id)  
    if caption:
       await message.reply_text(f"**Your Caption :**\n\n`{caption}`")
    else:
       await message.reply_text("**⚠️ Oops! No caption found to show ❌**")
