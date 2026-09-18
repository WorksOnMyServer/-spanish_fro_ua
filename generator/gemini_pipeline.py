import os
import json
import logging
import asyncio
import edge_tts
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from database.connection import AsyncSessionLocal
from database.crud import save_generated_lesson

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація клієнта Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Pydantic-схеми для валідації JSON від Gemini ---

class WordSchema(BaseModel):
    text_es: str = Field(description="Слово або фраза іспанською")
    text_ua: str = Field(description="Переклад українською")
    part_of_speech: str = Field(description="Частина мови або тип (noun, verb, chunk)")
    example_es: str = Field(description="Приклад вживання іспанською")
    example_ua: str = Field(description="Переклад прикладу українською")
    grammar_tag: str = Field(description="Короткий тег граматики (напр. presente_indicativo)")

class GrammarSchema(BaseModel):
    title: str = Field(description="Заголовок мікро-правила")
    rule_text: str = Field(description="Пояснення правила українською (2-3 речення)")

class EveningTextSchema(BaseModel):
    text_es: str = Field(description="Короткий текст іспанською (3-5 речень), що містить вивчені слова")
    text_ua: str = Field(description="Точний та природний переклад тексту українською")

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


# --- Генерація аудіо через edge-tts ---

async def generate_audio_file(text_es: str, output_path: str, voice: str = "es-ES-AlvaroNeural"):
    """Генерує MP3-файл із вимовою іспанського тексту."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        communicate = edge_tts.Communicate(text_es, voice)
        await communicate.save(output_path)
        logger.info(f"Аудіо згенеровано: {output_path}")
    except Exception as e:
        logger.error(f"Помилка генерації аудіо для '{text_es}': {e}")


# --- Основна функція генерації уроку ---

async def generate_daily_lesson(topic_ua: str, topic_es: str, level: str = "A1", day_number: int = 1) -> dict:
    """Генерує повний урок через Gemini та створює аудіофайли."""
    if not client:
        raise ValueError("GEMINI_API_KEY не знайдено в змінних оточення!")

    prompt = f"""
    Ти професійний викладач іспанської мови для україномовних студентів.
    Створи повноцінний навчальний блок для рівня {level} на тему: "{topic_ua}" ({topic_es}).

    КРИТИЧНІ ВИМОГИ ДО КІЛЬКОСТІ ЛЕКСИКИ (words):
    1. Якщо тема є фундаментальною, системною або перелічувальною (наприклад: "Числа", "Дні тижня та місяці", "Алфавіт", "Кольори", "Пори року"):
       - Потрібно розкрити тему МАКСИМАЛЬНО ПОВНО. 
       - Надай від 7 до 12 основних слів/чисел/елементів (наприклад, усі 7 днів тижня; ключові числа від 0 до 100; основні кольори тощо).
    2. Якщо тема є загальнолексичною або побутовою (наприклад: "В ресторані", "Орієнтування в місті", "В готелі"):
       - Надай 6–8 найважливіших уживаних слів та готових фраз-шаблонів (chunks).
    
    ДОДАТКОВІ ВИМОГИ:
    - Для КОЖНОГО слова обов'язково надай точний приклад речення (example_es) та його переклад (example_ua).
    - Дай 1 мікро-правило граматики (коротке, зрозуміле, 2-3 речення).
    - Напиши вечірній зв'язний текст (3-5 речень), який застосовує нові слова та граматику теми.
    - Створи 1-2 квізи з 4 варіантами відповідей для перевірки знань. Обов'язково вкажи питання іспанською (question_es) та його переклад українською (question_ua).
    """

    logger.info(f"Надсилання запиту до Gemini для теми: {topic_ua}...")

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

    # Папка для аудіофайлів конкретного дня
    audio_dir = f"/app/audio/day_{day_number}"

    # 1. Створення ЄДИНОГО аудіофайлу для всього блоку слів
    words_es_list = [word["text_es"] for word in lesson_data["words"]]
    combined_words_text = ". ".join(words_es_list) + "."
    
    words_audio_path = f"{audio_dir}/words_block.mp3"
    await generate_audio_file(combined_words_text, words_audio_path)
    
    # Записуємо шлях до аудіо блоку на рівні самого уроку!
    # У словах НЕ прописуємо audio_path, щоб бот не дублював його.
    lesson_data["words_audio_path"] = words_audio_path

    # 2. Генерація аудіо для вечірнього тексту
    evening_audio_path = f"{audio_dir}/evening_text.mp3"
    await generate_audio_file(lesson_data["evening_text"]["text_es"], evening_audio_path)
    lesson_data["evening_text"]["audio_path"] = evening_audio_path

    return lesson_data

# --- Обгортка для генерації та збереження в БД ---

async def generate_and_save_post_gemini(topic_ua: str, topic_es: str, level: str = "A1", day_number: int = 1):
    """Генерує урок і відразу зберігає його в базі даних."""
    lesson_data = await generate_daily_lesson(topic_ua, topic_es, level, day_number)
    async with AsyncSessionLocal() as session:
        lesson = await save_generated_lesson(session, lesson_data)
        return lesson
