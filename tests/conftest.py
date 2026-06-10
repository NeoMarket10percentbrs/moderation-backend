import pytest
import sqlalchemy as sa
from httpx import AsyncClient, ASGITransport

from main import app
from core.database import AsyncSessionLocal, Base, engine, get_db


import models


async def _truncate_all(session):
    # Expunge all pending objects to avoid flush after truncate
    session.expunge_all()

    await session.execute(
        sa.text(
            "TRUNCATE TABLE "
            "ticket_history, "
            "field_reports, "
            "ticket_blocking_reasons, "
            "processed_events, "
            "refresh_tokens, "
            "product_moderation, "
            "moderators, "
            "blocking_reasons "
            "RESTART IDENTITY CASCADE"
        )
    )
    await session.commit()


@pytest.fixture(autouse=True)
async def init_db():

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        await _truncate_all(session)
        try:
            yield session
        finally:
            await _truncate_all(session)


@pytest.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://moderation-app.moderation-backend.orb.local",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
