import httpx
from fastapi import HTTPException, status
from core.config import settings


async def fetch_product(product_id: str) -> dict:
    if not settings.B2B_SERVICE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="B2B_SERVICE_URL not configured",
        )

    url = f"{settings.B2B_SERVICE_URL}/api/products/{product_id}"
    headers = {"X-Service-Key": settings.MOD_SERVICE_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch product from B2B",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch product from B2B",
        )

    product_data = response.json()
    _strip_private_sku_fields(product_data)
    return product_data


async def send_moderation_event(payload: dict) -> None:
    if not settings.B2B_SERVICE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="B2B_SERVICE_URL not configured",
        )

    url = f"{settings.B2B_SERVICE_URL}/api/products/events"
    headers = {"X-Service-Key": settings.MOD_SERVICE_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send moderation event to B2B",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send moderation event to B2B",
        )


def _strip_private_sku_fields(product_data: dict) -> None:
    skus = product_data.get("skus")
    if not isinstance(skus, list):
        return
    for sku in skus:
        if not isinstance(sku, dict):
            continue
        sku.pop("cost_price", None)
        sku.pop("reserved_quantity", None)
