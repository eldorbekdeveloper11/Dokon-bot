import asyncio, base64, json, logging, os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
import admin
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Update
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, ChatJoinRequestHandler,
                          ChatMemberHandler, MessageHandler, filters)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # token loglarda ko'rinmasin
log = logging.getLogger("bot")

TOKEN = os.environ["BOT_TOKEN"]
GH = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "eldorbekdeveloper11/Dokon-bot")
PUBLIC_CHANNEL = "@meningsevimlimusiqam"
PUBLIC_URL = "https://t.me/meningsevimlimusiqam"
PRIVATE_ID = -1004369700217
PRIVATE_URL = "https://t.me/+7ha5JpZjMXY5NmU6"
AUTO_REPLY = (
    "👋 Assalomu alaykum!\n\n"
    "📢 Siz bergan reklamalarni Telegram guruhlarda kuniga kamida 2 marta yuboramiz.\n\n"
    "REKLAMA YUKLAMOQCHI BO'LSANGIZ @ELDOR_231 GA MUROJAT QILING\n"
    "YOKI +998958565307 GA SMS YOZING\n\n"
    "MAQSAD: O'RGANISH VA PUL ISHLASH"
)
ASK = "❗️ Botdan foydalanish uchun kanallarga a'zo bo'ling, so'ng «✅ Tekshirish» ni bosing."
groups, reqs, lock = set(), set(), asyncio.Lock()


def url(p): return f"https://api.github.com/repos/{REPO}/contents/{p}"
def hdr(): return {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}


async def gh_get(p):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(url(p), headers=hdr() if GH else {})
    if r.status_code == 200:
        j = r.json()
        return json.loads(base64.b64decode(j["content"])), j["sha"]
    return None, None


async def gh_save(p, key, vals):
    if not GH:
        return
    async with lock:
        try:
            data, sha = await gh_get(p)
            data = data or {}
            data[key] = sorted(vals)
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode()
            body = {"message": "update " + p, "content": base64.b64encode(raw).decode()}
            if sha:
                body["sha"] = sha
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.put(url(p), headers=hdr(), json=body)
            log.info("%s saqlandi: %s", p, r.status_code)
        except Exception as e:
            log.warning("%s saqlanmadi: %s", p, e)


async def is_member(bot, chat, uid):
    try:
        m = await bot.get_chat_member(chat, uid)
    except TelegramError as e:
        log.warning("obuna tekshirilmadi: %s", e)
        return False
    return m.status in ("member", "administrator", "creator") or (
        m.status == "restricted" and m.is_member)


async def subscribed(bot, uid):
    if not await is_member(bot, PUBLIC_CHANNEL, uid):
        return False
    return uid in reqs or await is_member(bot, PRIVATE_ID, uid)


async def on_join(u, ctx):  # so'rov TASDIQLANMAYDI, faqat eslab qolinadi
    r = u.chat_join_request
    if r.chat.id == PRIVATE_ID and r.from_user.id not in reqs:
        reqs.add(r.from_user.id)
        await gh_save("requests.json", "users", reqs)


async def on_check(u, ctx):
    q = u.callback_query
    if await subscribed(ctx.bot, q.from_user.id):
        await q.answer()
        await ctx.bot.send_message(q.from_user.id, AUTO_REPLY)
    else:
        await q.answer("Avval ikkala kanalga a'zo bo'ling.", show_alert=True)


async def on_msg(u, ctx):
    chat, msg = u.effective_chat, u.effective_message
    if not chat or not msg:
        return
    if chat.type == "private":
        if await subscribed(ctx.bot, u.effective_user.id):
            await msg.reply_text(AUTO_REPLY)
        else:
            kb = Kb([[Btn("📢 1-kanal", url=PUBLIC_URL)],
                     [Btn("📝 2-kanal (so'rov yuborish)", url=PRIVATE_URL)],
                     [Btn("✅ Tekshirish", callback_data="check")]])
            await msg.reply_text(ASK, reply_markup=kb)
    elif chat.type in ("group", "supergroup"):
        await add_group(chat.id)


async def add_group(cid):
    if cid not in groups:
        groups.add(cid)
        await gh_save("groups.json", "groups", groups)


async def on_member(u, ctx):
    c = u.effective_chat
    if c and c.type in ("group", "supergroup"):
        await add_group(c.id)


async def post_init(app):
    for p, key, s in (("groups.json", "groups", groups), ("requests.json", "users", reqs)):
        try:
            d, _ = await gh_get(p)
            s.update((d or {}).get(key, []))
        except Exception as e:
            log.warning("%s o'qilmadi: %s", p, e)
    log.info("Guruhlar: %d, so'rovlar: %d", len(groups), len(reqs))


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("PORT", "10000"))
    threading.Thread(target=HTTPServer(("0.0.0.0", port), Health).serve_forever, daemon=True).start()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    admin.register(app)
    app.add_handler(ChatJoinRequestHandler(on_join))
    app.add_handler(CallbackQueryHandler(on_check, pattern="^check$"))
    app.add_handler(ChatMemberHandler(on_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_msg))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
