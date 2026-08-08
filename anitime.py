import asyncio
import logging
import os
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

from config import TOKEN, ADMIN_IDS, REQUIRED_CHANNELS, POST_CHANNEL
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
        "📺 Kanal postidagi <b>Yuklab olish</b> tugmasini bosing va animelarni olish uchun foydalaning.",
        parse_mode="HTML"
    )

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
    anime_id = int(call.data.split(":")[1])
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    await state.update_data(anime_id=anime_id)
    await state.set_state(AddEpisodeState.waiting_season)
    
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="back_to_list")]
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

async def show_list(user_id: int, msg_or_call):
    """List menyu ko'rsatish"""
    animes = db.list_animes_with_episode_counts()
    text = "📋 <b>Barcha animelar:</b>\n\n"
    buttons = []
    
    if animes:
        for a in animes:
            text += f"🆔 {a['id']} | 🎬 {a['title']} ({a['episode_count']} ta epizod)\n"
            buttons.append([
                InlineKeyboardButton(text=f"➕ Epizod", callback_data=f"add_episode:{a['id']}"),
                InlineKeyboardButton(text=f"✏️ Edit", callback_data=f"edit_anime:{a['id']}"),
                InlineKeyboardButton(text=f"🗑️ O'chirish", callback_data=f"delete_anime:{a['id']}")
            ])
            buttons.append([
                InlineKeyboardButton(text=f"📢 {a['title']} -> Kanal", callback_data=f"post_confirm:{a['id']}")
            ])
    else:
        text += "Hali anime qo'shilmagan.\n"
    
    buttons.append([
        InlineKeyboardButton(text="➕ Yangi anime qo'shish", callback_data="add_anime_btn")
    ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    if isinstance(msg_or_call, types.Message):
        await msg_or_call.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await msg_or_call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await msg_or_call.answer()

@dp.message(Command("list"))
async def cmd_list(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    await show_list(msg.from_user.id, msg)

@dp.callback_query(F.data == "back_to_list")
async def callback_back_to_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_list(call.from_user.id, call)

@dp.message(Command("help"))
async def cmd_help(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer(
        "🛠 <b>Admin komandalari:</b>\n\n"
        "/list — barcha animelar, yangi qo'shish, epizod qo'shish\n"
        "/help — ushbu yordam\n\n"
        "<b>🎬 List menusida:</b>\n"
        "➕ Yangi anime qo'shish\n"
        "➕ Epizod qo'shish\n"
        "✏️ Anime tahrirlash\n"
        "🗑️ Animeni o'chirish\n"
        "📢 Kanalga post qilish",
        parse_mode="HTML"
    )

# ─── Post to Channel Logic ───────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("post_confirm:"))
async def callback_post_confirm(call: CallbackQuery):
    anime_id = int(call.data.split(":")[1])
    await share_to_channel(call.from_user.id, anime_id)
    await call.answer("Kanalga yuborildi!")

async def share_to_channel(admin_id: int, anime_id: int):
    anime = db.get_anime(anime_id)
    if not anime:
        await bot.send_message(admin_id, "❌ Anime topilmadi.")
        return

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=anime_{anime_id}"
    
    text = (
        f"🎬 <b>{anime['title']}</b>\n\n"
        f"{anime['description']}\n\n"
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
        await bot.send_message(admin_id, f"✅ <b>{anime['title']}</b> kanalga joylandi!")
    except Exception as e:
        await bot.send_message(admin_id, f"❌ Kanalga joylashda xatolik: {str(e)}")

# ─── Admin: O'chirish (Delete) ───────────────────────────────────────────────

@dp.callback_query(F.data.startswith("delete_anime:"))
async def callback_delete_anime(call: CallbackQuery):
    anime_id = int(call.data.split(":")[1])
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Albatta o'chirish", callback_data=f"confirm_delete:{anime_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_delete:{anime_id}")
        ]
    ])
    
    await call.message.edit_text(
        f"⚠️ <b>{anime['title']}</b> ni haqiqatan ham o'chirib tashlamoqchisiz?\n"
        f"Bu amalni qaytarib bo'lmaydi!",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_delete:"))
async def callback_confirm_delete(call: CallbackQuery):
    anime_id = int(call.data.split(":")[1])
    anime = db.get_anime(anime_id)
    
    db.delete_anime(anime_id)
    await call.message.edit_text(f"🗑️ <b>{anime['title']}</b> o'chirib tashlandi!", parse_mode="HTML")
    await call.answer("✅ Anime o'chirib tashlandi!")

@dp.callback_query(F.data.startswith("cancel_delete:"))
async def callback_cancel_delete(call: CallbackQuery):
    await show_list(call.from_user.id, call)

# ─── Admin: Tahrirlash (Edit) ────────────────────────────────────────────────

@dp.callback_query(F.data.startswith("edit_anime:"))
async def callback_edit_anime(call: CallbackQuery, state: FSMContext):
    anime_id = int(call.data.split(":")[1])
    anime = db.get_anime(anime_id)
    
    if not anime:
        await call.answer("❌ Anime topilmadi!", show_alert=True)
        return
    
    await state.update_data(edit_anime_id=anime_id)
    await state.set_state(EditAnimeState.waiting_title)
    
    edit_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Foydalanishdan voz kechish", callback_data="cancel_edit")]
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
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        BotCommand(command="start",  description="Botni ishga tushirish"),
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
