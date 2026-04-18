"""
helper/ask.py
─────────────
Native Pyrogram v2 replacement for pyromod's client.ask().

Drop-in usage:
    from helper.ask import ask
    import asyncio

    try:
        response = await ask(client, chat_id, "Send me your text:", timeout=30)
        user_input = response.text
    except asyncio.TimeoutError:
        await client.send_message(chat_id, "⏰ Timed out. Please try again.")

asyncio.TimeoutError replaces pyromod's ListenerTimeout.
"""

import asyncio

from pyrogram import Client
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message


async def ask(
    client: Client,
    chat_id: int,
    text: str,
    timeout: int = 30,
    filters=None,
    **send_kwargs,
) -> Message:
    """
    Send a prompt message to chat_id and wait for the user's reply.

    Parameters
    ----------
    client        Pyrogram Client instance.
    chat_id       The chat / user ID to prompt and listen to.
    text          The prompt text to send.
    timeout       Seconds to wait for a reply (default 30).
    filters       Optional Pyrogram filter (e.g. pyrogram.filters.text).
                  Only messages passing this filter are accepted.
    **send_kwargs Extra kwargs passed to client.send_message()
                  (e.g. disable_web_page_preview=True).

    Returns
    -------
    pyrogram.types.Message — the first matching reply received.

    Raises
    ------
    asyncio.TimeoutError — if no reply arrives within timeout seconds.
    """

    # send_message does not accept these — silently drop them
    send_kwargs.pop("reply_to_message_id", None)

    # Send the prompt first
    await client.send_message(chat_id, text, **send_kwargs)

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()

    async def _on_message(_, message: Message) -> None:
        # Only accept messages from the correct chat
        if message.chat.id != chat_id:
            return
        # Apply optional Pyrogram filter
        if filters is not None:
            if not await filters(client, message):
                return
        # Resolve the future only once
        if not future.done():
            future.set_result(message)

    handler = MessageHandler(_on_message)
    # group=-1 gives this handler high priority so it fires before regular handlers
    client.add_handler(handler, group=-1)

    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except asyncio.TimeoutError:
        if not future.done():
            future.cancel()
        raise
    finally:
        try:
            client.remove_handler(handler, group=-1)
        except Exception:
            pass
