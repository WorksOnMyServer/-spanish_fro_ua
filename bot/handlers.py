import os
import logging
from aiogram import Bot, Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.connection import AsyncSessionLocal
from database.crud import (
    get_lesson_by_day, 
    get_max_day_number, 
    save_generated_lesson,
    get_current_publishing_day,
    set_current_publishing_day
)
from generator.gemini_pipeline import generate_daily_lesson
<<<<<<< HEAD
from generator.topics import DEFAULT_TOPICS
=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
from bot.scheduler import job_morning_words, job_afternoon_quiz, job_evening_text

router = Router()
logger = logging.getLogger(__name__)

# ID адмінів з .env
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

<<<<<<< HEAD
=======
# Розширений список 50 тем для рівнів A1-A2
DEFAULT_TOPICS = [
    {"ua": "Знайомство та привітання", "es": "Saludos y presentaciones"},
#    {"ua": "Алфавіт та вимова", "es": "El alfabeto y la pronunciación"},
    {"ua": "Числа від 0 до 100", "es": "Los números del 0 al 100"},
    {"ua": "Дні тижня та місяці", "es": "Los días de la semana y los meses"},
    {"ua": "Пори року та погода", "es": "Las estaciones y el tiempo"},
    {"ua": "Кольори та форми", "es": "Los colores y las formas"},
    {"ua": "Сім'я та родичі", "es": "La familia y los parientes"},
    {"ua": "Опис зовнішності та характеру", "es": "Descripción física y de carácter"},
    {"ua": "Професії та діяльність", "es": "Las profesiones y los oficios"},
    {"ua": "Країни та національності", "es": "Países y nacionalidades"},
    {"ua": "Мови світу", "es": "Las lenguas del mundo"},
    {"ua": "Особисті дані та анкета", "es": "Datos personales y formulario"},
    {"ua": "Мій дім та квартира", "es": "Mi casa y mi piso"},
    {"ua": "Меблі та інтер'єр", "es": "Los muebles y la decoración"},
    {"ua": "Побутова техніка", "es": "Los electrodomésticos"},
    {"ua": "Одяг та взуття", "es": "La ropa y el calzado"},
    {"ua": "Аксесуари та прикраси", "es": "Los accesorios y las joyas"},
    {"ua": "Їжа та основні продукты", "es": "La comida y los alimentos básicos"},
    {"ua": "Фрукти та овочі", "es": "Las frutas y las verduras"},
    {"ua": "Напої", "es": "Las bebidas"},
    {"ua": "В ресторані та кафе", "es": "En el restaurante y la cafetería"},
    {"ua": "Покупки та супермаркет", "es": "Las compras y el supermercado"},
    {"ua": "Ціни та гроші", "es": "Los precios y el dinero"},
    {"ua": "Розпорядок дня", "es": "La rutina diaria"},
    {"ua": "Годинник та час", "es": "El reloj y la hora"},
    {"ua": "Вільний час та хобі", "es": "El tiempo libre y los aficiones"},
    {"ua": "Спорт та активність", "es": "El deporte y la actividad física"},
    {"ua": "Музика та мистецтво", "es": "La música y el arte"},
    {"ua": "Місто та його інфраструктура", "es": "La ciudad y la infraestructura"},
    {"ua": "Орієнтування в місті та напрямки", "es": "Pedir y dar direcciones"},
    {"ua": "Транспорт та квитки", "es": "El transporte y los billetes"},
    {"ua": "Подорожі та відпочинок", "es": "Los viajes y las vacaciones"},
    {"ua": "В готелі", "es": "En el hotel"},
    {"ua": "На аеропорту та вокзалі", "es": "En el aeropuerto y la estación"},
    {"ua": "Тварини (домашні та дикі)", "es": "Los animales (domésticos y salvajes)"},
    {"ua": "Природа та навколишнє середовище", "es": "La naturaleza y el medio ambiente"},
    {"ua": "Частини тіла", "es": "Las partes del cuerpo"},
    {"ua": "Здоров'я та самопочуття", "es": "La salud y el estado físico"},
    {"ua": "У лікаря та в аптеці", "es": "En el médico y en la farmacia"},
    {"ua": "Навчання та школа", "es": "Los estudios y la escuela"},
    {"ua": "Шкільне та офісне приладдя", "es": "El material escolar y de oficina"},
    {"ua": "Робочий день та офіс", "es": "El día laborable y la oficina"},
    {"ua": "Свята та традиції", "es": "Las fiestas y las tradiciones"},
    {"ua": "Дні народження та подарунки", "es": "Los cumpleaños y los regalos"},
    {"ua": "Емоції та почуття", "es": "Las emociones y los sentimientos"},
    {"ua": "Вподобання (що подобається і ні)", "es": "Gustos y preferencias"},
    {"ua": "Географія та сторони світу", "es": "La geografía y los puntos cardinales"},
    {"ua": "Технології та гаджети", "es": "La tecnología y los dispositivos"},
    {"ua": "Соціальні мережі та інтернет", "es": "Las redes sociales e internet"},
    {"ua": "Плани на майбутнє", "es": "Planes para el futuro"}
]

