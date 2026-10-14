import os
import re
import json
import logging
import asyncio
import edge_tts
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from database.connection import AsyncSessionLocal
from database.crud import save_generated_lesson

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class WordSchema(BaseModel):
    text_es: str = Field(description="Слово або фраза іспанською")
    text_ua: str = Field(description="Переклад українською")
    part_of_speech: str = Field(description="Частина мови або тип (noun, verb, chunk)")
    example_es: str = Field(description="Приклад вживання іспанською")
    example_ua: str = Field(description="Переклад прикладу українською")
    grammar_tag: str = Field(description="Короткий тег граматики")


class GrammarSchema(BaseModel):
    title: str = Field(description="Заголовок мікро-правила")
    rule_text: str = Field(description="Пояснення правила українською (2-3 речення)")


class EveningTextSchema(BaseModel):
    text_es: str = Field(description="Короткий текст іспанською (3-5 речень)")
    text_ua: str = Field(description="Точний переклад тексту українською")


class QuizSchema(BaseModel):
    question_es: str = Field(description="Питання іспанською мовою")
    question_ua: str = Field(description="Переклад питання українською мовою")
    options: list[str] = Field(description="4 варіанти відповідей")
    correct_index: int = Field(description="Індекс правильної відповіді (0, 1, 2 або 3)")
    explanation: str = Field(description="Пояснення відповіді українською")


class LessonGeneratedData(BaseModel):
    topic_title_ua: str
    topic_title_es: str
    level: str
    words: list[WordSchema]
    grammar: GrammarSchema
    evening_text: EveningTextSchema
    quizzes: list[QuizSchema]


def clean_text_for_tts(text: str) -> str:
    """Очищає спецсимволи (/, (), {}, тощо), які TTS може озвучувати буквально."""
    if not text:
        return ""
    # Замінюємо слеші та дужки на пробіли або крапки, щоб синтезатор читав текст плавно
    cleaned = re.sub(r'[/\\()\[\]{}|]', ' ', text)
    # Прибираємо зайві пробіли
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


async def generate_audio_file(text_es: str, text_ua: str, output_path: str):
    """
    Генерує єдиний MP3-файл, де послідовно озвучується як іспанський текст (голосовим движком es-ES),
    так і український переклад (голосовим движком uk-UA), без озвучування спецсимволів.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Очищаємо текст від непотрібних символів
        clean_es = clean_text_for_tts(text_es)
        clean_ua = clean_text_for_tts(text_ua)

        # Генеруємо іспанську частину (використовуємо іспанський голос)
        es_path = f"{output_path}.es.mp3"
        comm_es = edge_tts.Communicate(clean_es, "es-ES-AlvaroNeural")
        await comm_es.save(es_path)

        # Генеруємо українську частину (використовуємо український голос, напр. Остап або Поліна)
        ua_path = f"{output_path}.ua.mp3"
        comm_ua = edge_tts.Communicate(clean_ua, "uk-UA-OstapNeural")
        await comm_ua.save(ua_path)

        # Об'єднуємо обидва MP3 файли в один фінальний
        with open(output_path, 'wb') as outfile:
            for p in [es_path, ua_path]:
                if os.path.exists(p):
                    with open(p, 'rb') as infile:
                        outfile.write(infile.read())
                    os.remove(p) # Видаляємо тимчасові частини

        logger.info(f"Двомовне аудіо успішно згенеровано: {output_path}")
    except Exception as e:
        logger.error(f"Помилка генерації двомовного аудіо: {e}")


async def generate_daily_lesson(topic_ua: str, topic_es: str, level: str = "A1", day_number: int = 1) -> dict:
    """Генерує повний урок через Gemini та створює аудіофайли в правильній послідовності."""
    if not client:
        raise ValueError("GEMINI_API_KEY не знайдено в змінних оточення!")

    prompt = f"""
    Ти професійний викладач іспанської мови для україномовних студентів.
    Створи повноцінний навчальний блок для рівня {level} на тему: "{topic_ua}" ({topic_es}).

    КРИТИЧНІ ВИМОГИ:
    - Надай 10-12 найважливіших слів та фраз із точним прикладом та перекладом.
    - Дай 1 мікро-правило граматики.
    - Напиши вечірній зв'язний текст (3-5 речень) із перекладом.
    - Створи 3 складних квізи з варіантами відповідей.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LessonGeneratedData,
            temperature=0.3,
        ),
    )

    lesson_data = json.loads(response.text)
    lesson_data["day_number"] = day_number

    audio_dir = f"/app/audio/day_{day_number}"
    os.makedirs(audio_dir, exist_ok=True)

# Послідовне генерування аудіо для кожного слова у потрібному порядку з обрізанням слешів:
    # 1. Слово (es) -> 2. Переклад (ua) -> 3. Приклад (es) -> 4. Переклад прикладу (ua)
    temp_files = []
    
    for idx, word in enumerate(lesson_data["words"]):
        # Беремо текст до слешу (якщо він є) та очищаємо
        raw_es = word['text_es'].split('/')[0] if word['text_es'] else ""
        raw_ua = word['text_ua'].split('/')[0] if word['text_ua'] else ""

        w_es = clean_text_for_tts(raw_es)
        w_ua = clean_text_for_tts(raw_ua)
        ex_es = clean_text_for_tts(word['example_es'])
        ex_ua = clean_text_for_tts(word['example_ua'])

        # Шматочки для конкретного слова
        word_parts = [
            (w_es, "es-ES-AlvaroNeural"),
            (w_ua, "uk-UA-OstapNeural"),
            (ex_es, "es-ES-AlvaroNeural"),
            (ex_ua, "uk-UA-OstapNeural")
        ]

        for p_idx, (text, voice) in enumerate(word_parts):
            if not text:
                continue
            part_path = f"{audio_dir}/temp_w_{idx}_{p_idx}.mp3"
            try:
                comm = edge_tts.Communicate(text, voice)
                await comm.save(part_path)
                temp_files.append(part_path)
            except Exception as e:
                logger.error(f"Помилка генерації частини аудіо: {e}")
    # Об'єднуємо всі частини в один фінальний words_block.mp3
    words_audio_path = f"{audio_dir}/words_block.mp3"
    with open(words_audio_path, 'wb') as outfile:
        for p in temp_files:
            if os.path.exists(p):
                with open(p, 'rb') as infile:
                    outfile.write(infile.read())
                os.remove(p)

    lesson_data["words_audio_path"] = words_audio_path

#    # Генерація аудіо для вечірнього тексту (спочатку іспанська, потім українська)
#   evening_audio_path = f"{audio_dir}/evening_text.mp3"
#    await generate_audio_file(
#        lesson_data["evening_text"]["text_es"],
#        lesson_data["evening_text"]["text_ua"],
#        evening_audio_path
#    )
#    lesson_data["evening_text"]["audio_path"] = evening_audio_path

#    return lesson_data

# Генерація аудіо для вечірнього тексту (ТІЛЬКИ іспанська мова)
    evening_audio_path = f"{audio_dir}/evening_text.mp3"
    try:
        os.makedirs(audio_dir, exist_ok=True)
        clean_evening_es = clean_text_for_tts(lesson_data["evening_text"]["text_es"])
        comm_es = edge_tts.Communicate(clean_evening_es, "es-ES-AlvaroNeural")
        await comm_es.save(evening_audio_path)
        logger.info(f"Вечірнє аудіо (тільки es) згенеровано: {evening_audio_path}")
    except Exception as e:
        logger.error(f"Помилка генерації вечірнього аудіо: {e}")

    lesson_data["evening_text"]["audio_path"] = evening_audio_path

    return lesson_data
