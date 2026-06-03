import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

from core.security import create_access_token
from schemas.moderator import ModeratorCreateRequest, ModeratorRole
from schemas.events import (
	IncomingB2BEvent,
	B2BEventType,
	EventProductCreated,
	EventProductEdited,
	EventProductDeleted,
)
from services import product_moderation_service
from services.blocking_reason_service import create_blocking_reason
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
async def test_hard_block_transitions_to_terminal_and_emits_event(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb_mod@example.com", ModeratorRole.MODERATOR)
	token = create_access_token(str(moderator.id), moderator.role)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="FORBIDDEN_GOODS", title="Forbidden", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	captured = {}

	async def _fake_send(payload: dict) -> None:
		captured.update(payload)

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/block",
		headers={"Authorization": f"Bearer {token}"},
		json={
			"blocking_reason_ids": [str(reason.id)],
			"comment": "Permanent",
			"field_reports": [
				{"field_path": "title", "message": "Forbidden title", "severity": "ERROR"}
			],
		},
	)

	assert resp.status_code == 200
	body = resp.json()
	assert body["status"] == "HARD_BLOCKED"
	assert captured.get("event_type") == "BLOCKED"
	assert captured.get("occurred_at")
	datetime.fromisoformat(captured["occurred_at"])
	assert captured.get("hard_block") is True
	assert captured.get("blocking_reason_id") == str(reason.id)
	assert captured.get("field_reports") == [
		{"field_name": "title", "comment": "Forbidden title"}
	]
	assert "blocking_reason_ids" not in captured
	assert "field_path" not in captured["field_reports"][0]
	assert "message" not in captured["field_reports"][0]
	assert "severity" not in captured["field_reports"][0]


@pytest.mark.asyncio
async def test_hard_block_event_carries_hard_block_true(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb2@example.com", ModeratorRole.MODERATOR)
	token = create_access_token(str(moderator.id), moderator.role)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="COUNTERFEIT", title="Counterfeit", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	captured = {}

	async def _fake_send(payload: dict) -> None:
		captured.update(payload)

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/block",
		headers={"Authorization": f"Bearer {token}"},
		json={"blocking_reason_ids": [str(reason.id)], "comment": "Counterfeit", "field_reports": []},
	)

	assert resp.status_code == 200
	assert captured.get("hard_block") is True


@pytest.mark.asyncio
async def test_any_modify_on_hard_blocked_returns_403(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb5@example.com", ModeratorRole.MODERATOR)
	token = create_access_token(str(moderator.id), moderator.role)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="FORBIDDEN_GOODS4", title="Forbidden4", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	async def _fake_send(_: dict) -> None:
		return None

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/block",
		headers={"Authorization": f"Bearer {token}"},
		json={"blocking_reason_ids": [str(reason.id)], "comment": "Terminal", "field_reports": []},
	)
	assert resp.status_code == 200
	assert resp.json()["status"] == "HARD_BLOCKED"

	approve_resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/approve",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert approve_resp.status_code == 403
	assert approve_resp.json() == {
		"code": "FORBIDDEN",
		"message": "Ticket is hard blocked",
	}

	release_resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/release",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert release_resp.status_code == 403
	assert release_resp.json() == {
		"code": "FORBIDDEN",
		"message": "Ticket is hard blocked",
	}

	block_resp = await client.post(
		f"/api/v1/tickets/{ticket.id}/block",
		headers={"Authorization": f"Bearer {token}"},
		json={"blocking_reason_ids": [str(reason.id)], "comment": "Repeat", "field_reports": []},
	)
	assert block_resp.status_code == 403
	assert block_resp.json() == {
		"code": "FORBIDDEN",
		"message": "Ticket is hard blocked",
	}


@pytest.mark.asyncio
async def test_edited_event_on_hard_blocked_is_ignored(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb3@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="FORBIDDEN_GOODS2", title="Forbidden2", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	async def _fake_send(_: dict) -> None:
		return None

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	
	await product_moderation_service.block_ticket(
		db_session,
		ticket,
		moderator.id,
		type("D", (), {"blocking_reason_ids": [reason.id], "field_reports": [], "comment": "x"})(),
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

	
	await db_session.refresh(ticket)
	assert ticket.status == "HARD_BLOCKED"


@pytest.mark.asyncio
async def test_created_event_on_hard_blocked_is_ignored(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb6@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="FORBIDDEN_GOODS5", title="Forbidden5", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	async def _fake_send(_: dict) -> None:
		return None

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	await product_moderation_service.block_ticket(
		db_session,
		ticket,
		moderator.id,
		type("D", (), {"blocking_reason_ids": [reason.id], "field_reports": [], "comment": "x"})(),
	)

	event = IncomingB2BEvent(
		event_type=B2BEventType.PRODUCT_CREATED,
		idempotency_key=uuid.uuid4(),
		occurred_at=datetime.now(timezone.utc),
		payload=EventProductCreated(
			product_id=ticket.product_id,
			seller_id=ticket.seller_id,
			category_id=ticket.category_id,
			queue_priority=1,
			json_after={"skus": [{"id": str(uuid.uuid4())}]},
		),
	)

	await product_moderation_service.handle_b2b_event(db_session, event)

	await db_session.refresh(ticket)
	assert ticket.status == "HARD_BLOCKED"


@pytest.mark.asyncio
async def test_deleted_event_removes_hard_blocked(client, db_session, monkeypatch):
	moderator = await _create_moderator(db_session, "hb4@example.com", ModeratorRole.MODERATOR)
	ticket = await _create_ticket(db_session, moderator.id, json_after={"skus": [{"id": str(uuid.uuid4())}]})

	reason = await create_blocking_reason(db_session, code="FORBIDDEN_GOODS3", title="Forbidden3", description="", hard_block=True)
	await db_session.commit()
	await db_session.refresh(reason)

	async def _fake_send(_: dict) -> None:
		return None

	monkeypatch.setattr(product_moderation_service, "send_moderation_event", _fake_send)

	await product_moderation_service.block_ticket(
		db_session,
		ticket,
		moderator.id,
		type("D", (), {"blocking_reason_ids": [reason.id], "field_reports": [], "comment": "x"})(),
	)

	event = IncomingB2BEvent(
		event_type=B2BEventType.PRODUCT_DELETED,
		idempotency_key=uuid.uuid4(),
		occurred_at=datetime.now(timezone.utc),
		payload=EventProductDeleted(product_id=ticket.product_id),
	)

	await product_moderation_service.handle_b2b_event(db_session, event)

	result = await db_session.execute(
		__import__("sqlalchemy").select(Ticket).where(Ticket.product_id == ticket.product_id)
	)
	assert result.scalar_one_or_none() is None
