# Bot token
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

TOKEN = os.getenv("BOT_TOKEN")

# Admin Telegram ID'lari (o'zingizning ID'ingizni kiriting)
ADMIN_IDS = [6981254334]  # <-- shu yerga o'z Telegram ID'ingizni qo'ying

# Majburiy obuna kanallari (username yoki -100xxxxxxxx formatda ID)
REQUIRED_CHANNELS = [
    {"name": "Dayleess Donat", "username": "@Dayleess_Donat", "url": "https://t.me/Dayleess_Donat"},
    {"name": "Ani Time", "username": "@AniTime_here", "url": "https://t.me/AniTime_here"},
    # Qo'shimcha kanal qo'shish uchun yuqoridagi formatda yozing
]
# Kanalga post joylash uchun kanal username yoki ID si
POST_CHANNEL = "@AniTime_here" 

# Premium tariflar (Telegram Stars)
PREMIUM_PLANS = {
    "1m": {"name": "1 oy", "days": 30, "price": 50},
    "3m": {"name": "3 oy", "days": 90, "price": 75},
    "6m": {"name": "6 oy", "days": 180, "price": 100},
    "1y": {"name": "1 yil", "days": 365, "price": 125},
    "vip": {"name": "VIP", "days": None, "price": 200},
}

# Aniq savdo posti havolasini .env yoki Render Environment orqali kiriting.
STARS_PURCHASE_URL = (
    os.getenv("STARS_PURCHASE_URL") or "https://t.me/Dayleess_Donat/172"
)
PAY_SUPPORT_CONTACT = os.getenv("PAY_SUPPORT_CONTACT") or "@Dayleess_369"
PAY_SUPPORT_URL = os.getenv("PAY_SUPPORT_URL") or "https://t.me/Dayleess_369"

# Ma'lumotlar bazasi (Cloud uchun PostgreSQL, aks holda SQLite)
DATABASE_URL = os.getenv("DATABASE_URL") # Masalan: postgres://user:pass@host:port/db
