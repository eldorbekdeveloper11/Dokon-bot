import asyncio, base64, json, os
import httpx
from telegram.ext import CommandHandler, MessageHandler, filters

ADMIN_ID = 8188527818
GH = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "eldorbekdeveloper11/Dokon-bot")
URL = f"https://api.github.com/repos/{REPO}/contents/ads.json"
HDR = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
lock = asyncio.Lock()
albums = {}   # media_group_id -> {"photos": [file_id, ...], "text": matn}
tasks = set()


async def read():
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(URL, headers=HDR)
    if r.status_code == 200:
        return json.loads(base64.b64decode(r.json()["content"]))
    return {"ads": [], "index": 0}


async def change(fn):
    """ads.json ni GitHub'dan o'qib, fn(data) bilan o'zgartiradi va qaytarib yozadi."""
    async with lock:
        async with httpx.AsyncClient(timeout=20) as c:
            for _ in range(3):
                r = await c.get(URL, headers=HDR)
                sha = r.json().get("sha") if r.status_code == 200 else None
                d = json.loads(base64.b64decode(r.json()["content"])) if sha else {"ads": [], "index": 0}
                result = fn(d)
                raw = json.dumps(d, ensure_ascii=False, indent=2).encode()
                body = {"message": "reklama yangilandi", "content": base64.b64encode(raw).decode()}
                if sha:
                    body["sha"] = sha
                p = await c.put(URL, headers=HDR, json=body)
                if p.status_code in (200, 201):
                    return result
    raise RuntimeError("ads.json saqlanmadi")


async def add_ad(msg, photos, text):
    def f(d):
        ad = {"photos": photos}
        if text:
            ad["text"] = text
        d.setdefault("ads", []).append(ad)
        return len(d["ads"])
    try:
        n = await change(f)
        await msg.reply_text(f"✅ Reklama №{n} qo'shildi ({len(photos)} ta rasm). Ro'yxat: /list")
    except Exception as e:
        await msg.reply_text(f"❌ Saqlanmadi: {e}")


async def finish(gid, msg):
    await asyncio.sleep(2)  # albomning hamma rasmi kelishini kutamiz
    a = albums.pop(gid, None)
    if a:
        await add_ad(msg, a["photos"][:10], a["text"])


async def on_photo(update, ctx):
    m = update.message
    fid, gid = m.photo[-1].file_id, m.media_group_id
    if not gid:
        return await add_ad(m, [fid], m.caption)
    if gid not in albums:
        albums[gid] = {"photos": [], "text": None}
        t = asyncio.create_task(finish(gid, m))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
    albums[gid]["photos"].append(fid)
    if m.caption:
        albums[gid]["text"] = m.caption


async def cmd_add(update, ctx):  # faqat matnli reklama: /add matn
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await update.message.reply_text(
            "Rasmli reklama: rasm(lar)ni matni (caption) bilan yuboring.\nFaqat matn: /add matn")
    def f(d):
        d.setdefault("ads", []).append({"text": parts[1]})
        return len(d["ads"])
    n = await change(f)
    await update.message.reply_text(f"✅ Reklama №{n} qo'shildi.")


async def cmd_list(update, ctx):
    ads = (await read()).get("ads", [])
    if not ads:
        return await update.message.reply_text("Reklamalar yo'q.")
    lines = []
    for i, a in enumerate(ads, 1):
        a = {"text": a} if isinstance(a, str) else a
        n = len(a.get("photos") or ([a["photo"]] if a.get("photo") else []))
        lines.append(f"{i}. 🖼{n} {(a.get('text') or '').replace(chr(10), ' ')[:40]}")
    await update.message.reply_text("\n".join(lines) + "\n\nO'chirish: /del 2")


async def cmd_del(update, ctx):
    try:
        n = int(ctx.args[0])
    except Exception:
        return await update.message.reply_text("Masalan: /del 2")
    def f(d):
        ads = d.get("ads", [])
        if not 1 <= n <= len(ads):
            return False
        ads.pop(n - 1)
        i = d.get("index", 0)
        d["index"] = (i - 1 if i > n - 1 else i) % len(ads) if ads else 0
        return True
    ok = await change(f)
    await update.message.reply_text(f"🗑 Reklama №{n} o'chirildi." if ok else "Bunday raqam yo'q. /list")


def register(app):
    adm = filters.User(ADMIN_ID) & filters.ChatType.PRIVATE
    app.add_handler(MessageHandler(adm & filters.PHOTO, on_photo))
    app.add_handler(CommandHandler("add", cmd_add, adm))
    app.add_handler(CommandHandler("list", cmd_list, adm))
    app.add_handler(CommandHandler("del", cmd_del, adm))
