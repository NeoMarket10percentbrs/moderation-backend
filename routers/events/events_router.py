from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2b_to_mod_key
from schemas.events import IncomingB2BEvent
from services import product_moderation_service

events_router = APIRouter(tags=["Events"])


@events_router.post(
    "/v1/events/product",
    dependencies=[Depends(require_b2b_to_mod_key)],
)
async def handle_product_event(
    data: IncomingB2BEvent, db: AsyncSession = Depends(get_db)
):
    """
    Handle B2B product events (CREATED, EDITED, DELETED).

    Per MOD-1 flow spec:
    - 200 OK: Event processed or ignored (HARD_BLOCKED, duplicate)
    - 400 Bad Request: Business logic error (duplicate CREATED, missing EDITED ticket)
    - 401 Unauthorized: Invalid X-Service-Key (handled by require_b2b_to_mod_key dependency)
    - 500 Internal: Database or B2B API errors (allows retry)
    """
    await product_moderation_service.handle_b2b_event(db, data)
