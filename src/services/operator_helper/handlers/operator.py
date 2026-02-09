import re
from contextlib import suppress
from typing import Optional, List

import phonenumbers
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramMigrateToChat
from aiogram.filters import Command, StateFilter, or_f, and_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, InputMediaDocument, InputMediaVideo, InputMediaAudio, \
    InputMediaAnimation
from phonenumbers import NumberParseException
from sqlalchemy.exc import IntegrityError

from src.use_cases.chat_keyboard_use_case import get_chat_keyboards
from ..filters.chat_exist import ChatExistFilter
from ..filters.chat_type import ChatTypeFilter
from ..keyboards.operator_kb import *
from ..models.chat_model import ChatModel
from ..schemas.chat_schema import ChatCreate
from ..schemas.message_schema import MessageCreate
from ..services.chat_service import chat_service
from ..services.message_service import message_service

router = Router()
router.message.filter(ChatTypeFilter())

start_message = "Отправить сообщение - выпадает список подключенных чатов, после нажатия данный чат будет выбран. Далее потребует сообщение. После успешной отправки бот выдаст соответсвующее сообщение."

LEAD_TEMPLATE = """
📞 Телефон
\t{phone}
👋🏾 Имя
\t{name}
📝 Комментарий
{comment}
"""


class OrderSend(StatesGroup):
    write_comment = State()
    write_number = State()
    write_name = State()


@router.callback_query(F.data == 'cancel')
async def cancel(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await state.clear()


@router.message(Command('start'))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    message = await message.answer(start_message, reply_markup=create_menu())
    await message.answer("Или найдите чат в поиске", reply_markup=InlineKeyboardMarkup(
        row_width=1,
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Открыть список чатов", web_app=WebAppInfo(url=settings.WEB_APP_URL))
            ]
        ]
    ))
    # await activate_sender(message, state)

