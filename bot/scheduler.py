import os
import re
import html
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
    get_setting,
    set_setting,
)
from generator.gemini_pipeline import generate_daily_lesson
from generator.topics import DEFAULT_TOPICS

logger = logging.getLogger(__name__)

CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

# Ліміти Telegram для send_poll
POLL_QUESTION_LIMIT = 300
POLL_OPTION_LIMIT = 100
POLL_EXPLANATION_LIMIT = 200


def _cut(text: str | None, limit: int) -> str:
    """Обрізає текст до ліміту Telegram, додаючи «…»."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


_HTML_TAG = re.compile(r"</?[a-zA-Z][^<>]*>")


def safe_html(text: str | None) -> str:
    """Текст від Gemini → безпечний для parse_mode=HTML.

    Прибирає HTML-теги, які міг додати Gemini, і екранує <, >, & — інакше
    Telegram відхиляє все повідомлення («can't parse entities»).
    Розмітку <b>/<i> додає лише наш код навколо цього тексту.
    """
    return html.escape(_HTML_TAG.sub("", text or ""), quote=False)


# Номер дня, ранковий пост якого вже вийшов. День «починається» з ранку:
# квізи й вечір за розкладом не публікуються, поки не вийшов ранок цього дня.
# Інакше після /force_today (день N → N+1) о 12:30 вийшли б квізи дня N+1 без його ранку.
MORNING_DONE_KEY = "morning_published_day"


async def _morning_done(session, day: int) -> bool:
    val = await get_setting(session, MORNING_DONE_KEY)
    return val is None or val == str(day)  # None — ще жодного ранку після оновлення бота


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

        await set_setting(session, MORNING_DONE_KEY, str(current_day))

        message = f"☀️ <b>¡Buenos días! День {lesson.day_number}</b>\n"
        message += f"📌 Тема: <b>{safe_html(lesson.topic.title_es)}</b> ({safe_html(lesson.topic.title_ua)})\n\n"
        message += "<b>Лексика та фрази дня:</b>\n\n"

        for word in lesson.words:
            message += f"🔹 <b>{safe_html(word.text_es)}</b> — {safe_html(word.text_ua)}\n"
            message += f"   <i>Приклад: {safe_html(word.example_es)} ({safe_html(word.example_ua)})</i>\n\n"

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

        failed = []
        for idx, quiz in enumerate(lesson.quizzes, 1):
            q_ua = getattr(quiz, 'question_ua', None)
            poll_question = f"{quiz.question_es}\n({q_ua})" if q_ua else quiz.question_es
            options = [_cut(str(opt), POLL_OPTION_LIMIT) for opt in (quiz.options_json or [])][:10]

            if len(options) < 2 or not 0 <= quiz.correct_option_index < len(options):
                logger.error(f"Квіз #{idx} дня {current_day} некоректний: {len(options)} варіантів, "
                             f"правильний індекс {quiz.correct_option_index}")
                failed.append(f"#{idx}: некоректні варіанти відповідей")
                continue

            # Помилка одного квізу не повинна зривати публікацію решти
            try:
                await bot.send_poll(
                    chat_id=CHANNEL_ID,
                    question=_cut(poll_question, POLL_QUESTION_LIMIT),
                    options=options,
                    type="quiz",
                    correct_option_id=quiz.correct_option_index,
                    explanation=_cut(quiz.explanation, POLL_EXPLANATION_LIMIT) or None,
                    is_anonymous=True
                )
            except Exception as e:
                logger.error(f"Не вдалося відправити квіз #{idx} дня {current_day}: {e}")
                failed.append(f"#{idx}: {e}")

        if failed:
            await _notify_admins(
                bot,
                f"⚠️ <b>День {current_day}: не опубліковано {len(failed)} з {len(lesson.quizzes)} квізів</b>\n"
                + "\n".join(html.escape(f) for f in failed)
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
        message += f"📖 <b>Мікро-граматика: {safe_html(lesson.grammar_rule_title)}</b>\n"
        message += f"{safe_html(lesson.grammar_rule_text)}\n\n"
        message += "📝 <b>Короткий текст дня:</b>\n"
        message += f"🇪🇸 {safe_html(lesson.evening_text_es)}\n\n"
        message += f"🇺🇦 <i>{safe_html(lesson.evening_text_ua)}</i>"

        # Текст окремим повідомленням (ліміт 4096), а не підписом до аудіо (ліміт 1024).
        # Помилка відправки не повинна блокувати зсув дня, інакше бот публікує той самий урок по колу.
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="HTML")

            if lesson.evening_audio_path and os.path.exists(lesson.evening_audio_path):
                audio = FSInputFile(lesson.evening_audio_path)
                await bot.send_audio(
                    chat_id=CHANNEL_ID,
                    audio=audio,
                    caption=f"🎧 <b>Озвучення тексту (День {lesson.day_number})</b>",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Помилка вечірньої публікації дня {current_day}: {e}")
            await _notify_admins(
                bot,
                f"⚠️ <b>Вечірній пост дня {current_day} не вийшов повністю!</b>\n"
                f"<code>{html.escape(str(e))}</code>\n\n"
                f"День все одно переведено на {current_day + 1}. "
                f"Щоб повторити: /set_day {current_day} → /publish → 🌙 Вечір"
            )

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
        await _notify_admins(
            bot,
            f"⚠️ <b>Автогенерація уроку №{day_number} не вдалася!</b>\n<code>{html.escape(str(e))}</code>"
        )


async def _notify_admins(bot: Bot, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception:
            pass


# --- Запуск за розкладом: квізи й вечір лише після ранку цього дня ---
# Ручні публікації (/publish, /force_today) викликають job_* напряму, без цієї перевірки.

async def _scheduled_after_morning(bot: Bot, job, label: str):
    async with AsyncSessionLocal() as session:
        current_day = await get_current_publishing_day(session)
        if not await _morning_done(session, current_day):
            logger.info(f"{label} дня {current_day} пропущено: ранок цього дня ще не публікувався "
                        f"(день почнеться завтра о 08:30).")
            return
    await job(bot)


async def scheduled_afternoon_quiz(bot: Bot):
    await _scheduled_after_morning(bot, job_afternoon_quiz, "Обідній квіз")


async def scheduled_evening_text(bot: Bot):
    await _scheduled_after_morning(bot, job_evening_text, "Вечірній пост")


def start_scheduler(bot: Bot):
    """Запускає планувальник задач без дублювання."""
    # misfire_grace_time: якщо бот був зайнятий/перезапускався, задача виконається із запізненням
    # до 10 хв, а не буде пропущена. coalesce: кілька пропущених запусків → один.
    job_opts = dict(misfire_grace_time=600, coalesce=True)
    scheduler.add_job(job_morning_words, 'cron', hour=8, minute=30, args=[bot], **job_opts)
    scheduler.add_job(scheduled_afternoon_quiz, 'cron', hour=12, minute=30, args=[bot], **job_opts)
    scheduler.add_job(scheduled_evening_text, 'cron', hour=18, minute=30, args=[bot], **job_opts)

    scheduler.start()
    logger.info("APScheduler успішно запущено (Часовий пояс: Europe/Kyiv)!")


def setup_scheduler(bot: Bot):
    start_scheduler(bot)
    return scheduler
