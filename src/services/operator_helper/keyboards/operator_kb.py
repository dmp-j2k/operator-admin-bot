from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from src.config.project_config import settings


def create_menu():
    kb = [[KeyboardButton(text='Отправить сообщение')]]
    keyboard = ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите команду"
    )
    return keyboard


def back_to_choosing():
    kb = [
        [InlineKeyboardButton(text='Показать список чатов (старый)', callback_data=f'1|0|0')],
        [
            InlineKeyboardButton(text="Открыть список чатов", web_app=WebAppInfo(url=settings.WEB_APP_URL))
        ]
    ]
    return InlineKeyboardMarkup(row_width=1, inline_keyboard=kb)
