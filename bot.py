import base64
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from telegram import Update
from telegram.ext import (
    Application,
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

AUTO_REPLY = (
    "REKLAMA YUKLAMOQCHI BO'LSANGIZ @ELDORBEK_231 GA MUROJAT QILING\n"
    "YOKI +998958565307 GA SMS YOZING\n\n"
    "MAQSAD: O'RGANISH VA PUL ISHLASH"
)

groups = set()


def gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


async def load_groups():
    """Guruhlar ro'yxatini GitHub'dagi groups.json dan o'qiydi."""
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
    """Guruhlar ro'yxatini GitHub'dagi groups.json ga yozadi."""
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


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    if chat.type == "private":
        await update.effective_message.reply_text(AUTO_REPLY)
    elif chat.type in ("group", "supergroup"):
        await remember_group(chat.id)


async def on_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        await remember_group(chat.id)


async def post_init(app: Application):
    groups.update(await load_groups())
    log.info("Yuklangan guruhlar: %d ta", len(groups))


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
    app.add_handler(ChatMemberHandler(on_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, on_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
