"""
plugins/premium.py
───────────────────────────────────────────────────────────────────────────────
Premium user system — storage backed by MongoDB via helper/database.py.

Admin commands  (Config.ADMIN only)
────────────────────────────────────
  /addpremium <user_id> [days]   Grant premium  (default 30 d, 0 = lifetime)
  /removepremium <user_id>       Revoke premium
  /checkpremium <user_id>        Inspect any user's premium status
  /premiumlist                   List all active premium users

User commands
─────────────
  /premium                       Check own premium status

Auto-expiry
───────────
  jishubotz.is_premium() auto-revokes and returns False when the stored
  expiry timestamp has passed — no separate cron job needed.
"""

import time
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.database import jishubotz


# ══════════════════════════════════════════════════════════════════════════════
# /premium — check own status
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("premium"))
async def cmd_premium(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in Config.ADMIN:
        return await message.reply_text(
            "⭐ **You are an Admin — permanent premium access.**"
        )

    info = await jishubotz.get_premium_info(user_id)

    if not info or not info.get("premium"):
        return await message.reply_text(
            "❌ **You do not have premium access.**\n\n"
            "Contact the admin to get premium."
        )

    expiry = info.get("premium_expiry")
    if expiry and expiry < time.time():
        await jishubotz.set_premium(user_id, False)
        return await message.reply_text(
            "❌ **Your premium has expired.**\n\n"
            "Contact the admin to renew."
        )

    if expiry:
        dt = datetime.fromtimestamp(expiry, tz=timezone.utc)
        remaining_days = int((expiry - time.time()) / 86400)
        await message.reply_text(
            f"⭐ **You have premium access.**\n\n"
            f"**Expires:** `{dt.strftime('%d %B %Y at %H:%M UTC')}`\n"
            f"**Days remaining:** `{remaining_days}`"
        )
    else:
        await message.reply_text("⭐ **You have lifetime premium access.**")


# ══════════════════════════════════════════════════════════════════════════════
# /addpremium — grant premium  (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("addpremium") & filters.user(Config.ADMIN))
async def cmd_add_premium(client: Client, message: Message):
    """
    /addpremium <user_id> [days]
    days = 0 → lifetime access.
    """
    parts = message.text.strip().split()

    if len(parts) < 2:
        return await message.reply_text(
            "**Usage:** `/addpremium <user_id> [days]`\n\n"
            "**Examples:**\n"
            "`/addpremium 123456789`       — 30 days (default)\n"
            "`/addpremium 123456789 60`    — 60 days\n"
            "`/addpremium 123456789 0`     — lifetime"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID. Must be a number.")

    days = 30
    if len(parts) >= 3:
        try:
            days = int(parts[2])
            if days < 0:
                raise ValueError
        except ValueError:
            return await message.reply_text("❌ Days must be a non-negative integer.")

    if days == 0:
        expiry  = None
        exp_str = "Lifetime"
    else:
        expiry  = time.time() + days * 86400
        dt      = datetime.fromtimestamp(expiry, tz=timezone.utc)
        exp_str = dt.strftime("%d %B %Y")

    await jishubotz.set_premium(target_id, True, expiry)

    # Notify the user
    try:
        notif = (
            "⭐ **You've been granted lifetime premium access!**"
            if days == 0
            else (
                f"⭐ **You've been granted premium for {days} day(s)!**\n\n"
                f"**Expires:** `{exp_str}`"
            )
        )
        await client.send_message(target_id, notif)
    except Exception:
        pass

    await message.reply_text(
        f"✅ **Premium granted to** `{target_id}`\n"
        f"**Duration:** {f'{days} day(s)' if days else 'Lifetime'}\n"
        f"**Expires:** `{exp_str}`"
    )


# ══════════════════════════════════════════════════════════════════════════════
# /removepremium — revoke premium  (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command(["removepremium", "rempremium"]) & filters.user(Config.ADMIN))
async def cmd_rem_premium(client: Client, message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply_text(
            "**Usage:** `/removepremium <user_id>`"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")

    await jishubotz.set_premium(target_id, False)

    try:
        await client.send_message(
            target_id,
            "❌ **Your premium access has been revoked.**\n"
            "Contact the admin for more info."
        )
    except Exception:
        pass

    await message.reply_text(f"✅ **Premium revoked for** `{target_id}`")


# ══════════════════════════════════════════════════════════════════════════════
# /checkpremium — inspect any user's status  (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("checkpremium") & filters.user(Config.ADMIN))
async def cmd_check_premium(client: Client, message: Message):
    """
    /checkpremium <user_id>
    Shows exact premium status, expiry, and whether it has lapsed.
    """
    parts = message.text.strip().split()
    if len(parts) < 2:
        return await message.reply_text(
            "**Usage:** `/checkpremium <user_id>`"
        )

    try:
        target_id = int(parts[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")

    # Admin check
    if target_id in Config.ADMIN:
        return await message.reply_text(
            f"👑 **User `{target_id}` is an Admin.**\n"
            "Admins always have permanent premium access."
        )

    info = await jishubotz.get_premium_info(target_id)

    if not info:
        return await message.reply_text(
            f"ℹ️ **User `{target_id}` is not registered** in the database.\n"
            "They have never started the bot."
        )

    has_premium = info.get("premium", False)
    expiry      = info.get("premium_expiry")
    now         = time.time()

    if not has_premium:
        return await message.reply_text(
            f"❌ **User `{target_id}` does not have premium.**"
        )

    if expiry and expiry < now:
        # Auto-revoke
        await jishubotz.set_premium(target_id, False)
        return await message.reply_text(
            f"⚠️ **User `{target_id}` had premium but it has expired.**\n"
            f"Expired on: `{datetime.fromtimestamp(expiry, tz=timezone.utc).strftime('%d %B %Y at %H:%M UTC')}`\n\n"
            "Their status has been auto-revoked."
        )

    if expiry:
        dt            = datetime.fromtimestamp(expiry, tz=timezone.utc)
        remaining_days = int((expiry - now) / 86400)
        await message.reply_text(
            f"⭐ **User `{target_id}` has active premium.**\n\n"
            f"**Expires:** `{dt.strftime('%d %B %Y at %H:%M UTC')}`\n"
            f"**Days remaining:** `{remaining_days}`"
        )
    else:
        await message.reply_text(
            f"⭐ **User `{target_id}` has lifetime premium.**"
        )


# ══════════════════════════════════════════════════════════════════════════════
# /premiumlist — list all active premium users  (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("premiumlist") & filters.user(Config.ADMIN))
async def cmd_premium_list(client: Client, message: Message):
    users = await jishubotz.get_all_premium_users()
    now   = time.time()
    lines = ["**⭐ Active Premium Users**\n"]
    count = 0
    expired_ids = []

    async for user in users:
        uid    = user["_id"]
        expiry = user.get("premium_expiry")
        if expiry and expiry < now:
            expired_ids.append(uid)  # collect for cleanup
            continue
        if expiry:
            dt = datetime.fromtimestamp(expiry, tz=timezone.utc)
            remaining = int((expiry - now) / 86400)
            lines.append(f"• `{uid}` — expires {dt.strftime('%d %b %Y')} ({remaining}d left)")
        else:
            lines.append(f"• `{uid}` — Lifetime")
        count += 1

    # Background: revoke expired users found during list
    for uid in expired_ids:
        await jishubotz.set_premium(uid, False)

    if count == 0:
        return await message.reply_text(
            "No active premium users." +
            (f"\n\n_Auto-revoked {len(expired_ids)} expired user(s)._" if expired_ids else "")
        )

    lines.append(f"\n**Total active:** {count}")
    if expired_ids:
        lines.append(f"_Auto-revoked {len(expired_ids)} expired user(s)._")

    await message.reply_text("\n".join(lines))
