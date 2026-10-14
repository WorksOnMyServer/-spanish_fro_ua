import logging
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database.models import (
    DailyLesson,
    Topic,
    LexicalUnit,
    Quiz,
    SystemSetting,
    Level
)

logger = logging.getLogger(__name__)


async def get_max_day_number(session) -> int:
    """Повертає максимальний номер дня, присутній у БД."""
    result = await session.execute(select(func.max(DailyLesson.day_number)))
    max_day = result.scalar()
    return max_day if max_day is not None else 0


async def get_current_publishing_day(session) -> int:
    """Отримує поточний день публікацій із таблиці налаштувань."""
    result = await session.execute(
        select(SystemSetting.value).where(SystemSetting.key == "current_publishing_day")
    )
    val = result.scalar()
    return int(val) if val and val.isdigit() else 1


async def set_current_publishing_day(session, day_number: int):
    """Оновлює або створює номер поточного дня публікацій."""
    result = await session.execute(
        select(SystemSetting).where(SystemSetting.key == "current_publishing_day")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = str(day_number)
    else:
        setting = SystemSetting(key="current_publishing_day", value=str(day_number))
        session.add(setting)

    await session.commit()


async def get_lesson_by_day(session, day_number: int):
    """Отримує урок за його номером з усіма зв'язаними даними."""
    stmt = (
        select(DailyLesson)
        .where(DailyLesson.day_number == day_number)
        .options(
            selectinload(DailyLesson.topic),
            selectinload(DailyLesson.words),
            selectinload(DailyLesson.quizzes)
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def save_generated_lesson(session, lesson_data: dict):
    """
    Зберігає або перезаписує згенерований урок (та всі зв'язані таблиці) у БД.
    """
    day_num = lesson_data["day_number"]

    # 1. Перевірка чи існує вже такий урок. Якщо так — прибираємо старий для перезапису
    existing_lesson = await get_lesson_by_day(session, day_num)
    if existing_lesson:
        await session.delete(existing_lesson)
        await session.flush()

    # 2. Створюємо або шукаємо рівень та тему
    level_code = lesson_data.get("level", "A1")
    stmt_level = select(Level).where(Level.code == level_code)
    result_level = await session.execute(stmt_level)
    level_obj = result_level.scalar_one_or_none()

    if not level_obj:
        level_obj = Level(code=level_code, title=f"Рівень {level_code}")
        session.add(level_obj)
        await session.flush()

    # Шукаємо або створюємо тему з прив'язкою level_id
    stmt_topic = select(Topic).where(Topic.title_ua == lesson_data["topic_title_ua"])
    result_topic = await session.execute(stmt_topic)
    topic = result_topic.scalar_one_or_none()

    if not topic:
        topic = Topic(
            level_id=level_obj.id,
            title_ua=lesson_data["topic_title_ua"],
            title_es=lesson_data["topic_title_es"]
        )
        session.add(topic)
        await session.flush()

    # 3. Створюємо об'єкт уроку
    lesson = DailyLesson(
        day_number=day_num,
        topic_id=topic.id,
        grammar_rule_title=lesson_data["grammar"]["title"],
        grammar_rule_text=lesson_data["grammar"]["rule_text"],
        evening_text_es=lesson_data["evening_text"]["text_es"],
        evening_text_ua=lesson_data["evening_text"]["text_ua"],
        evening_audio_path=lesson_data["evening_text"]["audio_path"]
    )
    session.add(lesson)
    await session.flush()

    # 4. Зберігаємо слова
    words_audio = lesson_data.get("words_audio_path")
    for w in lesson_data["words"]:
        word_obj = LexicalUnit(
            lesson_id=lesson.id,
            text_es=w["text_es"],
            text_ua=w["text_ua"],
            part_of_speech=w["part_of_speech"],
            example_es=w["example_es"],
            example_ua=w["example_ua"],
            grammar_tag=w["grammar_tag"],
            audio_path=w.get("audio_path", words_audio)
        )
        session.add(word_obj)

    # 5. Зберігаємо квізи (з урахуванням question_ua)
    for q in lesson_data["quizzes"]:
        quiz_obj = Quiz(
            lesson_id=lesson.id,
            question_es=q["question_es"],
            question_ua=q.get("question_ua", ""),
            options_json=q["options"],
            correct_option_index=q["correct_index"],
            explanation=q["explanation"]
        )
        session.add(quiz_obj)

    await session.commit()
    logger.info(f"Урок №{day_num} успішно збережено в БД.")
    return lesson
