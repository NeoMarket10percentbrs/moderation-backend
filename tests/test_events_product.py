import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

from schemas.events import IncomingB2BEvent, B2BEventType
from models import Ticket, ProcessedEvent


async def _create_ticket(
    db,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    status: str = "IN_REVIEW",
    json_after: dict = None,
    assigned_moderator_id: uuid.UUID = None,
) -> Ticket:
    """Helper to create a ticket in the database."""
    ticket = Ticket(
        product_id=product_id,
        seller_id=seller_id,
        category_id=uuid.uuid4(),
        kind="CREATE",
        status=status,
        queue_priority=1,
        json_before=None,
        json_after=json_after or {"name": "Test Product"},
        assigned_moderator_id=assigned_moderator_id,
        claimed_at=datetime.now(timezone.utc) if assigned_moderator_id else None,
    )
    db.add(ticket)
    await db.flush()
    return ticket


@pytest.mark.asyncio
async def test_created_pending(client, db_session, monkeypatch):
    """
    Verify that sending a PRODUCT_CREATED event creates a new ticket with PENDING status.
    Checks: status == PENDING, kind == CREATE, all fields are set correctly.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Mock B2B fetch to return product data
    async def _fake_fetch_product(product_id):
        return {"name": "Test Product", "price": 100}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.CREATED,
        date=event_date,
    )

    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},  # B2B_TO_MOD_KEY
    )

    assert response.status_code == 200

    # Verify ticket was created with PENDING status
    result = await db_session.execute(
        select(Ticket).where(Ticket.product_id == product_id)
    )
    ticket = result.scalar_one_or_none()

    assert ticket is not None
    assert ticket.status == "PENDING"
    assert ticket.kind == "CREATE"
    assert ticket.seller_id == seller_id
    assert ticket.json_after == {"name": "Test Product", "price": 100}
    assert ticket.json_before is None
    assert ticket.assigned_moderator_id is None
    assert ticket.claimed_at is None


@pytest.mark.asyncio
async def test_edited_returns_to_review_from_moderated(client, db_session, monkeypatch):
    """
    Verify that an EDITED event on a MODERATED ticket returns it to PENDING status.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Create an existing ticket in MODERATED state
    ticket = await _create_ticket(
        db_session,
        product_id=product_id,
        seller_id=seller_id,
        status="MODERATED",
        json_after={"name": "Old Product", "price": 50},
    )
    await db_session.commit()

    # Mock B2B fetch
    async def _fake_fetch_product(product_id):
        return {"name": "Updated Product", "price": 150}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.EDITED,
        date=event_date,
    )

    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )

    assert response.status_code == 200

    # Verify ticket status changed to PENDING
    await db_session.refresh(ticket)
    assert ticket.status == "PENDING"
    assert ticket.kind == "EDIT"
    assert ticket.json_after == {"name": "Updated Product", "price": 150}
    assert ticket.json_before == {"name": "Old Product", "price": 50}


@pytest.mark.asyncio
async def test_edited_returns_to_review_from_blocked(client, db_session, monkeypatch):
    """
    Verify that an EDITED event on a BLOCKED ticket returns it to PENDING status.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Create an existing ticket in BLOCKED state
    ticket = await _create_ticket(
        db_session,
        product_id=product_id,
        seller_id=seller_id,
        status="BLOCKED",
        json_after={"name": "Old Product"},
    )
    await db_session.commit()

    # Mock B2B fetch
    async def _fake_fetch_product(product_id):
        return {"name": "Updated Product", "description": "New Description"}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.EDITED,
        date=event_date,
    )

    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )

    assert response.status_code == 200

    await db_session.refresh(ticket)
    assert ticket.status == "PENDING"
    assert ticket.kind == "EDIT"


@pytest.mark.asyncio
async def test_edited_updates_in_review(client, db_session, monkeypatch):
    """
    Verify that an EDITED event on an IN_REVIEW ticket updates its fields
    and resets moderation-related fields.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    moderator_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Create an existing ticket in IN_REVIEW state (claimed by moderator)
    ticket = await _create_ticket(
        db_session,
        product_id=product_id,
        seller_id=seller_id,
        status="IN_REVIEW",
        json_after={"name": "Old Product", "status": "active"},
        assigned_moderator_id=moderator_id,
    )
    await db_session.commit()
    ticket_id = ticket.id

    # Mock B2B fetch
    async def _fake_fetch_product(product_id):
        return {"name": "Updated Product", "status": "archived", "price": 200}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.EDITED,
        date=event_date,
    )

    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )

    assert response.status_code == 200

    # Verify ticket fields were updated
    result = await db_session.execute(select(Ticket).where(Ticket.id == ticket_id))
    updated_ticket = result.scalar_one()

    assert updated_ticket.status == "PENDING"
    assert updated_ticket.kind == "EDIT"
    assert updated_ticket.json_after == {
        "name": "Updated Product",
        "status": "archived",
        "price": 200,
    }
    assert updated_ticket.json_before == {"name": "Old Product", "status": "active"}
    # Moderation fields should be reset
    assert updated_ticket.assigned_moderator_id is None
    assert updated_ticket.claimed_at is None


