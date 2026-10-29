import asyncio, json, os, time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import Forbidden, TelegramError

TOKEN = os.environ["BOT_TOKEN"]
MIN_GAP = 90 * 60  # oxirgi yuborishdan kamida 90 daqiqa o'tishi kerak
BUTTON_TEXT = "📢 Reklama berish"
BUTTON_MSG = "👇 Reklama berish uchun bosing"


def load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def send_ad(bot, chat_id, ad, markup):
    # ad: oddiy matn yoki {"text": "...", "photo": "a.jpg"} yoki {"photos": ["a.jpg", "b.jpg"]}
    if isinstance(ad, str):
        ad = {"text": ad}
    text = ad.get("text")
    photos = ad.get("photos") or ([ad["photo"]] if ad.get("photo") else [])
    photos = [p for p in photos if os.path.exists(p)][:10]
    if len(photos) >= 2:
        media = []
        for i, p in enumerate(photos):
            with open(p, "rb") as f:
                media.append(InputMediaPhoto(f.read(), caption=text if i == 0 else None))
        await bot.send_media_group(chat_id=chat_id, media=media)
        await bot.send_message(chat_id=chat_id, text=BUTTON_MSG, reply_markup=markup)
    elif photos:
        with open(photos[0], "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=text, reply_markup=markup)
    elif text:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    else:
        print("Reklamada matn ham, rasm ham topilmadi:", ad)


async def main():
    gdata = load("groups.json", {})
    groups = list(gdata.get("groups", []))
    adata = load("ads.json", {"ads": [], "index": 0})
    ads = adata.get("ads", [])
    if not ads or not groups:
        return
    if time.time() - adata.get("last_sent", 0) < MIN_GAP:
        print("Hali erta, o'tkazib yuborildi")
        return

    idx = adata.get("index", 0) % len(ads)
    bot = Bot(token=TOKEN)
    me = await bot.get_me()
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, url=f"https://t.me/{me.username}?start=reklama")]]
    )

    dead = []
    for chat_id in groups:
        try:
            await send_ad(bot, chat_id, ads[idx], markup)
        except Forbidden:  # bot guruhdan chiqarilgan
            dead.append(chat_id)
        except TelegramError as e:
            print("Xato:", chat_id, e)

    if dead:
        gdata["groups"] = [g for g in groups if g not in dead]
        save("groups.json", gdata)

    adata["index"] = (idx + 1) % len(ads)
    adata["last_sent"] = int(time.time())
    save("ads.json", adata)


asyncio.run(main())
