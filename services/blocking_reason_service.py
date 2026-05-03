from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.blocking_reason import BlockingReason


BLOCKING_REASONS_SEED = [
    ("Описание не соответствует товару", False),
    ("Изображение не соответствует товару", False),
    ("Некорректная категория товара", False),
    ("Недостаточно информации о товаре", False),
    ("Нецензурные или оскорбительные материалы", False),
    ("Дублирование существующего товара", False),
    ("Некорректная цена", False),
    ("Контрафактный товар", True),
    ("Товар запрещён к продаже на территории РФ", True),
    ("Товар нарушает авторские права", True),
]


async def seed_blocking_reasons(db: AsyncSession) -> None:
    result = await db.execute(select(BlockingReason))
    existing = result.scalars().all()
    existing_titles = {reason.title for reason in existing}

    for title, hard_block in BLOCKING_REASONS_SEED:
        if title in existing_titles:
            continue
        db.add(BlockingReason(title=title, hard_block=hard_block))
