"""
plugins/file_rename.py
───────────────────────
Rename pipeline:

  Step 1  User sends file     → bot asks for new name (ForceReply)
  Step 2  User sends name     → bot shows Document / Video / Audio buttons
  Step 3  User picks type     → download → metadata → upload

After upload SUCCEEDS the post-processing task is spawned.
The original file is NOT deleted until the task coroutine has captured
its path into a local variable and ffmpeg is done with it.

Post-processing order (only during rename, never standalone):
  parallel:  sample_video  +  screenshot
  then:      dump  (channel receives only the renamed file)
"""

import asyncio
import os
import random
import time
from asyncio import sleep

from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)

from config import Config
from helper.database import jishubotz
from helper.ffmpeg import (
    add_metadata,
    fix_thumb,
    generate_sample_video,
    take_multi_screenshots,
    take_screen_shot,
)
from helper.utils import add_prefix_suffix, convert, humanbytes, progress_for_pyrogram
from messages import log, Msg

_VIDEO_EXTS = (
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".flv", ".ts",  ".m4v", ".wmv", ".3gp",
)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — File received → ask for new name
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
    file     = getattr(message, message.media.value)
    filename = file.file_name

    if await jishubotz.is_banned(int(message.from_user.id)):
        return await message.reply(
            "**ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ. "
            "ᴄᴏɴᴛᴀᴄᴛ @Suh0_kang ᴛᴏ ʀᴇsᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇ!!**"
        )

    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text(
            "Oops~ That file's too big to handle right now… "
            "Maybe try a smaller one? I wanna play with something more manageable~"
        )

    try:
        await message.reply_text(
            text=(
                f"**Hey~ Give me a new name for your file, darling...**\n\n"
                f"**Old File Name** :- `{filename}`"
            ),
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True),
        )
        await sleep(30)
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(
            text=(
                f"**Hey cutie, enter the new filename for me~**\n\n"
                f"**Old File Name** :- `{filename}`"
            ),
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True),
        )
    except Exception as e:
        log.error(Msg.RENAME_START_ERR, error=e)

    await asyncio.sleep(600)
    try:
        await message.delete()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — User replied with new name → show upload-type buttons
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if not (reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply)):
        return

    new_name = message.text
    await message.delete()

    msg  = await client.get_messages(message.chat.id, reply_message.id)
    file = msg.reply_to_message
    if not file or not file.media:
        return

    media = getattr(file, file.media.value)

    if "." not in new_name:
        extn = (
            media.file_name.rsplit(".", 1)[-1]
            if "." in (media.file_name or "")
            else "mkv"
        )
        new_name = f"{new_name}.{extn}"

    await reply_message.delete()

    button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
    if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
        button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
    elif file.media == MessageMediaType.AUDIO:
        button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])

    await message.reply(
        text=f"**Select The Output File Type**\n\n**File Name :-** `{new_name}`",
        reply_to_message_id=file.id,
        reply_markup=InlineKeyboardMarkup(button),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Upload-type chosen → download → (metadata) → upload
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):
    if not os.path.isdir("Metadata"):
        os.mkdir("Metadata")

    user_id     = update.from_user.id
    chat_id     = update.message.chat.id
    upload_type = update.data.split("_")[1]   # document | video | audio

    # ── Filename with prefix/suffix ───────────────────────────────────────────
    prefix        = await jishubotz.get_prefix(chat_id)
    suffix        = await jishubotz.get_suffix(chat_id)
    new_name      = update.message.text
    new_filename_ = new_name.split(":-")[1].strip()

    try:
        new_filename = add_prefix_suffix(new_filename_, prefix, suffix)
    except Exception as e:
        return await update.message.edit(
            f"Something Went Wrong Can't Set Prefix/Suffix 🥺\n\n**Error:** `{e}`"
        )

    dl_dir    = f"downloads/{user_id}"
    os.makedirs(dl_dir, exist_ok=True)
    file_path = f"{dl_dir}/{new_filename}"
    file      = update.message.reply_to_message

    # ── Download ──────────────────────────────────────────────────────────────
    try:
        ms = await update.message.edit("🚀 Mmm~ Let's get that download started, darling... ⚡")
    except Exception as e:
        log.warning(Msg.RENAME_EDIT_MSG_ERR, error=e)
        ms = update.message

    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 Ahn~ Downloading in progress... Don't blink! ⚡", ms, time.time()),
        )
    except Exception as e:
        return await ms.edit(str(e))

    # ── Metadata injection ────────────────────────────────────────────────────
    _bool_metadata = await jishubotz.get_metadata(chat_id)
    metadata_path  = f"Metadata/{new_filename}"

    if _bool_metadata:
        metadata_fields = await jishubotz.get_metadata_fields(chat_id)
        result = await add_metadata(path, metadata_path, metadata_fields, ms)
        if not result:
            _bool_metadata = False
    else:
        await ms.edit("⏳ Mmm~ Changing modes... Be gentle, won't you? ⚡")

    # ── Duration ──────────────────────────────────────────────────────────────
    duration = 0
    try:
        parser = createParser(file_path)
        if parser:
            meta = extractMetadata(parser)
            if meta and meta.has("duration"):
                duration = meta.get("duration").seconds
            parser.stream._input.close()
    except Exception:
        pass

    # ── Thumbnail (untouched) ─────────────────────────────────────────────────
    ph_path = None
    media   = getattr(file, file.media.value)
    c_thumb = await jishubotz.get_thumbnail(chat_id)

    if media.thumbs or c_thumb:
        if c_thumb:
            ph_path = await bot.download_media(c_thumb)
            _, __, ph_path = await fix_thumb(ph_path)
        else:
            try:
                ph_path_ = await take_screen_shot(
                    file_path,
                    os.path.dirname(os.path.abspath(file_path)),
                    random.randint(0, max(duration - 1, 0)),
                )
                if ph_path_:
                    _, __, ph_path = await fix_thumb(ph_path_)
            except Exception as e:
                ph_path = None
                log.warning(Msg.RENAME_THUMB_ERR, error=e)

    # ── Caption ───────────────────────────────────────────────────────────────
    c_caption = await jishubotz.get_caption(chat_id)
    if c_caption:
        try:
            caption = c_caption.format(
                filename=new_filename,
                filesize=humanbytes(media.file_size),
                duration=convert(duration),
            )
        except Exception as e:
            return await ms.edit(text=f"Your Caption Error: ({e})")
    else:
        caption = f"**{new_filename}**"

    # ── Upload ────────────────────────────────────────────────────────────────
    upload_path = metadata_path if _bool_metadata else file_path

    try:
        await ms.edit("💠 Mmm~ Try uploading that spicy file again for me... ⚡")
    except Exception as e:
        log.warning(Msg.RENAME_EDIT_MSG_ERR, error=e)

    sent_message = None
    try:
        if upload_type == "document":
            sent_message = await bot.send_document(
                chat_id,
                document=upload_path,
                thumb=ph_path,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=("💠 Nn~ Uploading for you, master... ⚡", ms, time.time()),
            )
        elif upload_type == "video":
            sent_message = await bot.send_video(
                chat_id,
                video=upload_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("💠 Nn~ Uploading for you, master... ⚡", ms, time.time()),
            )
        elif upload_type == "audio":
            sent_message = await bot.send_audio(
                chat_id,
                audio=upload_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("💠 Uploading... ⚡", ms, time.time()),
            )

        await bot.copy_message(
            chat_id=Config.BIN_CHANNEL,
            from_chat_id=chat_id,
            message_id=sent_message.id,
        )

    except Exception as e:
        for p in (file_path, ph_path):
            if p and os.path.exists(p):
                os.remove(p)
        return await ms.edit(f"**Error:** `{e}`")

    # ── Post-processing ───────────────────────────────────────────────────────
    # Fetch settings in ONE DB call before any cleanup runs.
    settings = await jishubotz.get_user_settings(user_id)

    ext        = os.path.splitext(new_filename)[1].lower()
    is_video   = upload_type in ("video", "document") and ext in _VIDEO_EXTS
    # needs_file: True when the task must read file_path for ffmpeg work.
    # Always use file_path (original download), NOT upload_path/metadata_path —
    # upload_path may already be queued for deletion below.
    needs_file = is_video and (
        settings.get("sample_video") or settings.get("screenshot")
    )

    asyncio.create_task(
        _post_rename_tasks(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            file_path=file_path,        # always original download path
            new_filename=new_filename,
            upload_type=upload_type,
            sent_message=sent_message,
            settings=settings,
            is_video=is_video,
            owns_file=needs_file,       # task deletes file_path when done
        )
    )

    # ── Cleanup ───────────────────────────────────────────────────────────────
    await ms.delete()
    # Thumbnail is never needed by the task
    if ph_path and os.path.exists(ph_path):
        try:
            os.remove(ph_path)
        except Exception:
            pass
    # Metadata output file — always safe to delete (task uses file_path, not metadata_path)
    if _bool_metadata and os.path.exists(metadata_path):
        try:
            os.remove(metadata_path)
        except Exception:
            pass
    # Original file — delete only when the task does NOT need it for ffmpeg
    if not needs_file and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Post-rename pipeline  (only callable from inside doc() above)
