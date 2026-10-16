# 🇪🇸 Spanish Daily Bot

Telegram-бот, який щодня автоматично публікує в канал уроки іспанської мови для україномовних.
Уроки генерує **Google Gemini**, озвучує **Microsoft Edge TTS**, зберігаються вони в **MySQL**.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.28-2CA5E0?logo=telegram&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-2.5_Flash-8E75B2?logo=googlegemini&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## Як це працює

Кожен день — це один урок на певну тему рівня A1 (у `generator/topics.py` понад 100 тем).
Урок публікується в канал трьома частинами:

| Час (Київ) | Публікація | Зміст |
|:---:|---|---|
| ☀️ **08:30** | Лексика дня | 10–12 слів і фраз з прикладами та перекладом + аудіо з вимовою |
| 🌤 **12:30** | Квіз | 3 вікторини (Telegram quiz poll) з поясненням відповіді |
| 🌙 **18:30** | Граматика й текст | Мікро-правило граматики + короткий текст іспанською з перекладом і аудіо |

Після вечірньої публікації бот переходить на наступний день і **сам генерує наступний урок**,
якщо його ще немає в базі. Якщо генерація не вдалася, адміни отримують повідомлення в особисті.

```
Gemini 2.5 Flash ──► JSON-урок ──► edge-tts (es + uk голоси) ──► MySQL ──► APScheduler ──► Telegram-канал
```

## Можливості адміна

Адмін-панель відкривається командою `/start` (лише для `ADMIN_IDS`).

| Команда | Що робить |
|---|---|
| `/start` | Панель керування з кнопками |
| `/status` | Скільки уроків готово в БД і який день наступний |
| `/show` | Перегляд наступного уроку з кнопками «Підтвердити» / «Перегенерувати» |
| `/generate` | Згенерувати наступний урок за списком тем |
| `/generate A2 майбутній час` | Згенерувати урок на довільну тему й рівень (A1–B2) |
| `/set_day N` | Змінити поточний день публікацій |
| `/publish` | Опублікувати ранок / квіз / вечір окремо, зараз |
| `/force_today` | Опублікувати всі три частини дня одразу |
| 📎 фото / відео / документ | Надіслане боту медіа з підписом копіюється в канал |

## Швидкий старт

Потрібні: Docker з Compose, токен бота від [@BotFather](https://t.me/BotFather),
ключ [Gemini API](https://aistudio.google.com/apikey), бот доданий адміном у канал.

```bash
git clone git@github.com:WorksOnMyServer/-spanish_fro_ua.git spain_bot
cd spain_bot
cp .env.example .env
nano .env                  # заповнити токени та паролі
docker compose up -d --build
docker compose logs -f app
```

Наповнити базу уроками наперед (необов'язково, 6 днів):

```bash
docker compose exec app python database/seed_data.py
```

## Змінні оточення

Повний шаблон лежить у [`.env.example`](.env.example).

| Змінна | Опис |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота від @BotFather |
| `CHANNEL_ID` | ID каналу (`-100…`) або `@username` |
| `ADMIN_IDS` | ID адмінів через кому, напр. `123456789,987654321` |
| `GEMINI_API_KEY` | Ключ Google Gemini API |
| `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` | Налаштування контейнера MySQL |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Підключення бота до БД (мають збігатися з `MYSQL_*`) |

> ⚠️ Якщо `ADMIN_IDS` порожній, адмін-команди доступні **всім**. Обов'язково вкажіть свій ID.

## Структура проєкту

```
├── main.py                  # точка входу: БД → бот → планувальник → polling
├── bot/
│   ├── handlers.py          # адмін-команди та кнопки
│   └── scheduler.py         # публікації 08:30 / 12:30 / 18:30 + автогенерація
├── database/
│   ├── connection.py        # async SQLAlchemy engine
│   ├── models.py            # Level, Topic, DailyLesson, LexicalUnit, Quiz, SystemSetting
│   ├── crud.py              # робота з уроками та поточним днем
│   └── seed_data.py         # пакетна генерація уроків наперед
├── generator/
│   ├── gemini_pipeline.py   # запит до Gemini + озвучка edge-tts
│   └── topics.py            # список тем A1
├── Dockerfile
├── docker-compose.yml       # app + MySQL 8.0
└── requirements.txt         # усі залежності з точними версіями
```

Аудіофайли зберігаються в `audio/day_N/` (не потрапляють у git).

## Ресурси

Стек оптимізований для маленького VPS (1 ГБ RAM): бот і MySQL разом займають **≈300 МБ**.
У `docker-compose.yml` задані ліміти пам'яті (`db` 256 МБ, `app` 300 МБ) і ротація логів.
Подробиці та виміри: [RAM_OPTIMIZATION.md](RAM_OPTIMIZATION.md).

## Оновлення на сервері

```bash
cd /opt/bots/spain_bot
git pull
docker compose up -d --build
```

Дані MySQL зберігаються в volume `prod_mysql_data` і переживають перезбірку.
