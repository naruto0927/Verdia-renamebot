"""
plugins/mediainfo.py
─────────────────────
/mi command — Reply to any media file to get full MediaInfo.

Pipeline
────────
  1. Download file  (full — ffprobe only reads the container header, so it's
     fast regardless of file size).
  2. _ffprobe_sync()  — subprocess.run inside run_blocking() so the event
     loop is NEVER blocked.  Returns rich parsed dict.
  3. _format_mediainfo()  — build the human-readable text report.
  4. _upload_to_telegraph()  — aiohttp POST with 3-retry loop.
     API: https://api.telegra.ph/createPage  (REST endpoint)
     URL: https://telegra.ph/<path>  (viewer, used only in the final link)
  5. Send Telegraph link, or fall back to inline <code> block.

NO pymediainfo — only ffprobe (ships with ffmpeg, always available).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from helper.database import jishubotz
from helper.ffmpeg import run_blocking
from messages import log, Msg

TEMP_DIR = "downloads/mediainfo"

# ── Module-level Telegraph token (created once, reused) ──────────────────────
_telegraph_token: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# /mi command
# ══════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.private & filters.command("mi"))
async def mediainfo_cmd(client: Client, message: Message):
    reply = message.reply_to_message
    if not reply or not reply.media:
        return await message.reply_text(
            "❌ **Reply to a media file** with /mi to get its MediaInfo."
        )

    media = getattr(reply, reply.media.value, None)
    if media is None:
        return await message.reply_text("❌ Unsupported media type.")

    if await jishubotz.is_banned(message.from_user.id):
        return

    status    = await message.reply_text("⏳ Fetching MediaInfo...")
    file_path = None

    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        raw_name  = getattr(media, "file_name", None) or f"mi_{int(time.time())}"
        file_size = getattr(media, "file_size", 0)
        safe_name = "".join(c for c in raw_name if c.isalnum() or c in "._- []@")
        file_path = os.path.join(
            TEMP_DIR,
            f"{message.from_user.id}_{int(time.time())}_{safe_name}",
        )

        # ── Partial download: first 15% of the file (max 50 MB) ──────────────
        # ffprobe only reads the container header — it does NOT need the full
        # file.  Stopping after 15% (or 50 MB) gives ffprobe everything it
        # needs while saving 85%+ of download time.
        partial_limit = min(int(file_size * 0.15), 50 * 1024 * 1024)
        partial_limit = max(partial_limit, 2 * 1024 * 1024)  # at least 2 MB

        await status.edit(
            f"⏳ Downloading header ({_humanbytes(partial_limit)} of "
            f"{_humanbytes(file_size)})..."
        )

        file_path = await _partial_download(
            client, reply, file_path, partial_limit
        )

        if not file_path or not os.path.exists(file_path):
            return await status.edit("❌ Failed to fetch file header.")

        actual_size = os.path.getsize(file_path)
        await status.edit(
            f"🔍 Analysing streams ({_humanbytes(actual_size)} fetched)..."
        )

        # ── ffprobe via run_blocking — never blocks event loop ─────────────────
        data      = await run_blocking(_ffprobe_sync, file_path)
        info_text = _format_mediainfo(data, raw_name, file_size)

        await status.edit("📤 Uploading to Telegraph...")
        page_url = await _upload_to_telegraph(f"MediaInfo of {raw_name}", info_text)

        if page_url:
            await status.edit(
                f"📊 **MediaInfo**\n\n"
                f"**File:** `{raw_name}`\n"
                f"**Size:** `{_humanbytes(file_size)}`\n\n"
                f"🔗 {page_url}",
                disable_web_page_preview=False,
            )
        else:
            truncated = info_text[:3800] + (
                "\n\n… (truncated)" if len(info_text) > 3800 else ""
            )
            await status.edit(f"📊 **MediaInfo**\n\n<code>{truncated}</code>")

    except Exception as e:
        log.error(Msg.MI_ERROR, error=e)
        await status.edit(f"❌ Failed to generate MediaInfo.\n\n`{e}`")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# _partial_download — download only the first N bytes of a Telegram file
#
# Strategy: use Pyrogram's iter_download() which yields chunks.  We stop
# writing once we hit the byte limit and cancel the generator.  This gives
# ffprobe the container header (moov atom / MKV EBML) it needs without
# downloading the entire file.
# ══════════════════════════════════════════════════════════════════════════════

async def _partial_download(
    client,
    message,
    dest_path: str,
    limit_bytes: int,
) -> str | None:
    """
    Download at most *limit_bytes* from *message* and write to *dest_path*.
    Returns dest_path on success, None on failure.
    """
    try:
        written = 0
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        with open(dest_path, "wb") as f:
            async for chunk in client.stream_media(message, limit=limit_bytes):
                f.write(chunk)
                written += len(chunk)
                if written >= limit_bytes:
                    break
        return dest_path if written > 0 else None
    except Exception as e:
        log.warning(Msg.MI_ERROR, error=f"partial download: {e}")
        # Fallback: full download
        try:
            return await client.download_media(message, file_name=dest_path)
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# ffprobe — sync subprocess (called via run_blocking, never touches event loop)
# ══════════════════════════════════════════════════════════════════════════════

def _ffprobe_sync(file_path: str) -> dict:
    """
    Runs ffprobe synchronously.  Must be called via run_blocking() so it
    executes in the thread pool and never blocks the event loop.

    Returns the raw parsed JSON dict from ffprobe, or {} on failure.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout:
            return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        pass
    except json.JSONDecodeError:
        pass
    except Exception:
        pass
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Formatter — builds full human-readable MediaInfo text from ffprobe dict
# ══════════════════════════════════════════════════════════════════════════════

