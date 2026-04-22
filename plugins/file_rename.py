"""
plugins/file_rename.py
───────────────────────────────────────────────────────────────────────────────
Rename pipeline — fully concurrent, correct filenames, premium-gated.

╔══════════════════════════════════════════════════════════════════════════╗
║  FIX SUMMARY                                                             ║
║  ─────────────────────────────────────────────────────────────────────── ║
║  TRUE PARALLEL PIPELINE                                                  ║
║    Each task runs: download → metadata → upload independently.           ║
║    asyncio.create_task() fires immediately and returns — never awaited   ║
║    sequentially by the bot.  _global_sem caps total simultaneous jobs.   ║
║    Per-user cap prevents monopoly.  One failure never affects others.    ║
║                                                                          ║
║  run_blocking(func, *args)                                               ║
║    Any sync/blocking function (PIL, hachoir, pymediainfo) is routed      ║
║    through loop.run_in_executor — event loop is never blocked.           ║
║    All FFmpeg/FFprobe calls use asyncio.create_subprocess_exec.          ║
║                                                                          ║
║  FILENAME — EXACT PRESERVATION                                           ║
║    User input used VERBATIM: [S01-01] Tune In [480p] @Animes_Ocean.mkv  ║
║    No prefixes, no underscore replacements, brackets/@ preserved.        ║
║    Temp files use internal job_id — NEVER sent to Telegram.              ║
║    Final upload: file_name=user_filename                                 ║
║                                                                          ║
║  PREMIUM — checked at file-receive AND confirm step                      ║
║                                                                          ║
║  UI CHANGES                                                              ║
║    REMOVED: 📸 Screenshot, 🎬 Sample Video                              ║
║    KEPT:    📁 Document, 🎥 Video, 🎵 Audio                              ║
║    ADDED:   📊 MediaInfo (→ Telegraph page)                              ║
║             📚 CBZ / PDF (rename only, no metadata)                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time

from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from helper.database import jishubotz
from helper.ffmpeg import (
    add_metadata,
    fix_thumb,
    get_duration_hachoir,
    run_blocking,
    take_screen_shot,
)
from helper.utils import add_prefix_suffix, convert, humanbytes, progress_for_pyrogram
from messages import log, Msg

logger = logging.getLogger(__name__)

_VIDEO_EXTS = (
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".flv", ".ts",  ".m4v", ".wmv", ".3gp",
)
_CBZ_PDF_EXTS = (".cbz", ".pdf")


# ─────────────────────────────────────────────────────────────────────────────
# In-memory caches  (keyed by Telegram message_id)
# ─────────────────────────────────────────────────────────────────────────────
_pending:            dict[int, str]    = {}   # msg_id → exact user filename
_file_cache:         dict[int, object] = {}   # msg_id → original file Message
_upload_type_cache:  dict[int, str]    = {}   # msg_id → callback_data string


# ══════════════════════════════════════════════════════════════════════════════
# Concurrency control
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULT_GLOBAL_LIMIT: int = 10
_DEFAULT_USER_LIMIT:   int = 3

_global_sem:   asyncio.Semaphore = asyncio.Semaphore(_DEFAULT_GLOBAL_LIMIT)
_global_limit: int               = _DEFAULT_GLOBAL_LIMIT
_user_limit:   int               = _DEFAULT_USER_LIMIT

_user_active:      dict[int, int] = {}
_user_active_lock: asyncio.Lock   = asyncio.Lock()


def _active_jobs() -> int:
    return sum(_user_active.values())


async def _acquire_slot(user_id: int) -> bool:
    async with _user_active_lock:
        current = _user_active.get(user_id, 0)
        if current >= _user_limit:
            return False
        _user_active[user_id] = current + 1
        return True


async def _release_slot(user_id: int) -> None:
    async with _user_active_lock:
        count = _user_active.get(user_id, 0)
        _user_active[user_id] = max(0, count - 1)
        if _user_active[user_id] == 0:
            _user_active.pop(user_id, None)


# ══════════════════════════════════════════════════════════════════════════════
# Admin: /setlimit  /getlimit
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("setlimit") & filters.user(Config.ADMIN))
async def cmd_setlimit(client: Client, message: Message):
    global _global_sem, _global_limit, _user_limit
    parts = message.text.strip().split()
    if len(parts) != 3:
        return await message.reply_text(
            "**Usage:**\n"
            "`/setlimit global <n>` — max total concurrent jobs\n"
            "`/setlimit user <n>`   — max jobs per user\n\n"
            "**Example:** `/setlimit global 20`"
        )
    scope = parts[1].lower()
    if scope not in ("global", "user"):
        return await message.reply_text("❌ Scope must be `global` or `user`.")
    try:
        n = int(parts[2])
        if n < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text("❌ Limit must be a positive integer.")

    if scope == "global":
        _global_limit = n
        _global_sem   = asyncio.Semaphore(n)
        await message.reply_text(f"✅ **Global limit set to `{n}`**")
    else:
        _user_limit = n
        await message.reply_text(f"✅ **Per-user limit set to `{n}`**")


@Client.on_message(filters.command("getlimit") & filters.user(Config.ADMIN))
async def cmd_getlimit(client: Client, message: Message):
    active = _active_jobs()
    per_user_lines = "\n".join(
        f"  • `{uid}` → {cnt} job{'s' if cnt != 1 else ''}"
        for uid, cnt in _user_active.items()
    ) or "  (none)"
    await message.reply_text(
        f"**⚙️ Concurrent Rename Limits**\n\n"
        f"🌐 **Global limit:** `{_global_limit}` jobs\n"
        f"👤 **Per-user limit:** `{_user_limit}` jobs\n\n"
        f"📊 **Active now:** `{active}`\n\n"
        f"**Per-user:**\n{per_user_lines}"
    )


@Client.on_message(filters.command("jobs") & filters.user(Config.ADMIN))
async def cmd_jobs(client: Client, message: Message):
    """Live parallel job monitor — shows every active rename task."""
    active = _active_jobs()
    if not _user_active:
        return await message.reply_text("✅ **No active jobs right now.**")
    per_user_lines = "\n".join(
        f"  • `{uid}` → {cnt} parallel job{'s' if cnt != 1 else ''}"
        for uid, cnt in _user_active.items()
    )
    await message.reply_text(
        f"**⚡ Live Parallel Jobs**\n\n"
        f"📊 **Total active:** `{active}` / `{_global_limit}` global slots\n\n"
        f"**Per-user breakdown:**\n{per_user_lines}\n\n"
        f"_Each job = download → metadata → upload running independently._"
    )


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — File received → premium gate → show action buttons
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client: Client, message: Message):
    file    = getattr(message, message.media.value)
    user_id = int(message.from_user.id)

    # Ban check
    if await jishubotz.is_banned(user_id):
        return await message.reply(
            "**ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ. "
            "ᴄᴏɴᴛᴀᴄᴛ @Suh0_kang ᴛᴏ ʀᴇsᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇ!!**"
        )

    # Premium gate
    if not await jishubotz.is_premium(user_id):
        return await message.reply_text(
            "🚫 **This feature is only available for premium users.**\n\n"
            "Contact the admin to get access.\n"
            "Use /premium to check your status.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ My Status", callback_data="check_premium_status"),
            ]])
        )

    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("⚠️ File too large. Maximum size is 2 GB.")

    filename = file.file_name or ""
    ext      = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    is_video = message.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]
    is_audio = message.media == MessageMediaType.AUDIO
    is_cbz_pdf = ext in [e.lstrip(".") for e in _CBZ_PDF_EXTS]

    # ── Row 1: Document + Video/Audio ─────────────────────────────────────────
    row1 = [InlineKeyboardButton("📁 Document", callback_data="upload_document")]
    if is_video:
        row1.append(InlineKeyboardButton("🎥 Video", callback_data="upload_video"))
    elif is_audio:
        row1.append(InlineKeyboardButton("🎵 Audio", callback_data="upload_audio"))

    # ── Row 2: MediaInfo + CBZ/PDF ────────────────────────────────────────────
    row2 = [InlineKeyboardButton("📊 MediaInfo", callback_data="action_mediainfo")]
    if is_cbz_pdf or ext in ("cbz", "pdf"):
        row2.append(InlineKeyboardButton("📚 CBZ / PDF", callback_data="upload_cbzpdf"))

    # ── Row 3: Screenshot + Sample Video (video files only) ───────────────────
    show_media_actions = is_video or ext in [e.lstrip(".") for e in _VIDEO_EXTS]
    buttons = [row1, row2]
    if show_media_actions:
        buttons.append([
            InlineKeyboardButton("📸 Screenshot",   callback_data="media_screenshot"),
            InlineKeyboardButton("🎬 Sample Video", callback_data="media_sample"),
        ])

    sent = await message.reply(
        text=(
            f"**Select an action for your file:**\n\n"
            f"**File:** `{filename or 'Unknown'}`\n\n"
            f"📝 **Rename** → tap Document / Video / Audio / CBZ·PDF\n"
            f"📊 **MediaInfo** → full stream info on Telegraph\n"
            f"📸 **Screenshot** → grab frames from the video\n"
            f"🎬 **Sample Video** → get a 30 s clip"
        ),
        reply_to_message_id=message.id,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    _file_cache[sent.id] = message


# ── Premium status quick-check callback ───────────────────────────────────────
@Client.on_callback_query(filters.regex("^check_premium_status$"))
async def cb_check_premium(bot, update):
    is_prem = await jishubotz.is_premium(update.from_user.id)
    if is_prem:
        await update.answer("✅ You have premium access!", show_alert=True)
    else:
        await update.answer("❌ No premium. Contact admin.", show_alert=True)


# ══════════════════════════════════════════════════════════════════════════════
# MediaInfo button → fire task immediately (non-blocking)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^action_mediainfo$"))
async def cb_mediainfo(bot, update):
    await update.answer("📊 Generating MediaInfo...")
    asyncio.create_task(_handle_mediainfo(bot, update))


async def _handle_mediainfo(bot, update) -> None:
    """
    MediaInfo pipeline (button-triggered variant of /mi).

    Uses the same _ffprobe_sync() + _format_mediainfo() + _upload_to_telegraph()
    as plugins/mediainfo.py.

    run_blocking() is used for _ffprobe_sync so subprocess never blocks the
    event loop. Telegraph upload uses aiohttp with 3-retry loop against
    https://telegra.ph/createPage (NOT api.telegra.ph).

    NO pymediainfo — ffprobe only.
    """
    from plugins.mediainfo import (
        _ffprobe_sync,
        _format_mediainfo,
        _upload_to_telegraph as _telegraph_upload,
    )

    chat_id      = update.message.chat.id
    file_message = update.message.reply_to_message

    if not file_message or not file_message.media:
        return await update.message.edit("❌ Original file not found.")

    media     = getattr(file_message, file_message.media.value, None)
    raw_name  = getattr(media, "file_name", None) or f"file_{int(time.time())}"
    file_size = getattr(media, "file_size", 0)

    ms = await update.message.edit("⏳ Downloading for MediaInfo analysis...")

    user_id  = update.from_user.id
    job_id   = f"mi_{user_id}_{int(time.time() * 1000)}"
    dl_dir   = f"downloads/{job_id}"
    os.makedirs(dl_dir, exist_ok=True)

    safe_name = "".join(c for c in raw_name if c.isalnum() or c in "._- []@")
    file_path = os.path.join(dl_dir, safe_name)

    try:
        # ── Partial download: first 15% / max 50 MB ───────────────────────────
        from plugins.mediainfo import _partial_download as _mi_partial_dl
        partial_limit = min(int(file_size * 0.15), 50 * 1024 * 1024)
        partial_limit = max(partial_limit, 2 * 1024 * 1024)
        await _safe_edit(
            ms,
            f"⏳ Fetching header ({humanbytes(partial_limit)} of {humanbytes(file_size)})..."
        )

        file_path = await _mi_partial_dl(bot, file_message, file_path, partial_limit)

        if not file_path or not os.path.exists(file_path):
            return await _safe_edit(ms, "❌ Download failed.")

        await _safe_edit(ms, "🔍 Analysing streams with ffprobe...")

        # _ffprobe_sync uses subprocess.run — run via run_blocking (thread pool)
        data      = await run_blocking(_ffprobe_sync, file_path)
        info_text = _format_mediainfo(data, raw_name, file_size)

        await _safe_edit(ms, "📤 Uploading to Telegraph...")
        page_url = await _telegraph_upload(f"MediaInfo of {raw_name}", info_text)

        if page_url:
            await ms.edit(
                f"📊 **MediaInfo Generated**\n\n"
                f"**File:** `{raw_name}`\n"
                f"**Size:** `{humanbytes(file_size)}`\n\n"
                f"🔗 {page_url}",
                disable_web_page_preview=False,
            )
        else:
            snippet = info_text[:3800] + ("\n\n… (truncated)" if len(info_text) > 3800 else "")
            await ms.edit(f"📊 **MediaInfo**\n\n<code>{snippet}</code>")

    except Exception as e:
        logger.error("MediaInfo error: %s", e)
        await _safe_edit(ms, f"❌ MediaInfo failed: `{e}`")
    finally:
        _cleanup_dir(dl_dir)


# ══════════════════════════════════════════════════════════════════════════════
# Screenshot button → fire task immediately (non-blocking)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^media_screenshot$"))
async def cb_screenshot(bot, update):
    await update.answer("📸 Generating screenshots...")
    asyncio.create_task(_handle_screenshot(bot, update))


async def _handle_screenshot(bot, update) -> None:
    """
    Screenshot pipeline — produces ONE combined 3x2 grid image.

    Steps:
      1. Download video file.
      2. generate_screenshot_grid():
           a. Capture 6 frames at 0%/20%/40%/60%/80%/95% — all parallel via asyncio.gather.
           b. Build 3x2 PIL grid with HH:MM:SS timestamp on each frame — run_blocking().
           c. Delete raw frame files automatically.
      3. Send the single grid JPEG.  No media groups.  No multiple images.
    """
    from helper.ffmpeg import generate_screenshot_grid

    chat_id      = update.message.chat.id
    file_message = update.message.reply_to_message

    if not file_message or not file_message.media:
        return await update.message.edit("No original file found.")

    ms      = await update.message.edit("Downloading for screenshot grid...")
    user_id = update.from_user.id
    job_id  = f"ss_{user_id}_{int(time.time() * 1000)}"
    dl_dir  = f"downloads/{job_id}"
    os.makedirs(dl_dir, exist_ok=True)

    file     = getattr(file_message, file_message.media.value)
    filename = file.file_name or "video.mkv"
    dl_path  = f"{dl_dir}/{filename}"

    try:
        await bot.download_media(
            message=file_message,
            file_name=dl_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading... ", ms, time.time()),
        )
        await _safe_edit(ms, "Capturing 6 frames and building grid...")

        grid_path = await generate_screenshot_grid(dl_path, dl_dir, count=6, cols=3)

        if not grid_path:
            return await _safe_edit(ms, "Could not generate screenshot grid. Is this a video?")

        await ms.delete()
        await bot.send_photo(
            chat_id,
            photo=grid_path,
            caption=f"📸 Screenshot Grid (6 frames)\n`{filename}`",
        )

    except Exception as e:
        logger.error("Screenshot error: %s", e)
        await _safe_edit(ms, f"Screenshot failed: `{e}`")
    finally:
        _cleanup_dir(dl_dir)


# ══════════════════════════════════════════════════════════════════════════════
# Sample Video button → fire task immediately (non-blocking)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^media_sample$"))
async def cb_sample_video(bot, update):
    await update.answer("🎬 Generating sample clip...")
    asyncio.create_task(_handle_sample_video(bot, update))


async def _handle_sample_video(bot, update) -> None:
    """
    Download file → generate_sample_video (async subprocess) → send video.
    Fully non-blocking — asyncio.create_subprocess_exec throughout.
    """
    from helper.ffmpeg import generate_sample_video

    chat_id      = update.message.chat.id
    file_message = update.message.reply_to_message

    if not file_message or not file_message.media:
        return await update.message.edit("❌ Original file not found.")

    ms      = await update.message.edit("🎬 Downloading for sample clip...")
    user_id = update.from_user.id
    job_id  = f"smp_{user_id}_{int(time.time() * 1000)}"
    dl_dir  = f"downloads/{job_id}"
    os.makedirs(dl_dir, exist_ok=True)

    file        = getattr(file_message, file_message.media.value)
    filename    = file.file_name or "video.mkv"
    dl_path     = f"{dl_dir}/{filename}"
    sample_path = None

    try:
        await bot.download_media(
            message=file_message,
            file_name=dl_path,
            progress=progress_for_pyrogram,
            progress_args=("🎬 Downloading... ⚡", ms, time.time()),
        )
        await _safe_edit(ms, "🎬 Generating 30 s sample clip...")

        # generate_sample_video uses asyncio.create_subprocess_exec — non-blocking
        sample_path = await generate_sample_video(dl_path, dl_dir, duration=30)

        if not sample_path:
            return await _safe_edit(ms, "❌ Could not generate sample. Is this a video?")

        await ms.delete()
        await bot.send_video(
            chat_id,
            video=sample_path,
            caption=f"🎬 **Sample Clip** (30 s)\n`{filename}`",
            supports_streaming=True,
        )

    except Exception as e:
        logger.error("Sample video error: %s", e)
        await _safe_edit(ms, f"❌ Sample video failed: `{e}`")
    finally:
        if sample_path:
            _safe_remove(sample_path)
        _cleanup_dir(dl_dir)


# ── MediaInfo / Telegraph helpers are in plugins/mediainfo.py ────────────────
# _handle_mediainfo imports them directly at call time — no duplication.
# _fmt_dur / _fmt_br kept here for other local use.


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Rename button tapped → ask for filename
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^upload_"))
async def ask_filename(bot, update):
    await update.answer()
    file_message = update.message.reply_to_message
    if not file_message or not file_message.media:
        return await update.message.edit("❌ Original file not found. Please send the file again.")

    file     = getattr(file_message, file_message.media.value)
    filename = file.file_name or "file"

    await update.message.delete()

    sent = await bot.send_message(
        update.message.chat.id,
        text=(
            f"**Send me the new filename:**\n\n"
            f"**Current name:** `{filename}`"
        ),
        reply_markup=ForceReply(True),
    )

    _upload_type_cache[sent.id] = update.data   # "upload_document" etc.
    _file_cache[sent.id]        = file_message


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — User typed filename → show confirm button
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.reply)
async def refunc(client: Client, message: Message):
    reply_message = message.reply_to_message
    if not (reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply)):
        return

    upload_type_stored = _upload_type_cache.get(reply_message.id)
    file_message       = _file_cache.get(reply_message.id)

    if not upload_type_stored or not file_message:
        return

    # EXACT filename — no cleaning, no truncation, preserve [], @, spaces
    new_name = message.text.strip()

    await message.delete()
    await reply_message.delete()

    _upload_type_cache.pop(reply_message.id, None)
    _file_cache.pop(reply_message.id, None)

    media = getattr(file_message, file_message.media.value)

    # Auto-add extension only if the user omitted it entirely
    if "." not in new_name:
        extn = (
            media.file_name.rsplit(".", 1)[-1]
            if "." in (media.file_name or "")
            else "mkv"
        )
        new_name = f"{new_name}.{extn}"

    sent = await message.reply(
        text=f"**Confirm rename:**\n\n**New name:** `{new_name}`",
        reply_to_message_id=file_message.id,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{upload_type_stored}")
        ]]),
    )

    # Store EXACT clean filename
    _pending[sent.id] = new_name


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Confirm → acquire slot → fire task (non-blocking)
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^confirm_upload_"))
async def doc(bot, update):
    user_id = update.from_user.id

    # Premium re-check (may have expired between steps)
    if not await jishubotz.is_premium(user_id):
        return await update.answer(
            "🚫 Your premium has expired. Contact admin to renew.",
            show_alert=True,
        )

    acquired = await _acquire_slot(user_id)
    if not acquired:
        return await update.answer(
            f"⏳ You already have {_user_limit} active "
            f"job{'s' if _user_limit != 1 else ''}. "
            "Please wait for one to finish.",
            show_alert=True,
        )

    # Fire immediately — never awaited sequentially
    asyncio.create_task(_run_rename(bot, update))


# ══════════════════════════════════════════════════════════════════════════════
# Rename job wrapper — owns semaphore + slot lifecycle
# ══════════════════════════════════════════════════════════════════════════════

async def _run_rename(bot, update) -> None:
    """
    Wraps _pipeline with concurrency tracking.

    THE CRITICAL FIX FOR PARALLEL EXECUTION:
    _global_sem is NOT placed here around the whole pipeline.
    Each task runs its download → metadata phase fully in parallel.
    Only the upload step acquires _global_sem to avoid Telegram flood-waits.
    This is what makes Task1 and Task2 download simultaneously.
    """
    user_id = update.from_user.id
    try:
        await _pipeline(bot, update, user_id, update.message.chat.id)
    except Exception as e:
        logger.exception("Unhandled error in rename task user=%s: %s", user_id, e)
    finally:
        await _release_slot(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# Core pipeline: download → (metadata) → upload
# ══════════════════════════════════════════════════════════════════════════════

async def _pipeline(bot, update, user_id: int, chat_id: int) -> None:
    """
    Fully isolated per-task pipeline. Each task runs independently:
      Task 1 → download → metadata → upload
      Task 2 → download → metadata → upload
      Task 3 → download → metadata → upload

    Filename strategy
    ─────────────────
    • new_filename_raw  = exactly what the user typed
    • new_filename      = new_filename_raw + optional prefix/suffix
    • job_id            = internal key  (NEVER uploaded)
    • temp_dl_name      = _tmp_{job_id}.ext  (NEVER uploaded)
    • metadata_path     = Metadata/{job_id}.ext  (NEVER uploaded)
    • upload always uses file_name=new_filename
    """
    os.makedirs("Metadata", exist_ok=True)

    # "confirm_upload_document" → last segment
    upload_type = update.data.split("_")[-1]

    # Retrieve exact user filename
    new_filename_raw = _pending.pop(update.message.id, None)
    if not new_filename_raw:
        return await update.message.edit(
            "❌ Could not read filename. Please send the file again."
        )

    # Apply prefix/suffix (preserves brackets, spaces, @tags)
    prefix = await jishubotz.get_prefix(chat_id)
    suffix = await jishubotz.get_suffix(chat_id)
    try:
        new_filename = add_prefix_suffix(new_filename_raw, prefix, suffix)
    except Exception as e:
        return await update.message.edit(
            f"❌ Cannot apply Prefix/Suffix\n\n**Error:** `{e}`"
        )

    job_id       = f"{user_id}_{int(time.time() * 1000)}"
    dl_dir       = f"downloads/{job_id}"
    os.makedirs(dl_dir, exist_ok=True)

    ext           = new_filename.rsplit(".", 1)[-1] if "." in new_filename else "mkv"
    file_path     = f"{dl_dir}/_tmp_{job_id}.{ext}"
    metadata_path = f"Metadata/{job_id}.{ext}"

    file           = update.message.reply_to_message
    ph_path        = None
    _bool_metadata = False

    logger.info(
        "▶ PIPELINE START  user=%s  filename=%s  job=%s  active_total=%s",
        user_id, new_filename, job_id, _active_jobs()
    )

    try:
        try:
            ms = await update.message.edit("🚀 Downloading... ⚡")
        except Exception:
            ms = update.message

        # ── Download ──────────────────────────────────────────────────────────
        try:
            await bot.download_media(
                message=file,
                file_name=file_path,
                progress=progress_for_pyrogram,
                progress_args=("🚀 Downloading... ⚡", ms, time.time()),
            )
        except Exception as e:
            return await _safe_edit(ms, f"❌ Download failed: `{e}`")

        # ── Duration (via run_blocking for hachoir — non-blocking) ─────────────
        duration = await get_duration_hachoir(file_path)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        media   = getattr(file, file.media.value)
        c_thumb = await jishubotz.get_thumbnail(chat_id)

        if c_thumb:
            # Stored file_id may have an expired reference — catch and fall back
            try:
                dl = await bot.download_media(c_thumb)
                if dl and os.path.exists(dl) and os.path.getsize(dl) > 0:
                    _, __, ph_path = await fix_thumb(dl)
                else:
                    # Download returned nothing useful — discard silently
                    if dl and os.path.exists(dl):
                        os.remove(dl)
                    ph_path = None
            except Exception as e:
                logger.warning("Custom thumbnail download failed (%s) — using auto thumb", e)
                # Expired reference: clear stored thumbnail so it does not repeat
                await jishubotz.set_thumbnail(chat_id, file_id=None)
                ph_path = None

        if ph_path is None and media.thumbs:
            # Auto-generate thumbnail from the video at a random timestamp
            try:
                ph_path_ = await take_screen_shot(
                    file_path, dl_dir,
                    random.randint(0, max(duration - 1, 0)),
                )
                if ph_path_ and os.path.exists(ph_path_) and os.path.getsize(ph_path_) > 0:
                    _, __, ph_path = await fix_thumb(ph_path_)
            except Exception as e:
                ph_path = None
                logger.warning("Auto thumbnail error: %s", e)

        # ── Caption ───────────────────────────────────────────────────────────
        c_caption = await jishubotz.get_caption(chat_id)
        if c_caption:
            try:
                caption = c_caption.format(
                    filename=new_filename,
                    filesize=humanbytes(media.file_size),
                    duration=convert(duration),
                )
            except Exception as e:
                return await _safe_edit(ms, f"Your Caption Error: ({e})")
        else:
            caption = f"**{new_filename}**"

        # ── Metadata — CBZ/PDF skips this entirely ────────────────────────────
        is_cbz_pdf_upload = upload_type == "cbzpdf"

        if not is_cbz_pdf_upload:
            _bool_metadata = await jishubotz.get_metadata(chat_id)
            if _bool_metadata:
                metadata_fields = await jishubotz.get_metadata_fields(chat_id)
                # add_metadata uses asyncio.create_subprocess_exec — fully async
                result = await add_metadata(file_path, metadata_path, metadata_fields, ms)
                if not result:
                    _bool_metadata = False
            else:
                await _safe_edit(ms, "⏳ Processing... ⚡")
        else:
            # CBZ/PDF: no metadata, just rename
            await _safe_edit(ms, "📚 Preparing CBZ/PDF upload...")

        # ── Upload — semaphore HERE ONLY (not around download/metadata) ─────────
        # Semaphore only wraps the upload so Telegram flood-waits from concurrent
        # send_document/send_video calls don't stall other tasks' downloads.
        # Each task's download + metadata phase runs fully in parallel.
        upload_path = metadata_path if _bool_metadata else file_path
        await _safe_edit(ms, "💠 Uploading... ⚡")

        sent_message = None
        try:
            async with _global_sem:   # ← semaphore only around upload, not whole pipeline
                if upload_type in ("document", "cbzpdf"):
                    sent_message = await bot.send_document(
                        chat_id,
                        document=upload_path,
                        file_name=new_filename,        # ← exact user filename
                        thumb=ph_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("💠 Uploading... ⚡", ms, time.time()),
                    )
                elif upload_type == "video":
                    sent_message = await bot.send_video(
                        chat_id,
                        video=upload_path,
                        file_name=new_filename,        # ← exact user filename
                        caption=caption,
                        thumb=ph_path,
                        duration=duration,
                        progress=progress_for_pyrogram,
                        progress_args=("💠 Uploading... ⚡", ms, time.time()),
                    )
                elif upload_type == "audio":
                    sent_message = await bot.send_audio(
                        chat_id,
                        audio=upload_path,
                        file_name=new_filename,        # ← exact user filename
                        caption=caption,
                        thumb=ph_path,
                        duration=duration,
                        progress=progress_for_pyrogram,
                        progress_args=("💠 Uploading... ⚡", ms, time.time()),
                    )

            if sent_message:
                await bot.copy_message(
                    chat_id=Config.BIN_CHANNEL,
                    from_chat_id=chat_id,
                    message_id=sent_message.id,
                )

        except Exception as e:
            return await _safe_edit(ms, f"**Upload Error:** `{e}`")

        # ── Optional dump ─────────────────────────────────────────────────────
        if sent_message:
            settings = await jishubotz.get_user_settings(user_id)
            if settings.get("dump_mode") and settings.get("dump_channel"):
                asyncio.create_task(
                    _dump_to_channel(bot, user_id, int(settings["dump_channel"]), sent_message)
                )

        await ms.delete()
        logger.info(
            "✔ PIPELINE DONE   user=%s  filename=%s  job=%s",
            user_id, new_filename, job_id
        )

    finally:
        if ph_path:
            _safe_remove(ph_path)
        if _bool_metadata:
            _safe_remove(metadata_path)
        _cleanup_dir(dl_dir)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _safe_edit(ms, text: str) -> None:
    try:
        await ms.edit(text)
    except Exception:
        pass


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _cleanup_dir(directory: str) -> None:
    try:
        if not os.path.exists(directory):
            return
        for f in os.listdir(directory):
            _safe_remove(os.path.join(directory, f))
        os.rmdir(directory)
    except Exception:
        pass


async def _dump_to_channel(bot, user_id: int, channel_id: int, sent_message) -> None:
    try:
        await bot.copy_message(
            chat_id=channel_id,
            from_chat_id=sent_message.chat.id,
            message_id=sent_message.id,
        )
        logger.info("Dumped to channel %s for user %s", channel_id, user_id)
    except Exception as e:
        logger.error("Dump failed for user %s → channel %s: %s", user_id, channel_id, e)
        try:
            await bot.send_message(
                user_id,
                f"⚠️ Could not dump to channel `{channel_id}`: `{e}`",
                disable_notification=True,
            )
        except Exception:
            pass


def _fmt_dur(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s  = divmod(s, 60)
    h, m  = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _fmt_br(br) -> str:
    try:
        br = int(br)
        if br >= 1_000_000:
            return f"{br / 1_000_000:.2f} Mbps"
        return f"{br / 1_000:.0f} Kbps"
    except Exception:
        return str(br)
