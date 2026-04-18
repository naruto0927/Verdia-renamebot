import os
from datetime import datetime
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
from messages import log, Msg
import pyrogram.utils

pyrogram.utils.MIN_CHAT_ID = -999999999999
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999


class Bot(Client):

    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username
        self.uptime = Config.BOT_UPTIME
        if Config.WEBHOOK:
            app = web.AppRunner(await web_server())
            await app.setup()
            PORT = int(os.environ.get("PORT", 8000))
            await web.TCPSite(app, "0.0.0.0", PORT).start()

        log.info(Msg.BOT_STARTED, name=me.first_name)

        for admin_id in Config.ADMIN:
            try:
                await self.send_message(
                    admin_id,
                    f"**{me.first_name} is online and ready.**"
                )
            except Exception as e:
                log.warning(Msg.BOT_ADMIN_NOTIFY_ERR, admin_id=admin_id, error=e)

        if Config.LOG_CHANNEL:
            try:
                curr = datetime.now(timezone("Asia/Kolkata"))
                date = curr.strftime('%d %B, %Y')
                time_str = curr.strftime('%I:%M:%S %p')
                await self.send_message(
                    Config.LOG_CHANNEL,
                    f"**{me.mention} started.**\n\n"
                    f"📅 Date : `{date}`\n⏰ Time : `{time_str}`\n"
                    f"🌐 Timezone : `Asia/Kolkata`\n\n"
                    f"🉐 Version : `v{__version__} (Layer {layer})`"
                )
            except Exception as e:
                log.warning(Msg.BOT_LOG_CHANNEL_ERR, error=e)

    async def stop(self):
        await super().stop()
        log.info(Msg.BOT_STOPPED, mention=self.mention)


Bot().run()
