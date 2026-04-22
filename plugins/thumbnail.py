from pyrogram import Client, filters
from helper.database import jishubotz


@Client.on_message(filters.private & filters.command(["view_thumb", "viewthumb"]))
async def viewthumb(client, message):
    thumb = await jishubotz.get_thumbnail(message.from_user.id)
    if thumb:
        try:
            await client.send_photo(chat_id=message.chat.id, photo=thumb)
        except Exception:
            await jishubotz.set_thumbnail(message.from_user.id, file_id=None)
            await message.reply_text(
                "**Thumbnail reference expired ❌**\n"
                "_Please resend your thumbnail photo to update it._"
            )
    else:
        await message.reply_text(
            "**You don\'t have a thumbnail set yet ❌**\n"
            "_Send me any photo and I\'ll save it as your thumbnail._"
        )


@Client.on_message(filters.private & filters.command(["del_thumb", "delthumb"]))
async def removethumb(client, message):
    await jishubotz.set_thumbnail(message.from_user.id, file_id=None)
    await message.reply_text("**Thumbnail removed ✅**")


@Client.on_message(filters.private & filters.photo)
async def addthumbs(client, message):
    mkn = await message.reply_text("Saving thumbnail...")
    # Store the file_unique_id as a stable key AND the current file_id.
    # file_unique_id never changes; file_id expires but can be refreshed.
    photo     = message.photo
    file_id   = photo.file_id
    await jishubotz.set_thumbnail(message.from_user.id, file_id=file_id)
    await mkn.edit("**Thumbnail saved ✅**")