@router.callback_query(F.data == 'back')
async def prev_state(call: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    match current_state:
        case OrderSend.write_comment.state:
            await write_name(call.message, state)
        case OrderSend.write_name.state:
            await write_number(call.message, state)
        case OrderSend.write_number.state:
            await menu(call.message, state)


@router.message(or_f(StateFilter(None), and_f(F.text.contains('Отправить сообщение'), OrderSend.write_comment)))
async def activate_sender(message: Message, state: FSMContext):
    messages = []
    chats = await chat_service.filter(limit=1000, order=['name'])
    for kb in get_chat_keyboards(chats, '0'):
        m = await message.answer("Выберите подключенный чат:",
                                 reply_markup=kb)
        messages.append(m.message_id)
    await state.update_data({'messages': messages})


@router.callback_query(F.data[0] == '1')
async def choosing_chats(call: CallbackQuery, state: FSMContext):
    await state.set_data({})
    messages = []
    chats = await chat_service.filter(limit=1000, order=['name'])
    for i, kb in enumerate(get_chat_keyboards(chats, '0')):
        if i == 0:
            m = await call.message.edit_text("Выберите подключенный чат:",
                                             reply_markup=kb)
        else:
            m = await call.message.answer("Выберите подключенный чат:",
                                          reply_markup=kb)
        messages.append(m.message_id)
    await state.update_data({'messages': messages})


@router.callback_query(F.data[0] == '0', ChatExistFilter(lambda x: x.data.split('|')[1]))
async def active_mail_message(call: CallbackQuery, state: FSMContext):
    chat: ChatModel = await chat_service.get(call.data.split('|')[1])
    state_data = await state.get_data()
    messages = state_data.get('messages', [])
    await state.update_data({'chat_id': int(call.data.split('|')[1])})
    for i in messages:
        with suppress(TelegramBadRequest):
            await call.bot.delete_message(call.from_user.id, i)

    await call.message.answer(f"Выбранный чат: {chat.name}\nТеперь отправьте телефон клиента",
                              reply_markup=back_to_choosing())
    await state.set_state(OrderSend.write_number)


def validate_phone_lib(phone: str, region: str = "RU") -> str | None:
    try:
        pn = phonenumbers.parse(phone, region)
        if phonenumbers.is_valid_number(pn):
            return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except NumberParseException:
        return None


@router.message(OrderSend.write_number)
async def write_number(message: Message, state: FSMContext):
    phone = validate_phone_lib(message.text)
    if phone is None:
        await message.answer("Введите корректный номер", reply_markup=back_to_choosing())
        return

    await state.update_data({'phone': phone})
    await message.answer('Введите имя клиента', reply_markup=back_to_choosing())
    await state.set_state(OrderSend.write_name)


@router.message(OrderSend.write_name)
async def write_name(message: Message, state: FSMContext):
    phone = message.text
    # TODO: add validation if needed
    await state.update_data({'name': phone})
    await message.answer('Введите имя клиента', reply_markup=back_to_choosing())
    await state.set_state(OrderSend.write_comment)


async def except_when_send_video(send_video_func, *args, **kwargs) -> Message:
    chat_id = kwargs["chat_id"]
    chat_name = kwargs["chat_name"]

    try:
        r = await send_video_func(*args, **kwargs)
    except TelegramMigrateToChat as e:
        await chat_service.delete(str(chat_id))
        try:
            await chat_service.create(ChatCreate(id=str(e.migrate_to_chat_id), name=chat_name))
        except IntegrityError:
            print('Supergroup already exists', chat_id)

        try:
            chat_id = str(e.migrate_to_chat_id)
            kwargs["chat_id"] = chat_id
            r = await send_video_func(*args, **kwargs)
        except Exception as e:
            print('Error:', chat_id, chat_name)
            print(f'Send to chat error: {e}')
            return None

    except Exception as e:
        print('Error:', chat_id, chat_name)
        print(f'Send to chat error: {e}')
        return None
    return r


@router.message(OrderSend.write_comment)
async def send_message_to_selected_chat(message: Message,
                                        state: FSMContext,
                                        album: Optional[List[Message]] = None):
    data = await state.get_data()

    chat_id = data.get('chat_id')
    phone = data.get('phone') or "—"
    name = data.get('name') or "—"

    if chat_id is None:
        await message.answer('Сначала выберите чат!')
        await state.clear()
        return
    if album:
        media_group = []
        text_data = ''
        for msg in album:
            caption = LEAD_TEMPLATE.format(phone=phone, name=name, comment=msg.caption)
            if msg.photo:
                file_id = msg.photo[-1].file_id
                media_group.append(InputMediaPhoto(media=file_id, caption=caption))
            else:
                obj_dict = msg.model_dump()
                file_id = obj_dict[msg.content_type]['file_id']
                if msg.document:
                    media_group.append(InputMediaDocument(media=file_id, caption=caption))
                elif msg.video:
                    media_group.append(InputMediaVideo(media=file_id, caption=caption))
                elif msg.audio:
                    media_group.append(InputMediaAudio(media=file_id, caption=caption))
                elif msg.animation:
                    media_group.append(InputMediaAnimation(media=file_id, caption=caption))
            if message.caption:
                text_data += message.caption + " "
        # await state.set_data({'message': media_group, 'sent': []})

        send_message = (await except_when_send_video(message.bot.send_media_group, chat_id=chat_id, media=media_group,
                                                     chat_name=message.chat.full_name))[0]
    else:
        if message.text:
            text_data = message.text
        else:
            if message.caption:
                text_data = message.caption
            else:
                text_data = ""
        send_message = await except_when_send_video(
            message.bot.send_message,
            LEAD_TEMPLATE.format(phone=phone, name=name, comment=message.text),
            chat_id=chat_id,
            chat_name=message.chat.full_name,
        )

    if text_data:
        numbers = re.finditer(r'((\+7|8|7)[\- ]?)[0-9]{10}', text_data)
        await message_service.create_many(
            [MessageCreate(id=str(send_message.message_id), chat_id=str(chat_id), phone=number[0][-10:],
                           message=text_data) for number in set(numbers)])

    await message.answer('Сообщение успешно отправлено!')
    await state.clear()
    await menu(message, state)
