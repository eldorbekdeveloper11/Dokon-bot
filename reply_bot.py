import asyncio
import json
import os
from telegram import Bot

TOKEN = os.environ["BOT_TOKEN"]
SITE_URL = "https://eldorbekdeveloper11.github.io/mini-dokon/"
STATE_FILE = "groups.json"

AUTO_REPLY = (
    "REKLAMA YUKLAMOQCHI BO'LSANGIZ @ELDORBEK_231 GA MUROJAT QILING\n"
    "YOKI +998958565307 GA SMS YOZING\n\n"
    "MAQSAD: O'RGANISH VA PUL ISHLASH"
)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            d = json.load(f)
            return set(d.get("groups", [])), d.get("offset", 0)
    return set(), 0


def save_state(groups, offset):
    with open(STATE_FILE, "w") as f:
        json.dump({"groups": list(groups), "offset": offset}, f, ensure_ascii=False, indent=2)


async def main():
    bot = Bot(token=TOKEN)
    groups, offset = load_state()

    updates = await bot.get_updates(offset=offset, timeout=5)
    for u in updates:
        offset = u.update_id + 1
        if u.message:
            chat = u.message.chat
            if chat.type in ("group", "supergroup"):
                groups.add(chat.id)
            elif chat.type == "private":
                try:
                    await bot.send_message(chat_id=chat.id, text=AUTO_REPLY)
                except Exception:
                    pass
        elif u.my_chat_member:
            chat = u.my_chat_member.chat
            if chat.type in ("group", "supergroup"):
                groups.add(chat.id)

    save_state(groups, offset)


asyncio.run(main())
