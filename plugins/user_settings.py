"""
plugins/user_settings.py
─────────────────────────
/dump — User Settings Panel

  [ 🎯 Set Dump Channel  ]
  [ 🎀 Dump Mode ] [ ✅/❌ ]
  [ ✖️ Close             ]

REMOVED: 🎥 Sample Video, 📸 Screenshot (per spec)
KEPT:    🎀 Dump Mode, 🎯 Set Dump Channel
"""

from pyrogram import Client, filters
from pyrogram.errors import (
    ChatAdminRequired,
    ChannelInvalid,
    PeerIdInvalid,
    UserNotParticipant,
    MessageNotModified,
)
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from helper.database import jishubotz
from messages import log, Msg

# State store  { user_id: "waiting_dump" }
user_states: dict[int, str] = {}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _icon(state: bool) -> str:
    return "✅" if state else "❌"


async def _build_markup(user_id: int) -> InlineKeyboardMarkup:
    try:
        s = await jishubotz.get_user_settings(user_id)
    except Exception as e:
        log.error(Msg.US_REFRESH_ERR, error=e)
        s = {"dump_channel": None, "dump_mode": False}

    dump_ch  = s.get("dump_channel")
    ch_label = f"📡 Channel: {dump_ch}" if dump_ch else "🎯 Set Dump Channel"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(ch_label, callback_data="us_set_dump")],
        [
            InlineKeyboardButton("🎀 Dump Mode", callback_data="us_noop"),
            InlineKeyboardButton(_icon(s.get("dump_mode", False)), callback_data="us_toggle_dump"),
        ],
        [InlineKeyboardButton("✖️ Close", callback_data="us_close")],
    ])


def _caption(mention: str) -> str:
    return Msg.US_CAPTION.format(mention=mention)


# ── /dump command ───────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command("dump"))
async def user_settings_cmd(client: Client, message: Message):
    user   = message.from_user
    markup = await _build_markup(user.id)
    text   = _caption(user.mention)

    if Config.SETTINGS_IMAGE:
        try:
            await message.reply_photo(
                photo=Config.SETTINGS_IMAGE,
                caption=text,
                reply_markup=markup,
            )
            return
        except Exception as e:
            log.warning(Msg.US_PHOTO_FAIL, error=e)

    await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


# ── us_* callback handler ─────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^us_"), group=1)
async def us_callback_handler(client: Client, query: CallbackQuery):
    data    = query.data
    user_id = query.from_user.id

    if data == "us_noop":
        await query.answer()
        return

    if data == "us_close":
        user_states.pop(user_id, None)
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.message.edit_text("Settings Closed.")
            except Exception:
                pass
        return

    if data == "us_set_dump":
        await query.answer()
        user_states[user_id] = "waiting_dump"
        await query.message.reply_text(
            Msg.US_SET_DUMP_PROMPT,
            disable_web_page_preview=True,
        )
        return

    if data == "us_toggle_dump":
        try:
            current = await jishubotz.get_dump_mode(user_id)
            if not current:
                dump_channel = await jishubotz.get_dump_channel(user_id)
                if not dump_channel:
                    await query.answer(
                        Msg.US_DUMP_MODE_NEEDS_CHANNEL,
                        show_alert=True,
                    )
                    return
            await jishubotz.set_dump_mode(user_id, not current)
            await query.answer("Dump Mode " + ("enabled ✅" if not current else "disabled ❌"))
            await _refresh_markup(query)
        except Exception as e:
            log.error(Msg.US_REFRESH_ERR, error=e)
            await query.answer("Something went wrong. Please try again.", show_alert=True)
        return

    await query.answer()


# ── Dump channel input handler ────────────────────────────────────────────────

@Client.on_message(filters.private & (filters.text | filters.forwarded), group=-1)
async def handle_dump_input(client: Client, message: Message):
    user_id = message.from_user.id

    if user_states.get(user_id) != "waiting_dump":
        return

    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        user_states.pop(user_id, None)
        await message.reply_text(Msg.US_CANCELLED)
        return

    channel_id = None

    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
    elif message.text:
        raw = message.text.strip()
        try:
            channel_id = int(raw)
        except ValueError:
            try:
                chat = await client.get_chat(raw)
                channel_id = chat.id
            except Exception:
                await message.reply_text(Msg.US_INVALID_CHANNEL_RESOLVE)
                return

    if channel_id is None:
        await message.reply_text(Msg.US_NO_CHANNEL_ID)
        return

    if not str(channel_id).startswith("-100"):
        await message.reply_text(Msg.US_BAD_CHANNEL_PREFIX)
        return

    valid, reason = await _check_bot_admin(client, channel_id)
    if not valid:
        await message.reply_text(Msg.ADMIN_CHECK_ERR.format(reason=reason))
        return

    try:
        await jishubotz.set_dump_channel(user_id, channel_id)
    except Exception as e:
        log.error(Msg.DB_UNBAN_ERR, user_id=user_id, error=e)
        await message.reply_text(f"❌ Failed to save channel.\n\n`{e}`")
        return

    user_states.pop(user_id, None)
    await message.reply_text(Msg.US_DUMP_SAVED.format(channel_id=channel_id))


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _refresh_markup(query: CallbackQuery) -> None:
    markup = await _build_markup(query.from_user.id)
    try:
        await query.message.edit_reply_markup(reply_markup=markup)
    except MessageNotModified:
        pass
    except Exception as e:
        log.warning(Msg.US_REFRESH_ERR, error=e)


async def _check_bot_admin(client: Client, channel_id: int) -> tuple[bool, str]:
    try:
        me     = await client.get_chat_member(channel_id, "me")
        status = me.status.value

        if status not in ("administrator", "creator"):
            return False, Msg.ADMIN_NOT_ADMIN

        if status == "administrator":
            if not (me.privileges and me.privileges.can_post_messages):
                return False, Msg.ADMIN_NO_POST

        return True, ""

    except ChatAdminRequired:
        return False, Msg.ADMIN_REQUIRED
    except (ChannelInvalid, PeerIdInvalid):
        return False, Msg.ADMIN_INVALID_CHAN
    except UserNotParticipant:
        return False, Msg.ADMIN_NOT_MEMBER
    except Exception as e:
        return False, Msg.ADMIN_UNEXPECTED.format(error=e)
