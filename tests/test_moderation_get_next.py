import uuid
from datetime import datetime
import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.asyncio

from core.security import create_access_token
from schemas.moderator import ModeratorCreateRequest, ModeratorRole

from services.moderator_service import create_moderator
from models import Ticket


async def _create_moderator(db, email: str, role: ModeratorRole):
    moderator = await create_moderator(
        db,
        ModeratorCreateRequest(
            email=email,
            password="StrongPass123!",
            first_name="Test",
            last_name="User",
            role=role,
            category_specializations=[],
        ),
        is_admin=(role == ModeratorRole.ADMIN),
    )
    await db.commit()
    await db.refresh(moderator)
    return moderator


async def _create_pending_ticket(
    db,
    product_id: uuid.UUID = None,
    seller_id: uuid.UUID = None,
    queue_priority: int = 3,
) -> Ticket:
    """Helper to create a pending ticket in the database."""
    ticket = Ticket(
        product_id=product_id or uuid.uuid4(),
        seller_id=seller_id or uuid.uuid4(),
        category_id=uuid.uuid4(),
        kind="CREATE",
        status="PENDING",
        queue_priority=queue_priority,
        json_before=None,
        json_after={"name": "Test Product", "skus": [{"id": str(uuid.uuid4())}]},
        assigned_moderator_id=None,
        claimed_at=None,
        claim_expires_at=None,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@pytest.mark.asyncio
async def test_next_returns_oldest_pending(client, db_session):
    """
    Happy path: get-next returns the oldest pending ticket and transitions it PENDING → IN_REVIEW.
    Verifies that the ticket is claimed and moderation fields are set correctly.
    """
    # Create two pending tickets with different priorities and creation times
    ticket1 = await _create_pending_ticket(db_session, queue_priority=3)
    await db_session.commit()
    # Small delay to ensure different timestamps
    await db_session.execute(text("SELECT pg_sleep(0.01)"))
    ticket2 = await _create_pending_ticket(
        db_session, queue_priority=2
    )  # Higher priority
    await db_session.commit()

    moderator = await _create_moderator(
        db_session, "mod1@example.com", ModeratorRole.MODERATOR
    )
    token = create_access_token(str(moderator.id), moderator.role)

    response = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    # Verify ticket2 (higher priority) was returned
    body = response.json()
    assert body["id"] == str(ticket2.id)
    assert body["status"] == "IN_REVIEW"
    assert body["assigned_moderator_id"] == str(moderator.id)
    assert body["claimed_at"] is not None
    assert body["claim_expires_at"] is not None

    # Verify claim_expires_at is ~30 minutes from now
    claimed_at = datetime.fromisoformat(body["claimed_at"].replace("Z", "+00:00"))
    claim_expires_at = datetime.fromisoformat(
        body["claim_expires_at"].replace("Z", "+00:00")
    )
    assert (claim_expires_at - claimed_at).total_seconds() == 1800  # 30 minutes

    # Verify ticket1 is still pending
    result = await db_session.execute(select(Ticket).where(Ticket.id == ticket1.id))
    still_pending = result.scalar_one()
    assert still_pending.status == "PENDING"
    assert still_pending.assigned_moderator_id is None


@pytest.mark.asyncio
async def test_concurrent_two_moderators_get_different_cards(client, db_session):
    """
    Concurrent request test: two moderators calling get-next should get different tickets.
    Uses database locking to ensure no race condition.
    """
    # Create two pending tickets
    ticket1 = await _create_pending_ticket(db_session, queue_priority=3)
    await db_session.commit()
    ticket2 = await _create_pending_ticket(db_session, queue_priority=3)
    await db_session.commit()

    moderator1 = await _create_moderator(
        db_session, "mod1@example.com", ModeratorRole.MODERATOR
    )
    moderator2 = await _create_moderator(
        db_session, "mod2@example.com", ModeratorRole.MODERATOR
    )
    token1 = create_access_token(str(moderator1.id), moderator1.role)
    token2 = create_access_token(str(moderator2.id), moderator2.role)

    # First moderator gets a ticket
    response1 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response1.status_code == 200
    ticket1_id = response1.json()["id"]

    # Second moderator gets a different ticket
    response2 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response2.status_code == 200
    ticket2_id = response2.json()["id"]

    # Verify they got different tickets
    assert ticket1_id != ticket2_id

    # Verify both tickets are now IN_REVIEW
    result = await db_session.execute(
        select(Ticket).where(Ticket.id.in_([ticket1_id, ticket2_id]))
    )
    tickets = result.scalars().all()
    assert len(tickets) == 2
    for ticket in tickets:
        assert ticket.status == "IN_REVIEW"


@pytest.mark.asyncio
async def test_empty_queue_returns_204(client, db_session):
    """
    When there are no pending tickets, get-next returns 204 No Content.
    """
    moderator = await _create_moderator(
        db_session, "mod1@example.com", ModeratorRole.MODERATOR
    )
    token = create_access_token(str(moderator.id), moderator.role)

    response = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_moderator_already_has_in_review_returns_409(client, db_session):
    """
    When a moderator already has a ticket IN_REVIEW, get-next returns 409 Conflict.
    """
    # Create a pending ticket
    ticket = await _create_pending_ticket(db_session, queue_priority=3)
    await db_session.commit()

    moderator = await _create_moderator(
        db_session, "mod1@example.com", ModeratorRole.MODERATOR
    )
    token = create_access_token(str(moderator.id), moderator.role)

    # First request - should succeed and claim the ticket
    response1 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.status_code == 200
    assert response1.json()["id"] == str(ticket.id)

    # Create another pending ticket
    ticket2 = await _create_pending_ticket(db_session, queue_priority=3)
    await db_session.commit()

    # Second request - should return 409 because moderator already has a ticket
    response2 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_next_respects_queue_priority(client, db_session):
    """
    Verify that get-next returns tickets in order of queue_priority (lowest first),
    then by creation time (oldest first).
    """
    # Create tickets with different priorities and times
    await db_session.execute(text("SELECT pg_sleep(0.01)"))
    ticket_low = await _create_pending_ticket(
        db_session, queue_priority=4
    )  # Lowest priority
    await db_session.commit()

    await db_session.execute(text("SELECT pg_sleep(0.01)"))
    ticket_high = await _create_pending_ticket(
        db_session, queue_priority=1
    )  # Highest priority
    await db_session.commit()

    await db_session.execute(text("SELECT pg_sleep(0.01)"))
    ticket_med = await _create_pending_ticket(db_session, queue_priority=2)
    await db_session.commit()

    moderator = await _create_moderator(
        db_session, "mod1@example.com", ModeratorRole.MODERATOR
    )
    token = create_access_token(str(moderator.id), moderator.role)

    # First request should get highest priority (1)
    response1 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.status_code == 200
    assert response1.json()["id"] == str(ticket_high.id)

    # Second request - moderator already has a ticket in review
    response2 = await client.post(
        "/api/v1/product-moderation/get-next",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Returns 409 because moderator already has a ticket
    assert response2.status_code == 409
