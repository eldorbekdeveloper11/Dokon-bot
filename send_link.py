import asyncio
import json
import os
import time
from telegram import Bot
from telegram.error import TelegramError

TOKEN = os.environ["BOT_TOKEN"]
GROUPS_FILE = "groups.json"
ADS_FILE = "ads.json"
MIN_GAP = 19 * 60  # oxirgi yuborishdan kamida 19 daqiqa o'tishi kerak


def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE) as f:
            return set(json.load(f).get("groups", []))
    return set()


def save_groups(groups):
    data = {}
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE) as f:
            data = json.load(f)
    data["groups"] = list(groups)
    with open(GROUPS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_ads():
    if os.path.exists(ADS_FILE):
        with open(ADS_FILE) as f:
            return json.load(f)
    return {"ads": [], "index": 0}


def save_ads(d):
    with open(ADS_FILE, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


async def send_ad(bot, chat_id, ad):
    # Reklama oddiy matn (str) yoki {"text": "...", "photo": "fayl.jpg"} bo'lishi mumkin
    if isinstance(ad, str):
        ad = {"text": ad}
    text = ad.get("text")
    photo = ad.get("photo")

    if photo and os.path.exists(photo):
        with open(photo, "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=text or None)
    elif text:
        await bot.send_message(chat_id=chat_id, text=text)
    else:
        print("Reklamada matn ham, topilgan rasm ham yo'q:", ad)


async def main():
    groups = load_groups()
    ads_data = load_ads()
    ads = ads_data.get("ads", [])
    if not ads or not groups:
        return

    # Ikki yuborish orasi 20 daqiqadan kam bo'lmasligi uchun himoya
    last_sent = ads_data.get("last_sent", 0)
    if time.time() - last_sent < MIN_GAP:
        print("Hali erta, o'tkazib yuborildi")
        return

    idx = ads_data.get("index", 0) % len(ads)
    ad = ads[idx]

    bot = Bot(token=TOKEN)
    dead = []
    for chat_id in list(groups):
        try:
            await send_ad(bot, chat_id, ad)
        except TelegramError as e:
            print("Xato:", chat_id, e)
            dead.append(chat_id)

    for d in dead:
        groups.discard(d)
    save_groups(groups)

    ads_data["index"] = (idx + 1) % len(ads)
    ads_data["last_sent"] = int(time.time())
    save_ads(ads_data)


asyncio.run(main())