>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
def is_admin(user_id: int) -> bool:
    """Перевірка чи користувач є адміном."""
    return not ADMIN_IDS or user_id in ADMIN_IDS


# --- 1. /start з меню адміна ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("¡Hola! Це бот автопостингу курсів іспанської мови.")
        return

    text = (
        "⚙️ <b>Панель управління адміна:</b>\n\n"
        "<b>Доступні команди:</b>\n"
        "🔹 /generate — Згенерувати наступний день через Gemini\n"
        "🔹 /show — Переглянути запланований контент на завтра\n"
        "🔹 /set_day [N] — Встановити поточний день публікацій (напр. /set_day 1)\n"
        "🔹 /force_today — Запушити всі пости дня в канал прямо зараз\n"
<<<<<<< HEAD
        "🔹 /publish — Опублікувати ранок/квіз/вечір ОКРЕМО, без прив'язки до таймера\n"
=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
        "🔹 /status — Стан бази даних та черги контенту\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✨ Згенерувати", callback_data="admin_generate"),
            InlineKeyboardButton(text="👁 Переглянути завтра", callback_data="admin_show")
        ],
        [
            InlineKeyboardButton(text="📊 Стан БД", callback_data="admin_status"),
            InlineKeyboardButton(text="🚀 Запушити день зараз", callback_data="admin_force_today")
<<<<<<< HEAD
        ],
        [
            InlineKeyboardButton(text="📤 Публікація частинами", callback_data="admin_publish_menu")
=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
        ]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


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


# --- 3. /generate — Генерація нового дня через Gemini ---