def _format_mediainfo(data: dict, display_name: str, file_size: int) -> str:
    """
    Produce a structured text report with sections:
      ━━ GENERAL ━━
      ━━ VIDEO   ━━
      ━━ AUDIO   ━━  (one per audio stream)
      ━━ SUBTITLE ━━ (one per subtitle stream)
    """
    fmt     = data.get("format", {})
    streams = data.get("streams", [])
    lines:  list[str] = []

    # ── GENERAL ───────────────────────────────────────────────────────────────
    lines += ["━━ GENERAL ━━"]
    lines += [f"  Name       : {display_name}"]
    lines += [f"  Size       : {_humanbytes(file_size)}"]

    fmt_name = fmt.get("format_long_name") or fmt.get("format_name") or "N/A"
    lines += [f"  Format     : {fmt_name}"]

    dur = float(fmt.get("duration") or 0)
    if dur:
        lines += [f"  Duration   : {_fmt_dur(int(dur))}"]

    br = fmt.get("bit_rate")
    if br:
        lines += [f"  Bitrate    : {_fmt_br(br)}"]

    nb_streams = fmt.get("nb_streams")
    if nb_streams:
        lines += [f"  Streams    : {nb_streams}"]

    lines += [""]

    # ── Per-stream sections ────────────────────────────────────────────────────
    video_idx = audio_idx = sub_idx = 0

    for s in streams:
        ctype = (s.get("codec_type") or "unknown").upper()

        if ctype == "VIDEO":
            video_idx += 1
            label = "VIDEO" if video_idx == 1 else f"VIDEO #{video_idx}"
            lines += [f"━━ {label} ━━"]

            codec_name = s.get("codec_name", "?")
            codec_long = s.get("codec_long_name", "")
            lines += [f"  Codec      : {codec_name}" + (f" ({codec_long})" if codec_long else "")]

            profile = s.get("profile")
            if profile:
                lines += [f"  Profile    : {profile}"]

            w = s.get("width")
            h = s.get("height")
            if w and h:
                lines += [f"  Resolution : {w} × {h}"]

            # Coded dimensions (may differ from display)
            cw = s.get("coded_width")
            ch = s.get("coded_height")
            if cw and ch and (cw != w or ch != h):
                lines += [f"  Coded Size : {cw} × {ch}"]

            # Frame rate — r_frame_rate is exact (e.g. "24000/1001"), avg is simpler
            rfr  = s.get("r_frame_rate", "")
            avgfr = s.get("avg_frame_rate", "")
            fps_str = _parse_fps(rfr) or _parse_fps(avgfr) or rfr or avgfr
            if fps_str:
                lines += [f"  FPS        : {fps_str}"]

            pix_fmt = s.get("pix_fmt")
            if pix_fmt:
                lines += [f"  Pixel Fmt  : {pix_fmt}"]

            color_space = s.get("color_space")
            if color_space:
                lines += [f"  Color Space: {color_space}"]

            color_range = s.get("color_range")
            if color_range:
                lines += [f"  Color Range: {color_range}"]

            color_primaries = s.get("color_primaries")
            if color_primaries:
                lines += [f"  Primaries  : {color_primaries}"]

            trc = s.get("color_transfer")
            if trc:
                lines += [f"  Transfer   : {trc}"]

            level = s.get("level")
            if level and level != -99:
                lines += [f"  Level      : {level}"]

            vbr = s.get("bit_rate")
            if vbr:
                lines += [f"  Bitrate    : {_fmt_br(vbr)}"]

            dur_s = s.get("duration")
            if dur_s:
                lines += [f"  Duration   : {_fmt_dur(int(float(dur_s)))}"]

            nb_frames = s.get("nb_frames")
            if nb_frames:
                lines += [f"  Frames     : {nb_frames}"]

            disp_ar = s.get("display_aspect_ratio")
            if disp_ar and disp_ar != "0:1":
                lines += [f"  Aspect     : {disp_ar}"]

            tags = s.get("tags", {})
            lang = tags.get("language") or tags.get("LANGUAGE")
            if lang:
                lines += [f"  Language   : {lang}"]

            title = tags.get("title") or tags.get("TITLE")
            if title:
                lines += [f"  Title      : {title}"]

            lines += [""]

        elif ctype == "AUDIO":
            audio_idx += 1
            label = "AUDIO" if audio_idx == 1 else f"AUDIO #{audio_idx}"
            lines += [f"━━ {label} ━━"]

            codec_name = s.get("codec_name", "?")
            codec_long = s.get("codec_long_name", "")
            lines += [f"  Codec      : {codec_name}" + (f" ({codec_long})" if codec_long else "")]

            profile = s.get("profile")
            if profile and profile != "unknown":
                lines += [f"  Profile    : {profile}"]

            ch = s.get("channels")
            if ch:
                ch_layout = s.get("channel_layout", "")
                lines += [f"  Channels   : {ch}" + (f" ({ch_layout})" if ch_layout else "")]

            sr = s.get("sample_rate")
            if sr:
                lines += [f"  Sample Rate: {int(sr):,} Hz"]

            abr = s.get("bit_rate")
            if abr:
                lines += [f"  Bitrate    : {_fmt_br(abr)}"]

            sample_fmt = s.get("sample_fmt")
            if sample_fmt:
                lines += [f"  Sample Fmt : {sample_fmt}"]

            tags = s.get("tags", {})
            lang = tags.get("language") or tags.get("LANGUAGE")
            if lang:
                lines += [f"  Language   : {lang}"]

            title = tags.get("title") or tags.get("TITLE")
            if title:
                lines += [f"  Title      : {title}"]

            lines += [""]

        elif ctype == "SUBTITLE":
            sub_idx += 1
            label = "SUBTITLE" if sub_idx == 1 else f"SUBTITLE #{sub_idx}"
            lines += [f"━━ {label} ━━"]

            codec_name = s.get("codec_name", "?")
            codec_long = s.get("codec_long_name", "")
            lines += [f"  Codec      : {codec_name}" + (f" ({codec_long})" if codec_long else "")]

            tags = s.get("tags", {})
            lang = tags.get("language") or tags.get("LANGUAGE")
            if lang:
                lines += [f"  Language   : {lang}"]

            title = tags.get("title") or tags.get("TITLE")
            if title:
                lines += [f"  Title      : {title}"]

            forced = s.get("disposition", {}).get("forced")
            if forced:
                lines += [f"  Forced     : Yes"]

            lines += [""]

    return "\n".join(lines).strip()


