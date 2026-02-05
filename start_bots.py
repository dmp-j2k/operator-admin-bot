import asyncio

import uvicorn
from aiogram import Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from fastapi import FastAPI, HTTPException, Header, Depends

from src.services.operator_helper.handlers.operator import OrderSend
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


@app.get("/selectGroup")
async def send_photo(
    user_id: int,
    group_id: int,
    token: None = Depends(verify_bearer_token) # pylint: disable=unused-argument
):
    bot = operator_bot.bot
    state: FSMContext = await dp.fsm.get_context(
        bot=bot,
        chat_id=user_id,
        user_id=user_id,
    )

    await state.update_data({'chat_id': int(group_id)})
    await state.set_state(OrderSend.write_text)

    return {"status": "ok"}


async def run_fastapi():
    config = uvicorn.Config(
        app, host="127.0.0.1", port=settings.SERVICE_PORT, loop="asyncio", log_level="info"
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