@pytest.mark.asyncio
async def test_deleted_archived(client, db_session):
    """
    Verify that a PRODUCT_DELETED event removes the ticket from the database.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Create an existing ticket
    ticket = await _create_ticket(
        db_session,
        product_id=product_id,
        seller_id=seller_id,
        status="PENDING",
        json_after={"name": "Product to Delete"},
    )
    await db_session.commit()

    # Send DELETE event
    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.DELETED,
        date=event_date,
    )

    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )

    assert response.status_code == 200

    # Verify ticket was deleted
    result = await db_session.execute(
        select(Ticket).where(Ticket.product_id == product_id)
    )
    deleted_ticket = result.scalar_one_or_none()

    assert deleted_ticket is None


@pytest.mark.asyncio
async def test_duplicate_event_no_side_effects(client, db_session, monkeypatch):
    """
    Verify that sending the same event twice (same product_id and date) creates
    the ticket only once and returns 200 both times without side effects.
    """
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    event_date = datetime.now(timezone.utc)

    # Mock B2B fetch
    async def _fake_fetch_product(product_id):
        return {"name": "Test Product"}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=seller_id,
        event=B2BEventType.CREATED,
        date=event_date,
    )

    event_dict = event.model_dump(mode="json")

    # First request
    response1 = await client.post(
        "/v1/events/product",
        json=event_dict,
        headers={"X-Service-Key": "5e8897654"},
    )
    assert response1.status_code == 200

    # Count tickets after first request
    result1 = await db_session.execute(
        select(Ticket).where(Ticket.product_id == product_id)
    )
    tickets_after_first = result1.scalars().all()
    assert len(tickets_after_first) == 1
    first_ticket = tickets_after_first[0]

    # Second request with same event (product_id and date)
    response2 = await client.post(
        "/v1/events/product",
        json=event_dict,
        headers={"X-Service-Key": "5e8897654"},
    )
    assert response2.status_code == 200

    # Count tickets after second request - should still be 1
    result2 = await db_session.execute(
        select(Ticket).where(Ticket.product_id == product_id)
    )
    tickets_after_second = result2.scalars().all()
    assert len(tickets_after_second) == 1
    second_ticket = tickets_after_second[0]

    # Verify the ticket is the same (no side effects)
    assert first_ticket.id == second_ticket.id
    assert first_ticket.json_after == second_ticket.json_after
    assert first_ticket.status == second_ticket.status

    # Verify ProcessedEvent was created (for idempotency)
    result = await db_session.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "b2b",
            ProcessedEvent.product_id == product_id,
        )
    )
    processed_events = result.scalars().all()
    # After two requests with same event, should have exactly 1 ProcessedEvent
    assert len(processed_events) == 1


@pytest.mark.asyncio
async def test_duplicate_event_different_products(client, db_session, monkeypatch):
    """
    Verify that different events (different product_ids) create separate tickets.
    """
    seller_id = uuid.uuid4()

    # Mock B2B fetch
    async def _fake_fetch_product(product_id):
        return {"name": f"Product {product_id}"}

    from services import product_moderation_service

    monkeypatch.setattr(
        product_moderation_service, "fetch_product", _fake_fetch_product
    )

    # First event
    product_id_1 = uuid.uuid4()
    event_date_1 = datetime.now(timezone.utc)
    event1 = IncomingB2BEvent(
        product_id=product_id_1,
        seller_id=seller_id,
        event=B2BEventType.CREATED,
        date=event_date_1,
    )

    response1 = await client.post(
        "/v1/events/product",
        json=event1.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )
    assert response1.status_code == 200

    # Second event (different product)
    product_id_2 = uuid.uuid4()
    event_date_2 = datetime.now(timezone.utc)
    event2 = IncomingB2BEvent(
        product_id=product_id_2,
        seller_id=seller_id,
        event=B2BEventType.CREATED,
        date=event_date_2,
    )

    response2 = await client.post(
        "/v1/events/product",
        json=event2.model_dump(mode="json"),
        headers={"X-Service-Key": "5e8897654"},
    )
    assert response2.status_code == 200

    # Both tickets should exist
    result = await db_session.execute(select(Ticket))
    all_tickets = result.scalars().all()
    assert len(all_tickets) == 2


@pytest.mark.asyncio
async def test_missing_service_header_401(client):
    """
    Verify that a request without X-Service-Key header returns 401 Unauthorized.
    """
    product_id = uuid.uuid4()

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=uuid.uuid4(),
        event=B2BEventType.CREATED,
        date=datetime.now(timezone.utc),
    )

    # Request WITHOUT X-Service-Key header
    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_service_header_403(client):
    """
    Verify that a request with invalid X-Service-Key header returns 403 Forbidden.
    """
    product_id = uuid.uuid4()

    event = IncomingB2BEvent(
        product_id=product_id,
        seller_id=uuid.uuid4(),
        event=B2BEventType.CREATED,
        date=datetime.now(timezone.utc),
    )

    # Request with INVALID X-Service-Key header
    response = await client.post(
        "/v1/events/product",
        json=event.model_dump(mode="json"),
        headers={"X-Service-Key": "invalid_key"},
    )

    assert response.status_code == 403
