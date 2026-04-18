"""
helper/ffmpeg.py
─────────────────
FFmpeg/FFprobe helpers.
All print() calls replaced with messages.log.
"""

import asyncio
import json
import os
import random
import time

from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from messages import log, Msg


# ══════════════════════════════════════════════════════════════════════════════
# fix_thumb  (original logic — untouched)
# ══════════════════════════════════════════════════════════════════════════════

async def fix_thumb(thumb: str):
    """
    Ensure *thumb* is a valid Baseline JPEG Pyrogram can attach.
    Returns (width, height, path) — path is None if anything fails.
    """
    width = height = 0
    if not thumb:
        return width, height, None

    try:
        parser = createParser(thumb)
        if parser:
            meta = extractMetadata(parser)
            if meta:
                if meta.has("width"):
                    width = meta.get("width")
                if meta.has("height"):
                    height = meta.get("height")
            parser.stream._input.close()

        img = Image.open(thumb).convert("RGB")
        if width and height:
            img = img.resize((width, height), Image.LANCZOS)
        else:
            width, height = img.size
        img.save(thumb, "JPEG", subsampling=0, quality=95)

    except Exception as e:
        log.error(Msg.THUMB_FIX_ERR, error=e)
        return 0, 0, None

    return width, height, thumb


# ══════════════════════════════════════════════════════════════════════════════
# take_screen_shot  (original logic — untouched)
# ══════════════════════════════════════════════════════════════════════════════

async def take_screen_shot(video_file: str, output_directory: str, ttl: int):
    """Extract a single frame from *video_file* at *ttl* seconds."""
    out_file = os.path.join(output_directory, f"{time.time()}.jpg")
    cmd = [
        "ffmpeg", "-ss", str(ttl),
        "-i", video_file,
        "-vframes", "1",
        out_file,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    return out_file if os.path.lexists(out_file) else None


# ══════════════════════════════════════════════════════════════════════════════
# add_metadata  (original logic — untouched)
# ══════════════════════════════════════════════════════════════════════════════

async def add_metadata(input_path: str, output_path: str, metadata_fields: dict, ms):
    """Embed per-field metadata into *input_path* and write to *output_path*."""
    try:
        await ms.edit("<i>Adding metadata to your file... ⚡</i>")

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-map", "0",
            "-c:s", "copy",
            "-c:a", "copy",
            "-c:v", "copy",
        ]

        for key in ("title", "author", "artist"):
            val = (metadata_fields.get(key) or "").strip()
            if val:
                cmd += ["-metadata", f"{key}={val}"]

        audio_val    = (metadata_fields.get("audio")    or "").strip()
        video_val    = (metadata_fields.get("video")    or "").strip()
        subtitle_val = (metadata_fields.get("subtitle") or "").strip()

        if audio_val:
            cmd += ["-metadata:s:a", f"title={audio_val}"]
        if video_val:
            cmd += ["-metadata:s:v", f"title={video_val}"]
        if subtitle_val:
            cmd += ["-metadata:s:s", f"title={subtitle_val}"]

        cmd.append(output_path)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Log ffmpeg output at DEBUG level (not printed to console)
        if stderr.decode().strip():
            log.debug(Msg.META_FFMPEG_STDERR, stderr=stderr.decode().strip())
        if stdout.decode().strip():
            log.debug(Msg.META_FFMPEG_STDOUT, stdout=stdout.decode().strip())

        if os.path.exists(output_path):
            await ms.edit("<i>Metadata added successfully ✅</i>")
            return output_path
        else:
            await ms.edit("<i>Could not add metadata ❌</i>")
            return None

    except Exception as e:
        log.error(Msg.META_ERROR, error=e)
        await ms.edit("<i>Metadata injection failed ❌</i>")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# get_video_duration
# ══════════════════════════════════════════════════════════════════════════════

async def get_video_duration(file_path: str) -> float:
    """Return duration in seconds using ffprobe JSON output. Returns 0.0 on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        data = json.loads(out.decode())
        return float(data["format"]["duration"])
    except Exception as e:
        log.warning(Msg.FFPROBE_DUR_ERR, error=e)
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# generate_sample_video
# ══════════════════════════════════════════════════════════════════════════════

async def generate_sample_video(
    input_path: str,
    output_directory: str,
    duration: int = 30,
) -> str | None:
    """
    Cut a *duration*-second clip from a random position.
    Tries stream copy first; falls back to libx264/aac re-encode if that fails.
    """
    total = await get_video_duration(input_path)

    if total <= 0:
        start = 0.0
    elif total <= duration:
        start = 0.0
    else:
        lo    = total * 0.10
        hi    = max(total * 0.70, lo + 1.0)
        start = random.uniform(lo, hi)
        start = min(start, total - duration - 0.5)

    out_file = os.path.join(output_directory, f"sample_{int(time.time())}.mp4")

    # Try stream copy (fast, no re-encode)
    cmd_copy = [
        "ffmpeg", "-y",
        "-ss", f"{start:.2f}",
        "-i", input_path,
        "-t", str(duration),
        "-map", "0",
        "-c", "copy",
        "-avoid_negative_ts", "1",
        out_file,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd_copy,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 0:
        return out_file

    # Fallback: re-encode
    log.warning(Msg.SAMPLE_COPY_FAIL, stderr=stderr.decode()[-200:])

    if os.path.exists(out_file):
        os.remove(out_file)

    cmd_encode = [
        "ffmpeg", "-y",
        "-ss", f"{start:.2f}",
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "ultrafast",
        "-crf", "28",
        out_file,
    ]
    proc2 = await asyncio.create_subprocess_exec(
        *cmd_encode,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr2 = await proc2.communicate()

    if proc2.returncode != 0:
        log.error(Msg.SAMPLE_ENCODE_FAIL, stderr=stderr2.decode()[-200:])
        return None

    return out_file if os.path.exists(out_file) and os.path.getsize(out_file) > 0 else None


# ══════════════════════════════════════════════════════════════════════════════
# take_multi_screenshots
# ══════════════════════════════════════════════════════════════════════════════

async def take_multi_screenshots(
    video_file: str,
    output_directory: str,
    count: int = 6,
) -> list[str]:
    """Extract *count* evenly-spaced frames in parallel. Returns valid paths."""
    duration = await get_video_duration(video_file)

    if duration <= 0:
        result = await take_screen_shot(video_file, output_directory, 0)
        return [result] if result else []

    margin     = duration * 0.05
    span       = duration - 2 * margin
    step       = span / max(count - 1, 1)
    timestamps = [margin + i * step for i in range(count)]

    async def _one_shot(ts: float) -> str | None:
        out = os.path.join(
            output_directory,
            f"ss_{int(time.time() * 1000)}_{ts:.0f}.jpg",
        )
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-ss", f"{ts:.2f}",
            "-i", video_file,
            "-vframes", "1",
            "-q:v", "2",
            out,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return out if os.path.exists(out) and os.path.getsize(out) > 0 else None

    results = await asyncio.gather(*[_one_shot(ts) for ts in timestamps])
    return [r for r in results if r]


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @JishuBotz & @Madflix_Bots
# Developer @JishuDeveloper
