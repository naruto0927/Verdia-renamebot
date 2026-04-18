import os
import time
import re

id_pattern = re.compile(r'^.\d+$')


class Config:
    API_ID       = int(os.environ.get("API_ID", ""))
    API_HASH     = os.environ.get("API_HASH", "")
    BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
    DB_NAME      = os.environ.get("DB_NAME", "rename")
    DB_URL       = os.environ.get("DB_URL", "")
    BOT_UPTIME   = time.time()
    START_PIC    = os.environ.get("START_PIC", "")
    ADMIN        = [int(x) for x in os.environ.get("ADMIN", "").split()]
    FORCE_SUB    = os.environ.get("FORCE_SUB", "")
    LOG_CHANNEL  = int(os.environ.get("LOG_CHANNEL", "-1002585613766"))
    BIN_CHANNEL  = int(os.environ.get("BIN_CHANNEL", "-1002585613766"))
    WEBHOOK      = bool(os.environ.get("WEBHOOK", ""))

    # ── Settings panel ────────────────────────────────────────────────────────
    # Image shown at the top of the /us settings panel.
    # Set via env var SETTINGS_IMAGE or replace the URL below.
    SETTINGS_IMAGE = os.environ.get(
        "SETTINGS_IMAGE",
        "",   # ← replace with your preferred image URL
    )


class Txt:
    START_TXT = (
        "{},\n\n"
        "Ara~ welcome to my little den of *file pleasure*, darling...\n\n"
        "With me, you can rename files, play with their thumbnails, and even "
        "*transform* videos into files... or files into videos—mmm~ just how you like it.\n\n"
        "And guess what, sweet thing~ I also support *custom thumbnails*, "
        "*custom captions*, and even your own juicy little *prefixes* and *suffixes*. "
        "Naughty, right?\n\n"
        "<b>Note :</b> While I do love playing around... "
        "<i>renaming adult content</i> is a big no-no~! \n"
        "Try it, and you'll get a permanent spanking—err, ban.\n"
    )

    ABOUT_TXT = (
        "\n<b>\n"
        "❍ Mmm~ they call me your seductive assistant... but you can scream my name however you like, darling~<br>\n"
        "❍ Currently hosted on: Heroku—so I'm always at your service, anytime, anywhere~<br>\n"
        "❍ My delicious brain? MongoDB, storing all your dirty little secrets~<br>\n"
        "❍ Language? Python 3—smooth, flexible, and oh-so-well-trained~<br>\n"
        "❍ And my master... the one who brought me to life: "
        "<a href='https://telegram.me/naruto0927'>Naruto</a>—do thank him properly~<br><br>\n\n"
        "➻ Tap those buttons below, sweetie... and I'll whisper more naughty secrets about myself just for you~</b>\n"
    )

    HELP_TXT = (
        "\n<b>\n"
        "Mmm~ this little rename bot is your naughty assistant, here to make managing and "
        "renaming your files as effortless—and as fun—as possible~<br><br>\n\n"
        "➻ Tap on the buttons below, darling, and I'll guide you through all the ways "
        "I can please your file fantasies~\n</b>\n"
    )

    THUMBNAIL_TXT = (
        "<b>» <u>Wanna set a custom thumbnail, darling? Let me guide your hands~</u></b>\n\n"
        "➲ /start: Send me any photo, and I'll *sensually* drape it over your files as a "
        "thumbnail—automatic and oh-so-satisfying~  \n"
        "➲ /delthumb: Feeling a bit reckless? Use this to strip away your thumbnail and "
        "leave your files *bare* and vulnerable~  \n"
        "➲ /viewthumb: Can't keep your eyes off it? Peek at your current thumbnail "
        "whenever you want, sweetie~\n\n"
        "<b>Note :</b> If you don't pamper me with a custom thumbnail, I'll just use the "
        "original file's thumbnail—after all, why deny your files their natural allure?  \n"
        "But remember—no naughty surprises! Keep things respectful, or I might have to "
        "withhold my teasing touch~  \n"
    )

    CAPTION_TXT = (
        "<b>» <u>Wanna set a custom caption and tease with your media type, darling?</u></b>\n\n"
        "<b>Variables you can play with :</b>  \n"
        "Size: {filesize}  \n"
        "Duration: {duration}  \n"
        "Filename: {filename}\n\n"
        "➲ /set_caption: Whisper your naughty custom caption to me, and I'll remember it just for you~  \n"
        "➲ /see_caption: Curious what seductive words you've set? Peek at your custom caption anytime, sweetie~  \n"
        "➲ /del_caption: Want to erase your teasing message? Use this to delete your caption and leave things mysterious again~\n\n"
        "» Example to get you started: /set_caption File name: {filename}  \n"
        "Mmm~ don't be shy, let your words seduce~\n"
    )

    PREFIX = (
        "<b>» <u>Ready to spice things up with a custom prefix, darling?</u></b>\n\n"
        "➲ /set_prefix: Tell me your naughty little secret prefix, and I'll wear it proudly on your files~  \n"
        "➲ /see_prefix: Curious what seductive prefix you've chosen? Peek anytime, sweetie~  \n"
        "➲ /del_prefix: Want to go bare again? Delete your custom prefix and feel the freedom~\n\n"
        "» Example to get you started: `/set_prefix @Animes_Ocean`  \n"
        "Mmm~ I can't wait to see what you choose~\n"
    )

    SUFFIX = (
        "<b>» <u>Want to leave a teasing little mark with a custom suffix, darling?</u></b>\n\n"
        "➲ /set_suffix: Whisper your naughty custom suffix to me, and I'll stick it on your files with love~  \n"
        "➲ /see_suffix: Can't wait to see what cheeky suffix you picked? Check it anytime, sweetie~  \n"
        "➲ /del_suffix: Feeling daring? Remove your suffix and let things breathe again~\n\n"
        "» Example to start: `/set_suffix @Animes_Ocean`  \n"
        "Mmm~ I'm excited just thinking about it~\n"
    )

    PROGRESS_BAR = (
        "\n\n<b>🔗 Size :</b> {1} | {2}  \n"
        "<b>⏳️ Done :</b> {0}% — Mmm, getting closer...  \n"
        "<b>🚀 Speed :</b> {3}/s — Flying fast, just like I like it~  \n"
        "<b>⏰️ ETA :</b> {4} — Almost there, darling, patience is a virtue~\n"
    )

    DONATE_TXT = (
        "\n<blockquote>❤️\u200d🔥 Oh, you're so sweet for thinking about supporting me~</blockquote>\n\n"
        "<b><i>💞 If you like what I do and want to keep me teasing your files, "
        "feel free to donate any amount — ₹10, ₹20, ₹50, ₹100, or whatever makes your heart race~</i></b>\n\n"
        "❣️ Every little donation makes me purr and helps me become even better for you, darling~  \n\n"
        "💖 UPI ID: `Narutoprit@fam`  \n"
        "Come on, don't be shy… show me some love~  \n"
    )

    SEND_METADATA = (
        "🖼️ 𝗛𝗼𝘄 𝘁𝗼 𝘀𝗲𝘁 𝘆𝗼𝘂𝗿 𝘃𝗲𝗿𝘆 𝗼𝘄𝗻 𝗰𝘂𝘀𝘁𝗼𝗺 𝗺𝗲𝘁𝗮𝗱𝗮𝘁𝗮, darling~\n\n"
        "For example, you can tease everyone with:\n\n"
        "<code>@Animes_Ocean</code>\n\n"
        "💬 Need a little help? Just whisper to @naruto0927 anytime~\n"
    )
