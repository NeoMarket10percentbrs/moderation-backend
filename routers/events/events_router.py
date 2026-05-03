from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2b_to_mod_key
from schemas.events import ProductEventIn, EventProcessedResponse
from services import product_moderation_service


events_router = APIRouter(tags=["Events"])


@events_router.post(
    "/v1/events/product",
    response_model=EventProcessedResponse,
    dependencies=[Depends(require_b2b_to_mod_key)],
)
async def handle_product_event(
    data: ProductEventIn,
    db: AsyncSession = Depends(get_db)
):
    response = await product_moderation_service.handle_b2b_event(db, data)
    return EventProcessedResponse(**response)
