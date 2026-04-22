import math, time, re, os
from datetime import datetime
from pytz import timezone
from config import Config, Txt 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# Per-message last-edit timestamp — throttle edits to max 1 per 8 seconds
# per message to prevent Telegram flood-waits from stalling the event loop.
_progress_last_edit: dict = {}

async def progress_for_pyrogram(current, total, ud_type, message, start):
    now  = time.time()
    diff = now - start
    if diff < 1:
        return  # too early — skip

    # Throttle: only update if 8 seconds have passed since last edit for this msg
    # or if transfer is complete.  This prevents FloodWait errors that cause ALL
    # concurrent tasks to stall while waiting for Telegram's rate-limit cooldown.
    msg_key = getattr(message, "id", id(message))
    last    = _progress_last_edit.get(msg_key, 0)
    if current != total and (now - last) < 8:
        return
    _progress_last_edit[msg_key] = now

    try:
        percentage = current * 100 / total
        speed      = current / diff if diff > 0 else 0

        elapsed_time          = round(diff) * 1000
        time_to_completion    = round((total - current) / speed) * 1000 if speed > 0 else 0
        estimated_total_time  = elapsed_time + time_to_completion

        elapsed_str = TimeFormatter(milliseconds=elapsed_time)
        eta_str     = TimeFormatter(milliseconds=estimated_total_time)

        progress = "{0}{1}".format(
            "".join(["▣" for _ in range(math.floor(percentage / 5))]),
            "".join(["▢" for _ in range(20 - math.floor(percentage / 5))]),
        )
        tmp = progress + Txt.PROGRESS_BAR.format(
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),
            eta_str if eta_str != "" else "0 s",
        )
        await message.edit(
            text=f"{ud_type}\n\n{tmp}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖️ 𝖢𝖺𝗇𝖼𝖾𝗅 ✖️", callback_data="close")]]
            ),
        )
    except Exception:
        pass
    finally:
        # Clean up finished entries to prevent unbounded growth
        if current == total:
            _progress_last_edit.pop(msg_key, None)

def humanbytes(size):    
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2] 

def convert(seconds):
    seconds = seconds % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60      
    return "%d:%02d:%02d" % (hour, minutes, seconds)

async def send_log(b, u):
    if Config.LOG_CHANNEL is not None:
        curr = datetime.now(timezone("Asia/Kolkata"))
        date = curr.strftime('%d %B, %Y')
        time = curr.strftime('%I:%M:%S %p')
        await b.send_message(
            Config.LOG_CHANNEL,
            f"""<b><u>🌿 A New Soul Has Entered the Garden</u></b>

<b>✨ Name</b> : {u.mention}  
<b>🆔 User ID</b> : <code>{u.id}</code>  
<b>🪷 First Name</b> : {u.first_name}  
<b>🖋️ Last Name</b> : {u.last_name}  
<b>🧿 Username</b> : @{u.username}  
<b>🔗 Direct Link</b> : <a href='tg://openmessage?user_id={u.id}'>Open Chat</a>

<b>📅 Date</b> : {date}  
<b>⏰ Time</b> : {time}
"""
        )
        



def add_prefix_suffix(input_string: str, prefix: str = '', suffix: str = '') -> str:
    """
    Apply optional prefix/suffix to a filename while preserving the extension
    and ALL special characters in the original name (brackets, spaces, @, etc.).

    Rules
    ─────
    • None / empty string  →  treated as "no prefix/suffix"
    • prefix is prepended directly to the name stem (no extra space)
    • suffix is appended after the stem with a single space, before the extension
    • The extension (last dot-segment) is always kept intact

    Examples
    ────────
      "[S01-01] Show [480p] @Chan.mkv", None, None  →  "[S01-01] Show [480p] @Chan.mkv"
      "[S01-01] Show.mkv", "@Ch", None              →  "@Ch[S01-01] Show.mkv"
      "[S01-01] Show.mkv", None, "@Ch"              →  "[S01-01] Show @Ch.mkv"
      "[S01-01] Show.mkv", "@A",  "@B"              →  "@A[S01-01] Show @B.mkv"

    The function NEVER strips, replaces, or mangles any character that the
    user typed — it only attaches the optional prefix/suffix bookends.
    """
    # Normalise: empty / whitespace-only → None
    prefix = (prefix or "").strip() or None
    suffix = (suffix or "").strip() or None

    if not prefix and not suffix:
        return input_string

    # Split off the last extension only — rsplit keeps everything else intact
    if "." in input_string:
        stem, ext = input_string.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = input_string, ""

    result = stem
    if prefix:
        result = prefix + result
    if suffix:
        result = result + " " + suffix

    return result + ext

def makedir(name: str):
    """
    Create a directory with the specified name.
    If a directory with the same name already exists, it will be removed and a new one will be created.
    """

    if os.path.exists(name):
        shutil.rmtree(name)
    os.mkdir(name)




# Jishu Developer 
# Don't Remove Credit 🥺
# Telegram Channel @JishuBotz
# Developer @JishuDeveloper
