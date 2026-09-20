import os
import logging
from aiogram import Bot, Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database.connection import AsyncSessionLocal
from database.crud import (
    get_lesson_by_day, 
    get_max_day_number, 
    save_generated_lesson,
    get_current_publishing_day,
    set_current_publishing_day
)
from generator.gemini_pipeline import generate_daily_lesson
from generator.topics import DEFAULT_TOPICS
from bot.scheduler import job_morning_words, job_afternoon_quiz, job_evening_text

router = Router()
logger = logging.getLogger(__name__)

# ID адмінів з .env
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

def is_admin(user_id: int) -> bool:
    """Перевірка чи користувач є адміном."""
    return not ADMIN_IDS or user_id in ADMIN_IDS


def get_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Постійна клавіатура внизу екрана для швидкого доступу."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Згенерувати наступний"), KeyboardButton(text="📊 Статус БД")],
            [KeyboardButton(text="👁 Переглянути завтра"), KeyboardButton(text="📤 Меню публікацій")] # <--- Прибрали рядок із "Запушити день зараз"
        ],
        resize_keyboard=True
    )


# --- 1. /start з меню адміна та нижньою клавіатурою ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("¡Hola! Це бот автопостингу курсів іспанської мови.")
        return

    text = (
        "⚙️ <b>Панель управління адміна:</b>\n\n"
        "<b>Доступні команди:</b>\n"
        "🔹 /generate [Рівень] [Тема] — Згенерувати тему (напр. <code>/generate A2 майбутній час</code>)\n"
        "🔹 /show — Переглянути запланований контент на завтра\n"
        "🔹 /set_day [N] — Встановити поточний день публікацій (напр. /set_day 1)\n"
        "🔹 /force_today — Запушити всі пости дня в канал прямо зараз\n"
        "🔹 /publish — Опублікувати ранок/квіз/вечір ОКРЕМО\n"
        "🔹 /status — Стан бази даних та черги контенту\n\n"
        "<i>💡 Також ви можете надіслати сюди картинку чи відео з підписом, і я опублікую їх у канал!</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✨ Згенерувати", callback_data="admin_generate"),
            InlineKeyboardButton(text="👁 Переглянути завтра", callback_data="admin_show")
        ],
        [
            InlineKeyboardButton(text="📊 Стан БД", callback_data="admin_status"),
            #InlineKeyboardButton(text="🚀 Запушити день зараз", callback_data="admin_force_today")
        ],
        [
            InlineKeyboardButton(text="📤 Публікація частинами", callback_data="admin_publish_menu")
        ]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await message.answer("Скористайтеся кнопками керування нижче 👇", reply_markup=get_admin_reply_keyboard())


# --- Обробники кнопок нижньої панелі ---

@router.message(F.text == "✨ Згенерувати наступний")
async def btn_generate(message: types.Message, bot: Bot):
    if is_admin(message.from_user.id):
        await cmd_generate(message, bot)

@router.message(F.text == "📊 Статус БД")
async def btn_status(message: types.Message):
    if is_admin(message.from_user.id):
        await cmd_status(message)

@router.message(F.text == "👁 Переглянути завтра")
async def btn_show(message: types.Message):
    if is_admin(message.from_user.id):
        await cmd_show(message)

@router.message(F.text == "🚀 Запушити день зараз")
async def btn_force(message: types.Message, bot: Bot):
    if is_admin(message.from_user.id):
        await cmd_force_today(message, bot)

@router.message(F.text == "📤 Меню публікацій")
async def btn_publish(message: types.Message):
    if is_admin(message.from_user.id):
        await cmd_publish_menu(message)


# --- 2. /status — Перевірка стану контенту ---

@router.message(Command("status"))
@router.callback_query(F.data == "admin_status")
async def cmd_status(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    async with AsyncSessionLocal() as session:
        max_day = await get_max_day_number(session)
        current_day = await get_current_publishing_day(session)

    text = f"📊 <b>Статус системи:</b>\n\n"
    text += f"• Всього готово днів у БД: <b>{max_day}</b>\n"
    text += f"• 🎯 <b>Заплановано на наступну публікацію: Урок №{current_day}</b>"

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, parse_mode="HTML")
    else:
        await event.answer(text, parse_mode="HTML")


# --- 3. /generate — Генерація уроку (підтримка довільних тем та рівнів) ---

