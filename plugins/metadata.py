"""
plugins/metadata.py
────────────────────
/metadata — Interactive metadata panel.

Fields aligned to standard ffmpeg tags:

  Field     ffmpeg flag                 What it sets
  ────────  ──────────────────────────  ─────────────────────────────
  Title     -metadata title=            File/video title
  Artist    -metadata artist=           Artist / creator name
  Author    -metadata author=           Author (alias, most containers)
  Comment   -metadata comment=          General comment / description
  Audio     -metadata:s:a title=        Audio stream label
  Video     -metadata:s:v title=        Video stream label
  Subtitle  -metadata:s:s title=        Subtitle stream label

Panel layout:
  ┌────────────────────────────────┐
  │  🏷 Title       │  🎨 Artist  │
  │  ✍️ Author      │  💬 Comment │
  │  🔊 Audio Track │  🎥 Video   │
  │  📝 Subtitle    │            │
  │  🔙 Disable  ✅ Enable  ❌ Close │
  └────────────────────────────────┘
"""

import asyncio
from typing import Dict, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from helper.database import jishubotz

# ─────────────────────────────────────────────────────────────────────────────
# In-memory state  { user_id: "waiting_<field_key>" | None }
# ─────────────────────────────────────────────────────────────────────────────
user_state:    Dict[int, Optional[str]] = {}
panel_message: Dict[int, Message]       = {}

# ─────────────────────────────────────────────────────────────────────────────
# Field registry
# callback_data → (button_label, db_key, display_name, ffmpeg_description)
# ─────────────────────────────────────────────────────────────────────────────
METADATA_FIELDS = {
    "mt_title":    ("🏷 Title",        "title",    "Title",        "-metadata title="),
    "mt_artist":   ("🎨 Artist",       "artist",   "Artist",       "-metadata artist="),
    "mt_author":   ("✍️ Author",        "author",   "Author",       "-metadata author="),
    "mt_comment":  ("💬 Comment",      "comment",  "Comment",      "-metadata comment="),
    "mt_audio":    ("🔊 Audio Track",  "audio",    "Audio Track",  "-metadata:s:a title="),
    "mt_video":    ("🎥 Video Track",  "video",    "Video Track",  "-metadata:s:v title="),
    "mt_subtitle": ("📝 Subtitle",     "subtitle", "Subtitle",     "-metadata:s:s title="),
}


# ─────────────────────────────────────────────────────────────────────────────
# UI builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_keyboard() -> InlineKeyboardMarkup:
    keys = list(METADATA_FIELDS.items())
    rows = []
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(keys[i][1][0], callback_data=keys[i][0])]
        if i + 1 < len(keys):
            row.append(InlineKeyboardButton(keys[i + 1][1][0], callback_data=keys[i + 1][0]))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("🔙 Disable", callback_data="mt_back"),
        InlineKeyboardButton("✅ Enable",  callback_data="mt_done"),
        InlineKeyboardButton("❌ Close",   callback_data="mt_close"),
    ])
    return InlineKeyboardMarkup(rows)


async def _build_panel_text(user_id: int) -> str:
    enabled = await jishubotz.get_metadata(user_id)
    fields  = await jishubotz.get_metadata_fields(user_id)
    status  = "✅ Enabled" if enabled else "❌ Disabled"

    lines = [
        "**🎬 Custom Metadata**",
        f"**Status:** {status}",
        "",
        "**Saved values:**",
    ]
    for cb, (label, key, display, fflag) in METADATA_FIELDS.items():
        val = (fields.get(key) or "").strip()
        display_val = f"`{val}`" if val else "—"
        lines.append(f"  {label}: {display_val}")

    lines += [
        "",
        "Tap a field to set its value.",
        "**Enable** to apply during rename · **Disable** to turn off.",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# /metadata command
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("metadata"))
async def cmd_metadata(bot: Client, message: Message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)

    text  = await _build_panel_text(user_id)
    panel = await message.reply_text(
        text,
        reply_markup=_build_keyboard(),
        disable_web_page_preview=True,
    )
    panel_message[user_id] = panel


