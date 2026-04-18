"""
plugins/metadata.py
────────────────────
Interactive metadata panel with per-field buttons.
Uses an in-memory state machine — no pyromod required.

Panel layout:
  ┌─────────────────────────────────────────┐
  │   ✏️ Custom Metadata  |  Page: 1/1      │
  ├──────────────┬──────────────────────────┤
  │  🏷 Title    │  ✍️ Author               │
  │  🎨 Artist   │  🔊 Audio                │
  │  🎬 Video    │  📝 Subtitle             │
  ├──────────────┴──────────────────────────┤
  │  🔙 Back     │  ✅ Done  │  ❌ Close    │
  └─────────────────────────────────────────┘
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
# In-memory state store  { user_id: "waiting_title" | None }
# ─────────────────────────────────────────────────────────────────────────────
user_state: Dict[int, Optional[str]] = {}

# Tracks the panel message so we can edit it later  { user_id: Message }
panel_message: Dict[int, Message] = {}

# ─────────────────────────────────────────────────────────────────────────────
# Field config:  callback_data → (button_label, db_key, display_name)
# ─────────────────────────────────────────────────────────────────────────────
METADATA_FIELDS = {
    "mt_title":    ("🏷 Title",    "title",    "Title"),
    "mt_author":   ("✍️ Author",   "author",   "Author"),
    "mt_artist":   ("🎨 Artist",   "artist",   "Artist"),
    "mt_audio":    ("🔊 Audio",    "audio",    "Audio"),
    "mt_video":    ("🎬 Video",    "video",    "Video"),
    "mt_subtitle": ("📝 Subtitle", "subtitle", "Subtitle"),
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_panel_keyboard() -> InlineKeyboardMarkup:
    """Build the 4-row metadata panel keyboard."""
    keys = list(METADATA_FIELDS.items())
    rows = []
    # Field buttons — 2 per row
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(keys[i][1][0], callback_data=keys[i][0])]
        if i + 1 < len(keys):
            row.append(InlineKeyboardButton(keys[i + 1][1][0], callback_data=keys[i + 1][0]))
        rows.append(row)
    # Bottom control row
    rows.append([
        InlineKeyboardButton("🔙 Back",  callback_data="mt_back"),
        InlineKeyboardButton("✅ Done",  callback_data="mt_done"),
        InlineKeyboardButton("❌ Close", callback_data="mt_close"),
    ])
    return InlineKeyboardMarkup(rows)


async def _build_panel_text(user_id: int) -> str:
    """Build the panel caption showing current stored values."""
    enabled = await jishubotz.get_metadata(user_id)
    fields  = await jishubotz.get_metadata_fields(user_id)
    status  = "✅ Enabled" if enabled else "❌ Disabled"

    lines = [
        "**✏️ Custom Metadata** | Page: 1/1",
        f"**Status:** {status}",
        "",
        "**Current Values:**",
    ]
    for cb, (label, key, display) in METADATA_FIELDS.items():
        val = fields.get(key) or "—"
        lines.append(f"  {label}: `{val}`")
    lines += [
        "",
        "_Tap a field to edit · **Done** to enable · **Back** to disable_",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# /metadata command — opens the panel
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("metadata"))
async def cmd_metadata(bot: Client, message: Message):
    user_id = message.from_user.id
    user_state.pop(user_id, None)           # clear any stale state

    text  = await _build_panel_text(user_id)
    panel = await message.reply_text(
        text,
        reply_markup=_build_panel_keyboard(),
        disable_web_page_preview=True,
    )
    panel_message[user_id] = panel


# ─────────────────────────────────────────────────────────────────────────────
# Callback query handler — all mt_* callbacks
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^mt_"))
async def cb_metadata(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    # ── Field button pressed ─────────────────────────────────────────────────
    if data in METADATA_FIELDS:
        _, _, display = METADATA_FIELDS[data]
        field_key = data[3:]  # "mt_title" → "title"

        user_state[user_id] = f"waiting_{field_key}"
        panel_message[user_id] = query.message

        await query.answer(f"Go on… give me your {display} value ✏️")

        await query.message.edit_text(
            f"✏️ **Send me your {display} metadata:**\n\n"
            f"Don’t hesitate… type it out, and I’ll take care of the rest.\n"
            f"Or walk away—tap **Cancel** or send /cancel.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Cancel", callback_data="mt_cancel")]
            ]),
        )
        return

    # ── Cancel input ─────────────────────────────────────────────────────────
    if data == "mt_cancel":
        user_state.pop(user_id, None)

        await query.answer("Backed out already? Hm… I expected more 😈")

        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_panel_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Done — enable metadata ───────────────────────────────────────────────
    if data == "mt_done":
        user_state.pop(user_id, None)
        fields = await jishubotz.get_metadata_fields(user_id)
        filled = {k: v for k, v in fields.items() if v}
        if not filled:
            await query.answer(
    "⚠️ Trying to move ahead already?\nSet at least one field… properly 😏",
    show_alert=True
)
            return
        await jishubotz.set_metadata(user_id, bool_meta=True)
        await query.answer("✅ Metadata enabled!")
        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_panel_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Back — disable metadata ──────────────────────────────────────────────
    if data == "mt_back":
        user_state.pop(user_id, None)
        await jishubotz.set_metadata(user_id, bool_meta=False)
        await query.answer("Metadata disabled.")
        text = await _build_panel_text(user_id)
        await query.message.edit_text(
            text,
            reply_markup=_build_panel_keyboard(),
            disable_web_page_preview=True,
        )
        return

    # ── Close ────────────────────────────────────────────────────────────────
    if data == "mt_close":
        user_state.pop(user_id, None)
        panel_message.pop(user_id, None)
        await query.answer("Closed.")
        await query.message.delete()
        return

    await query.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Message capture handler — runs at group=1 (before rename handler at group=0)
# Only activates when user_state is set for this user
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(
    filters.private & filters.text & ~filters.command([
        "start", "metadata", "cancel", "ban", "unban", "broadcast",
        "status", "restart", "ping", "set_caption", "del_caption",
        "see_caption", "set_prefix", "del_prefix", "see_prefix",
        "set_suffix", "del_suffix", "see_suffix",
        "view_thumb", "viewthumb", "del_thumb", "delthumb",
    ]),
    group=1,
)
async def capture_metadata_input(bot: Client, message: Message):
    user_id = message.from_user.id
    state   = user_state.get(user_id)

    # Not in an input state → pass through to other handlers
    if not state or not state.startswith("waiting_"):
        return

    # Handle typed /cancel
    if message.text.strip().lower() in ("/cancel", "cancel"):
        user_state.pop(user_id, None)
        ack = await message.reply_text("❌ Backed out just like that?\nDon’t worry… I’ll be here. /metadata 😈")
        await asyncio.sleep(4)
        try:
            await ack.delete()
            await message.delete()
        except Exception:
            pass
        return

    # Extract which field we are setting
    field_key = state[len("waiting_"):]     # e.g. "title"
    value     = message.text.strip()

    # Save to DB
    await jishubotz.set_metadata_field(user_id, field_key, value)

    # Clear state immediately
    user_state.pop(user_id, None)

    # Delete user's input message (clean UI)
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
                reply_markup=_build_panel_keyboard(),
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

    # Fallback: send a fresh panel
    panel = await bot.send_message(
        user_id,
        text,
        reply_markup=_build_panel_keyboard(),
        disable_web_page_preview=True,
    )
    panel_message[user_id] = panel


# ─────────────────────────────────────────────────────────────────────────────
# /cancel command (standalone)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("cancel"))
async def cmd_cancel(bot: Client, message: Message):
    user_id = message.from_user.id

    if user_state.pop(user_id, None):
        await message.reply_text(
            "❌ Cancelled. Not ready to continue?\nFind me again with /metadata 😈"
        )
    else:
        await message.reply_text(
            "Nothing active… you didn’t give me anything to work with 💫"
        )


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @JishuBotz
# Developer @JishuDeveloper
