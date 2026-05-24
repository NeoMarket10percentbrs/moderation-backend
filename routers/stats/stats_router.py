from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_moderator
from schemas.stats import StatsOverview, ModeratorStats
from services.stats_service import get_overview, get_moderator_stats


stats_router = APIRouter(
    prefix="/v1/stats",
    tags=["Stats"],
    dependencies=[Depends(get_current_moderator)],
)


@stats_router.get("/overview", response_model=StatsOverview)
async def stats_overview(period: str = "today", db: AsyncSession = Depends(get_db)):
    data = await get_overview(db, period)
    return StatsOverview(**data)


@stats_router.get("/moderators", response_model=list[ModeratorStats])
async def stats_moderators(period: str = "week", db: AsyncSession = Depends(get_db)):
    data = await get_moderator_stats(db, period)
    return [ModeratorStats(**row) for row in data]