@router.message(Command("generate"))
@router.callback_query(F.data == "admin_generate")
async def cmd_generate(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, types.CallbackQuery):
        await event.answer("Запускаємо генерацію...")
        msg = event.message
    else:
        msg = event

    status_msg = await msg.answer("⏳ Генерація нового уроку та аудіофайлів через Gemini API (~15 сек)...")

    try:
        async with AsyncSessionLocal() as session:
            max_day = await get_max_day_number(session)
            next_day = max_day + 1
            
            topic_info = DEFAULT_TOPICS[(next_day - 1) % len(DEFAULT_TOPICS)]

            lesson_data = await generate_daily_lesson(
                topic_ua=topic_info["ua"],
                topic_es=topic_info["es"],
                level="A1",
                day_number=next_day
            )
            await save_generated_lesson(session, lesson_data)

        await status_msg.edit_text(
            f"✅ <b>Урок №{next_day} ({topic_info['ua']}) успішно згенеровано!</b>\n"
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
<<<<<<< HEAD


# --- 8. Ручна публікація ОКРЕМИХ частин уроку (незалежно від APScheduler) ---
#
# job_morning_words / job_afternoon_quiz / job_evening_text — це ті самі
# функції, що викликає таймер (bot/scheduler.py). Тут вони просто
# запускаються вручну, по одній, без очікування 08:30 / 12:30 / 18:30.
#
# ⚠️ Важливий нюанс: job_evening_text сама інкрементує
# current_publishing_day в БД (переводить бота на наступний день).
# Це поведінка самої job-функції, і вона зберігається тут теж —
# ручний запуск вечірньої частини так само посуне лічильник дня вперед.

def get_publish_keyboard() -> InlineKeyboardMarkup:
    """Кнопки для ручної, поштучної публікації частин уроку в канал."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="☀️ Ранок (слова)", callback_data="publish_morning"),
        ],
        [
            InlineKeyboardButton(text="🌤 Обід (квіз)", callback_data="publish_afternoon"),
        ],
        [
            InlineKeyboardButton(text="🌙 Вечір (граматика)", callback_data="publish_evening"),
        ],
        [
            InlineKeyboardButton(text="🚀 Все одразу", callback_data="admin_force_today"),
        ],
    ])


@router.message(Command("publish"))
@router.callback_query(F.data == "admin_publish_menu")
async def cmd_publish_menu(event: types.Message | types.CallbackQuery):
    """Меню ручної публікації: ранок / квіз / вечір окремо одне від одного."""
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
        f"Оберіть, яку частину відправити в канал прямо зараз, "
        f"незалежно від розкладу APScheduler:",
        parse_mode="HTML",
        reply_markup=get_publish_keyboard()
    )


async def _publish_part(callback: types.CallbackQuery, bot: Bot, job_func, label: str):
    """Спільна логіка запуску однієї job-функції вручну з обробкою помилок."""
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    await callback.answer(f"Публікую: {label}")

    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)

    status_msg = await callback.message.answer(
        f"⏳ Публікація «{label}» (Урок №{current_day})..."
    )
    try:
        await job_func(bot)
        await status_msg.edit_text(f"✅ «{label}» опубліковано (Урок №{current_day})!")
    except Exception as e:
        logger.error(f"Помилка ручної публікації '{label}' для дня {current_day}: {e}")
        await status_msg.edit_text(f"❌ Помилка публікації «{label}»: {e}")


@router.callback_query(F.data == "publish_morning")
async def callback_publish_morning(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_morning_words, "☀️ Ранкові слова")


@router.callback_query(F.data == "publish_afternoon")
async def callback_publish_afternoon(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_afternoon_quiz, "🌤 Обідній квіз")


@router.callback_query(F.data == "publish_evening")
async def callback_publish_evening(callback: types.CallbackQuery, bot: Bot):
    await _publish_part(callback, bot, job_evening_text, "🌙 Вечірній текст (день буде +1)")


# Текстові команди-дублікати кнопок — зручно для швидкого виклику без меню
@router.message(Command("post_morning"))
async def cmd_post_morning(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    status_msg = await message.answer("⏳ Публікую ранкові слова...")
    try:
        await job_morning_words(bot)
        await status_msg.edit_text("✅ Ранкові слова опубліковано!")
    except Exception as e:
        logger.error(f"Помилка /post_morning: {e}")
        await status_msg.edit_text(f"❌ Помилка: {e}")


@router.message(Command("post_afternoon"))
async def cmd_post_afternoon(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    status_msg = await message.answer("⏳ Публікую обідній квіз...")
    try:
        await job_afternoon_quiz(bot)
        await status_msg.edit_text("✅ Обідній квіз опубліковано!")
    except Exception as e:
        logger.error(f"Помилка /post_afternoon: {e}")
        await status_msg.edit_text(f"❌ Помилка: {e}")


@router.message(Command("post_evening"))
async def cmd_post_evening(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    status_msg = await message.answer("⏳ Публікую вечірній текст...")
    try:
        await job_evening_text(bot)
        await status_msg.edit_text("✅ Вечірній текст опубліковано! (лічильник дня автоматично +1)")
    except Exception as e:
        logger.error(f"Помилка /post_evening: {e}")
        await status_msg.edit_text(f"❌ Помилка: {e}")
=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
