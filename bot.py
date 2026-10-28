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
log = logging.getLogger("bot")

TOKEN = os.environ["BOT_TOKEN"]
GH_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "eldorbekdeveloper11/Dokon-bot")
GROUPS_FILE = "groups.json"

# Majburiy obuna kanallari
PUBLIC_CHANNEL = "@meningsevimlimusiqam"
PUBLIC_URL = "https://t.me/meningsevimlimusiqam"
PRIVATE_CHANNEL_ID = -1004369700217  # zayafka kanal (qo'shilish so'rovi bilan)
PRIVATE_URL = "https://t.me/+7ha5JpZjMXY5NmU6"

AUTO_REPLY = (
    "👋 Assalomu alaykum!\n\n"
    "📢 Siz bergan reklamalarni Telegram guruhlarda kuniga kamida 2 marta yuboramiz.\n\n"
    "REKLAMA YUKLAMOQCHI BO'LSANGIZ @ELDORBEK_231 GA MUROJAT QILING\n"
    "YOKI +998958565307 GA SMS YOZING\n\n"
    "MAQSAD: O'RGANISH VA PUL ISHLASH"
)

SUBSCRIBE_TEXT = (
    "❗️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, "
    "so'ng «✅ Tekshirish» tugmasini bosing."
)

groups = set()


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
    b = await is_member(bot, PRIVATE_CHANNEL_ID, user_id)
    return a and b


def subscribe_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 1-kanal", url=PUBLIC_URL)],
            [InlineKeyboardButton("📝 2-kanal (so'rov yuborish)", url=PRIVATE_URL)],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check")],
        ]
    )


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if req and req.chat.id == PRIVATE_CHANNEL_ID:
        try:
            await req.approve()
        except TelegramError as e:
            log.warning("So'rov tasdiqlanmadi: %s", e)


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


async def load_groups():
    url = f"https://api.github.com/repos/{REPO}/contents/{GROUPS_FILE}"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url, headers=gh_headers() if GH_TOKEN else {})
            if r.status_code == 200:
                data = json.loads(base64.b64decode(r.json()["content"]))
                return set(data.get("groups", []))
    except Exception as e:
        log.warning("groups.json o'qilmadi: %s", e)
    return set()


async def save_groups():
    if not GH_TOKEN:
        log.warning("GITHUB_TOKEN yo'q, ro'yxat saqlanmadi")
        return
    url = f"https://api.github.com/repos/{REPO}/contents/{GROUPS_FILE}"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url, headers=gh_headers())
            sha = None
            data = {"groups": [], "offset": 0}
            if r.status_code == 200:
                sha = r.json()["sha"]
                data = json.loads(base64.b64decode(r.json()["content"]))
            data["groups"] = sorted(groups)
            body = {
                "message": "Guruhlar yangilandi",
                "content": base64.b64encode(
                    json.dumps(data, ensure_ascii=False, indent=2).encode()
                ).decode(),
            }
            if sha:
                body["sha"] = sha
            pr = await c.put(url, headers=gh_headers(), json=body)
            log.info("groups.json saqlandi: %s", pr.status_code)
    except Exception as e:
        log.warning("groups.json saqlanmadi: %s", e)


async def remember_group(chat_id):
    if chat_id not in groups:
        groups.add(chat_id)
        await save_groups()


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
    groups.update(await load_groups())
    log.info("Yuklangan guruhlar: %d ta", len(groups))


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
