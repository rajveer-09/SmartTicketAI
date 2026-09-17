from datetime import UTC, datetime

import pytest

from app.models import TicketStatus, UserRole
from tests.conftest import auth_headers

S = TicketStatus


@pytest.fixture
async def people(make_user):
    return {
        "owner": await make_user("owner@example.com", password=None),
        "other": await make_user("other@example.com", password=None),
        "mod": await make_user("mod@example.com", password=None, role=UserRole.MODERATOR),
        "mod2": await make_user("mod2@example.com", password=None, role=UserRole.MODERATOR),
        "admin": await make_user("admin@example.com", password=None, role=UserRole.ADMIN),
    }


def names(events) -> list[str]:
    return [e.name for e in events]


# --- Creating and listing ---


async def test_create_ticket_saves_and_emits_event(db_client, people, events):
    owner = people["owner"]
    resp = await db_client.post(
        "/api/tickets",
        json={"title": "  VPN keeps dropping  ", "description": "Disconnects every 5 minutes."},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "VPN keeps dropping"
    assert body["status"] == "open"
    assert body["created_by"]["email"] == "owner@example.com"
    assert body["assignee"] is None
    assert names(events) == ["ticket/created"]
    assert events[0].data["ticket_id"] == body["id"]


async def test_create_ticket_requires_auth_and_valid_body(db_client, people):
    assert (await db_client.post("/api/tickets", json={})).status_code == 401
    resp = await db_client.post(
        "/api/tickets",
        json={"title": "Hi", "description": "short"},
        headers=auth_headers(people["owner"]),
    )
    assert resp.status_code == 422


async def test_my_tickets_scopes_and_filters(db_client, people, make_ticket):
    owner = people["owner"]
    old = datetime(2026, 1, 10, 12, tzinfo=UTC)
    await make_ticket(owner, "Laptop won't boot", created_at=old)
    await make_ticket(owner, "Email bounce 100%", status=S.IN_PROGRESS, assignee=people["mod"])
    await make_ticket(owner, "Old closed issue", status=S.CLOSED, assignee=people["mod"])
    await make_ticket(people["other"], "Someone else's laptop")
    h = auth_headers(owner)

    async def titles(**params) -> list[str]:
        resp = await db_client.get("/api/tickets/mine", params=params, headers=h)
        assert resp.status_code == 200, resp.text
        return sorted(t["title"] for t in resp.json()["items"])

    assert await titles() == ["Email bounce 100%", "Laptop won't boot"]
    assert await titles(scope="history") == ["Old closed issue"]
    assert await titles(scope="all", q="LAPTOP") == ["Laptop won't boot"]
    assert await titles(scope="all", status=["in_progress", "closed"]) == [
        "Email bounce 100%",
        "Old closed issue",
    ]
    assert await titles(date_to="2026-01-10") == ["Laptop won't boot"]
    assert await titles(date_from="2026-01-11") == ["Email bounce 100%"]
    # LIKE wildcards are matched literally.
    assert await titles(scope="all", q="%") == ["Email bounce 100%"]

    resp = await db_client.get("/api/tickets/mine", params={"size": 1}, headers=h)
    assert resp.json()["total"] == 2
    assert resp.json()["pages"] == 2


async def test_bad_date_range_is_rejected(db_client, people):
    resp = await db_client.get(
        "/api/tickets/mine",
        params={"date_from": "2026-02-01", "date_to": "2026-01-01"},
        headers=auth_headers(people["owner"]),
    )
    assert resp.status_code == 422


# --- Visibility ---


@pytest.mark.parametrize(
    ("viewer", "status_code", "sees_notes"),
    [
        ("owner", 200, False),
        ("mod", 200, True),  # assignee
        ("admin", 200, True),
        ("other", 404, None),
        ("mod2", 404, None),  # moderator not assigned
    ],
)
async def test_ticket_visibility(db_client, people, make_ticket, viewer, status_code, sees_notes):
    ticket = await make_ticket(
        people["owner"], status=S.ASSIGNED, assignee=people["mod"], ai_notes="Check the fuse"
    )
    resp = await db_client.get(f"/api/tickets/{ticket.id}", headers=auth_headers(people[viewer]))

    assert resp.status_code == status_code
    if status_code == 200:
        assert (resp.json()["ai_notes"] == "Check the fuse") is sees_notes


# --- Lifecycle ---


async def test_full_ticket_lifecycle(db_client, people, make_ticket, events):
    owner, mod, admin = people["owner"], people["mod"], people["admin"]
    ticket = await make_ticket(owner)
    url = f"/api/tickets/{ticket.id}"

    resp = await db_client.post(
        f"/api/admin/tickets/{ticket.id}/assign",
        json={"moderator_id": str(mod.id)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "assigned"
    assert resp.json()["assignee"]["id"] == str(mod.id)
    assert resp.json()["assigned_at"]

    for status, actor in [("in_progress", mod), ("resolved", mod), ("closed", owner)]:
        resp = await db_client.patch(
            f"{url}/status", json={"status": status}, headers=auth_headers(actor)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == status

    body = resp.json()
    assert body["resolved_at"] and body["closed_at"]
    changes = [(e.data["from"], e.data["to"]) for e in events if e.name == "ticket/status_changed"]
    assert changes == [
        ("open", "assigned"),
        ("assigned", "in_progress"),
        ("in_progress", "resolved"),
        ("resolved", "closed"),
    ]
    assert "ticket/assigned" in names(events)

    history = await db_client.get(
        "/api/tickets/mine", params={"scope": "history"}, headers=auth_headers(owner)
    )
    assert [t["id"] for t in history.json()["items"]] == [str(ticket.id)]


@pytest.mark.parametrize(
    ("start", "actor", "target", "expected"),
    [
        (S.ASSIGNED, "mod", "resolved", 409),  # must go through in_progress
        (S.ASSIGNED, "owner", "in_progress", 403),  # only the assignee works the ticket
        (S.IN_PROGRESS, "mod2", "resolved", 404),  # not their ticket
        (S.RESOLVED, "mod", "closed", 403),  # the owner (or admin) closes
        (S.CLOSED, "admin", "closed", 409),
        (S.ASSIGNED, "mod", "assigned", 422),  # not settable by hand
        (S.ASSIGNED, "admin", "in_progress", 200),
    ],
)
async def test_status_rules(db_client, people, make_ticket, events, start, actor, target, expected):
    ticket = await make_ticket(people["owner"], status=start, assignee=people["mod"])
    resp = await db_client.patch(
        f"/api/tickets/{ticket.id}/status", json={"status": target}, headers=auth_headers(people[actor])
    )
    assert resp.status_code == expected, resp.text
    if expected != 200:
        assert events == []


# --- Comments ---


async def test_comments(db_client, people, make_ticket, events):
    owner, mod = people["owner"], people["mod"]
    ticket = await make_ticket(owner, status=S.IN_PROGRESS, assignee=mod)
    url = f"/api/tickets/{ticket.id}/comments"

    resp = await db_client.post(url, json={"body": "Any update?"}, headers=auth_headers(owner))
    assert resp.status_code == 201
    assert resp.json()["author"]["email"] == "owner@example.com"
    resp = await db_client.post(url, json={"body": "Working on it"}, headers=auth_headers(mod))
    assert resp.status_code == 201
    assert events == []  # not resolved yet: no special email

    other = await db_client.post(url, json={"body": "hi"}, headers=auth_headers(people["other"]))
    assert other.status_code == 404

    detail = await db_client.get(f"/api/tickets/{ticket.id}", headers=auth_headers(owner))
    assert [c["body"] for c in detail.json()["comments"]] == ["Any update?", "Working on it"]


async def test_moderator_comment_after_resolution_emits_event(
    db_client, people, make_ticket, events
):
    ticket = await make_ticket(people["owner"], status=S.RESOLVED, assignee=people["mod"])
    resp = await db_client.post(
        f"/api/tickets/{ticket.id}/comments",
        json={"body": "Reopen if it happens again"},
        headers=auth_headers(people["mod"]),
    )
    assert resp.status_code == 201
    assert names(events) == ["ticket/comment_after_resolution"]


async def test_owner_cannot_comment_on_closed_ticket(db_client, people, make_ticket):
    ticket = await make_ticket(people["owner"], status=S.CLOSED, assignee=people["mod"])
    resp = await db_client.post(
        f"/api/tickets/{ticket.id}/comments",
        json={"body": "hello"},
        headers=auth_headers(people["owner"]),
    )
    assert resp.status_code == 409


# --- Moderator dashboard ---


async def test_moderator_dashboard(db_client, people, make_ticket):
    mod = people["mod"]
    await make_ticket(people["owner"], "Assigned one", status=S.ASSIGNED, assignee=mod)
    await make_ticket(people["owner"], "Working one", status=S.IN_PROGRESS, assignee=mod)
    await make_ticket(people["owner"], "Done one", status=S.RESOLVED, assignee=mod)
    await make_ticket(people["owner"], "Someone else's", status=S.ASSIGNED, assignee=people["mod2"])
    h = auth_headers(mod)

    assigned = await db_client.get("/api/moderator/tickets", headers=h)
    assert sorted(t["title"] for t in assigned.json()["items"]) == ["Assigned one", "Working one"]
    solved = await db_client.get("/api/moderator/tickets", params={"scope": "solved"}, headers=h)
    assert [t["title"] for t in solved.json()["items"]] == ["Done one"]
    search = await db_client.get("/api/moderator/tickets", params={"q": "work"}, headers=h)
    assert [t["title"] for t in search.json()["items"]] == ["Working one"]

    resp = await db_client.get("/api/moderator/tickets", headers=auth_headers(people["owner"]))
    assert resp.status_code == 403
