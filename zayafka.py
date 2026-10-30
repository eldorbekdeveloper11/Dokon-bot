import asyncio, base64, json, os, time
import httpx
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, InputMediaPhoto
from telegram.ext import CallbackQueryHandler, MessageHandler, filters
import admin

GH = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "eldorbekdeveloper11/Dokon-bot")
PURL = f"https://api.github.com/repos/{REPO}/contents/pending.json"
HDR = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
lock = asyncio.Lock()
albums, tasks = {}, set()
SUB = None  # bot.py dan beriladi: obuna tekshiruvchi funksiya


async def pchange(fn):
    """pending.json ni GitHub'da o'qib, fn(data) bilan o'zgartirib yozadi."""
    async with lock:
        async with httpx.AsyncClient(timeout=20) as c:
            for _ in range(3):
                r = await c.get(PURL, headers=HDR)
                sha = r.json().get("sha") if r.status_code == 200 else None
                d = json.loads(base64.b64decode(r.json()["content"])) if sha else {}
                result = fn(d)
                raw = json.dumps(d, ensure_ascii=False, indent=2).encode()
                body = {"message": "zayafka yangilandi", "content": base64.b64encode(raw).decode()}
                if sha:
                    body["sha"] = sha
                p = await c.put(PURL, headers=HDR, json=body)
                if p.status_code in (200, 201):
                    return result
    raise RuntimeError("pending.json saqlanmadi")


async def submit(ctx, msg, user, photos, text):
    app_id = str(int(time.time() * 1000) % 10**9)
    who = user.full_name + (f" (@{user.username})" if user.username else "")
    photos = photos[:10]
    try:
        await pchange(lambda d: d.update({app_id: {"uid": user.id, "who": who, "photos": photos, "text": text}}))
        cap = (text or "")[:1000] or None
        if len(photos) == 1:
            await ctx.bot.send_photo(admin.ADMIN_ID, photos[0], caption=cap)
        else:
            await ctx.bot.send_media_group(admin.ADMIN_ID, [
                InputMediaPhoto(p, caption=cap if i == 0 else None) for i, p in enumerate(photos)])
        link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        tg = f"@{user.username}" if user.username else "username yo'q (tugma orqali oching)"
        kb = Kb([[Btn("✅ Qabul", callback_data=f"zy:ok:{app_id}"),
                  Btn("❌ Rad", callback_data=f"zy:no:{app_id}")],
                 [Btn("👤 Telegrami", url=link)]])
        await ctx.bot.send_message(
            admin.ADMIN_ID, f"📥 Yangi zayafka №{app_id}\n👤 {user.full_name}\n📱 Telegram: {tg}\n🆔 {user.id}",
            reply_markup=kb)
        await msg.reply_text("✅ Zayafkangiz qabul qilindi. Ko'rib chiqib, javob beramiz.")
    except Exception as e:
        await msg.reply_text("❌ Xatolik yuz berdi, birozdan keyin qayta urinib ko'ring.")
        print("zayafka xato:", e)


async def finish(gid, ctx, msg, user):
    await asyncio.sleep(2)  # albomning hamma rasmi kelishini kutamiz
    a = albums.pop(gid, None)
    if a:
        await submit(ctx, msg, user, a["photos"], a["text"])


async def on_photo(u, ctx):
    m, user = u.message, u.effective_user
    if not await SUB(ctx.bot, user.id):
        return await FALLBACK(u, ctx)
    fid, gid = m.photo[-1].file_id, m.media_group_id
    if not gid:
        return await submit(ctx, m, user, [fid], m.caption)
    if gid not in albums:
        albums[gid] = {"photos": [], "text": None}
        t = asyncio.create_task(finish(gid, ctx, m, user))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
    albums[gid]["photos"].append(fid)
    if m.caption:
        albums[gid]["text"] = m.caption


async def on_decide(u, ctx):
    q = u.callback_query
    if q.from_user.id != admin.ADMIN_ID:
        return await q.answer("Ruxsat yo'q", show_alert=True)
    _, act, app_id = q.data.split(":")
    box = {}
    await pchange(lambda d: box.update(a=d.pop(app_id, None)))
    a = box["a"]
    if not a:
        return await q.answer("Bu zayafka allaqachon ko'rib chiqilgan.", show_alert=True)
    if act == "ok":
        def add(d):
            ad = {"photos": a["photos"]}
            if a.get("text"):
                ad["text"] = a["text"]
            d.setdefault("ads", []).append(ad)
            return len(d["ads"])
        try:
            n = await admin.change(add)
        except Exception as e:  # saqlanmasa, zayafkani qaytarib qo'yamiz
            await pchange(lambda d: d.update({app_id: a}))
            return await q.answer(f"Saqlanmadi: {e}", show_alert=True)
        await q.edit_message_text(f"✅ Qabul qilindi: №{n} reklama sifatida qo'shildi.\n👤 {a['who']}")
        note = "✅ Reklamangiz tasdiqlandi va ro'yxatga qo'shildi. Tez orada guruhlarga yuboriladi."
    else:
        await q.edit_message_text(f"❌ Rad etildi.\n👤 {a['who']}")
        note = "❌ Afsuski, reklamangiz qabul qilinmadi. Savollar uchun @ELDOR_231 ga yozing."
    await q.answer()
    try:
        await ctx.bot.send_message(a["uid"], note)
    except Exception:
        pass


def register(app, subscribed, fallback):
    global SUB, FALLBACK
    SUB, FALLBACK = subscribed, fallback
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE & ~filters.User(admin.ADMIN_ID), on_photo))
    app.add_handler(CallbackQueryHandler(on_decide, pattern=r"^zy:(ok|no):\d+$"))
