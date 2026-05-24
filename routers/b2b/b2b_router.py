from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2b_to_mod_key
from core.errors import raise_api_error
from schemas.events import IncomingB2BEvent
from services.product_moderation_service import handle_b2b_event


b2b_router = APIRouter(prefix="/v1/b2b", tags=["B2B Events"])


@b2b_router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_b2b_to_mod_key)],
)
async def receive_b2b_event(
    data: IncomingB2BEvent,
    db: AsyncSession = Depends(get_db),
):
    is_duplicate = await handle_b2b_event(db, data)
    if is_duplicate:
        raise_api_error(status.HTTP_409_CONFLICT, "DUPLICATE_EVENT", "Event already processed")