#
# Order:
#   1. sample_video  ┐  asyncio.gather  (parallel)
#   2. screenshot    ┘
#   3. dump          (after both complete — channel gets only the renamed file)
# ══════════════════════════════════════════════════════════════════════════════

async def _post_rename_tasks(
    bot,
    chat_id: int,
    user_id: int,
    file_path: str,
    new_filename: str,
    upload_type: str,
    sent_message,
    settings: dict,
    is_video: bool,
    owns_file: bool,
):
    try:
        file_alive = os.path.exists(file_path)

        # ── Parallel: sample clip + screenshots ──────────────────────────────
        parallel = []
        if settings.get("sample_video") and is_video and file_alive:
            parallel.append(_send_sample_video(bot, chat_id, file_path, new_filename))
        if settings.get("screenshot") and is_video and file_alive:
            parallel.append(_send_screenshots(bot, chat_id, file_path, new_filename))

        if parallel:
            await asyncio.gather(*parallel, return_exceptions=True)

        # ── Dump (always last — only the renamed file) ────────────────────────
        if settings.get("dump_mode") and settings.get("dump_channel"):
            await _dump_to_channel(
                bot, user_id, int(settings["dump_channel"]), sent_message
            )

    finally:
        # Task owns file cleanup when it needed the file for ffmpeg work
        if owns_file and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Dump helper
