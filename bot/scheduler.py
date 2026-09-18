import os
import logging
from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.connection import AsyncSessionLocal
from database.crud import (
    get_lesson_by_day,
    get_current_publishing_day,
<<<<<<< HEAD
    set_current_publishing_day,
    save_generated_lesson,
)
from generator.gemini_pipeline import generate_daily_lesson
from generator.topics import DEFAULT_TOPICS
=======
    set_current_publishing_day
)
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546

logger = logging.getLogger(__name__)

CHANNEL_ID = os.getenv("CHANNEL_ID")
<<<<<<< HEAD
# Адміни отримують сповіщення, якщо нічна автогенерація уроку впаде з помилкою
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")


# --- ☀️ 1. РАНОК (08:30): Словниковий запас ---

async def job_morning_words(bot: Bot):
    """Надсилає ранковий пост з новими словами та ОДНИМ спільним аудіофайлом вимови."""
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        logger.info(f"Запуск ранкової публікації для дня {current_day}...")
        
        lesson = await get_lesson_by_day(session, current_day)
        if not lesson or not lesson.words:
            logger.warning(f"Урок або слова для дня {current_day} не знайдено у БД.")
            return

        # 1. Формуємо один спільний текст із лексикою
        message = f"☀️ <b>¡Buenos días! День {lesson.day_number}</b>\n"
        message += f"📌 Тема: <b>{lesson.topic.title_es}</b> ({lesson.topic.title_ua})\n\n"
        message += "<b>Лексика та фрази дня:</b>\n\n"

        for word in lesson.words:
            message += f"🔹 <b>{word.text_es}</b> — {word.text_ua}\n"
            message += f"   <i>Приклад: {word.example_es} ({word.example_ua})</i>\n\n"

        message += "🎧 <i>Слухайте вимову всіх слів у закрипленому аудіо нижче 👇</i>"

        # 2. Спочатку надсилаємо ТЕКСТОВИЙ ПОСТ (тут ліміт 4096 символів, точно вистачить)
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="HTML"
        )

        # 3. Окремо надсилаємо ОДИН аудіофайл з коротким підписом
        words_audio_path = lesson.words[0].audio_path
        if words_audio_path and os.path.exists(words_audio_path):
            audio = FSInputFile(words_audio_path)
            await bot.send_audio(
                chat_id=CHANNEL_ID,
                audio=audio,
                caption=f"🔊 <b>Аудіовимова слів (День {lesson.day_number})</b>",
                parse_mode="HTML"
            )

# --- 🌤 2. ОБІД (13:00): Інтерактивний Quiz ---

async def job_afternoon_quiz(bot: Bot):
    """Надсилає інтерактивне опитування у формі Вікторини (з перекладом питання)."""
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        logger.info(f"Запуск обіднього квізу для дня {current_day}...")

        lesson = await get_lesson_by_day(session, current_day)
        if not lesson or not lesson.quizzes:
            logger.warning(f"Квізи для дня {current_day} відсутні.")
            return

        for quiz in lesson.quizzes:
            # Формуємо питання з перекладом українською
            q_ua = getattr(quiz, 'question_ua', None)
            poll_question = f"{quiz.question_es}\n({q_ua})" if q_ua else quiz.question_es

            await bot.send_poll(
                chat_id=CHANNEL_ID,
                question=poll_question[:300],  # Обмеження Telegram у 300 символів
                options=quiz.options_json,
                type="quiz",
                correct_option_id=quiz.correct_option_index,
                explanation=quiz.explanation,
                is_anonymous=True
            )


# --- 🌙 3. ВЕЧІР (18:30): Граматика та Текст ---

