from aiogram import Router, types, F
from aiogram.filters import CommandObject
from generator.gemini_pipeline import generate_and_save_post_gemini
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, update, func
from database.connection import AsyncSessionLocal
from database.models import LessonPost, PostStatus
from database.crud import get_next_draft_post, update_post_status, delete_post

router = Router()

def get_moderation_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Створення інлайн-кнопок для модерації поста."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{post_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"delete_{post_id}")
            ],
            [
                InlineKeyboardButton(text="⏭ Next / Skip", callback_data="review_next")
            ]
        ]
    )
    return keyboard

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "¡Hola! Я бот для автопостингу та навчання іспанської мови.\n\n"
        "<b>Доступні команди:</b>\n"
        "📊 /status — Переглянути статистику постів\n"
        "🔍 /review — Почати покроковий перегляд чернеток (draft)\n"
        "⚡️ /approve_all — Схвалити всі чернетки оптом\n"
        "❌ /cancel — Скасувати поточну дію / зупинити перегляд",
        parse_mode="HTML"
    )

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message):
    await message.answer("🛑 Поточний процес або режим перегляду зупинено.", reply_markup=types.ReplyKeyboardRemove())

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    async with AsyncSessionLocal() as session:
        # Використовуємо select(func.count()) для отримання числового значення кількості
        drafts = await session.scalar(
            select(func.count()).select_from(LessonPost).where(LessonPost.status == PostStatus.DRAFT)
        )
        approved = await session.scalar(
            select(func.count()).select_from(LessonPost).where(LessonPost.status == PostStatus.APPROVED)
        )
        published = await session.scalar(
            select(func.count()).select_from(LessonPost).where(LessonPost.status == PostStatus.PUBLISHED)
        )
        
        await message.answer(
            f"<b>📊 Статистика постів у БД:</b>\n\n"
            f"📝 Чернетки (Draft): {drafts or 0}\n"
            f"✅ Готові до публікації (Approved): {approved or 0}\n"
            f"🚀 Опубліковано (Published): {published or 0}",
            parse_mode="HTML"
        )

@router.message(Command("review"))
async def cmd_review(message: types.Message):
    """Початок перегляду першої чернетки."""
    await send_next_draft(message.chat.id, message.bot)

async def send_next_draft(chat_id: int, bot):
    """Пошук і відправка наступного DRAFT-поста користувачу."""
    async with AsyncSessionLocal() as session:
        post = await get_next_draft_post(session)
        
        if not post:
            await bot.send_message(chat_id, "🎉 Усі чернетки перевірено! Більше немає постів зі статусом DRAFT.")
            return

        preview_text = (
            f"📌 <b>Чернетка ID: {post.id}</b> (Рівень: {post.level})\n"
            f"Тема: <i>{post.topic}</i>\n"
            f"───────────────────\n\n"
            f"{post.content_html}"
        )
        
        await bot.send_message(
            chat_id=chat_id,
            text=preview_text,
            parse_mode="HTML",
            reply_markup=get_moderation_keyboard(post.id)
        )


@router.message(Command("generate"))
async def cmd_generate(message: types.Message, command: CommandObject):
    """
    Приклад використання в боті:
    /generate A1 Дієслова Tener та Hacer
    або просто:
    /generate Дієслова Tener та Hacer
    """
    if not command.args:
        await message.answer(
            "⚠️ Будь ласка, вкажіть тему після команди.\n"
            "<b>Приклад:</b> <code>/generate A1 Дієслово Tener</code>",
            parse_mode="HTML"
        )
        return

    # Розбираємо аргументи (якщо перше слово рівень: A1, A2, B1, B2)
    args = command.args.split(" ", 1)
    if args[0].upper() in ["A1", "A2", "B1", "B2"] and len(args) > 1:
        level = args[0].upper()
        topic = args[1]
    else:
        level = "A1"  # Дефолтний рівень
        topic = command.args

    status_msg = await message.answer(f"⏳ Генерую пост через Gemini для теми: <b>{topic}</b> ({level})...", parse_mode="HTML")

    async with AsyncSessionLocal() as session:
        # Відправляємо запит до Gemini (передаємо тему як raw_text)
        await generate_and_save_post_gemini(
            session=session,
            level=level,
            topic=topic,
            raw_text=f"Створи повноцінний урок на тему: {topic}"
        )

    await status_msg.edit_text("✅ Пост згенеровано та збережено в чернетки (DRAFT)!")
    
    # Одразу показуємо цей згенерований пост для модерації
    await send_next_draft(message.chat.id, message.bot)




@router.callback_query(F.data.startswith("approve_"))
async def process_approve(callback: types.CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        await update_post_status(session, post_id, PostStatus.APPROVED)
        
    await callback.answer("✅ Пост схвалено і переведено у статус APPROVED!")
    await callback.message.edit_reply_markup(reply_markup=None)  # Прибираємо кнопки з відпрацьованого поста
    
    # Відразу показуємо наступний пост
    await send_next_draft(callback.message.chat.id, callback.bot)

@router.callback_query(F.data.startswith("delete_"))
async def process_delete(callback: types.CallbackQuery):
    post_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        await delete_post(session, post_id)
        
    await callback.answer("🗑 Пост видалено!")
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Відразу показуємо наступний пост
    await send_next_draft(callback.message.chat.id, callback.bot)

@router.callback_query(F.data == "review_next")
async def process_skip(callback: types.CallbackQuery):
    await callback.answer("⏭ Пропущено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await send_next_draft(callback.message.chat.id, callback.bot)

@router.message(Command("approve_all"))
async def cmd_approve_all(message: types.Message):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(LessonPost)
            .where(LessonPost.status == PostStatus.DRAFT)
            .values(status=PostStatus.APPROVED)
        )
        await session.commit()
        await message.answer("✅ Усі чернетки переведено в статус `approved`!")
