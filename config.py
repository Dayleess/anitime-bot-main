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

# Ma'lumotlar bazasi (Cloud uchun PostgreSQL, aks holda SQLite)
DATABASE_URL = os.getenv("DATABASE_URL") # Masalan: postgres://user:pass@host:port/db