async def job_evening_text(bot: Bot):
    """Надсилає вечірню мікро-граматику та короткий текст з аудіо."""
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        logger.info(f"Запуск вечірньої публікації для дня {current_day}...")

        lesson = await get_lesson_by_day(session, current_day)
        if not lesson:
            logger.warning(f"Вечірній урок для дня {current_day} не знайдено у БД.")
            return

        message = f"🌙 <b>Вечірнє закріплення (День {lesson.day_number})</b>\n\n"
        message += f"📖 <b>Мікро-граматика: {lesson.grammar_rule_title}</b>\n"
        message += f"{lesson.grammar_rule_text}\n\n"
        message += "📝 <b>Короткий текст дня:</b>\n"
        message += f"🇪🇸 {lesson.evening_text_es}\n\n"
        message += f"🇺🇦 <i>{lesson.evening_text_ua}</i>"

        # Озвучка вечірнього тексту разом із постом
        if lesson.evening_audio_path and os.path.exists(lesson.evening_audio_path):
            audio = FSInputFile(lesson.evening_audio_path)
            await bot.send_audio(
                chat_id=CHANNEL_ID,
                audio=audio,
                caption=message,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="HTML")

        # Переходимо до наступного дня на завтра
        next_day = current_day + 1
        await set_current_publishing_day(session, next_day)
        logger.info(f"День публікацій успішно інкрементовано в БД: {current_day} -> {next_day}")

<<<<<<< HEAD
        # Автогенерація теми/уроку на наступний день, щоб контент був готовий
        # ще до ранкової публікації (08:30), без ручного /generate.
        await ensure_next_day_lesson(session, next_day, bot)


# --- 🌱 Автогенерація наступного дня наперед ---

async def ensure_next_day_lesson(session, day_number: int, bot: Bot):
    """
    Перевіряє, чи вже є в БД урок на day_number, і якщо ні — одразу
    генерує його через Gemini (тему бере зі спільного списку DEFAULT_TOPICS
    за індексом дня, так само як /generate у handlers.py).

    Викликається наприкінці вечірньої публікації (job_evening_text),
    тобто "в кінці поточного дня" — щоб наступний день був вже готовий.
    """
    existing = await get_lesson_by_day(session, day_number)
    if existing:
        logger.info(f"Урок №{day_number} вже є в БД — автогенерація не потрібна.")
        return

    topic_info = DEFAULT_TOPICS[(day_number - 1) % len(DEFAULT_TOPICS)]
    logger.info(f"Автогенерація уроку №{day_number} ({topic_info['ua']}) наперед...")

    try:
        lesson_data = await generate_daily_lesson(
            topic_ua=topic_info["ua"],
            topic_es=topic_info["es"],
            level="A1",
            day_number=day_number
        )
        await save_generated_lesson(session, lesson_data)
        logger.info(f"✅ Урок №{day_number} автоматично згенеровано та збережено.")
    except Exception as e:
        logger.error(f"❌ Помилка автогенерації уроку №{day_number}: {e}")
        await _notify_admins_generation_failed(bot, day_number, e)


async def _notify_admins_generation_failed(bot: Bot, day_number: int, error: Exception):
    """Сповіщає адмінів у особисті чати, якщо нічна автогенерація впала,
    щоб не проспати відсутність контенту на ранкову публікацію."""
    if not ADMIN_IDS:
        return
    text = (
        f"⚠️ <b>Автогенерація уроку №{day_number} не вдалася!</b>\n"
        f"<code>{error}</code>\n\n"
        f"Згенеруйте вручну через /generate, інакше ранкова публікація "
        f"о 08:30 не матиме контенту."
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception as notify_err:
            logger.error(f"Не вдалося сповістити адміна {admin_id}: {notify_err}")

=======
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546

# --- Ініціалізація та реєстрація задач ---

def start_scheduler(bot: Bot):
    """Запускає планувальник задач."""
    # Ранкові слова о 08:30
    scheduler.add_job(job_morning_words, 'cron', hour=8, minute=30, args=[bot])
    
<<<<<<< HEAD
    # Обідній квіз о 12:30
    scheduler.add_job(job_afternoon_quiz, 'cron', hour=12, minute=30, args=[bot])
    
    # Вечірній текст о 18:30
    scheduler.add_job(job_evening_text, 'cron', hour=18, minute=30, args=[bot])
=======
    # Обідній квіз о 13:00
    scheduler.add_job(job_afternoon_quiz, 'cron', hour=12, minute=30, args=[bot])
    
    # Вечірній текст о 18:30
    scheduler.add_job(job_evening_text, 'cron', hour=17, minute=00, args=[bot])
>>>>>>> ef3c3ad921dbc23b0803e3433be3742c5e1cd546
    
    scheduler.start()
    logger.info("APScheduler успішно запущено (Часовий пояс: Europe/Kyiv)!")


def setup_scheduler(bot: Bot):
    """Аліас для сумісності з main.py."""
    start_scheduler(bot)
    return scheduler
