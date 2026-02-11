import asyncio
import base64
import os

import uvicorn
from aiogram import Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import InputMediaDocument, FSInputFile, InlineKeyboardMarkup, WebAppInfo, InlineKeyboardButton
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

from src.services.operator_helper.keyboards.operator_kb import create_menu
from src.services.operator_helper.handlers.operator import start_message, LEAD_TEMPLATE
from src.s3_client import s3client
from src.config.project_config import settings
from src.services.admin.bot import admin_bot
from src.services.admin.middlewares.album_middleware import AlbumMiddleware
from src.services.admin.middlewares.log_middleware import LogMiddleware
from src.services.operator_helper.bot import operator_bot

key_builder = DefaultKeyBuilder(with_bot_id=True)
redis_storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=key_builder)

app = FastAPI(title="OperatorBot API")
operator_dp = Dispatcher(storage=redis_storage)
admins_dp = Dispatcher(storage=redis_storage)


async def verify_bearer_token(authorization: str | None = Header(None)):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.split(" ")[1]
    if token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


class LeadRequest(BaseModel):
    phone: str
    name: str
    comment: str
    files: list[str]


@app.post("/selectGroup")
async def send_photo(
    user_id: int,
    group_id: str,
    lead: LeadRequest,
    token: None = Depends(verify_bearer_token)  # pylint: disable=unused-argument
):
    print(user_id, group_id)
    print(lead)

    bot = operator_bot.bot
    state: FSMContext = operator_dp.fsm.get_context(
        bot=bot,
        chat_id=user_id,
        user_id=user_id,
    )
    message = LEAD_TEMPLATE.format(
        phone=lead.phone,
        name=lead.name,
        comment=lead.comment if lead.comment else "-",
    )

    if not lead.files:
        await bot.send_message(group_id, message)
    else:
        temp_files = await s3client.download_files(lead.files)
        try:
            media = [
                InputMediaDocument(media=FSInputFile(tmp.path, filename=base64.b64decode(tmp.real_name).decode('utf-8')))
                for tmp in temp_files
            ]
            media[-1].caption = message
            await bot.send_media_group(
                chat_id=group_id,
                media=media,
            )

            await s3client.delete_files(lead.files)
        finally:
            for tmp in temp_files:
                try:
                    if os.path.exists(tmp.path):
                        os.remove(tmp.path)
                except OSError:
                    pass

    await state.clear()
    await bot.send_message(user_id, "Сообщение отправлено")
    message = await bot.send_message(user_id, start_message, reply_markup=create_menu())
    await message.answer("Или найдите чат в поиске", reply_markup=InlineKeyboardMarkup(
        row_width=1,
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Открыть список чатов", web_app=WebAppInfo(url=settings.WEB_APP_URL))
            ]
        ]
    ))
    return {"status": "ok"}


async def run_fastapi():
    config = uvicorn.Config(
        app, host="0.0.0.0", port=settings.SERVICE_PORT, loop="asyncio", log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def start_bots_polling():
    operator_dp.message.outer_middleware(AlbumMiddleware())
    operator_dp.message.outer_middleware(LogMiddleware())
    operator_dp.callback_query.outer_middleware(LogMiddleware())

    admins_dp.message.outer_middleware(AlbumMiddleware())
    admins_dp.message.outer_middleware(LogMiddleware())
    admins_dp.callback_query.outer_middleware(LogMiddleware())

    await admin_bot.start_bot(admins_dp)
    await operator_bot.start_bot(operator_dp)

    loop = asyncio.get_running_loop()
    loop.create_task(run_fastapi())

    await asyncio.gather(
        operator_dp.start_polling(operator_bot.bot),
        admins_dp.start_polling(admin_bot.bot),
    )


if __name__ == '__main__':
    asyncio.run(start_bots_polling())