@router.message(Command("generate"))
@router.callback_query(F.data == "admin_generate")
async def cmd_generate(event: types.Message | types.CallbackQuery, bot: Bot = None):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, types.CallbackQuery):
        await event.answer("Запускаємо генерацію...")
        msg = event.message
    else:
        msg = event

    # Парсинг аргументів команди (наприклад: /generate A2 утворення майбутнього часу)
    text_payload = msg.text if hasattr(msg, "text") and msg.text else ""
    args = text_payload.split(maxsplit=2)
    
    custom_level = "A1"
    custom_topic_ua = None

    if len(args) >= 2:
        potential_level = args[1].upper()
        if potential_level in ["A1", "A2", "B1", "B2"]:
            custom_level = potential_level
            if len(args) >= 3:
                custom_topic_ua = args[2]
        else:
            custom_topic_ua = text_payload.replace("/generate", "").strip()

    status_msg = await msg.answer(f"⏳ Генерація уроку (рівень {custom_level}) через Gemini API (~15 сек)...")

    try:
        async with AsyncSessionLocal() as session:
            max_day = await get_max_day_number(session)
            next_day = max_day + 1
            
            if custom_topic_ua:
                topic_ua = custom_topic_ua
                topic_es = custom_topic_ua
            else:
                topic_info = DEFAULT_TOPICS[(next_day - 1) % len(DEFAULT_TOPICS)]
                topic_ua = topic_info["ua"]
                topic_es = topic_info["es"]

            lesson_data = await generate_daily_lesson(
                topic_ua=topic_ua,
                topic_es=topic_es,
                level=custom_level,
                day_number=next_day
            )
            await save_generated_lesson(session, lesson_data)

        await status_msg.edit_text(
            f"✅ <b>Урок №{next_day} ({topic_ua}) [Рівень {custom_level}] успішно згенеровано!</b>\n"
            f"Введіть /show для перегляду та підтвердження.", 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка при адмін-генерації: {e}")
        await status_msg.edit_text(f"❌ Помилка під час генерації: {e}")


# --- 4. /force_today — Екстрена публікація всіх постів дня ---

@router.message(Command("force_today"))
async def cmd_force_today(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)

    status_msg = await message.answer(f"🚀 Запускаємо публікацію всіх постів для <b>Уроку №{current_day}</b> у канал...", parse_mode="HTML")

    try:
        await status_msg.edit_text(f"⏳ [1/3] Публікація ранкових слів (День {current_day})...")
        await job_morning_words(bot)

        await status_msg.edit_text(f"⏳ [2/3] Публікація обіднього квізу (День {current_day})...")
        await job_afternoon_quiz(bot)

        await status_msg.edit_text(f"⏳ [3/3] Публікація вечірнього тексту (День {current_day})...")
        await job_evening_text(bot)

        await status_msg.edit_text(f"✅ <b>Усі публікації для Уроку №{current_day} успішно відправлено в канал!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка при ручній публікації дня {current_day}: {e}")
        await status_msg.edit_text(f"❌ Помилка під час відправки: {e}")


@router.callback_query(F.data == "admin_force_today")
async def callback_force_today(callback: types.CallbackQuery, bot: Bot):
    await callback.answer("Запускаємо постинг...")
    await cmd_force_today(callback.message, bot)


# --- 5. /show — Перегляд контенту та модерація ---

@router.message(Command("show"))
@router.callback_query(F.data == "admin_show")
async def cmd_show(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        lesson = await get_lesson_by_day(session, current_day)

        if not lesson:
            await msg.answer(f"⚠️ Урок №{current_day} ще не згенеровано в БД. Введіть /generate.")
            return

    text = f"🔍 <b>Запланований контент на наступну публікацію (Урок №{lesson.day_number}):</b>\n\n"
    text += f"📌 <b>Тема:</b> {lesson.topic.title_es} ({lesson.topic.title_ua})\n\n"
    text += f"☀️ <b>Слів у блоці:</b> {len(lesson.words)}\n"
    for w in lesson.words:
        text += f"  • {w.text_es} — {w.text_ua}\n"

    if lesson.quizzes:
        q = lesson.quizzes[0]
        q_ua = getattr(q, 'question_ua', None)
        text += f"\n🌤 <b>Питання квізу:</b> {q.question_es}\n"
        if q_ua:
            text += f"<i>({q_ua})</i>\n"
    else:
        text += f"\n🌤 <b>Питання квізу:</b> Немає\n"

    text += f"\n🌙 <b>Граматика:</b> {lesson.grammar_rule_title}\n"
    text += f"<i>{lesson.evening_text_es}</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити (ОК)", callback_data=f"confirm_day_{lesson.day_number}"),
            InlineKeyboardButton(text="🔄 Перегенерувати", callback_data=f"regenerate_day_{lesson.day_number}")
        ]
    ])

    await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)