# ══════════════════════════════════════════════════════════════════════════════

async def _dump_to_channel(bot, user_id: int, channel_id: int, sent_message):
    """Send the renamed file to the user's dump channel (copy, no re-upload)."""
    try:
        await bot.copy_message(
            chat_id=channel_id,
            from_chat_id=sent_message.chat.id,
            message_id=sent_message.id,
        )
        log.info(Msg.DUMP_SUCCESS, user_id=user_id, channel_id=channel_id)
    except Exception as e:
        log.error(Msg.DUMP_FAILED_LOG, user_id=user_id, channel_id=channel_id, error=e)
        try:
            await bot.send_message(
                user_id,
                f"⚠️ **Dump Failed**\n\n"
                f"Could not send to dump channel `{channel_id}`.\n"
                f"Error: `{e}`\n\n"
                "Make sure the bot is still admin with Post permission.",
                disable_notification=True,
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Sample video helper
# ══════════════════════════════════════════════════════════════════════════════

async def _send_sample_video(bot, chat_id: int, file_path: str, filename: str):
    """Generate a random 30-second clip and send to the user."""
    out_dir     = os.path.dirname(os.path.abspath(file_path))
    sample_path = None
    try:
        sample_path = await generate_sample_video(file_path, out_dir, duration=30)
        if not sample_path:
            return
        await bot.send_video(
            chat_id,
            video=sample_path,
            caption=f"🎬 **Sample Clip** (30s)\n`{filename}`",
            supports_streaming=True,
        )
    except Exception as e:
        log.error(Msg.SAMPLE_SEND_ERR, error=e)
    finally:
        if sample_path and os.path.exists(sample_path):
            try:
                os.remove(sample_path)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Screenshots helper
# ══════════════════════════════════════════════════════════════════════════════

async def _send_screenshots(bot, chat_id: int, file_path: str, filename: str):
    """Generate 6 evenly-spaced screenshots and send as a media group."""
    out_dir     = os.path.dirname(os.path.abspath(file_path))
    screenshots = []
    try:
        screenshots = await take_multi_screenshots(file_path, out_dir, count=6)
        if not screenshots:
            return

        media_group = [
            InputMediaPhoto(
                media=ss,
                caption=f"📸 Screenshots — `{filename}`" if i == 0 else "",
            )
            for i, ss in enumerate(screenshots)
        ]
        for i in range(0, len(media_group), 10):
            await bot.send_media_group(chat_id, media_group[i:i + 10])

    except Exception as e:
        log.error(Msg.SS_ERROR, error=e)
    finally:
        for p in screenshots:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