# ─────────────────────────────────────────────────────────────────────────────
# Callback handler — all mt_* callbacks
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^mt_"))
async def cb_metadata(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data    = query.data

    # ── Field button pressed ──────────────────────────────────────────────────
    if data in METADATA_FIELDS:
        label, key, display, fflag = METADATA_FIELDS[data]
        user_state[user_id]    = f"waiting_{key}"
        panel_message[user_id] = query.message

        await query.answer(f"Send your {display} value")
        await query.message.edit_text(
            f"✏️ **Set {display}**\n\n"
            f"ffmpeg tag: `{fflag}`\n\n"
            f"Type the value and send it.\n"
            f"Send /cancel to go back.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Cancel", callback_data="mt_cancel")]
            ]),
        )
        return

    # ── Cancel ────────────────────────────────────────────────────────────────
    if data == "mt_cancel":
        user_state.pop(user_id, None)
        await query.answer("Cancelled.")
        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Enable metadata ───────────────────────────────────────────────────────
    if data == "mt_done":
        user_state.pop(user_id, None)
        fields = await jishubotz.get_metadata_fields(user_id)
        filled = {k: v for k, v in fields.items() if (v or "").strip()}
        if not filled:
            await query.answer(
                "⚠️ Set at least one field before enabling.",
                show_alert=True,
            )
            return
        await jishubotz.set_metadata(user_id, bool_meta=True)
        await query.answer("✅ Metadata enabled!")
        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Disable metadata ──────────────────────────────────────────────────────
    if data == "mt_back":
        user_state.pop(user_id, None)
        await jishubotz.set_metadata(user_id, bool_meta=False)
        await query.answer("Metadata disabled.")
        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Close ─────────────────────────────────────────────────────────────────
    if data == "mt_close":
        user_state.pop(user_id, None)
        panel_message.pop(user_id, None)
        await query.answer("Closed.")
        await query.message.delete()
        return

    await query.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Message capture — intercepts user input when a field is being set
# group=1 fires after the rename handler (group=0) but this is intentional:
# the rename handler only acts on ForceReply messages, so plain text is safe here.
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.private & filters.text & ~filters.command([
        "start", "metadata", "cancel", "ban", "unban", "broadcast",
        "status", "restart", "ping", "dump", "setlimit", "getlimit",
        "set_caption", "del_caption", "see_caption",
        "set_prefix", "del_prefix", "see_prefix",
        "set_suffix", "del_suffix", "see_suffix",
        "view_thumb", "viewthumb", "del_thumb", "delthumb",
    ]),
    group=1,
)
async def capture_metadata_input(bot: Client, message: Message):
    user_id = message.from_user.id
    state   = user_state.get(user_id)

    if not state or not state.startswith("waiting_"):
        return

    # /cancel typed as plain text
    if message.text.strip().lower() in ("/cancel", "cancel"):
        user_state.pop(user_id, None)
        ack = await message.reply_text("❌ Cancelled. Use /metadata to reopen.")
        await asyncio.sleep(3)
        try:
            await ack.delete()
            await message.delete()
        except Exception:
            pass
        return

    field_key = state[len("waiting_"):]
    value     = message.text.strip()

    await jishubotz.set_metadata_field(user_id, field_key, value)
    user_state.pop(user_id, None)

    try:
        await message.delete()
    except Exception:
        pass

    # Refresh the panel
    panel_msg = panel_message.get(user_id)
    text = await _build_panel_text(user_id)
    if panel_msg:
        try:
            await panel_msg.edit_text(
                text,
                reply_markup=_build_keyboard(),
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

    panel = await bot.send_message(
        user_id, text,
        reply_markup=_build_keyboard(),
        disable_web_page_preview=True,
    )
    panel_message[user_id] = panel


# ─────────────────────────────────────────────────────────────────────────────
# /cancel command
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("cancel"))
async def cmd_cancel(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_state.pop(user_id, None):
        await message.reply_text("❌ Cancelled. Use /metadata to reopen.")
    else:
        await message.reply_text("Nothing active to cancel.")


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @JishuBotz
# Developer @JishuDeveloper
