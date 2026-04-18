from pyrogram import Client, filters 
from helper.database import jishubotz


@Client.on_message(filters.private & filters.command(['view_thumb', 'viewthumb']))
async def viewthumb(client, message):    
    thumb = await jishubotz.get_thumbnail(message.from_user.id)
    if thumb:
       await client.send_photo(chat_id=message.chat.id, photo=thumb)
    else:
        await message.reply_text("**Aww~ You don’t have a thumbnail yet, darling... ❌**\n_Shall I help you pick something pretty?_")

@Client.on_message(filters.private & filters.command(['del_thumb', 'delthumb']))
async def removethumb(client, message):
    await jishubotz.set_thumbnail(message.from_user.id, file_id=None)
    await message.reply_text("**Mmh~ I’ve tossed that old thumbnail out, just for you... 🗑️**\n_Now, don’t leave me empty-handed~_")
@Client.on_message(filters.private & filters.photo)
async def addthumbs(client, message):
    mkn = await message.reply_text("Please Wait ...")
    await jishubotz.set_thumbnail(message.from_user.id, file_id=message.photo.file_id)                
    await mkn.edit("**Mmh~ I’ve saved your pretty little thumbnail... Just for you, darling~ ✅️**")
