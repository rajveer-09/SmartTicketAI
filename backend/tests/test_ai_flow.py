"""Phase 4: model fallback, skill matching, the agent's steps and email idempotency.

Gemini is always faked here; no test makes a real AI call.
"""

import json
from datetime import timedelta

import pytest
from google.genai import errors as genai_errors
from sqlalchemy import select

from app.ai import gemini
from app.core.config import settings
from app.core.security import utcnow
from app.models import ModelQuotaState, SentEmail, Ticket, TicketPriority, TicketStatus, UserRole
from app.services import ai_flow, matching, notifications

MODELS = ["big-model", "mid-model", "small-model"]
ANALYSIS = {
    "category": "network",
    "priority": "high",
    "required_skills": ["VPN", "Networking", "vpn"],
    "summary": "VPN drops every few minutes.",
}
NOTES_MD = "### Likely cause\n* Stale VPN client\n* Check the adapter logs first"


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeModels:
    """Replays a scripted outcome per model name."""

    def __init__(self, outcomes: dict[str, object]):
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        # A schema means the analysis call; without one it's the free-text notes call.
        default = FakeResponse(json.dumps(ANALYSIS) if config.response_schema else NOTES_MD)
        outcome = self.outcomes.get(model, default)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, models: FakeModels):
        self.aio = type("Aio", (), {"models": models})()


