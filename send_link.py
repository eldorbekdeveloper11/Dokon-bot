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


def src(p):
    # repodagi fayl bo'lsa o'qiydi, aks holda Telegram file_id deb oladi
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    return p


async def send_ad(bot, chat_id, ad, markup):
    # ad: matn yoki {"text": "...", "photos": ["fayl.jpg yoki file_id", ...]}
    if isinstance(ad, str):
        ad = {"text": ad}
    text = ad.get("text")
    photos = (ad.get("photos") or ([ad["photo"]] if ad.get("photo") else []))[:10]
    if len(photos) >= 2:
        media = [InputMediaPhoto(src(p), caption=text if i == 0 else None)
                 for i, p in enumerate(photos)]
        await bot.send_media_group(chat_id=chat_id, media=media)
        await bot.send_message(chat_id=chat_id, text=BUTTON_MSG, reply_markup=markup)
    elif photos:
        await bot.send_photo(chat_id=chat_id, photo=src(photos[0]), caption=text,
                             reply_markup=markup)
    elif text:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    else:
        print("Bo'sh reklama:", ad)


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
