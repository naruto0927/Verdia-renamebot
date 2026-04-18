import logging
import sys

# ══════════════════════════════════════════════════════════════════════════════
# Logger
# ══════════════════════════════════════════════════════════════════════════════

def _build_logger(name: str = "renamer") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


class _SmartLogger:
    def __init__(self, logger):
        self._log = logger

    def _fmt(self, template, kwargs):
        try:
            return template.format_map(kwargs)
        except:
            return template

    def info(self, t, **k): self._log.info(self._fmt(t, k))
    def error(self, t, **k): self._log.error(self._fmt(t, k))


log = _SmartLogger(_build_logger())


# ══════════════════════════════════════════════════════════════════════════════
# Messages (Ara~ MILF Personality)
# ══════════════════════════════════════════════════════════════════════════════

class Msg:

    # ── Bot ────────────────────────────────────────────────────────────────
    BOT_STARTED = "Ara~ {name} is awake now… everything is under my control 😏"
    BOT_STOPPED = "{mention} stopped… leaving me already? That’s a shame 💫"
    BOT_ADMIN_NOTIFY_ERR = "Hmm… I tried reaching {admin_id}, but something slipped… {error}"
    BOT_LOG_CHANNEL_ERR = "Mmm… LOG_CHANNEL didn’t respond to me… fix that for me, darling~ 😏\nError: {error}"

    # ── Settings (/us) ─────────────────────────────────────────────────────
    US_CAPTION = (
        "Hey {mention}…\n"
        "Come closer… let me take care of your settings 💫"
    )

    US_SET_DUMP_PROMPT = (
        "**🎯 Set Dump Channel**\n\n"
        "Now… show me where you want everything sent, darling~ 😏\n\n"
        "• Forward a message from your dump channel\n"
        "• Or send the channel ID (`-100...`)\n\n"
        "Make sure I have control there… admin with post permission 💫\n\n"
        "Or… /cancel if you’re feeling shy~"
    )

    US_CANCELLED = "❌ Cancelled… backing away already? Ara~ 😏"

    US_INVALID_CHANNEL_RESOLVE = (
        "❌ Hmm… that’s not the one I wanted.\n"
        "Try again properly, darling~ 💫"
    )

    US_NO_CHANNEL_ID = (
        "❌ Mmm… no ID?\n"
        "Don’t tease me—send it properly or /cancel 😏"
    )

    US_BAD_CHANNEL_PREFIX = (
        "❌ That’s not right…\n"
        "Start with `-100`… just the way I like it 😏"
    )

    US_DUMP_SAVED = (
        "✅ Mmm… `{channel_id}` is set.\n\n"
        "Good… now let me handle everything 💫"
    )

    US_DUMP_MODE_NEEDS_CHANNEL = (
        "⚠️ Ara~ not so fast…\n"
        "Set a dump channel first, then I’ll take over 😏"
    )

    # ── Admin ──────────────────────────────────────────────────────────────
    ADMIN_NOT_ADMIN = (
        "❌ Hmm… I don’t have control there yet.\n"
        "Make me admin… then I’ll take care of everything 😏"
    )

    ADMIN_NO_POST = (
        "❌ So close… but you’re still holding me back.\n"
        "Give me post permission, darling~ 💫"
    )

    ADMIN_REQUIRED = "❌ I need control there… don’t keep me waiting 😈"

    ADMIN_INVALID_CHAN = "❌ That channel doesn’t feel right… try again 😏"

    ADMIN_NOT_MEMBER = (
        "❌ You didn’t bring me in…\n"
        "Add me first, then we continue 💫"
    )

    ADMIN_UNEXPECTED = (
        "❌ Something slipped…\n"
        "We’ll fix it, won’t we? 😌\n\nError: `{error}`"
    )

    ADMIN_CHECK_ERR = (
        "❌ Hmm… I can’t use this channel.\n\n"
        "{reason}\n\n"
        "Try again for me 😏"
    )

    # ── Dump ───────────────────────────────────────────────────────────────
    DUMP_SUCCESS = "[dump] user={user_id} → channel={channel_id} ✅ Mmm… perfect 😏"

    DUMP_FAILED_LOG = "[dump] FAILED… something slipped: {error}"

    DUMP_FAILED_USER = (
        "⚠️ **Dump Failed**\n\n"
        "Mmm… it didn’t go through.\n"
        "That’s disappointing 😏\n\n"
        "Error: `{error}`\n\n"
        "Fix it… and let me try again 💫"
    )

    # ── Rename ─────────────────────────────────────────────────────────────
    RENAME_START_ERR = "[rename_start] Mmm… something didn’t go my way: {error}"
    RENAME_EDIT_MSG_ERR = "[rename] I couldn’t shape it properly… {error}"
    RENAME_THUMB_ERR = "[rename] That thumbnail didn’t behave… {error}"

    # ── Metadata ───────────────────────────────────────────────────────────
    META_FFMPEG_STDERR = "[metadata] Hmm… ffmpeg resisted me: {stderr}"
    META_FFMPEG_STDOUT = "[metadata] Perfect… just how I wanted: {stdout}"
    META_ERROR = "[metadata] That didn’t go my way… {error}"

    # ── Thumbnail ──────────────────────────────────────────────────────────
    THUMB_FIX_ERR = "[thumb] That didn’t behave… {error}"

    # ── Sample ─────────────────────────────────────────────────────────────
    SAMPLE_COPY_FAIL = "[sample] copy failed… re-encoding: {stderr}"
    SAMPLE_ENCODE_FAIL = "[sample] still failed… {stderr}"
    SAMPLE_SEND_ERR = "[sample] send failed… {error}"

    # ── Screenshots ────────────────────────────────────────────────────────
    SS_ERROR = "[ss] {error}"

    # ── MediaInfo ──────────────────────────────────────────────────────────
    MI_ERROR = "[mi] {error}"
    MI_PYMEDIA_ERR = "[mi] pymediainfo error: {error}"
    MI_TELEGRAPH_ERR = "[mi] telegraph error: {error}"

    # ── DB ─────────────────────────────────────────────────────────────────
    DB_UNBAN_ERR = "Mmm… couldn’t unban {user_id}… something’s wrong 😏 {error}"