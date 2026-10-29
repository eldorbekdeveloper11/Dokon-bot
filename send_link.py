import asyncio
import json
import os
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

TOKEN = os.environ["BOT_TOKEN"]
GROUPS_FILE = "groups.json"
ADS_FILE = "ads.json"
MIN_GAP = 90 * 60  # oxirgi yuborishdan kamida 19 daqiqa o'tishi kerak
BUTTON_TEXT = "📢 Reklama berish"


def load_groups():
    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE) as f:
            return set(json.load(f).get("groups", []))
    return set()


def save_groups(groups):
    data = {}
    if os.path.exists(GROUPS_FILE):
        with open(GRO