def api_error(status: int) -> genai_errors.APIError:
    message = {429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE", 500: "INTERNAL"}[status]
    return genai_errors.APIError(status, {"error": {"code": status, "message": message}})


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_models", ",".join(MODELS))
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def _install(outcomes: dict[str, object]) -> FakeModels:
        models = FakeModels(outcomes)
        monkeypatch.setattr(gemini, "client", lambda: FakeClient(models))
        return models

    return _install


# --- Model fallback ---


async def test_uses_the_strongest_model_that_works(sessionmaker, fake_gemini):
    fake = fake_gemini({})
    async with sessionmaker() as session:
        result = await gemini.generate(session, "hi")

    assert result.model == "big-model"
    assert fake.calls == ["big-model"]


async def test_quota_error_falls_back_and_remembers(sessionmaker, fake_gemini):
    fake = fake_gemini({"big-model": api_error(429)})
    async with sessionmaker() as session:
        result = await gemini.generate(session, "hi")
        assert result.model == "mid-model"
        assert fake.calls == ["big-model", "mid-model"]

        row = await session.get(ModelQuotaState, "big-model")
        assert row.exhausted_until > utcnow()

        # The next ticket skips the exhausted model entirely.
        again = await gemini.generate(session, "hi again")
    assert again.model == "mid-model"
    assert fake.calls == ["big-model", "mid-model", "mid-model"]


async def test_transient_error_falls_back_without_marking_quota(sessionmaker, fake_gemini):
    fake_gemini({"big-model": api_error(503)})
    async with sessionmaker() as session:
        result = await gemini.generate(session, "hi")
        assert result.model == "mid-model"
        assert await session.get(ModelQuotaState, "big-model") is None


async def test_all_models_failing_raises(sessionmaker, fake_gemini):
    fake_gemini(dict.fromkeys(MODELS, api_error(429)))
    async with sessionmaker() as session:
        with pytest.raises(gemini.AIUnavailableError) as exc:
            await gemini.generate(session, "hi")
    assert set(exc.value.attempts) == set(MODELS)


async def test_expired_quota_block_is_retried(sessionmaker, fake_gemini):
    fake = fake_gemini({})
    async with sessionmaker() as session:
        session.add(
            ModelQuotaState(model_name="big-model", exhausted_until=utcnow() - timedelta(hours=1))
        )
        await session.commit()
        result = await gemini.generate(session, "hi")

    assert result.model == "big-model"
    assert fake.calls == ["big-model"]


# --- Skill matching ---


async def test_picks_best_skill_match_then_least_busy(
    sessionmaker, make_user, make_ticket, admin_skills
):
    generalist = await make_user("gen@example.com", password=None, role=UserRole.MODERATOR)
    expert = await make_user("vpn@example.com", password=None, role=UserRole.MODERATOR)
    await admin_skills(generalist, ["printers"])
    await admin_skills(expert, ["vpn troubleshooting", "networking"])
    owner = await make_user("owner@example.com", password=None)
    # The expert is busier, but skills win.
    await make_ticket(owner, status=TicketStatus.ASSIGNED, assignee=expert)

    async with sessionmaker() as session:
        best = await matching.pick_moderator(session, ["vpn"])
    assert best.user.id == expert.id
    assert best.matched == ["vpn"]


async def test_no_skill_match_falls_back_to_least_busy(
    sessionmaker, make_user, make_ticket, admin_skills
):
    busy = await make_user("busy@example.com", password=None, role=UserRole.MODERATOR)
    free = await make_user("free@example.com", password=None, role=UserRole.MODERATOR)
    await admin_skills(busy, ["email"])
    owner = await make_user("owner@example.com", password=None)
    await make_ticket(owner, status=TicketStatus.IN_PROGRESS, assignee=busy)

    async with sessionmaker() as session:
        best = await matching.pick_moderator(session, ["hardware"])
    assert best.user.id == free.id
    assert best.matched == []


async def test_inactive_and_non_moderators_are_ignored(sessionmaker, make_user):
    await make_user("plain@example.com", password=None)
    await make_user("gone@example.com", password=None, role=UserRole.MODERATOR, is_active=False)
    await make_user("boss@example.com", password=None, role=UserRole.ADMIN)

    async with sessionmaker() as session:
        assert await matching.pick_moderator(session, ["anything"]) is None


# --- Agent steps ---


@pytest.fixture
def admin_skills(sessionmaker):
    from app.models import ModeratorSkill

    async def _set(user, skills: list[str]) -> None:
        async with sessionmaker() as session:
            session.add_all(ModeratorSkill(user_id=user.id, skill=s) for s in skills)
            await session.commit()

    return _set


@pytest.fixture(autouse=True)
def job_sessions(sessionmaker, monkeypatch):
    """Background steps open their own sessions: point them at the test database."""
    from app.inngest import functions as inngest_functions

    monkeypatch.setattr(ai_flow, "session_scope", lambda: sessionmaker())
    monkeypatch.setattr(inngest_functions, "_session", lambda: sessionmaker())


@pytest.fixture
def no_publish(monkeypatch):
    """Events raised inside steps are captured instead of sent to Inngest."""
    from app import events as events_module

    captured: list = []

    async def fake_publish(batch):
        captured.extend(batch)

    monkeypatch.setattr(events_module, "publish", fake_publish)
    return captured


async def test_analyze_saves_classification(sessionmaker, make_user, make_ticket, fake_gemini):
    owner = await make_user("owner@example.com", password=None)
    ticket = await make_ticket(owner, "VPN drops")
    fake_gemini({})

    result = await ai_flow.analyze(str(ticket.id))

    assert result["ok"] is True
    assert result["model"] == "big-model"
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.category == "network"
    assert saved.priority == TicketPriority.HIGH
    assert saved.required_skills == ["vpn", "networking"]  # deduplicated and normalised
    assert saved.ai_model_used == "big-model"


async def test_analyze_reports_when_ai_is_unavailable(make_user, make_ticket, fake_gemini):
    owner = await make_user("owner@example.com", password=None)
    ticket = await make_ticket(owner)
    fake_gemini(dict.fromkeys(MODELS, api_error(429)))

    assert await ai_flow.analyze(str(ticket.id)) == {"ok": False, "reason": "ai_unavailable"}


async def test_write_notes_saves_notes(sessionmaker, make_user, make_ticket, fake_gemini):
    owner = await make_user("owner@example.com", password=None)
    ticket = await make_ticket(owner)
    fake_gemini({})

    assert (await ai_flow.write_notes(str(ticket.id)))["ok"] is True
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.ai_notes == NOTES_MD


async def test_assign_step_assigns_best_moderator(
    sessionmaker, make_user, make_ticket, admin_skills, no_publish
):
    owner = await make_user("owner@example.com", password=None)
    mod = await make_user("mod@example.com", password=None, role=UserRole.MODERATOR)
    await admin_skills(mod, ["vpn"])
    ticket = await make_ticket(owner)
    async with sessionmaker() as session:
        loaded = await session.get(Ticket, ticket.id)
        loaded.required_skills = ["vpn"]
        await session.commit()

    result = await ai_flow.assign(str(ticket.id))

    assert result["ok"] is True
    assert result["moderator_id"] == str(mod.id)
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.status == TicketStatus.ASSIGNED
    assert saved.assignee_id == mod.id
    assert {e.name for e in no_publish} == {"ticket/assigned", "ticket/status_changed"}


async def test_assign_without_moderators_reports_it(make_user, make_ticket):
    owner = await make_user("owner@example.com", password=None)
    ticket = await make_ticket(owner)
    assert await ai_flow.assign(str(ticket.id)) == {"ok": False, "reason": "no_moderator"}


async def test_pending_review_parks_ticket_and_emails_admins(
    sessionmaker, make_user, make_ticket, outbox, no_publish
):
    owner = await make_user("owner@example.com", password=None)
    await make_user("boss@example.com", password=None, role=UserRole.ADMIN)
    ticket = await make_ticket(owner)

    result = await ai_flow.mark_pending_review(str(ticket.id), "ai_unavailable", "evt-1")

    assert result == {"ok": True, "reason": "ai_unavailable", "admins_notified": 1}
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.status == TicketStatus.PENDING_REVIEW
    assert [m[0] for m in outbox.templates("pending_review.html")] == ["boss@example.com"]
    assert [e.name for e in no_publish] == ["ticket/status_changed"]


# --- Email idempotency ---


async def test_same_event_never_sends_twice(sessionmaker, make_user, make_ticket, outbox):
    owner = await make_user("owner@example.com", password=None)
    mod = await make_user("mod@example.com", password=None, role=UserRole.MODERATOR)
    ticket = await make_ticket(owner, status=TicketStatus.ASSIGNED, assignee=mod)

    async with sessionmaker() as session:
        loaded = await ai_flow.load_ticket(session, ticket.id)
        assert await notifications.notify_assignment(session, "evt-1", loaded) is True
        assert await notifications.notify_assignment(session, "evt-1", loaded) is False  # retry
        assert await notifications.notify_assignment(session, "evt-2", loaded) is True

        keys = (await session.scalars(select(SentEmail.idempotency_key))).all()
    assert len(outbox.templates("ticket_assigned.html")) == 2
    assert sorted(keys) == [
        "evt-1:ticket_assigned:mod@example.com",
        "evt-2:ticket_assigned:mod@example.com",
    ]


async def test_status_email_goes_to_the_ticket_owner(sessionmaker, make_user, make_ticket, outbox):
    owner = await make_user("owner@example.com", password=None)
    mod = await make_user("mod@example.com", password=None, role=UserRole.MODERATOR)
    ticket = await make_ticket(owner, status=TicketStatus.RESOLVED, assignee=mod)

    async with sessionmaker() as session:
        loaded = await ai_flow.load_ticket(session, ticket.id)
        await notifications.notify_status_change(session, "evt-9", loaded, TicketStatus.RESOLVED)

    to, _, context = outbox.templates("status_update.html")[0]
    assert to == "owner@example.com"
    assert context["status"] == "resolved"
    assert context["assignee_name"] == mod.full_name


# --- Inngest function wiring (driven by a stub step runner, no Inngest server) ---


class FakeStep:
    """Runs each step immediately, recording its id, like Inngest does on a first run."""

    def __init__(self) -> None:
        self.ids: list[str] = []

    async def run(self, step_id: str, handler, *args):
        self.ids.append(step_id)
        return await handler(*args)


class FakeCtx:
    def __init__(self, name: str, data: dict, event_id: str = "evt-test"):
        self.event = type("E", (), {"name": name, "data": data, "id": event_id})()
        self.step = FakeStep()


async def test_ticket_created_function_runs_the_whole_agent(
    sessionmaker, make_user, make_ticket, admin_skills, fake_gemini, no_publish, outbox
):
    from app.inngest.functions import handle_ticket_assigned, handle_ticket_created

    owner = await make_user("owner@example.com", password=None)
    mod = await make_user("mod@example.com", password=None, role=UserRole.MODERATOR)
    await admin_skills(mod, ["vpn"])
    ticket = await make_ticket(owner, "VPN drops constantly")
    fake_gemini({})

    ctx = FakeCtx("ticket/created", {"ticket_id": str(ticket.id)})
    result = await handle_ticket_created(ctx)

    assert ctx.step.ids == ["analyze", "write-notes", "assign"]
    assert result["moderator_id"] == str(mod.id)
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.status == TicketStatus.ASSIGNED
    assert saved.category == "network"
    assert saved.ai_notes

    # The assignment event then emails the moderator, notes included.
    assigned = next(e for e in no_publish if e.name == "ticket/assigned")
    await handle_ticket_assigned(FakeCtx("ticket/assigned", assigned.data, "evt-assign"))
    to, _, context = outbox.templates("ticket_assigned.html")[0]
    assert to == "mod@example.com"
    assert saved.ai_notes == NOTES_MD
    assert "<h3>Likely cause</h3>" in context["notes_html"]  # Markdown rendered, not raw
    assert "###" not in context["notes_html"]
    assert context["priority"] == "high"


async def test_ticket_created_falls_back_to_pending_review_when_ai_is_out_of_quota(
    sessionmaker, make_user, make_ticket, fake_gemini, no_publish, outbox
):
    from app.inngest.functions import handle_ticket_created

    owner = await make_user("owner@example.com", password=None)
    await make_user("boss@example.com", password=None, role=UserRole.ADMIN)
    ticket = await make_ticket(owner)
    fake_gemini(dict.fromkeys(MODELS, api_error(429)))

    ctx = FakeCtx("ticket/created", {"ticket_id": str(ticket.id)})
    result = await handle_ticket_created(ctx)

    assert ctx.step.ids == ["analyze", "pending-review"]
    assert result["reason"] == "ai_unavailable"
    async with sessionmaker() as session:
        saved = await session.get(Ticket, ticket.id)
    assert saved.status == TicketStatus.PENDING_REVIEW
    assert [m[0] for m in outbox.templates("pending_review.html")] == ["boss@example.com"]


async def test_status_change_function_emails_the_user(sessionmaker, make_user, make_ticket, outbox):
    from app.inngest.functions import handle_status_changed

    owner = await make_user("owner@example.com", password=None)
    ticket = await make_ticket(owner, status=TicketStatus.RESOLVED)

    ctx = FakeCtx(
        "ticket/status_changed",
        {"ticket_id": str(ticket.id), "from": "in_progress", "to": "resolved"},
    )
    assert (await handle_status_changed(ctx))["sent"] is True
    assert (await handle_status_changed(ctx))["sent"] is False  # retry sends nothing
    assert [m[0] for m in outbox.templates("status_update.html")] == ["owner@example.com"]


async def test_welcome_function_emails_a_new_user(make_user, outbox):
    from app.inngest.functions import handle_user_created

    user = await make_user("newbie@example.com", password=None)
    ctx = FakeCtx("user/created", {"user_id": str(user.id), "source": "email"})

    assert (await handle_user_created(ctx))["sent"] is True
    assert [m[0] for m in outbox.templates("welcome.html")] == ["newbie@example.com"]