# --- 6. /set_day — Зміна поточного дня публікацій ---

@router.message(Command("set_day"))
async def cmd_set_day(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Вкажіть номер дня! Приклад: <code>/set_day 1</code>", parse_mode="HTML")
        return

    new_day = int(args[1])
    async with AsyncSessionLocal() as session:
        max_day = await get_max_day_number(session)
        if new_day > max_day:
            await message.answer(
                f"⚠️ Увага: Урок №{new_day} ще не згенеровано у БД (максимальний доступний: {max_day}).\n"
                f"Спочатку згенеруйте контент через /generate.",
                parse_mode="HTML"
            )
            return

        await set_current_publishing_day(session, new_day)

    await message.answer(f"🎯 <b>Поточний день публікацій успішно змінено на №{new_day}!</b>", parse_mode="HTML")


# --- 7. Обробка кнопок підтвердження та перегенерації ---

@router.callback_query(F.data.startswith("confirm_day_"))
async def process_confirm(callback: types.CallbackQuery):
    await callback.answer("Підтверджено!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ <b>Урок успішно підтверджено до публікації!</b>", 
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("regenerate_day_"))
async def process_regenerate(callback: types.CallbackQuery):
    await callback.answer("Перезапуск генерації...")
    
    day_num = int(callback.data.split("_")[-1])
    await callback.message.edit_text(f"🔄 Запускаємо перезапис та перегенерацію для уроку №{day_num}...")

    try:
        async with AsyncSessionLocal() as session:
            topic_info = DEFAULT_TOPICS[(day_num - 1) % len(DEFAULT_TOPICS)]
            
            lesson_data = await generate_daily_lesson(
                topic_ua=topic_info["ua"],
                topic_es=topic_info["es"],
                level="A1",
                day_number=day_num
            )
            await save_generated_lesson(session, lesson_data)

        await callback.message.answer(
            f"🎉 <b>Урок №{day_num} успішно перегенеровано та перезаписано в БД!</b>\n"
            f"Натисніть /show для перевірки.", 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка при перегенерації: {e}")
        await callback.message.answer(f"❌ Помилка під час перегенерації: {e}")


# --- 8. Ручна публікація медіа (фото, відео, документи) в канал ---

@router.message(F.photo | F.video | F.document)
async def forward_media_to_channel(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    channel_id = os.getenv("CHANNEL_ID")
    if not channel_id:
        await message.answer("⚠️ Не вказано `CHANNEL_ID` у файлі .env!")
        return

    try:
        await message.send_copy(chat_id=channel_id)
        await message.answer("✅ Медіа успішно опубліковано в канал!")
    except Exception as e:
        logger.error(f"Помилка при публікації медіа в канал: {e}")
        await message.answer(f"❌ Не вдалося опублікувати: {e}")


# --- 9. Меню ручної публікації частин уроку ---

def get_publish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Ранок (слова)", callback_data="publish_morning")],
        [InlineKeyboardButton(text="🌤 Обід (квіз)", callback_data="publish_afternoon")],
        [InlineKeyboardButton(text="🌙 Вечір (граматика)", callback_data="publish_evening")],
        [InlineKeyboardButton(text="🚀 Все одразу", callback_data="admin_force_today")],
    ])


@router.message(Command("publish"))
@router.callback_query(F.data == "admin_publish_menu")
async def cmd_publish_menu(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)

    await msg.answer(
        f"📤 <b>Ручна публікація для Уроку №{current_day}</b>\n\n"
        f"Оберіть, яку частину відправити в канал прямо зараз:",
        parse_mode="HTML",
        reply_markup=get_publish_keyboard()
    )


async def _publish_part(callback: types.CallbackQuery, bot: Bot, job_func, label: str):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer(f"Публікую: {label}")

    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)

    status_msg = await callback.message.answer(f"⏳ Публікація «{label}» (Урок №{current_day})...")
    try:
        await job_func(bot)
        await status_msg.edit_text(f"✅ «{label}» опубліковано (Урок №{current_day})!")
    except Exception as e:
        logger.error(f"Помилка ручної публікації '{label}': {e}")
        await status_msg.edit_text(f"❌ Помилка публікації: {e}")


@router.callback_query(F.data == "publish_morning")
async def callback_publish_morning(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_morning_words, "☀️ Ранкові слова")


@router.callback_query(F.data == "publish_afternoon")
async def callback_publish_afternoon(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_afternoon_quiz, "🌤 Обідній квіз")


@router.callback_query(F.data == "publish_evening")
async def callback_publish_evening(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_evening_text, "🌙 Вечірній текст (день буде +1)")
