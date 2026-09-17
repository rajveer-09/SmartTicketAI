import pytest
from sqlalchemy import select

from app.models import RefreshToken, Ticket, TicketStatus, UserRole
from tests.conftest import auth_headers

S = TicketStatus


@pytest.fixture
async def admin(make_user):
    return await make_user("admin@example.com", password=None, role=UserRole.ADMIN)


@pytest.fixture
async def mod(make_user):
    return await make_user("mod@example.com", password=None, role=UserRole.MODERATOR)


@pytest.fixture
async def owner(make_user):
    return await make_user("owner@example.com", password=None)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/tickets"),
        ("get", "/api/admin/users"),
        ("get", "/api/admin/moderators/workload"),
        ("get", "/api/admin/search?q=x"),
    ],
)
async def test_admin_routes_reject_non_admins(db_client, mod, owner, method, path):
    assert (await db_client.request(method, path)).status_code == 401
    for user in (mod, owner):
        resp = await db_client.request(method, path, headers=auth_headers(user))
        assert resp.status_code == 403


async def test_admin_ticket_list_filters(db_client, admin, mod, owner, make_ticket):
    await make_ticket(owner, "Unassigned", status=S.PENDING_REVIEW)
    await make_ticket(owner, "Assigned", status=S.ASSIGNED, assignee=mod)

    resp = await db_client.get("/api/admin/tickets", headers=auth_headers(admin))
    assert resp.json()["total"] == 2
    resp = await db_client.get(
        "/api/admin/tickets", params={"unassigned": True}, headers=auth_headers(admin)
    )
    assert [t["title"] for t in resp.json()["items"]] == ["Unassigned"]
    resp = await db_client.get(
        "/api/admin/tickets", params={"assignee_id": str(mod.id)}, headers=auth_headers(admin)
    )
    assert [t["title"] for t in resp.json()["items"]] == ["Assigned"]


async def test_create_user_with_skills(db_client, admin, events):
    body = {
        "full_name": "Nina Patel",
        "email": "Nina@Example.com",
        "password": "temporary-pass",
        "role": "moderator",
        "skills": ["  Networking ", "billing", "NETWORKING", ""],
    }
    resp = await db_client.post("/api/admin/users", json=body, headers=auth_headers(admin))
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "nina@example.com"
    assert resp.json()["role"] == "moderator"
    assert resp.json()["skills"] == ["billing", "networking"]
    assert [e.name for e in events] == ["user/created"]

    login = await db_client.post(
        "/api/auth/login", json={"email": "nina@example.com", "password": "temporary-pass"}
    )
    assert login.status_code == 200

    dup = await db_client.post("/api/admin/users", json=body, headers=auth_headers(admin))
    assert dup.status_code == 409


async def test_replace_skills(db_client, admin, mod, owner):
    url = f"/api/admin/users/{mod.id}/skills"
    resp = await db_client.put(url, json={"skills": ["VPN", "email"]}, headers=auth_headers(admin))
    assert resp.status_code == 200, resp.text
    assert resp.json()["skills"] == ["email", "vpn"]

    resp = await db_client.put(url, json={"skills": ["hardware"]}, headers=auth_headers(admin))
    assert resp.json()["skills"] == ["hardware"]

    resp = await db_client.put(
        f"/api/admin/users/{owner.id}/skills", json={"skills": ["x"]}, headers=auth_headers(admin)
    )
    assert resp.status_code == 409


async def test_user_search(db_client, admin, mod, owner):
    resp = await db_client.get(
        "/api/admin/users", params={"q": "MOD", "role": "moderator"}, headers=auth_headers(admin)
    )
    assert [u["email"] for u in resp.json()["items"]] == ["mod@example.com"]


