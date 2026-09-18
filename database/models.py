from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, func
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)


class Level(Base):
    __tablename__ = "levels"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(5), unique=True, nullable=False)  # 'A1', 'A2', 'B1'
    title = Column(String(50), nullable=False)

    topics = relationship("Topic", back_populates="level", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    level_id = Column(Integer, ForeignKey("levels.id", ondelete="CASCADE"), nullable=False)
    title_ua = Column(String(100), nullable=False)
    title_es = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)

    level = relationship("Level", back_populates="topics")
    lessons = relationship("DailyLesson", back_populates="topic", cascade="all, delete-orphan")


class DailyLesson(Base):
    __tablename__ = "daily_lessons"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    day_number = Column(Integer, nullable=False, index=True)
    
    # Вечірній контент (Граматика та текст)
    grammar_rule_title = Column(String(255), nullable=True)
    grammar_rule_text = Column(Text, nullable=True)
    evening_text_es = Column(Text, nullable=False)
    evening_text_ua = Column(Text, nullable=False)
    evening_audio_path = Column(String(512), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    topic = relationship("Topic", back_populates="lessons")
    words = relationship("LexicalUnit", back_populates="lesson", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="lesson", cascade="all, delete-orphan")


class LexicalUnit(Base):
    __tablename__ = "lexical_units"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("daily_lessons.id", ondelete="CASCADE"), nullable=False)
    
    text_es = Column(String(255), nullable=False)
    text_ua = Column(String(255), nullable=False)
    part_of_speech = Column(String(50), nullable=True)
    
    example_es = Column(Text, nullable=False)
    example_ua = Column(Text, nullable=False)
    
    audio_path = Column(String(512), nullable=True)
    grammar_tag = Column(String(100), nullable=True)

    lesson = relationship("DailyLesson", back_populates="words")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("daily_lessons.id", ondelete="CASCADE"), nullable=False)
    
    question_es = Column(Text, nullable=False)
    question_ua = Column(String(500), nullable=True) # Додайте це поле
    options_json = Column(JSON, nullable=False)  # Зберігає масив відповідей у JSON форматі
    correct_option_index = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=True)

    lesson = relationship("DailyLesson", back_populates="quizzes")
