"""FinTrack backend package."""
import asyncio
import sys

# На Windows (Python 3.8+) asyncio по умолчанию использует ProactorEventLoop,
# а psycopg (как и asyncpg) умеет работать только с SelectorEventLoop. Поэтому
# на Windows явно переключаем политику. Это безопасно: SelectorEventLoop поддерживает
# всё, что нам нужно (TCP, async IO); единственное ограничение — нет нативной
# поддержки subprocess через asyncio, но мы их и не запускаем.
#
# Ставим переключение в __init__.py пакета, чтобы оно сработало при ЛЮБОМ импорте
# чего-либо из app.*: alembic/env.py, app.main под uvicorn, test_db.py — все они
# пройдут через эту строку до первого asyncio.run().
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
