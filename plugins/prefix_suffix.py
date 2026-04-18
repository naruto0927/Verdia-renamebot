"""
plugins/prefix_suffix.py
─────────────────────────
Prefix and suffix command handlers.

Commands
  /set_prefix  — save a prefix
  /see_prefix  — show current prefix
  /del_prefix  — clear prefix

  /set_suffix  — save a suffix
  /see_suffix  — show current suffix
  /del_suffix  — clear suffix
"""

from pyrogram import Client, filters
from pyrogram.types import Message
from helper.database import jishubotz


# ══════════════════════════════════════════════════════════════════════════════
# PREFIX
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("set_prefix"))
async def set_prefix(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/set_prefix YourPrefix`\n\n"
            "**Example:** `/set_prefix @MyChannel`\n\n"
            "The prefix will be added to the beginning of every renamed file."
        )
    prefix = message.text.split(None, 1)[1].strip()
    await jishubotz.set_prefix(message.from_user.id, prefix)
    await message.reply_text(f"✅ **Prefix saved:** `{prefix}`")


@Client.on_message(filters.private & filters.command("see_prefix"))
async def see_prefix(client: Client, message: Message):
    prefix = await jishubotz.get_prefix(message.from_user.id)
    if prefix:
        await message.reply_text(f"**Your current prefix:**\n\n`{prefix}`")
    else:
        await message.reply_text("❌ No prefix set.")


@Client.on_message(filters.private & filters.command("del_prefix"))
async def del_prefix(client: Client, message: Message):
    prefix = await jishubotz.get_prefix(message.from_user.id)
    if not prefix:
        return await message.reply_text("❌ No prefix to delete.")
    await jishubotz.set_prefix(message.from_user.id, None)
    await message.reply_text("✅ Prefix deleted.")


# ══════════════════════════════════════════════════════════════════════════════
# SUFFIX
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("set_suffix"))
async def set_suffix(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/set_suffix YourSuffix`\n\n"
            "**Example:** `/set_suffix @MyChannel`\n\n"
            "The suffix will be added after the filename (before the extension)."
        )
    suffix = message.text.split(None, 1)[1].strip()
    await jishubotz.set_suffix(message.from_user.id, suffix)
    await message.reply_text(f"✅ **Suffix saved:** `{suffix}`")


@Client.on_message(filters.private & filters.command("see_suffix"))
async def see_suffix(client: Client, message: Message):
    suffix = await jishubotz.get_suffix(message.from_user.id)
    if suffix:
        await message.reply_text(f"**Your current suffix:**\n\n`{suffix}`")
    else:
        await message.reply_text("❌ No suffix set.")


@Client.on_message(filters.private & filters.command("del_suffix"))
async def del_suffix(client: Client, message: Message):
    suffix = await jishubotz.get_suffix(message.from_user.id)
    if not suffix:
        return await message.reply_text("❌ No suffix to delete.")
    await jishubotz.set_suffix(message.from_user.id, None)
    await message.reply_text("✅ Suffix deleted.")
