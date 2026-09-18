from pydantic import BaseModel, Field
from typing import List, Optional

class QuizOption(BaseModel):
    option_text: str = Field(description="Текст варіанта відповіді")
    is_correct: bool = Field(description="Чи є цей варіант правильним")

class PostGenerationSchema(BaseModel):
    title: str = Field(description="Заголовок поста з емодзі (іспанською/українською)")
    explanation: str = Field(description="Коротке, зрозуміле пояснення граматичної або лексичної теми (HTML розмітка)")
    examples: List[str] = Field(description="Приклади речень іспанською з перекладом (HTML розмітка)")
    vocabulary: List[str] = Field(description="Словничок нових слів (слово - переклад)")
    quiz_question: Optional[str] = Field(default=None, description="Питання для міні-тесту/вікторини")
    quiz_options: Optional[List[QuizOption]] = Field(default=None, description="Варіанти відповідей (3-4 варіанти)")
