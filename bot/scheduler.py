import os
import html
import random
import logging
from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.connection import AsyncSessionLocal
from database.crud import (
    get_lesson_by_day,
    get_current_publishing_day,
    set_current_publishing_day,
    save_generated_lesson,
    get_quizzes_for_days,
    save_quiz_poll,
)
from generator.gemini_pipeline import generate_daily_lesson
from generator.topics import DEFAULT_TOPICS

logger = logging.getLogger(__name__)

CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

# Субота: скільки питань з уроків тижня надсилати на перевірку
WEEKEND_REVIEW_MAX_QUIZZES = 10


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

        message = f"☀️ <b>¡Buenos días! День {lesson.day_number}</b>\n"
        message += f"📌 Тема: <b>{lesson.topic.title_es}</b> ({lesson.topic.title_ua})\n\n"
        message += "<b>Лексика та фрази дня:</b>\n\n"

        for word in lesson.words:
            message += f"🔹 <b>{word.text_es}</b> — {word.text_ua}\n"
            message += f"   <i>Приклад: {word.example_es} ({word.example_ua})</i>\n\n"

        message += "🎧 <i>Слухайте вимову всіх слів та прикладів у закрипленому аудіо нижче 👇</i>"

        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="HTML"
        )

        words_audio_path = lesson.words[0].audio_path
        if words_audio_path and os.path.exists(words_audio_path):
            audio = FSInputFile(words_audio_path)
            await bot.send_audio(
                chat_id=CHANNEL_ID,
                audio=audio,
                caption=f"🔊 <b>Аудіовимова (День {lesson.day_number})</b>",
                parse_mode="HTML"
            )


# --- 🌤 2. ОБІД (12:30): Інтерактивний Quiz ---

async def job_afternoon_quiz(bot: Bot):
    """Надсилає інтерактивне опитування у формі Вікторини."""
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        logger.info(f"Запуск обіднього квізу для дня {current_day}...")

        lesson = await get_lesson_by_day(session, current_day)
        if not lesson or not lesson.quizzes:
            logger.warning(f"Квізи для дня {current_day} відсутні.")
            return

        for quiz in lesson.quizzes:
            await _send_quiz(bot, quiz)


async def _send_quiz(bot: Bot, quiz):
    """Надсилає одне опитування та український переклад питання зі спойлером."""
    q_ua = getattr(quiz, 'question_ua', None)

    # Опитування не підтримує спойлери, тому переклад питання надсилаємо окремим повідомленням
    poll_msg = await bot.send_poll(
        chat_id=CHANNEL_ID,
        question=quiz.question_es[:300],
        options=quiz.options_json,
        type="quiz",
        correct_option_id=quiz.correct_option_index,
        explanation=quiz.explanation,
        is_anonymous=True
    )

    await _record_quiz_poll(quiz, poll_msg)

    if q_ua:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"🇺🇦 <tg-spoiler>{html.escape(q_ua)}</tg-spoiler>",
            parse_mode="HTML"
        )


async def _record_quiz_poll(quiz, poll_msg):
    """Зберігає зв'язок опитування з квізом для статистики. Збій не має зупиняти публікацію."""
    try:
        async with AsyncSessionLocal() as session:
            await save_quiz_poll(
                session,
                quiz_id=quiz.id,
                poll_id=poll_msg.poll.id,
                correct_option_index=quiz.correct_option_index,
            )
    except Exception as e:
        logger.error(f"Не вдалося зберегти статистику для квізу {getattr(quiz, 'id', '?')}: {e}")


# --- 🧠 4. СУБОТА (12:30): Перевірка знань за тиждень ---

async def job_weekend_review(bot: Bot):
    """У суботу надсилає квізи з уроків, опублікованих за тиждень (Пн–Пт).

    На суботу current_publishing_day вже вказує на понеділок наступного тижня,
    тому уроки тижня мають номери [current-5, current-1].
    """
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        first_day = max(1, current_day - 5)
        last_day = current_day - 1
        logger.info(f"Субота: перевірка уроків №{first_day}–{last_day}...")

        quizzes = await get_quizzes_for_days(session, first_day, last_day)

    if not quizzes:
        logger.warning(f"Квізи для перевірки за уроки №{first_day}–{last_day} відсутні.")
        return

    random.shuffle(quizzes)
    quizzes = quizzes[:WEEKEND_REVIEW_MAX_QUIZZES]

    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=(
            f"🧠 <b>Вихідна перевірка знань</b>\n"
            f"Питання з уроків №{first_day}–{last_day}. Перевірте себе 👇"
        ),
        parse_mode="HTML"
    )

    for quiz in quizzes:
        await _send_quiz(bot, quiz)


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
        message += "📝 <b>Короткий текст дня:</b>\n"
        message += f"🇪🇸 {html.escape(lesson.evening_text_es)}\n\n"
        message += f"🇺🇦 <tg-spoiler>{html.escape(lesson.evening_text_ua)}</tg-spoiler>"

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

        next_day = current_day + 1
        await set_current_publishing_day(session, next_day)
        logger.info(f"День публікацій успішно інкрементовано в БД: {current_day} -> {next_day}")

        await ensure_next_day_lesson(session, next_day, bot)


async def ensure_next_day_lesson(session, day_number: int, bot: Bot):
    existing = await get_lesson_by_day(session, day_number)
    if existing:
        return

    topic_info = DEFAULT_TOPICS[(day_number - 1) % len(DEFAULT_TOPICS)]
    try:
        lesson_data = await generate_daily_lesson(
            topic_ua=topic_info["ua"],
            topic_es=topic_info["es"],
            level="A1",
            day_number=day_number
        )
        await save_generated_lesson(session, lesson_data)
        logger.info(f"✅ Урок №{day_number} автоматично згенеровано.")
    except Exception as e:
        logger.error(f"❌ Помилка автогенерації уроку №{day_number}: {e}")
        await _notify_admins_generation_failed(bot, day_number, e)


async def _notify_admins_generation_failed(bot: Bot, day_number: int, error: Exception):
    if not ADMIN_IDS:
        return
    text = f"⚠️ <b>Автогенерація уроку №{day_number} не вдалася!</b>\n<code>{error}</code>"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception:
            pass


def start_scheduler(bot: Bot):
    """Запускає планувальник задач без дублювання."""
    # Пн–Пт — звичайні публікації; у суботу — перевірка тижня; неділя — без постів
    scheduler.add_job(job_morning_words, 'cron', day_of_week='mon-fri', hour=8, minute=30, args=[bot])
    scheduler.add_job(job_afternoon_quiz, 'cron', day_of_week='mon-fri', hour=12, minute=30, args=[bot])
    scheduler.add_job(job_evening_text, 'cron', day_of_week='mon-fri', hour=18, minute=30, args=[bot])
    scheduler.add_job(job_weekend_review, 'cron', day_of_week='sat', hour=12, minute=30, args=[bot])
    
    scheduler.start()
    logger.info("APScheduler успішно запущено (Часовий пояс: Europe/Kyiv)!")


def setup_scheduler(bot: Bot):
    start_scheduler(bot)
    return scheduler
