import os
import json
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from generator.schemas import PostGenerationSchema
from database.crud import create_lesson_post
from database.models import PostStatus

# Ініціалізація асинхронного клієнта OpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ти — досвідчений викладач іспанської мови. Твоя мета — створювати цікаві, структуровані та легкі для сприйняття навчальні пости для Telegram.

Правила форматування HTML для Telegram:
1. Використовуй тільки HTML-теги: <b>, <i>, <code>, <s>.
2. Не використовуй Markdown (*, **).
3. Пояснення має бути стислим, дружнім та структурованим.
4. Додавай до кожного прикладу переклад українською мовою.
"""

def build_telegram_html(data: PostGenerationSchema) -> str:
    """Формує підготовлений HTML-текст для відправки в Telegram."""
    examples_str = "\n".join([f"• {ex}" for ex in data.examples])
    vocab_str = "\n".join([f"🔹 <code>{item}</code>" for item in data.vocabulary])

    html_content = (
        f"<b>{data.title}</b>\n\n"
        f"{data.explanation}\n\n"
        f"<b>📌 Приклади:</b>\n{examples_str}\n\n"
        f"<b>📚 Словничок:</b>\n{vocab_str}"
    )
    return html_content

async def generate_and_save_post(
    session: AsyncSession,
    level: str,
    topic: str,
    raw_text: str
) -> None:
    """Генерує пост за допомогою LLM та зберігає його у статусі DRAFT в MySQL."""
    prompt = f"Рівень: {level}\nТема: {topic}\nМатеріал з підручника:\n{raw_text}"

    # Виклики з підтримкою Structured Outputs (Pydantic parsing)
    completion = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format=PostGenerationSchema,
    )

    parsed_data: PostGenerationSchema = completion.choices[0].message.parsed
    
    # Формуємо HTML та JSON вікторини
    content_html = build_telegram_html(parsed_data)
    
    quiz_json = None
    if parsed_data.quiz_question and parsed_data.quiz_options:
        quiz_json = {
            "question": parsed_data.quiz_question,
            "options": [opt.model_dump() for opt.quiz_options in [parsed_data.quiz_options] for opt in opt] if isinstance(parsed_data.quiz_options, list) else []
        }

    # Зберігаємо готовий черновик у БД
    await create_lesson_post(
        session=session,
        level=level,
        topic=topic,
        content_html=content_html,
        quiz_data=quiz_json,
        status=PostStatus.DRAFT
    )
    print(f"[+] Пост успішно згенеровано та збережено в БД: {topic}")
