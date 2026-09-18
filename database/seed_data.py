import sys
from pathlib import Path
import asyncio

# Додаємо корінь проєкту до sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import logging
from database.connection import AsyncSessionLocal
from database.crud import save_generated_lesson, get_max_day_number
from generator.gemini_pipeline import generate_daily_lesson

logging.basicConfig(level=logging.INFO)

# Список тем для рівня A1 (на перші дні)
TOPICS_A1 = [
    {"ua": "Знайомство та привітання", "es": "Saludos y presentaciones"},
    {"ua": "Алфавіт та вимова", "es": "El alfabeto y la pronunciación"},
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
    {"ua": "Їжа та основні продукти", "es": "La comida y los alimentos básicos"},
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
    {"ua": " В готелі", "es": "En el hotel"},
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
    {"ua": " Дні народження та подарунки", "es": "Los cumpleaños y los regalos"},
    {"ua": "Емоції та почуття", "es": "Las emociones y los sentimientos"},
    {"ua": "Вподобання (що подобається і ні)", "es": "Gustos y preferencias"},
    {"ua": "Географія та сторони світу", "es": "La geografía y los puntos cardinales"},
    {"ua": "Технології та гаджети", "es": "La tecnología y los dispositivos"},
    {"ua": "Соціальні мережі та інтернет", "es": "Las redes sociales e internet"},
    {"ua": "Плани на майбутнє", "es": "Planes para el futuro"}
]
async def seed_database(days_to_generate: int = 6):
    async with AsyncSessionLocal() as session:
        current_max_day = await get_max_day_number(session)
        start_day = current_max_day + 1

        for i in range(days_to_generate):
            day_num = start_day + i
            topic_info = TOPICS_A1[i % len(TOPICS_A1)]
            
            logging.info(f"Генерація дня {day_num}: {topic_info['ua']}...")
            
            try:
                # 1. Запит до Gemini + створення MP3 через edge-tts
                lesson_data = await generate_daily_lesson(
                    topic_ua=topic_info["ua"],
                    topic_es=topic_info["es"],
                    level="A1",
                    day_number=day_num
                )
                
                # 2. Запис у базу MySQL
                await save_generated_lesson(session, lesson_data)
                
                # Невелика пауза між запитами до API
                await asyncio.sleep(2)
            except Exception as e:
                logging.error(f"Помилка генерації для дня {day_num}: {e}")

if __name__ == "__main__":
    # Запускаємо генерацію на 6 днів
    asyncio.run(seed_database(days_to_generate=6))
