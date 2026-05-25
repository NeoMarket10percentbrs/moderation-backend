import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

from core.security import create_access_token
from schemas.moderator import ModeratorCreateRequest, ModeratorRole
from schemas.events import (
	IncomingB2BEvent,
	B2BEventType,
	EventProductEdited,
)
from services import product_moderation_service
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


async def _create_ticket(db, moderator_id, json_after: dict, status: str = "IN_REVIEW") -> Ticket:
	now = datetime.now(timezone.utc)
	ticket = Ticket(
		product_id=uuid.uuid4(),
		seller_id=uuid.uuid4(),
		category_id=uuid.uuid4(),
		kind="CREATE",
		status=status,
		queue_priority=1,
		json_before=None,
		json_after=json_after,
		assigned_moderator_id=moderator_id,
		claimed_at=now,
		claim_expires_at=now + timedelta(minutes=30),
	)
	db.add(ticket)
	await db.commit()
	await db.refresh(ticket)
	return ticket


@pytest.mark.asyncio
async def test_approve_transitions_to_moderated_and_emits_event(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "mod1@example.com", ModeratorRole.MODERATOR)
	token = create_access_token(str(moderator.id), moderator.role)
	ticket = await _create_ticket(
		db_session,
		moderator.id,
		json_after={"skus": [{"id": str(uuid.uuid4())}]},
	)

	captured = {}

	async def _fake_send(payload: dict) -> None:
		captured.update(payload)

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/approve",
		headers={"Authorization": f"Bearer {token}"},
	)

	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert body["status"] == "APPROVED"
	assert captured["event_type"] == "MODERATED"
	assert captured["product_id"] == str(ticket.product_id)


@pytest.mark.asyncio
async def test_approve_others_card_returns_403(client, db_session):
	owner = await _create_moderator(db_session, "owner@example.com", ModeratorRole.MODERATOR)
	other = await _create_moderator(db_session, "other@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(
		db_session,
		owner.id,
		json_after={"skus": [{"id": str(uuid.uuid4())}]},
	)
	token = create_access_token(str(other.id), other.role)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/approve",
		headers={"Authorization": f"Bearer {token}"},
	)

	assert resp.status_code == 403
	payload = resp.json()
	assert payload == {
		"code": "FORBIDDEN",
		"message": "Ticket is assigned to another moderator",
	}


@pytest.mark.asyncio
async def test_approve_after_edited_returns_409(client, db_session):
	moderator = await _create_moderator(db_session, "mod2@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(
		db_session,
		moderator.id,
		json_after={"skus": [{"id": str(uuid.uuid4())}]},
	)

	event = IncomingB2BEvent(
		event_type=B2BEventType.PRODUCT_EDITED,
		idempotency_key=uuid.uuid4(),
		occurred_at=datetime.now(timezone.utc),
		payload=EventProductEdited(
			product_id=ticket.product_id,
			seller_id=ticket.seller_id,
			category_id=ticket.category_id,
			queue_priority=1,
			json_before={"skus": [{"id": str(uuid.uuid4())}]},
			json_after={"skus": [{"id": str(uuid.uuid4())}]},
		),
	)
	await product_moderation_service.handle_b2b_event(db_session, event)

	token = create_access_token(str(moderator.id), moderator.role)
	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/approve",
		headers={"Authorization": f"Bearer {token}"},
	)

	assert resp.status_code == 409
	payload = resp.json()
	assert payload == {
		"code": "TICKET_WRONG_STATUS",
		"message": "Ticket is not in review",
	}


@pytest.mark.asyncio
async def test_approve_without_sku_returns_409(client, db_session):
	moderator = await _create_moderator(db_session, "mod3@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(
		db_session,
		moderator.id,
		json_after={"skus": []},
	)
	token = create_access_token(str(moderator.id), moderator.role)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/approve",
		headers={"Authorization": f"Bearer {token}"},
	)

	assert resp.status_code == 409
	payload = resp.json()
	assert payload == {
		"code": "PRODUCT_NO_SKU",
		"message": "Product has no SKU",
	}
