import asyncio
import html
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    TOKEN,
    ADMIN_IDS,
    REQUIRED_CHANNELS,
    POST_CHANNEL,
    PREMIUM_PLANS,
    PAY_SUPPORT_CONTACT,
    PAY_SUPPORT_URL,
)
import database as db

logging.basicConfig(level=logging.INFO)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable o'rnatilmagan.")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

db.init_db()

# ─── FSM States ───────────────────────────────────────────────────────────────

class AddAnimeState(StatesGroup):
    waiting_title = State()
    waiting_desc = State()
    waiting_photo = State()

class EditAnimeState(StatesGroup):
    waiting_anime_id = State()
    waiting_title = State()
    waiting_desc = State()
    waiting_photo = State()

class AddEpisodeState(StatesGroup):
    waiting_anime_id = State()
    waiting_season = State()
    waiting_episode = State()
    waiting_video = State()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_subscriptions(user_id: int) -> list[dict]:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi"""
    not_subscribed = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch["username"], user_id)
            if member.status not in ("creator", "administrator", "member", "restricted"):
                not_subscribed.append(ch)
        except Exception as e:
            logging.error(f"Obuna tekshirishda xatolik ({ch['username']}): {e}")
            # Agar bot kanal admini bo'lmasa yoki kanal topilmasa ham obuna bo'lishni so'raymiz
            not_subscribed.append(ch)
    return not_subscribed

def subscription_keyboard(not_subscribed: list[dict], anime_id: int) -> InlineKeyboardMarkup:
    """Obuna tugmalari klaviaturasi"""
    buttons = [
        [InlineKeyboardButton(text=f"📢 {ch['name']} ga obuna bo'lish", url=ch["url"])]
        for ch in not_subscribed
    ]
    buttons.append([
        InlineKeyboardButton(
            text="✅ Obuna bo'ldim, tekshirish",
            callback_data=f"check_sub:{anime_id}"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 oy", callback_data="buy_premium:1m"),
            InlineKeyboardButton(text="3 oy", callback_data="buy_premium:3m"),
        ],
        [
            InlineKeyboardButton(text="6 oy", callback_data="buy_premium:6m"),
            InlineKeyboardButton(text="1 yil", callback_data="buy_premium:1y"),
        ],
        [InlineKeyboardButton(text="VIP umrbod", callback_data="buy_premium:vip")],
    ])

def format_premium_status(status: dict) -> str:
    if status["is_vip"]:
        return "VIP obunangiz umrbod faol."
    if status["active"] and status["expires_at"]:
        expires_at = datetime.fromtimestamp(status["expires_at"], tz=timezone.utc)
        return f"Premium obunangiz {expires_at:%d.%m.%Y} sanasigacha faol."
    return "Sizda hozir faol Premium obuna yo'q."

async def send_premium_menu(user_id: int, premium_anime: str | None = None):
    if is_admin(user_id):
        await bot.send_message(
            user_id,
            "<b>Siz bot adminisiz.</b>\n\n"
            "Barcha Premium animelar siz uchun doim ochiq.",
            parse_mode="HTML",
        )
        return

    status = db.get_premium_status(user_id)
    intro = ""
    if premium_anime:
        intro = f"<b>{premium_anime}</b> Premium foydalanuvchilar uchun.\n\n"
    await bot.send_message(
        user_id,
        f"{intro}<b>AniTime Premium</b>\n\n"
        f"{format_premium_status(status)}\n\n"
        f"Kerakli tarifni tanlang. Bot adminga so'rov yuboradi, "
        f"keyin to'lovni shaxsiy chatda kelishasiz.",
        reply_markup=premium_keyboard(),
        parse_mode="HTML",
    )

# ─── /start (Deep Link) ───────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    args = msg.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""

    # Deep link: /start anime_42
    if payload.startswith("anime_"):
        try:
            anime_id = int(payload.split("_")[1])
        except (IndexError, ValueError):
            await msg.answer("❌ Noto'g'ri havola.")
            return
        await send_anime_or_check_sub(msg.from_user.id, anime_id, msg)
        return

    # Oddiy start
    await msg.answer(
        "👋 Salom! Men <b>AniTime</b> botiman.\n\n"
        "📺 Kanal postidagi <b>Yuklab olish</b> tugmasini bosing va animelarni olish uchun foydalaning.\n\n"
        "⭐ Premium olish uchun /premium buyrug'ini bosing.",
        parse_mode="HTML"
    )

@dp.message(Command("premium"))
async def cmd_premium(msg: types.Message):
    await send_premium_menu(msg.from_user.id)

@dp.message(Command("premium_status"))
async def cmd_premium_status(msg: types.Message):
    if is_admin(msg.from_user.id):
        await msg.answer(
            "Siz bot adminisiz. Barcha Premium animelar siz uchun doim ochiq."
        )
        return

    status = db.get_premium_status(msg.from_user.id)
    await msg.answer(format_premium_status(status))

@dp.message(Command("paysupport"))
async def cmd_paysupport(msg: types.Message):
    await msg.answer(
        f"Premium bo'yicha yordam: {PAY_SUPPORT_CONTACT}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Adminga yozish", url=PAY_SUPPORT_URL)]
        ]),
    )

@dp.callback_query(F.data.startswith("buy_premium:"))
async def callback_buy_premium(call: CallbackQuery):
    if is_admin(call.from_user.id):
        await call.answer(
            "Siz bot adminisiz. Premium siz uchun doim ochiq.",
            show_alert=True,
        )
        return

    plan_code = call.data.split(":", maxsplit=1)[1]
    plan = PREMIUM_PLANS.get(plan_code)
    if not plan:
        await call.answer("Tarif topilmadi.", show_alert=True)
        return

    status = db.get_premium_status(call.from_user.id)
    if status["is_vip"]:
        await call.answer("Sizda umrbod VIP allaqachon faol.", show_alert=True)
        return

    request = db.create_premium_request(call.from_user.id, plan_code)
    request_plan = PREMIUM_PLANS.get(request["plan_code"])
    if not request["created"]:
        await call.answer(
            f"Sizda #{request['id']} raqamli {request_plan['name']} so'rovi kutilmoqda.",
            show_alert=True,
        )
        return

    request_id = request["id"]
    username = f"@{call.from_user.username}" if call.from_user.username else "username yo'q"
    user_name = html.escape(call.from_user.full_name)
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Premium berish",
                callback_data=f"approve_premium:{request_id}",
            ),
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"reject_premium:{request_id}",
            ),
        ]
    ])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 <b>Premium so'rov #{request_id}</b>\n\n"
                f"Foydalanuvchi: <b>{user_name}</b>\n"
                f"Username: {username}\n"
                f"User ID: <code>{call.from_user.id}</code>\n"
                f"Tarif: <b>{plan['name']}</b>\n\n"
                f"Pul kelganidan keyin Premium berish tugmasini bosing.",
                reply_markup=admin_markup,
                parse_mode="HTML",
            )
        except Exception:
            logging.exception("Premium so'rovini adminga yuborib bo'lmadi")

    draft_text = quote(
        f"Assalomu alaykum! Premium so'rov #{request_id}. Tarif: {plan['name']}",
        safe="",
    )
    contact_url = f"{PAY_SUPPORT_URL}?text={draft_text}"
    await call.message.answer(
        f"✅ <b>So'rov #{request_id}</b> adminga yuborildi.\n"
        f"Tanlangan tarif: <b>{plan['name']}</b>\n\n"
        f"Quyidagi tugma orqali adminga yozing. So'rov matni tayyor turadi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Adminga yozish", url=contact_url)]
        ]),
        parse_mode="HTML",
    )
    await call.answer("So'rov yuborildi")

async def premium_expiry_warning_worker():
    while True:
        try:
            subscriptions = await asyncio.to_thread(
                db.claim_expiring_premium_notifications
            )
            for subscription in subscriptions:
                user_id = subscription["user_id"]
                expires_at = subscription["expires_at"]
                try:
                    status = await asyncio.to_thread(db.get_premium_status, user_id)
                    if (
                        not status["active"]
                        or status["is_vip"]
                        or status["expires_at"] != expires_at
                    ):
                        continue
                    expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                    await bot.send_message(
                        user_id,
                        "<b>Premium obunangiz tugashiga 1 kundan kam vaqt qoldi.</b>\n\n"
                        f"Tugash sanasi: <b>{expiry:%d.%m.%Y}</b>\n"
                        "Xohlasangiz, quyidagi tariflardan birini tanlab "
                        "Premium obunangizni uzaytirishingiz mumkin.",
                        reply_markup=premium_keyboard(),
                        parse_mode="HTML",
                    )
                except Exception:
                    await asyncio.to_thread(
                        db.release_premium_notification_claim,
                        user_id,
                        expires_at,
                    )
                    logging.exception(
                        "Premium tugash ogohlantirishini user %s ga yuborib bo'lmadi",
                        user_id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Premium tugash muddatini tekshirishda xatolik")

        await asyncio.sleep(15 * 60)

@dp.callback_query(F.data.startswith("approve_premium:"))
async def callback_approve_premium(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return

    request_id = int(call.data.split(":", maxsplit=1)[1])
    request = db.get_premium_request(request_id)
    plan = PREMIUM_PLANS.get(request["plan_code"]) if request else None
    if not request or not plan:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return

    result = db.approve_premium_request(request_id, call.from_user.id, plan["days"])
    if not result:
        await call.answer("Bu so'rov avval ko'rib chiqilgan.", show_alert=True)
        return

    await call.message.edit_text(
        f"✅ <b>Premium so'rov #{request_id} tasdiqlandi</b>\n\n"
        f"User ID: <code>{result['user_id']}</code>\n"
        f"Tarif: <b>{plan['name']}</b>\n"
        f"{format_premium_status(result)}",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(
            result["user_id"],
            f"✅ Sizga <b>{plan['name']}</b> Premium berildi.\n\n"
            f"{format_premium_status(result)}",
            parse_mode="HTML",
        )
    except Exception:
        logging.exception("Premium tasdiqini foydalanuvchiga yuborib bo'lmadi")
    await call.answer("Premium faollashtirildi")

@dp.callback_query(F.data.startswith("reject_premium:"))
async def callback_reject_premium(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return

    request_id = int(call.data.split(":", maxsplit=1)[1])
    result = db.reject_premium_request(request_id, call.from_user.id)
    if not result:
        await call.answer("Bu so'rov avval ko'rib chiqilgan.", show_alert=True)
        return

    plan = PREMIUM_PLANS.get(result["plan_code"])
    await call.message.edit_text(
        f"❌ <b>Premium so'rov #{request_id} rad etildi</b>\n\n"
        f"User ID: <code>{result['user_id']}</code>\n"
        f"Tarif: <b>{plan['name'] if plan else result['plan_code']}</b>",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(
            result["user_id"],
            f"❌ Premium so'rov #{request_id} rad etildi. "
            f"Batafsil ma'lumot uchun {PAY_SUPPORT_CONTACT} ga yozing.",
        )
    except Exception:
        logging.exception("Rad etish xabarini foydalanuvchiga yuborib bo'lmadi")
    await call.answer("So'rov rad etildi")

async def send_anime_or_check_sub(user_id: int, anime_id: int, msg: types.Message):
    not_subscribed = await check_subscriptions(user_id)
    if not_subscribed:
        await msg.answer(
            "⚠️ Anime olish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=subscription_keyboard(not_subscribed, anime_id)
        )
        return
    await deliver_anime(user_id, anime_id, msg)

# ─── Callback: Obunani tekshirish ─────────────────────────────────────────────

@dp.callback_query(F.data.startswith("check_sub:"))
async def callback_check_sub(call: CallbackQuery):
    anime_id = int(call.data.split(":")[1])
    not_subscribed = await check_subscriptions(call.from_user.id)

    if not_subscribed:
        await call.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        await call.message.edit_reply_markup(
            reply_markup=subscription_keyboard(not_subscribed, anime_id)
        )
        return

    await call.message.delete()
    await deliver_anime(call.from_user.id, anime_id, call.message)

# ─── Anime epizodlarini yuborish ──────────────────────────────────────────────

async def deliver_anime(user_id: int, anime_id: int, msg: types.Message):
    anime = db.get_anime(anime_id)
    if not anime:
        await bot.send_message(user_id, "❌ Anime topilmadi.")
        return

    if anime.get("is_premium") and not is_admin(user_id):
        status = db.get_premium_status(user_id)
        if not status["active"]:
            await send_premium_menu(user_id, anime["title"])
            return

    episodes = db.get_episodes(anime_id)
    if not episodes:
        await bot.send_message(user_id, "⚠️ Bu animening epizodlari hali yuklanmagan.")
        return

    await bot.send_message(
        user_id,
        f"🎬 <b>{anime['title']}</b>\n{anime['description']}\n\n📥 Epizodlar yuklanmoqda...",
        parse_mode="HTML"
    )

    current_season = None
    for ep in episodes:
        if ep["season"] != current_season:
            current_season = ep["season"]
            await bot.send_message(user_id, f"━━━ 📁 {current_season}-Fasl ━━━")
        caption = f"🎞 {anime['title']} | {ep['season']}-Fasl {ep['episode']}-Qism"
        await bot.send_video(user_id, ep["file_id"], caption=caption)

    await bot.send_message(user_id, "✅ Barcha epizodlar yuborildi!")

# ─── Admin: Anime qo'shish ────────────────────────────────────────────────────

@dp.callback_query(F.data == "add_anime_btn")
async def callback_add_anime(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    await state.set_state(AddAnimeState.waiting_title)
    await call.message.edit_text("🎬 Anime nomini yozing:")
    await call.answer()

@dp.message(AddAnimeState.waiting_title)
async def addanime_title(msg: types.Message, state: FSMContext):
    await state.update_data(title=msg.text)
    await state.set_state(AddAnimeState.waiting_desc)
    await msg.answer("📝 Anime tavsifini yozing (yoki /skip bosing):")

@dp.message(AddAnimeState.waiting_desc)
async def addanime_desc(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    desc = "" if msg.text == "/skip" else msg.text
    await state.update_data(desc=desc)
    await state.set_state(AddAnimeState.waiting_photo)
    await msg.answer("🖼 Anime posterni yuboring (yoki /skip bosing):")

@dp.message(AddAnimeState.waiting_photo, F.photo)
async def addanime_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = msg.photo[-1].file_id
    anime_id = db.add_anime(data["title"], data["desc"], photo_file_id)
    await state.clear()
    await msg.answer(
        f"✅ Anime qo'shildi!\n"
        f"🆔 ID: <b>{anime_id}</b>\n"
        f"📌 Nom: <b>{data['title']}</b>\n\n"
        f"Epizod qo'shish uchun /list bosing va anime tanlang.",
        parse_mode="HTML"
    )

@dp.message(AddAnimeState.waiting_photo)
async def addanime_photo_skip(msg: types.Message, state: FSMContext):
    # Faqat text xabarlari uchun (rasmlar uchun emas)
    if not msg.text:
        await msg.answer("❌ Iltimos, rasm faylni yuboring yoki /skip bosing!")
        return
    
    if msg.text == "/skip":
        data = await state.get_data()
        anime_id = db.add_anime(data["title"], data["desc"], None)
        await state.clear()
        await msg.answer(
            f"✅ Anime qo'shildi!\n"
            f"🆔 ID: <b>{anime_id}</b>\n"
            f"📌 Nom: <b>{data['title']}</b>\n\n"
            f"Epizod qo'shish uchun /list bosing va anime tanlang.",
            parse_mode="HTML"
        )
    else:
        await msg.answer("❌ Iltimos, rasm faylni yuboring yoki /skip bosing!")

# ─── Admin: Epizod qo'shish ───────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("add_episode:"))
async def callback_add_episode(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    await state.update_data(anime_id=anime_id, return_page=page)
    await state.set_state(AddEpisodeState.waiting_season)
    
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⬅️ Orqaga",
            callback_data=f"back_to_anime:{anime_id}:{page}",
        )]
    ])
    
    await call.message.edit_text(
        f"🎬 <b>{anime['title']}</b>\n\n"
        f"📁 Fasl raqamini yozing (masalan: 1):",
        reply_markup=back_kb,
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(AddEpisodeState.waiting_season)
async def addepisode_season(msg: types.Message, state: FSMContext):
    try:
        season = int(msg.text)
    except ValueError:
        await msg.answer("❌ Raqam kiriting:")
        return
    await state.update_data(season=season)
    await state.set_state(AddEpisodeState.waiting_episode)
    await msg.answer("🎞 Qism raqamini yozing (masalan: 1):")

@dp.message(AddEpisodeState.waiting_episode)
async def addepisode_episode(msg: types.Message, state: FSMContext):
    try:
        episode = int(msg.text)
    except ValueError:
        await msg.answer("❌ Raqam kiriting:")
        return
    await state.update_data(episode=episode)
    await state.set_state(AddEpisodeState.waiting_video)
    await msg.answer("📤 Endi videoni yuboring:")

@dp.message(AddEpisodeState.waiting_video, F.video)
async def addepisode_video(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = msg.video.file_id
    ep_id = db.add_episode(data["anime_id"], data["season"], data["episode"], file_id)
    anime = db.get_anime(data["anime_id"])
    await state.clear()
    await msg.answer(
        f"✅ Epizod saqlandi!\n"
        f"📌 {anime['title']} | {data['season']}-Fasl {data['episode']}-Qism\n"
        f"🆔 Epizod ID: {ep_id}"
    )

@dp.message(AddEpisodeState.waiting_video)
async def addepisode_not_video(msg: types.Message):
    await msg.answer("❌ Iltimos, video faylni yuboring!")

# ─── Admin: List va Control ───────────────────────────────────────────────────

ANIME_LIST_PAGE_SIZE = 8

async def show_list(user_id: int, msg_or_call, page: int = 0):
    """Ixcham va sahifalangan anime ro'yxatini ko'rsatish."""
    animes = db.list_animes_with_episode_counts()
    total_pages = max(1, (len(animes) + ANIME_LIST_PAGE_SIZE - 1) // ANIME_LIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * ANIME_LIST_PAGE_SIZE
    page_animes = animes[start:start + ANIME_LIST_PAGE_SIZE]
    premium_count = sum(bool(anime["is_premium"]) for anime in animes)

    text = (
        "🎬 <b>Anime boshqaruvi</b>\n\n"
        f"Jami: <b>{len(animes)}</b>  |  "
        f"⭐ Premium: <b>{premium_count}</b>  |  "
        f"🆓 Bepul: <b>{len(animes) - premium_count}</b>\n"
    )
    buttons = []

    if page_animes:
        text += f"Sahifa: <b>{page + 1}/{total_pages}</b>\n\nBoshqarish uchun anime tanlang:"
        for anime in page_animes:
            access_icon = "⭐" if anime["is_premium"] else "🆓"
            buttons.append([
                InlineKeyboardButton(
                    text=(
                        f"{access_icon} {anime['id']}. {anime['title']} "
                        f"| {anime['episode_count']} qism"
                    ),
                    callback_data=f"manage_anime:{anime['id']}:{page}",
                )
            ])
    else:
        text += "\nHali anime qo'shilmagan."

    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"list_page:{page - 1}")
            )
        navigation.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="list_noop")
        )
        if page < total_pages - 1:
            navigation.append(
                InlineKeyboardButton(text="➡️", callback_data=f"list_page:{page + 1}")
            )
        buttons.append(navigation)

    buttons.append([
        InlineKeyboardButton(text="➕ Yangi anime qo'shish", callback_data="add_anime_btn")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(msg_or_call, types.Message):
        await msg_or_call.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await msg_or_call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await msg_or_call.answer()

async def show_anime_management(call: CallbackQuery, anime_id: int, page: int = 0):
    anime = db.get_anime(anime_id)
    if not anime:
        await call.answer("Anime topilmadi.", show_alert=True)
        return False

    episode_count = db.get_episode_count(anime_id)
    access = "⭐ Premium" if anime.get("is_premium") else "🆓 Bepul"
    poster = "✅ Bor" if anime.get("photo_file_id") else "➖ Yo'q"
    title = html.escape(anime["title"])
    text = (
        f"🎬 <b>{title}</b>\n\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎞 Qismlar: <b>{episode_count}</b>\n"
        f"🔐 Holat: <b>{access}</b>\n"
        f"🖼 Poster: <b>{poster}</b>\n\n"
        "Kerakli amalni tanlang:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="➕ Epizod",
                callback_data=f"add_episode:{anime_id}:{page}",
            ),
            InlineKeyboardButton(
                text="✏️ Tahrirlash",
                callback_data=f"edit_anime:{anime_id}:{page}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🆓 Bepul qilish" if anime.get("is_premium") else "⭐ Premium qilish",
                callback_data=f"toggle_premium:{anime_id}:{page}",
            ),
            InlineKeyboardButton(
                text="📢 Kanalga",
                callback_data=f"post_confirm:{anime_id}:{page}",
            ),
        ],
        [InlineKeyboardButton(
            text="🗑 O'chirish",
            callback_data=f"delete_anime:{anime_id}:{page}",
        )],
        [InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data=f"list_page:{page}")],
    ])
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    return True

@dp.message(Command("list"))
async def cmd_list(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    await show_list(msg.from_user.id, msg)

@dp.callback_query(F.data == "back_to_list")
async def callback_back_to_list(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    await state.clear()
    await show_list(call.from_user.id, call)

@dp.callback_query(F.data.startswith("list_page:"))
async def callback_list_page(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    await state.clear()
    page = int(call.data.split(":", maxsplit=1)[1])
    await show_list(call.from_user.id, call, page)

@dp.callback_query(F.data == "list_noop")
async def callback_list_noop(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data.startswith("manage_anime:"))
async def callback_manage_anime(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    if await show_anime_management(call, anime_id, page):
        await call.answer()

@dp.callback_query(F.data.startswith("back_to_anime:"))
async def callback_back_to_anime(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    await state.clear()
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    if await show_anime_management(call, anime_id, page):
        await call.answer()

@dp.callback_query(F.data.startswith("toggle_premium:"))
async def callback_toggle_premium(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return

    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    if not anime:
        await call.answer("Anime topilmadi.", show_alert=True)
        return

    db.set_anime_premium(anime_id, not bool(anime.get("is_premium")))
    await show_anime_management(call, anime_id, page)
    await call.answer("Anime holati yangilandi.")

@dp.message(Command("help"))
async def cmd_help(msg: types.Message):
    help_text = (
        "<b>AniTime botdan foydalanish</b>\n\n"
        "<b>Anime olish:</b>\n"
        "Kanalimizdagi anime posti ostida joylashgan "
        "<b>Yuklab olish</b> tugmasini bosing. Bot kerakli anime va "
        "qismlarni sizga yuboradi.\n\n"
        "<b>Premium olish:</b>\n"
        "1. /premium buyrug'ini yuboring.\n"
        "2. Kerakli tarifni tanlang.\n"
        "3. <b>Adminga yozish</b> tugmasini bosing.\n"
        "4. To'lovni admin bilan kelishing.\n"
        "5. To'lov tasdiqlangach, Premium avtomatik faollashtiriladi.\n\n"
        "/premium_status - Premium muddatini tekshirish\n"
        "/paysupport - Premium bo'yicha adminga yozish"
    )

    if is_admin(msg.from_user.id):
        help_text += (
            "\n\n<b>Admin boshqaruvi:</b>\n"
            "/list - barcha animelarni boshqarish\n"
            "/help - ushbu yordam\n\n"
            "Premium so'rovlari tasdiqlash va rad etish tugmalari bilan "
            "sizga avtomatik keladi.\n\n"
            "<b>List menyusida:</b>\n"
            "Yangi anime qo'shish\n"
            "Epizod qo'shish\n"
            "Anime tahrirlash\n"
            "Animeni o'chirish\n"
            "Anime turini Bepul yoki Premium qilish\n"
            "Kanalga post qilish"
        )

    await msg.answer(help_text, parse_mode="HTML")

# ─── Post to Channel Logic ───────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("post_confirm:"))
async def callback_post_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    if not anime:
        await call.answer("Anime topilmadi.", show_alert=True)
        return

    await call.message.edit_text(
        f"📢 <b>{html.escape(anime['title'])}</b> ni kanalga joylaysizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Kanalga joylash",
                callback_data=f"post_anime:{anime_id}:{page}",
            )],
            [InlineKeyboardButton(
                text="⬅️ Bekor qilish",
                callback_data=f"manage_anime:{anime_id}:{page}",
            )],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@dp.callback_query(F.data.startswith("post_anime:"))
async def callback_post_anime(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    posted = await share_to_channel(call.from_user.id, anime_id)
    if posted:
        await show_anime_management(call, anime_id, page)
        await call.answer("Kanalga joylandi.")
    else:
        await call.answer("Kanalga joylashda xatolik yuz berdi.", show_alert=True)

async def share_to_channel(admin_id: int, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        await bot.send_message(admin_id, "❌ Anime topilmadi.")
        return False

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=anime_{anime_id}"
    title = html.escape(anime["title"])
    description = html.escape(anime.get("description") or "")
    
    text = (
        f"🎬 <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"{'⭐ Premium anime' if anime.get('is_premium') else '🆓 Bepul anime'}\n\n"
        f"📥 Animeni ko'rish uchun quyidagi tugmani bosing:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Ko'rish", url=link)]
    ])
    
    try:
        if anime['photo_file_id']:
            await bot.send_photo(
                chat_id=POST_CHANNEL,
                photo=anime['photo_file_id'],
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=POST_CHANNEL,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        return True
    except Exception as e:
        await bot.send_message(admin_id, f"❌ Kanalga joylashda xatolik: {str(e)}")
        return False

# ─── Admin: O'chirish (Delete) ───────────────────────────────────────────────

@dp.callback_query(F.data.startswith("delete_anime:"))
async def callback_delete_anime(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Ha, o'chirish",
                callback_data=f"confirm_delete:{anime_id}:{page}",
            ),
            InlineKeyboardButton(
                text="❌ Bekor qilish",
                callback_data=f"cancel_delete:{anime_id}:{page}",
            ),
        ]
    ])
    
    await call.message.edit_text(
        f"⚠️ <b>{html.escape(anime['title'])}</b> ni haqiqatan ham "
        "o'chirib tashlamoqchisiz?\n"
        f"Bu amalni qaytarib bo'lmaydi!",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_delete:"))
async def callback_confirm_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    if not anime:
        await call.answer("Anime topilmadi.", show_alert=True)
        return

    db.delete_anime(anime_id)
    await call.message.edit_text(
        f"🗑 <b>{html.escape(anime['title'])}</b> o'chirib tashlandi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Ro'yxatga", callback_data=f"list_page:{page}")]
        ]),
        parse_mode="HTML",
    )
    await call.answer("✅ Anime o'chirib tashlandi!")

@dp.callback_query(F.data.startswith("cancel_delete:"))
async def callback_cancel_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    if await show_anime_management(call, anime_id, page):
        await call.answer()

# ─── Admin: Tahrirlash (Edit) ────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("edit_anime:"))
async def callback_edit_anime(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Bu amal faqat admin uchun.", show_alert=True)
        return
    parts = call.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    await state.update_data(edit_anime_id=anime_id, return_page=page)
    await state.set_state(EditAnimeState.waiting_title)
    
    edit_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⬅️ Bekor qilish",
            callback_data=f"back_to_anime:{anime_id}:{page}",
        )]
    ])
    
    await call.message.edit_text(
        f"✏️ <b>{anime['title']}</b> ni tahrirlash\n\n"
        f"Yangi nomini yozing (yoki /skip bosing):",
        reply_markup=edit_kb,
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(EditAnimeState.waiting_title)
async def edit_anime_title(msg: types.Message, state: FSMContext):
    if msg.text and msg.text.startswith("/") and msg.text != "/skip":
        await state.clear()
        if msg.text == "/list":
            return await cmd_list(msg)
        return
    
    if msg.text == "/skip":
        await state.set_state(EditAnimeState.waiting_desc)
        await msg.answer("📝 Yangi tavsifni yozing (yoki /skip bosing):")
    else:
        await state.update_data(edit_title=msg.text)
        await state.set_state(EditAnimeState.waiting_desc)
        await msg.answer("📝 Yangi tavsifni yozing (yoki /skip bosing):")

@dp.message(EditAnimeState.waiting_desc)
async def edit_anime_desc(msg: types.Message, state: FSMContext):
    if msg.text and msg.text.startswith("/") and msg.text != "/skip":
        await state.clear()
        if msg.text == "/list":
            return await cmd_list(msg)
        return
    
    if msg.text == "/skip":
        await state.set_state(EditAnimeState.waiting_photo)
        await msg.answer("🖼️ Yangi poster rasmini yuboring (yoki /skip bosing):")
    else:
        await state.update_data(edit_desc=msg.text)
        await state.set_state(EditAnimeState.waiting_photo)
        await msg.answer("🖼️ Yangi poster rasmini yuboring (yoki /skip bosing):")

@dp.message(EditAnimeState.waiting_photo, F.photo)
async def edit_anime_photo(msg: types.Message, state: FSMContext):
    photo_file_id = msg.photo[-1].file_id
    data = await state.get_data()
    anime_id = data['edit_anime_id']
    anime = db.get_anime(anime_id)
    title = data.get('edit_title', anime['title'])
    desc = data.get('edit_desc', anime['description'])
    
    db.update_anime(anime_id, title, desc, photo_file_id)
    await state.clear()
    await msg.answer(f"✅ <b>{title}</b> muvaffaqiyatli tahrirlandi!", parse_mode="HTML")

@dp.message(EditAnimeState.waiting_photo)
async def edit_anime_photo_skip(msg: types.Message, state: FSMContext):
    if not msg.text:
        await msg.answer("❌ Iltimos, rasm yuboring yoki /skip bosing!")
        return
    
    if msg.text.startswith("/") and msg.text != "/skip":
        await state.clear()
        if msg.text == "/list":
            return await cmd_list(msg)
        return
    
    if msg.text == "/skip":
        data = await state.get_data()
        anime_id = data['edit_anime_id']
        anime = db.get_anime(anime_id)
        title = data.get('edit_title', anime['title'])
        desc = data.get('edit_desc', anime['description'])
        
        db.update_anime(anime_id, title, desc, anime['photo_file_id'])
        await state.clear()
        await msg.answer(f"✅ <b>{title}</b> muvaffaqiyatli tahrirlandi!", parse_mode="HTML")
    else:
        await msg.answer("❌ Iltimos, rasm yuboring yoki /skip bosing!")

@dp.callback_query(F.data == "cancel_edit")
async def callback_cancel_edit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_list(call.from_user.id, call)

# ─── Bot buyruqlar menyusi ────────────────────────────────────────────────────

async def set_commands():
    """Telegram pastki input qismida chiquvchi buyruqlar menyusi"""
    user_commands = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="help", description="Botdan foydalanish bo'yicha yordam"),
        BotCommand(command="premium", description="Premium olish"),
        BotCommand(command="premium_status", description="Obuna holatini tekshirish"),
        BotCommand(command="paysupport", description="Premium bo'yicha yordam"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        BotCommand(command="start",  description="Botni ishga tushirish"),
        BotCommand(command="premium", description="Premium olish"),
        BotCommand(command="premium_status", description="Obuna holatini tekshirish"),
        BotCommand(command="paysupport", description="Premium bo'yicha yordam"),
        BotCommand(command="list",   description="📋 Barcha animelar menus"),
        BotCommand(command="help",   description="🛠 Yordam"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception:
            pass

# ─── Render Health Check Server ───────────────────────────────────────────────

from aiohttp import web

async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
        logging.info("Health check server started on port %s", port)
    except OSError as e:
        logging.warning("Health check server port %s band: %s", port, e)

# ─── Run ──────────────────────────────────────────────────────────────────────

async def main():
    await set_commands()
    # Web serverni fonda ishga tushirish
    asyncio.create_task(start_web_server())
    warning_task = asyncio.create_task(premium_expiry_warning_worker())
    try:
        await dp.start_polling(bot)
    finally:
        warning_task.cancel()
        await asyncio.gather(warning_task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