async def test_demoting_moderator_releases_their_open_tickets(
    db_client, admin, mod, owner, make_ticket, sessionmaker, events
):
    working = await make_ticket(owner, "Working", status=S.IN_PROGRESS, assignee=mod)
    solved = await make_ticket(owner, "Solved", status=S.RESOLVED, assignee=mod)

    resp = await db_client.patch(
        f"/api/admin/users/{mod.id}", json={"role": "user"}, headers=auth_headers(admin)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "user"

    async with sessionmaker() as s:
        working = await s.get(Ticket, working.id)
        solved = await s.get(Ticket, solved.id)
    assert (working.status, working.assignee_id) == (S.PENDING_REVIEW, None)
    assert (solved.status, solved.assignee_id) == (S.RESOLVED, mod.id)  # history kept
    assert [(e.data["from"], e.data["to"]) for e in events] == [("in_progress", "pending_review")]

    # An admin then clears Pending Review by assigning someone else.
    resp = await db_client.post(
        f"/api/admin/tickets/{working.id}/assign",
        json={"moderator_id": str(admin.id)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "assigned"


async def test_reassign_keeps_status_and_emits_assigned(
    db_client, admin, mod, owner, make_user, make_ticket, events
):
    mod2 = await make_user("mod2@example.com", password=None, role=UserRole.MODERATOR)
    ticket = await make_ticket(owner, status=S.IN_PROGRESS, assignee=mod)

    resp = await db_client.post(
        f"/api/admin/tickets/{ticket.id}/assign",
        json={"moderator_id": str(mod2.id)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["assignee"]["id"] == str(mod2.id)
    assert [e.name for e in events] == ["ticket/assigned"]
    assert events[0].data["previous_assignee_id"] == str(mod.id)


@pytest.mark.parametrize(
    ("status", "assign_to", "expected"),
    [(S.OPEN, "owner", 409), (S.CLOSED, "mod", 409), (S.OPEN, "missing", 404)],
)
async def test_invalid_assignments(
    db_client, admin, mod, owner, make_ticket, status, assign_to, expected
):
    import uuid

    ticket = await make_ticket(owner, status=status)
    target = {"owner": owner.id, "mod": mod.id, "missing": uuid.uuid4()}[assign_to]
    resp = await db_client.post(
        f"/api/admin/tickets/{ticket.id}/assign",
        json={"moderator_id": str(target)},
        headers=auth_headers(admin),
    )
    assert resp.status_code == expected


async def test_remove_user_deactivates_and_signs_out(db_client, admin, make_user, sessionmaker):
    victim = await make_user("leaving@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": "leaving@example.com", "password": "password123"}
    )
    assert login.status_code == 200

    resp = await db_client.delete(f"/api/admin/users/{victim.id}", headers=auth_headers(admin))
    assert resp.status_code == 204

    again = await db_client.post(
        "/api/auth/login", json={"email": "leaving@example.com", "password": "password123"}
    )
    assert again.status_code == 403
    async with sessionmaker() as s:
        live = await s.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == victim.id, RefreshToken.revoked_at.is_(None)
            )
        )
        assert live.all() == []


@pytest.mark.parametrize("change", [{"role": "moderator"}, {"is_active": False}])
async def test_admin_cannot_lock_themselves_out(db_client, admin, change):
    resp = await db_client.patch(
        f"/api/admin/users/{admin.id}", json=change, headers=auth_headers(admin)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "self_lockout"
    resp = await db_client.delete(f"/api/admin/users/{admin.id}", headers=auth_headers(admin))
    assert resp.status_code == 400


async def test_workload(db_client, admin, mod, owner, make_user, make_ticket):
    idle = await make_user("idle@example.com", password=None, role=UserRole.MODERATOR)
    await make_ticket(owner, status=S.ASSIGNED, assignee=mod)
    await make_ticket(owner, status=S.IN_PROGRESS, assignee=mod)
    await make_ticket(owner, status=S.RESOLVED, assignee=mod)
    await make_ticket(owner, status=S.CLOSED, assignee=mod)

    resp = await db_client.get("/api/admin/moderators/workload", headers=auth_headers(admin))
    assert resp.status_code == 200
    rows = {r["email"]: r for r in resp.json()}
    assert set(rows) == {"mod@example.com", "idle@example.com"}
    m = rows["mod@example.com"]
    assert (m["active"], m["resolved"], m["closed"], m["total"]) == (2, 1, 1, 4)
    assert rows[idle.email]["total"] == 0
    assert resp.json()[0]["email"] == "mod@example.com"  # busiest first


async def test_global_search(db_client, admin, mod, owner, make_ticket):
    await make_ticket(owner, "Outlook crashes on start")
    await make_ticket(owner, "Unrelated")

    resp = await db_client.get("/api/admin/search", params={"q": "out"}, headers=auth_headers(admin))
    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()["tickets"]] == ["Outlook crashes on start"]

    resp = await db_client.get("/api/admin/search", params={"q": "mod@"}, headers=auth_headers(admin))
    assert [u["email"] for u in resp.json()["users"]] == ["mod@example.com"]

    assert (
        await db_client.get("/api/admin/search", params={"q": " "}, headers=auth_headers(admin))
    ).status_code == 422
