from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.blocking_reason import BlockingReason


BLOCKING_REASONS_SEED = [
    ("DESCRIPTION_MISMATCH", "Description does not match product", False),
    ("IMAGE_MISMATCH", "Image does not match product", False),
    ("INVALID_CATEGORY", "Invalid product category", False),
    ("INSUFFICIENT_INFO", "Insufficient product information", False),
    ("OFFENSIVE_CONTENT", "Offensive content", False),
    ("DUPLICATE_PRODUCT", "Duplicate product", False),
    ("INVALID_PRICE", "Invalid price", False),
    ("COUNTERFEIT", "Counterfeit product", True),
    ("FORBIDDEN_GOODS", "Forbidden goods", True),
    ("COPYRIGHT_VIOLATION", "Copyright violation", True),
]


async def seed_blocking_reasons(db: AsyncSession) -> None:
    result = await db.execute(select(BlockingReason))
    existing = result.scalars().all()
    existing_codes = {reason.code for reason in existing}

    for code, title, hard_block in BLOCKING_REASONS_SEED:
        if code in existing_codes:
            continue
        db.add(BlockingReason(code=code, title=title, hard_block=hard_block, is_active=True))


async def list_blocking_reasons(
    db: AsyncSession, hard_block: bool | None, is_active: bool | None
) -> list[BlockingReason]:
    query = select(BlockingReason)
    if hard_block is not None:
        query = query.where(BlockingReason.hard_block == hard_block)
    if is_active is not None:
        query = query.where(BlockingReason.is_active == is_active)
    result = await db.execute(query.order_by(BlockingReason.title.asc()))
    return result.scalars().all()


async def get_blocking_reason(db: AsyncSession, reason_id: str) -> BlockingReason | None:
    result = await db.execute(
        select(BlockingReason).where(BlockingReason.id == reason_id)
    )
    return result.scalar_one_or_none()


async def create_blocking_reason(
    db: AsyncSession, code: str, title: str, description: str | None, hard_block: bool
) -> BlockingReason:
    reason = BlockingReason(
        code=code,
        title=title,
        description=description,
        hard_block=hard_block,
        is_active=True,
    )
    db.add(reason)
    return reason
