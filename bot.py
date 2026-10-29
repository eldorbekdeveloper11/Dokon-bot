import asyncio
import base64
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # loglarda bot tokeni ko'rinmasligi uchun
log = logging.getLogger("bot")

TOKEN = os.environ["BOT_TOKEN"]
GH_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "eldorbekdeveloper11/Dokon-bot")
GROUPS_FILE = "groups.json"
REQUESTS_FILE = "requests.json"

# Majburiy obuna kanallari
PUBLIC_CHANNEL = "@meningsevimlimusiqam"
PUBLIC_URL = "https://t.me/meningsevimlimusiqam"
PRIVATE_CHANNEL_ID = -1004369700217  # zayafka kanal (qo'shilish so'rovi bilan)
PRIVATE_URL = "https://t.me/+7ha5JpZjMXY5NmU6"

AUTO_REPLY = (
    "👋 Assalomu alaykum!\n\n"
    "📢 Siz bergan reklamalarni Telegram guruhlarda kuniga kamida 2 marta yuboramiz.\n\n"
    "REKLAMA YUKLAMOQCHI BO'LSANGIZ @ELDOR_231 GA MUROJAT QILING\n"
    "YOKI +998958565307 GA SMS YOZING ! QOʻNGʻIROQ QILMANG DARSDA BOʻLISHI MUMKIN\n\n"
    "MAQSAD: O'RGANISH VA PUL ISHLASH"
)

SUBSCRIBE_TEXT = (
    "❗️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, "
    "so'ng «✅ Tekshirish» tugmasini bosing."
)

groups = set()
join_requests = set()  # yopiq kanalga so'rov yuborgan foydalanuvchilar
gh_lock = asyncio.Lock()


# ---------- Majburiy obuna ----------
async def is_member(bot, chat_id, user_id):
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError as e:
        log.warning("Obuna tekshirib bo'lmadi (%s): %s", chat_id, e)
        return False
    if m.status in ("member", "administrator", "creator"):
        return True
    if m.status == "restricted" and getattr(m, "is_member", False):
        return True
    return False


async def is_subscribed(bot, user_id):
    a = await is_member(bot, PUBLIC_CHANNEL, user_id)
    if not a:
        return False
    # Yopiq kanal: so'rov yuborgan yoki (tasdiqlangan bo'lsa) a'zo bo'lgan
    if user_id in join_requests:
        return True
    return await is_member(bot, PRIVATE_CHANNEL_ID, user_id)


def subscribe_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 1-kanal", url=PUBLIC_URL)],
            [InlineKeyboardButton("📝 2-kanal (so'rov yuborish)", url=PRIVATE_URL)],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check")],
        ]
    )


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # So'rov tasdiqlanmaydi: faqat kim so'rov yuborganini eslab qolamiz
    req = update.chat_join_request
    if req and req.chat.id == PRIVATE_CHANNEL_ID:
        uid = req.from_user.id
        if uid not in join_requests:
            join_requests.add(uid)
            await gh_update(
                REQUESTS_FILE, "users", join_requests, "So'rovlar yangilandi", {"users": []}
            )


async def on_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if await is_subscribed(context.bot, q.from_user.id):
        await q.answer()
        try:
            await q.edit_message_text(AUTO_REPLY)
        except TelegramError:
            await context.bot.send_message(chat_id=q.from_user.id, text=AUTO_REPLY)
    else:
        await q.answer("Avval ikkala kanalga a'zo bo'ling.", show_alert=True)


# ---------- Guruhlar ro'yxati (GitHub'da saqlanadi) ----------
def gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def api_url(path):
    return f"https://api.github.com/repos/{REPO}/contents/{path}"


async def gh_read(path):
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(api_url(path), headers=gh_headers() if GH_TOKEN else {})
            if r.status_code == 200:
                return json.loads(base64.b64decode(r.json()["content"]))
    except Exception as e:
        log.warning("%s o'qilmadi: %s", path, e)
    return None


async def gh_update(path, key, values, message, default):
    if not GH_TOKEN:
        log.warning("GITHUB_TOKEN yo'q, %s saqlanmadi", path)
        return
    async with gh_lock:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(api_url(path), headers=gh_headers())
                sha = None
                data = dict(default)
                if r.status_code == 200:
                    sha = r.json()["sha"]
                    data = json.loads(base64.b64decode(r.json()["content"]))
                data[key] = sorted(values)
                body = {
                    "message": message,
                    "content": base64.b64encode(
                        json.dumps(data, ensure_ascii=False, indent=2).encode()
                    ).decode(),
                }
                if sha:
                    body["sha"] = sha
                pr = await c.put(api_url(path), headers=gh_headers(), json=body)
                log.info("%s saqlandi: %s", path, pr.status_code)
        except Exception as e:
            log.warning("%s saqlanmadi: %s", path, e)


async def remember_group(chat_id):
    if chat_id not in groups:
        groups.add(chat_id)
        await gh_update(
            GROUPS_FILE, "groups", groups, "Guruhlar yangilandi", {"groups": [], "offset": 0}
        )


# ---------- Xabarlar ----------
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return
    if chat.type == "private":
        user = update.effective_user
        if user and await is_subscribed(context.bot, user.id):
            await msg.reply_text(AUTO_REPLY)
        else:
            await msg.reply_text(SUBSCRIBE_TEXT, reply_markup=subscribe_keyboard())
    elif chat.type in ("group", "supergroup"):
        await remember_group(chat.id)


async def on_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        await remember_group(chat.id)


async def post_init(app: Application):
    g = await gh_read(GROUPS_FILE)
    if g:
        groups.update(g.get("groups", []))
    r = await gh_read(REQUESTS_FILE)
    if r:
        join_requests.update(r.get("users", []))
    log.info("Guruhlar: %d ta, so'rovlar: %d ta", len(groups), len(join_requests))


# ---------- Render uchun kichik veb-server ----------
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def run_health():
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()


def main():
    threading.Thread(target=run_health, daemon=True).start()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CallbackQueryHandler(on_check, pattern="^check$"))
    app.add_handler(ChatMemberHandler(on_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