# ══════════════════════════════════════════════════════════════════════════════
# Telegraph uploader — aiohttp + 3-retry loop
#
# Uses https://telegra.ph/createPage  (NOT api.telegra.ph — that host causes
# connection failures in many environments).
# Content is sent as a JSON-encoded "pre" node so the raw text is preserved
# exactly with all spacing — no HTML parsing issues.
# ══════════════════════════════════════════════════════════════════════════════

async def _upload_to_telegraph(title: str, content: str) -> str | None:
    """
    Upload a MediaInfo report to Telegraph and return the public URL.

    API endpoint:  https://api.telegra.ph  (the correct REST host)
    Viewer URL:    https://telegra.ph      (CDN — only for final links)

    POSTing to telegra.ph directly fails in many environments because it
    redirects to the CDN rather than serving the API.  api.telegra.ph is
    the only reliable endpoint for createAccount / createPage calls.
    """
    global _telegraph_token

    # Truncate to Telegraph's hard limit (~64 KB)
    if len(content) > 60_000:
        content = content[:60_000] + "\n\n… (truncated)"

    # <pre> node preserves all spacing and line-breaks exactly
    nodes = json.dumps([{"tag": "pre", "children": [content]}])

    # ── Step 1: create / reuse account token ──────────────────────────────────
    if not _telegraph_token:
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as session:
                    async with session.post(
                        "https://api.telegra.ph/createAccount",   # ← correct endpoint
                        data={
                            "short_name":  "MediaInfoBot",
                            "author_name": "MediaInfo",
                        },
                    ) as r:
                        text = await r.text()
                        try:
                            d = json.loads(text)
                        except Exception:
                            log.warning(Msg.MI_TELEGRAPH_ERR,
                                        error=f"createAccount non-JSON: {text[:200]}")
                            d = {}
                        if d.get("ok"):
                            _telegraph_token = d["result"]["access_token"]
                            break
                        log.warning(Msg.MI_TELEGRAPH_ERR,
                                    error=f"createAccount attempt {attempt+1}: {d.get('error')}")
            except Exception as exc:
                log.warning(Msg.MI_TELEGRAPH_ERR,
                            error=f"createAccount attempt {attempt+1}: {exc}")
            if attempt < 2:
                await asyncio.sleep(3)

    if not _telegraph_token:
        log.warning(Msg.MI_TELEGRAPH_ERR, error="could not create Telegraph account after 3 tries")
        return None

    # ── Step 2: create page — 3 retries, reset token on auth error ────────────
    page_title = (title or "MediaInfo")[:256]

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.post(
                    "https://api.telegra.ph/createPage",   # ← correct endpoint
                    data={
                        "access_token": _telegraph_token,
                        "title":        page_title,
                        "author_name":  "MediaInfo Bot",
                        "content":      nodes,
                    },
                ) as r:
                    text = await r.text()
                    try:
                        result = json.loads(text)
                    except Exception:
                        log.warning(Msg.MI_TELEGRAPH_ERR,
                                    error=f"createPage non-JSON: {text[:200]}")
                        result = {}

                    if result.get("ok"):
                        path = result["result"]["path"]
                        return f"https://telegra.ph/{path}"   # viewer URL ← correct

                    err = result.get("error", "unknown")
                    log.warning(Msg.MI_TELEGRAPH_ERR,
                                error=f"createPage attempt {attempt+1}: {err}")

                    # INVALID_ACCESS_TOKEN → force token refresh on next retry
                    if "ACCESS_TOKEN" in str(err).upper():
                        _telegraph_token = None
                        break

        except Exception as exc:
            log.warning(Msg.MI_TELEGRAPH_ERR,
                        error=f"createPage attempt {attempt+1}: {exc}")

        if attempt < 2:
            await asyncio.sleep(3)

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers (shared across this module)
# ══════════════════════════════════════════════════════════════════════════════

