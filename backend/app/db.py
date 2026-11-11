from tortoise import Tortoise


async def init_db(database_url: str, generate_schemas: bool = False):
    # Sanic creates request tasks separately from the startup listener task.
    # Match Tortoise's Sanic integration so those tasks share the worker's DB.
    await Tortoise.init(db_url=database_url, modules={"models": ["backend.app.models"]}, use_tz=True, timezone="UTC", _enable_global_fallback=True)
    if generate_schemas:
        await Tortoise.generate_schemas(safe=True)


async def close_db():
    await Tortoise.close_connections()
