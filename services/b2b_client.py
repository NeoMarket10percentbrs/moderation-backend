import httpx
from fastapi import status
from core.config import settings
from core.errors import raise_api_error


async def fetch_product(product_id: str) -> dict:
    if not settings.B2B_SERVICE_URL:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "B2B service URL is not configured",
        )

    url = f"{settings.B2B_SERVICE_URL}/api/products/{product_id}"
    headers = {"X-Service-Key": settings.MOD_SERVICE_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15.0)
    except httpx.RequestError:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "BAD_GATEWAY",
            "Failed to fetch product from B2B",
        )

    if response.status_code >= 400:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "BAD_GATEWAY",
            "Failed to fetch product from B2B",
        )

    product_data = response.json()
    _strip_private_sku_fields(product_data)
    return product_data


async def send_moderation_event(payload: dict) -> None:
    if not settings.B2B_SERVICE_URL:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "B2B service URL is not configured",
        )

    url = f"{settings.B2B_SERVICE_URL}/api/v1/moderation/events"
    headers = {"X-Service-Key": settings.MOD_SERVICE_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
    except httpx.RequestError:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "BAD_GATEWAY",
            "Failed to send moderation event to B2B",
        )

    if response.status_code >= 400:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "BAD_GATEWAY",
            "Failed to send moderation event to B2B",
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
