import os
import logging
import random
import io
import asyncio
from dotenv import load_dotenv
load_dotenv()
from PIL import Image, ImageDraw, UnidentifiedImageError
from telegram import Update, ForceReply
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import nest_asyncio

# Применяем патч для asyncio (решает потенциальные проблемы с вложенными циклами событий)
nest_asyncio.apply()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class PhotoStorage:
    def __init__(self):
        self.storage = {}

    def initialize_chat_data(self, chat_id: int, user1: str, user2: str, msg_id: int) -> None:
        self.storage[chat_id] = {
            "user1": user1,
            "user2": user2,
            "step": 1,
            "message_id_to_reply": msg_id
        }

    def get_chat_data(self, chat_id: int) -> dict:
        return self.storage.get(chat_id)

    def set_avatar1(self, chat_id: int, image: Image.Image) -> None:
        if chat_id in self.storage:
            self.storage[chat_id]["avatar1"] = image
            self.storage[chat_id]["step"] = 2

    def set_avatar2(self, chat_id: int, image: Image.Image) -> None:
        if chat_id in self.storage:
            self.storage[chat_id]["avatar2"] = image

    def is_first_photo_step(self, chat_id: int) -> bool:
        return self.storage.get(chat_id, {}).get("step") == 1

    def remove_chat_data(self, chat_id: int) -> None:
        if chat_id in self.storage:
            del self.storage[chat_id]


class ImageProcessor:
    @staticmethod
    def create_heart(size: int = 100) -> Image.Image:
        heart = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(heart)
        points = [
            (size * 0.5, size * 0.2),
            (size * 0.85, size * 0.5),
            (size * 0.5, size * 0.8),
            (size * 0.15, size * 0.5)
        ]
        draw.polygon(points, fill='red')
        return heart

    @staticmethod
    def create_compatibility_image(
        avatar1: Image.Image,
        avatar2: Image.Image,
        percentage: int,
        love_phrase: str
    ) -> Image.Image:
        try:
            result = Image.new('RGBA', (400, 200), 'white')
            avatar1 = avatar1.resize((100, 100))
            avatar2 = avatar2.resize((100, 100))
            mask = Image.new('L', (100, 100), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 100, 100), fill=255)
            avatar1.putalpha(mask)
            avatar2.putalpha(mask)
            result.paste(avatar1, (30, 50), avatar1)
            result.paste(avatar2, (270, 50), avatar2)
            heart = ImageProcessor.create_heart(size=100)
            result.paste(heart, (150, 50), heart)
            draw_result = ImageDraw.Draw(result)
            draw_result.text((200, 160), f"{percentage}%", fill='black', anchor='mm')
            draw_result.text((20, 10), love_phrase, fill='black')
            return result
        except Exception as exc:
            logger.error(f"Ошибка при создании изображения: {exc}")
            return None


class CompatibilityAnalyzer:
    @staticmethod
    def get_love_phrase(percentage: int) -> str:
        phrases = {
            range(0, 20): [
                "Увы, кажется, это не ваша история...",
                "Звезды сейчас не на вашей стороне.",
                "Возможно, стоит поискать в другом месте."
            ],
            range(20, 40): [
                "Шансы невелики, но чудеса случаются!",
                "Пока что не видно искры, но кто знает...",
                "Начните с дружбы, а там посмотрим."
            ],
            range(40, 60): [
                "Есть небольшая искра, но нужно больше огня.",
                "Попробуйте узнать друг друга получше.",
                "Не все потеряно, но работа предстоит большая."
            ],
            range(60, 80): [
                "Вы отлично ладите друг с другом!",
                "Между вами есть сильная связь.",
                "Любовь витает в воздухе!"
            ],
            range(80, 101): [
                "Вы — две половинки одного целого!",
                "Ваша любовь — это нечто особенное.",
                "Берегите друг друга!"
            ]
        }
        for range_key, messages in phrases.items():
            if percentage in range_key:
                return random.choice(messages)
        return "Что-то пошло не так..."

    @staticmethod
    def get_random_compatibility() -> int:
        return random.randint(1, 100)


def is_valid_username(username: str) -> bool:
    if len(username) > 32:
        return False
    return all(c.isalnum() or c == '_' for c in username)


class BotHandler:
    def __init__(self, token: str):
        self.app = Application.builder().token(token).build()
        self.photo_storage = PhotoStorage()
        self.app.add_handler(CommandHandler("mery", self.mery_command))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

    async def mery_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text(
                "❌ Укажите два username:\nПример: /mery @username1 @username2",
                reply_markup=ForceReply(selective=True)
            )
            return

        user1, user2 = (u.replace('@', '') for u in args)
        if not (is_valid_username(user1) and is_valid_username(user2)):
            await update.message.reply_text(
                "❌ Неверный формат username. Разрешены буквы, цифры и '_'.",
                reply_markup=ForceReply(selective=True)
            )
            return

        chat_id = update.effective_chat.id
        self.photo_storage.initialize_chat_data(
            chat_id=chat_id,
            user1=user1,
            user2=user2,
            msg_id=update.message.id
        )

        await update.message.reply_text(
            f"@{user1}, пожалуйста, отправьте вашу фотографию.",
            reply_to_message_id=update.message.id,
            reply_markup=ForceReply(selective=True)
        )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        data = self.photo_storage.get_chat_data(chat_id)
        if not data:
            await update.message.reply_text(
                "❌ Сначала вызовите команду /mery.",
                reply_markup=ForceReply(selective=True)
            )
            return

        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        try:
            with Image.open(io.BytesIO(photo_bytes)) as test_img:
                test_img.verify()
            avatar = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
        except (UnidentifiedImageError, OSError):
            logger.error("Неверный файл изображения или ошибка чтения файла.")
            await update.message.reply_text(
                "❌ Неверный файл изображения. Попробуйте снова.",
                reply_markup=ForceReply(selective=True)
            )
            self.photo_storage.remove_chat_data(chat_id)
            return

        if self.photo_storage.is_first_photo_step(chat_id):
            self.photo_storage.set_avatar1(chat_id, avatar)
            await update.message.reply_text(
                f"@{data['user2']}, теперь ваша очередь отправить фотографию.",
                reply_markup=ForceReply(selective=True)
            )
            return

        self.photo_storage.set_avatar2(chat_id, avatar)
        compatibility = CompatibilityAnalyzer.get_random_compatibility()
        love_phrase = CompatibilityAnalyzer.get_love_phrase(compatibility)

        result_image = ImageProcessor.create_compatibility_image(
            avatar1=data["avatar1"],
            avatar2=data["avatar2"],
            percentage=compatibility,
            love_phrase=love_phrase
        )

        if result_image:
            bio = io.BytesIO()
            result_image.save(bio, format='PNG')
            bio.seek(0)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=bio,
                caption=(
                    f"❤️ Совместимость @{data['user1']} и @{data['user2']}: {compatibility}%\n\n"
                    f"Вердикт: {love_phrase}\n"
                ),
                reply_to_message_id=data["message_id_to_reply"]
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при создании изображения.",
                reply_markup=ForceReply(selective=True)
            )

        self.photo_storage.remove_chat_data(chat_id)

    async def run_bot(self) -> None:
        logger.info("Бот запущен. Ожидание сообщений...")
        await self.app.run_polling()
        await asyncio.Future()


async def main():
    # Получаем токен из переменной окружения
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in environment variables")

    bot_handler = BotHandler(BOT_TOKEN)
    await bot_handler.run_bot()


if __name__ == '__main__':
    asyncio.run(main())
