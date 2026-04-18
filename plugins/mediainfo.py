"""
plugins/mediainfo.py
─────────────────────
/mi — Reply to any media file to get formatted MediaInfo.

Strategy (simple and reliable)
  1. Download the full file via download_media (Pyrogram handles it correctly).
  2. Run ffprobe on it with -show_format -show_streams -of json (async subprocess).
  3. Also try pymediainfo for richer output.
  4. Format the result.
  5. Upload to Telegra.ph; fall back to inline code block if Telegraph fails.
  6. Delete the temp file.

No partial-download tricks — ffprobe is fast regardless of file size because
it only reads the container header.
"""

import asyncio
import json
import os
import time

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from helper.database import jishubotz
from messages import log, Msg

TEMP_DIR = "downloads/mediainfo"

# Module-level Telegraph token (created once per bot session)
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

    status    = await message.reply_text("⏳ Downloading file for analysis...")
    file_path = None

    try:
        # ── 1. Download ───────────────────────────────────────────────────────
        os.makedirs(TEMP_DIR, exist_ok=True)
        raw_name  = getattr(media, "file_name", None) or f"mi_{int(time.time())}"
        safe_name = "".join(c for c in raw_name if c.isalnum() or c in "._- ")
        file_path = os.path.join(TEMP_DIR, f"{message.from_user.id}_{int(time.time())}_{safe_name}")

        file_path = await client.download_media(reply, file_name=file_path)

        if not file_path or not os.path.exists(file_path):
            return await status.edit("❌ Failed to download file.")

        # ── 2. Parse with ffprobe ─────────────────────────────────────────────
        await status.edit("🔍 Analysing with ffprobe...")
        info_text = await _run_ffprobe(file_path, raw_name, media)

        # ── 3. Try enriching with pymediainfo ─────────────────────────────────
        pymedia_text = await asyncio.to_thread(_run_pymediainfo, file_path, raw_name, media)
        if pymedia_text:
            info_text = pymedia_text   # pymediainfo gives richer output

        # ── 4. Upload to Telegraph ────────────────────────────────────────────
        await status.edit("📤 Uploading report...")
        page_url = await _upload_to_telegraph(raw_name, info_text)

        if page_url:
            await status.edit(
                f"📊 **MediaInfo**\n\n"
                f"**File :** `{raw_name}`\n"
                f"**Size :** `{_humanbytes(getattr(media, 'file_size', 0))}`\n\n"
                f"🔗 [View Full Report]({page_url})",
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
# ffprobe parser  (async subprocess)
# ══════════════════════════════════════════════════════════════════════════════

async def _run_ffprobe(file_path: str, display_name: str, media_obj) -> str:
    """Run ffprobe and return formatted string. Always returns something."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()

        if not out:
            return f"ffprobe returned no output.\nstderr: {err.decode()[:300]}"

        data    = json.loads(out.decode())
        fmt     = data.get("format", {})
        streams = data.get("streams", [])

        lines = [
            f"📄 File     : {display_name}",
            f"💾 Size     : {_humanbytes(getattr(media_obj, 'file_size', 0))}",
            f"📦 Format   : {fmt.get('format_long_name', 'N/A')}",
        ]

        dur = float(fmt.get("duration") or 0)
        if dur:
            lines.append(f"⏱ Duration  : {_fmt_dur(int(dur * 1000))}")

        br = fmt.get("bit_rate")
        if br:
            lines.append(f"📶 Bitrate   : {_fmt_br(br)}")

        lines.append("")

        for s in streams:
            ctype = s.get("codec_type", "?").upper()
            lines.append(f"━━ {ctype} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"  Codec       : {s.get('codec_name', '?')} ({s.get('codec_long_name', '')})")
            if ctype == "VIDEO":
                lines.append(f"  Resolution  : {s.get('width', '?')} × {s.get('height', '?')}")
                lines.append(f"  FPS         : {s.get('r_frame_rate', '?')}")
                if s.get("bit_rate"):
                    lines.append(f"  Bitrate     : {_fmt_br(s['bit_rate'])}")
                if s.get("pix_fmt"):
                    lines.append(f"  Pixel Fmt   : {s['pix_fmt']}")
            elif ctype == "AUDIO":
                lines.append(f"  Channels    : {s.get('channels', '?')}")
                lines.append(f"  Sample Rate : {s.get('sample_rate', '?')} Hz")
                if s.get("bit_rate"):
                    lines.append(f"  Bitrate     : {_fmt_br(s['bit_rate'])}")
                if s.get("tags", {}).get("language"):
                    lines.append(f"  Language    : {s['tags']['language']}")
            elif ctype == "SUBTITLE":
                if s.get("tags", {}).get("language"):
                    lines.append(f"  Language    : {s['tags']['language']}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"ffprobe error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# pymediainfo parser  (sync — run in thread pool)
# ══════════════════════════════════════════════════════════════════════════════

def _run_pymediainfo(file_path: str, display_name: str, media_obj) -> str:
    """Return formatted pymediainfo output, or empty string if not available."""
    try:
        from pymediainfo import MediaInfo
        info  = MediaInfo.parse(file_path)
        lines = [
            f"📄 File     : {display_name}",
            f"💾 Size     : {_humanbytes(getattr(media_obj, 'file_size', 0))}",
            "",
        ]
        for track in info.tracks:
            t = track.track_type
            if t == "General":
                lines.append("━━ General ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                if track.duration:
                    lines.append(f"  Duration    : {_fmt_dur(int(float(track.duration)))}")
                if track.format:
                    lines.append(f"  Format      : {track.format}")
                if track.overall_bit_rate:
                    lines.append(f"  Bitrate     : {_fmt_br(track.overall_bit_rate)}")
            elif t == "Video":
                lines.append("━━ Video ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                if track.format:
                    lines.append(f"  Codec       : {track.format}")
                if track.codec_id:
                    lines.append(f"  Codec ID    : {track.codec_id}")
                if track.width and track.height:
                    lines.append(f"  Resolution  : {track.width} × {track.height}")
                if track.frame_rate:
                    lines.append(f"  FPS         : {track.frame_rate}")
                if track.bit_rate:
                    lines.append(f"  Bitrate     : {_fmt_br(track.bit_rate)}")
                if track.bit_depth:
                    lines.append(f"  Bit Depth   : {track.bit_depth}-bit")
                if track.color_space:
                    lines.append(f"  Color Space : {track.color_space}")
                if track.chroma_subsampling:
                    lines.append(f"  Chroma      : {track.chroma_subsampling}")
            elif t == "Audio":
                lines.append("━━ Audio ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                if track.format:
                    lines.append(f"  Codec       : {track.format}")
                if track.channel_s:
                    lines.append(f"  Channels    : {track.channel_s}")
                if track.sampling_rate:
                    lines.append(f"  Sample Rate : {track.sampling_rate} Hz")
                if track.bit_rate:
                    lines.append(f"  Bitrate     : {_fmt_br(track.bit_rate)}")
                if track.language:
                    lines.append(f"  Language    : {track.language}")
                if track.title:
                    lines.append(f"  Title       : {track.title}")
            elif t == "Text":
                lines.append("━━ Subtitle ━━━━━━━━━━━━━━━━━━━━━━━━━━")
                if track.format:
                    lines.append(f"  Format      : {track.format}")
                if track.language:
                    lines.append(f"  Language    : {track.language}")
            lines.append("")
        return "\n".join(lines).strip()
    except ImportError:
        return ""   # pymediainfo not installed — caller uses ffprobe output
    except Exception as e:
        log.warning(Msg.MI_PYMEDIA_ERR, error=e)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# Telegraph uploader
# ══════════════════════════════════════════════════════════════════════════════

async def _upload_to_telegraph(title: str, content: str) -> str | None:
    global _telegraph_token

    nodes = []
    for line in content.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("━━"):
            nodes.append({"tag": "h4", "children": [s]})
        elif ":" in s:
            key, _, val = s.partition(":")
            nodes.append({
                "tag": "p",
                "children": [{"tag": "b", "children": [key.strip() + ": "]}, val.strip()],
            })
        else:
            nodes.append({"tag": "p", "children": [s]})

    if not nodes:
        nodes = [{"tag": "p", "children": [content[:4096]]}]

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            # Create account once
            if not _telegraph_token:
                async with session.post(
                    "https://api.telegra.ph/createAccount",
                    json={"short_name": "MediaInfoBot", "author_name": "MediaInfo"},
                ) as r:
                    d = await r.json()
                    if d.get("ok"):
                        _telegraph_token = d["result"]["access_token"]

            if not _telegraph_token:
                return None

            async with session.post(
                "https://api.telegra.ph/createPage",
                json={
                    "access_token": _telegraph_token,
                    "title": (title or "MediaInfo")[:256],
                    "author_name": "MediaInfo Bot",
                    "content": nodes,
                    "return_content": False,
                },
            ) as r:
                result = await r.json()
                if result.get("ok"):
                    return f"https://telegra.ph{result['result']['path']}"

    except Exception as e:
        log.warning(Msg.MI_TELEGRAPH_ERR, error=e)

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
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