def _humanbytes(size) -> str:
    try:
        size = int(size)
    except (TypeError, ValueError):
        return "N/A"
    if size <= 0:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def _fmt_dur(seconds: int) -> str:
    """Convert integer seconds → H:MM:SS or M:SS string."""
    h   = seconds // 3600
    m   = (seconds % 3600) // 60
    s   = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_br(br) -> str:
    try:
        br = int(br)
        if br >= 1_000_000:
            return f"{br / 1_000_000:.2f} Mbps"
        if br >= 1_000:
            return f"{br / 1_000:.0f} Kbps"
        return f"{br} bps"
    except Exception:
        return str(br)


def _parse_fps(fraction_str: str) -> str:
    """Convert ffprobe fraction string like '24000/1001' → '23.976 fps'."""
    try:
        if "/" in fraction_str:
            num, den = fraction_str.split("/")
            val = float(num) / float(den)
            if val <= 0:
                return ""
            # Common exact values
            for known in (23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 59.94, 60.0, 120.0):
                if abs(val - known) < 0.01:
                    return f"{known:.3f}".rstrip("0").rstrip(".") + " fps"
            return f"{val:.3f} fps"
        val = float(fraction_str)
        return f"{val:.3f}".rstrip("0").rstrip(".") + " fps" if val > 0 else ""
    except Exception:
        return ""
