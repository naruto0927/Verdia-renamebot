"""
messages.py
────────────
Centralized logging + message string registry for the Rename Bot.

USAGE
─────
  from messages import log, Msg

  log.info(Msg.BOT_STARTED, name="MyBot")
  log.error(Msg.DUMP_FAILED_LOG, user_id=123, channel_id=-100xxx, error=e)
  log.warning(Msg.SAMPLE_COPY_FAIL, stderr="...")
  log.debug(Msg.META_FFMPEG_STDERR, stderr="...")

  # Plain string for Telegram reply text
  await message.reply_text(Msg.US_CANCELLED)
"""

import logging
import sys


# ══════════════════════════════════════════════════════════════════════════════
# Logger setup
# ══════════════════════════════════════════════════════════════════════════════

def _build_logger(name: str = "renamer") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File — DEBUG and above (skipped on read-only filesystems like Heroku)
    try:
        fh = logging.FileHandler("bot.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass

    return logger


class _SmartLogger:
    """
    Wrapper around stdlib Logger.
    Accepts a template string + keyword args:

        log.info("Hello {name}", name="world")

    Missing keys are left as-is — never raises KeyError.
    """

    def __init__(self, logger: logging.Logger):
        self._log = logger

    @staticmethod
    def _fmt(template: str, kwargs: dict) -> str:
        if not kwargs:
            return template
        try:
            return template.format_map(kwargs)
        except Exception:
            return template

    def debug(self, template: str, **kwargs) -> None:
        self._log.debug(self._fmt(template, kwargs))

    def info(self, template: str, **kwargs) -> None:
        self._log.info(self._fmt(template, kwargs))

    def warning(self, template: str, **kwargs) -> None:
        self._log.warning(self._fmt(template, kwargs))

    # alias so both spellings work
    warn = warning

    def error(self, template: str, **kwargs) -> None:
        self._log.error(self._fmt(template, kwargs))

    def exception(self, template: str, **kwargs) -> None:
        self._log.exception(self._fmt(template, kwargs))

    def critical(self, template: str, **kwargs) -> None:
        self._log.critical(self._fmt(template, kwargs))


# Module-level singleton — import this everywhere
log: _SmartLogger = _SmartLogger(_build_logger("renamer"))


# ══════════════════════════════════════════════════════════════════════════════
# Message strings
# ══════════════════════════════════════════════════════════════════════════════

class Msg:
    """
    All human-readable strings in one place.

    Groups
    ──────
      BOT_*       bot lifecycle
      US_*        /us settings panel
      ADMIN_*     admin/channel validation
      DUMP_*      dump channel feature
      RENAME_*    rename pipeline
      THUMB_*     thumbnail system
      META_*      metadata injection
      SAMPLE_*    sample video generation
      SS_*        screenshot generation
      MI_*        /mi mediainfo command
      FFPROBE_*   ffprobe helpers
      DB_*        database errors
    """

    # ── Bot lifecycle ─────────────────────────────────────────────────────────
    BOT_STARTED          = "Bot {name} started successfully ✅"
    BOT_STOPPED          = "Bot {mention} stopped."
    BOT_ADMIN_NOTIFY_ERR = "Failed to notify admin {admin_id}: {error}"
    BOT_LOG_CHANNEL_ERR  = "Failed to send startup message to LOG_CHANNEL: {error}"

    # ── /us settings panel — internal logs ────────────────────────────────────
    US_PHOTO_FAIL        = "[us] Failed to send settings photo: {error}"
    US_REFRESH_ERR       = "[us] Failed to refresh inline keyboard: {error}"

    # ── /us settings panel — user-facing replies ──────────────────────────────
    US_CAPTION                  = "Hey {mention}\nHere You Can Change Or Configure Your Settings"
    US_SET_DUMP_PROMPT          = (
        "**🎯 Set Dump Channel**\n\n"
        "Please do one of the following:\n"
        "• **Forward any message** from your dump channel\n"
        "• **Send the channel ID** (must start with `-100`)\n\n"
        "Make sure the bot is already an **admin** with Post Messages permission.\n\n"
        "Send /cancel to abort."
    )
    US_CANCELLED                = "❌ Cancelled."
    US_INVALID_CHANNEL_RESOLVE  = (
        "❌ Could not resolve that channel.\n"
        "Forward a message from it, or send its numeric ID (e.g. `-1001234567890`)."
    )
    US_NO_CHANNEL_ID            = "❌ No channel ID found. Try again or send /cancel."
    US_BAD_CHANNEL_PREFIX       = (
        "❌ That doesn't look like a valid channel ID.\n"
        "Channel IDs must start with `-100` (e.g. `-1001234567890`)."
    )
    US_DUMP_SAVED               = "✅ **Dump channel saved:** `{channel_id}`\n\nOpen /dump to enable Dump Mode."
    US_DUMP_MODE_NEEDS_CHANNEL  = "⚠️ Set a Dump Channel first before enabling Dump Mode."

    # ── Admin / channel validation ─────────────────────────────────────────────
    ADMIN_NOT_ADMIN      = (
        "❌ The bot is **not an admin** in that channel.\n"
        "Add it as admin and grant **Post Messages** permission."
    )
    ADMIN_NO_POST        = (
        "❌ The bot is admin but lacks **Post Messages** permission.\n"
        "Enable it in the channel admin settings."
    )
    ADMIN_REQUIRED       = "❌ Bot needs admin rights in that channel."
    ADMIN_INVALID_CHAN   = "❌ Invalid channel. Make sure the bot is already a member/admin."
    ADMIN_NOT_MEMBER     = "❌ The bot is not a member of that channel."
    ADMIN_UNEXPECTED     = "❌ Unexpected error while checking admin status: `{error}`"
    ADMIN_CHECK_ERR      = "❌ Cannot use this channel.\n\n{reason}"

    # ── Dump feature ──────────────────────────────────────────────────────────
    DUMP_SUCCESS         = "[dump] user={user_id} → channel={channel_id} ✅"
    DUMP_FAILED_LOG      = "[dump] user={user_id} → channel={channel_id} FAILED: {error}"
    DUMP_FAILED_USER     = (
        "⚠️ **Dump Failed**\n\n"
        "Could not send to dump channel `{channel_id}`.\n"
        "Error: `{error}`\n\n"
        "Make sure the bot is still admin with Post permission."
    )

    # ── Rename pipeline ───────────────────────────────────────────────────────
    RENAME_START_ERR     = "[rename_start] {error}"
    RENAME_EDIT_MSG_ERR  = "[rename] Failed to edit status message: {error}"
    RENAME_THUMB_ERR     = "[rename] Thumbnail error: {error}"

    # ── Metadata ──────────────────────────────────────────────────────────────
    META_FFMPEG_STDERR   = "[add_metadata] ffmpeg stderr: {stderr}"
    META_FFMPEG_STDOUT   = "[add_metadata] ffmpeg stdout: {stdout}"
    META_ERROR           = "[add_metadata] {error}"

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    THUMB_FIX_ERR        = "[fix_thumb] {error}"

    # ── Sample video ──────────────────────────────────────────────────────────
    SAMPLE_COPY_FAIL     = "[sample_video] stream copy failed, re-encoding. stderr: {stderr}"
    SAMPLE_ENCODE_FAIL   = "[sample_video] re-encode also failed: {stderr}"
    SAMPLE_SEND_ERR      = "[sample_video] send error: {error}"

    # ── Screenshots ───────────────────────────────────────────────────────────
    SS_ERROR             = "[screenshots] {error}"

    # ── MediaInfo ─────────────────────────────────────────────────────────────
    MI_ERROR             = "[mediainfo] {error}"
    MI_PYMEDIA_ERR       = "[pymediainfo] {error}"
    MI_TELEGRAPH_ERR     = "[telegraph] {error}"

    # ── ffprobe ───────────────────────────────────────────────────────────────
    FFPROBE_DUR_ERR      = "[get_video_duration] {error}"

    # ── Database ──────────────────────────────────────────────────────────────
    DB_UNBAN_ERR         = "Failed to unban user {user_id}: {error}"
