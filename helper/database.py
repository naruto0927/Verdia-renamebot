import motor.motor_asyncio
from config import Config
from .utils import send_log
from messages import log, Msg


class Database:

    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.jishubotz = self._client[database_name]
        self.col = self.jishubotz.user
        self.bannedList = self.jishubotz.bannedList

    # ─────────────────────── schema ────────────────────────────────────────

    def new_user(self, id):
        return dict(
            _id=int(id),
            file_id=None,
            caption=None,
            prefix=None,
            suffix=None,
            metadata=False,
            metadata_code="By :- @Suh0_Kang",
            metadata_fields={
                "title":    "",
                "author":   "",
                "artist":   "",
                "audio":    "",
                "video":    "",
                "subtitle": "",
            },
            dump_channel=None,
            sample_video=False,
            screenshot=False,
            dump_mode=False,
        )

    # ─────────────────────── user management ───────────────────────────────

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            await self.col.insert_one(user)
            await send_log(b, u)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return bool(user)

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'_id': int(user_id)})

    # ─────────────────────── thumbnail ─────────────────────────────────────

    async def set_thumbnail(self, id, file_id):
        await self.col.update_one({'_id': int(id)}, {'$set': {'file_id': file_id}})

    async def get_thumbnail(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('file_id', None) if user else None

    # ─────────────────────── caption ───────────────────────────────────────

    async def set_caption(self, id, caption):
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}})

    async def get_caption(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption', None) if user else None

    # ─────────────────────── prefix ────────────────────────────────────────

    async def set_prefix(self, id, prefix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'prefix': prefix}})

    async def get_prefix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('prefix', None) if user else None

    # ─────────────────────── suffix ────────────────────────────────────────

    async def set_suffix(self, id, suffix):
        await self.col.update_one({'_id': int(id)}, {'$set': {'suffix': suffix}})

    async def get_suffix(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('suffix', None) if user else None

    # ─────────────────────── metadata toggle ───────────────────────────────

    async def set_metadata(self, id, bool_meta):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata': bool_meta}})

    async def get_metadata(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('metadata', False) if user else False

    # ─────────────────────── legacy metadata_code ──────────────────────────

    async def set_metadata_code(self, id, metadata_code):
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_code': metadata_code}})

    async def get_metadata_code(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('metadata_code', '') if user else ''

    # ─────────────────────── per-field metadata ────────────────────────────

    async def set_metadata_field(self, id: int, field: str, value: str):
        await self.col.update_one(
            {'_id': int(id)},
            {'$set': {f'metadata_fields.{field}': value}},
            upsert=True,
        )

    async def get_metadata_fields(self, id: int) -> dict:
        user = await self.col.find_one({'_id': int(id)})
        if not user:
            return {}
        fields = user.get('metadata_fields', {})
        defaults = {"title": "", "author": "", "artist": "",
                    "audio": "", "video": "", "subtitle": ""}
        return {**defaults, **fields}

    async def get_metadata_field(self, id: int, field: str) -> str:
        fields = await self.get_metadata_fields(id)
        return fields.get(field, "")

    # ─────────────────────── ban management ────────────────────────────────

    async def ban_user(self, user_id):
        user = await self.bannedList.find_one({'banId': int(user_id)})
        if user:
            return False
        await self.bannedList.insert_one({'banId': int(user_id)})
        return True

    async def is_banned(self, user_id):
        user = await self.bannedList.find_one({'banId': int(user_id)})
        return bool(user)

    async def is_unbanned(self, user_id):
        try:
            if await self.bannedList.find_one({'banId': int(user_id)}):
                await self.bannedList.delete_one({'banId': int(user_id)})
                return True
            return False
        except Exception as e:
            log.error(Msg.DB_UNBAN_ERR, user_id=user_id, error=e)
            return False

    # ═══════════════════════════════════════════════════════════════════════
    #  USER SETTINGS
    # ═══════════════════════════════════════════════════════════════════════

    async def _ensure_settings_fields(self, id: int):
        await self.col.update_one(
            {'_id': int(id)},
            {'$setOnInsert': {
                'dump_channel': None,
                'sample_video': False,
                'screenshot':   False,
                'dump_mode':    False,
            }},
            upsert=True,
        )

    async def set_dump_channel(self, id: int, channel_id: int | None):
        await self.col.update_one(
            {'_id': int(id)},
            {'$set': {'dump_channel': channel_id}},
            upsert=True,
        )

    async def get_dump_channel(self, id: int) -> int | None:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('dump_channel', None) if user else None

    async def set_sample_video(self, id: int, value: bool):
        await self.col.update_one(
            {'_id': int(id)},
            {'$set': {'sample_video': value}},
            upsert=True,
        )

    async def get_sample_video(self, id: int) -> bool:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('sample_video', False) if user else False

    async def set_screenshot(self, id: int, value: bool):
        await self.col.update_one(
            {'_id': int(id)},
            {'$set': {'screenshot': value}},
            upsert=True,
        )

    async def get_screenshot(self, id: int) -> bool:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('screenshot', False) if user else False

    async def set_dump_mode(self, id: int, value: bool):
        await self.col.update_one(
            {'_id': int(id)},
            {'$set': {'dump_mode': value}},
            upsert=True,
        )

    async def get_dump_mode(self, id: int) -> bool:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('dump_mode', False) if user else False

    async def get_user_settings(self, id: int) -> dict:
        user = await self.col.find_one({'_id': int(id)})
        if not user:
            return {
                'dump_channel': None,
                'sample_video': False,
                'screenshot':   False,
                'dump_mode':    False,
            }
        return {
            'dump_channel': user.get('dump_channel', None),
            'sample_video': user.get('sample_video', False),
            'screenshot':   user.get('screenshot',   False),
            'dump_mode':    user.get('dump_mode',     False),
        }


# Module-level singleton
jishubotz = Database(Config.DB_URL, Config.DB_NAME)
