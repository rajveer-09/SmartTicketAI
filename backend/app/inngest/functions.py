"""Inngest functions: all the slow work that happens after an API request returns.

Each `step.run` is retried on its own and its result is remembered, so a retry never
repeats a step that already succeeded (and so never re-sends an email).
"""

import logging
import uuid

import inngest

from app.core.database import get_sessionmaker
from app.inngest.client import inngest_client
from app.models import TicketStatus
from app.services import ai_flow, notifications

logger = logging.getLogger(__name__)

RETRIES = 3


def _session():
    return get_sessionmaker()()


async def handle_ticket_created(ctx: inngest.Context) -> dict:
    """AI analysis -> helpful notes -> best-fit moderator. Falls back to Pending Review."""
    ticket_id = ctx.event.data["ticket_id"]

    analysis = await ctx.step.run("analyze", ai_flow.analyze, ticket_id)
    if not analysis["ok"]:
        if analysis["reason"] in ("ticket_not_found", "already_processed"):
            return analysis
        return await ctx.step.run(
            "pending-review",
            ai_flow.mark_pending_review,
            ticket_id,
            analysis["reason"],
            ctx.event.id,
        )

    await ctx.step.run("write-notes", ai_flow.write_notes, ticket_id)

    assignment = await ctx.step.run("assign", ai_flow.assign, ticket_id)
    if not assignment["ok"] and assignment["reason"] == "no_moderator":
        return await ctx.step.run(
            "pending-review", ai_flow.mark_pending_review, ticket_id, "no_moderator", ctx.event.id
        )
    return assignment


async def handle_ticket_assigned(ctx: inngest.Context) -> dict:
    async def _send() -> dict:
        async with _session() as session:
            ticket = await ai_flow.load_ticket(session, uuid.UUID(ctx.event.data["ticket_id"]))
            if ticket is None:
                return {"sent": False, "reason": "ticket_not_found"}
            sent = await notifications.notify_assignment(session, ctx.event.id, ticket)
            return {"sent": sent}

    return await ctx.step.run("email-moderator", _send)


async def handle_status_changed(ctx: inngest.Context) -> dict:
    async def _send() -> dict:
        async with _session() as session:
            ticket = await ai_flow.load_ticket(session, uuid.UUID(ctx.event.data["ticket_id"]))
            if ticket is None:
                return {"sent": False, "reason": "ticket_not_found"}
            status = TicketStatus(ctx.event.data["to"])
            sent = await notifications.notify_status_change(session, ctx.event.id, ticket, status)
            return {"sent": sent, "status": status.value}

    return await ctx.step.run("email-user", _send)


async def handle_comment_after_resolution(ctx: inngest.Context) -> dict:
    async def _send() -> dict:
        from app.models import TicketComment

        async with _session() as session:
            ticket = await ai_flow.load_ticket(session, uuid.UUID(ctx.event.data["ticket_id"]))
            comment = await session.get(TicketComment, uuid.UUID(ctx.event.data["comment_id"]))
            if ticket is None or comment is None:
                return {"sent": False, "reason": "not_found"}
            author = await ai_flow.load_user(session, ctx.event.data["author_id"])
            if author is None:
                return {"sent": False, "reason": "author_not_found"}
            sent = await notifications.notify_new_message(
                session, ctx.event.id, ticket, author, comment.body
            )
            return {"sent": sent}

    return await ctx.step.run("email-user", _send)


async def handle_user_created(ctx: inngest.Context) -> dict:
    async def _send() -> dict:
        async with _session() as session:
            user = await ai_flow.load_user(session, ctx.event.data["user_id"])
            if user is None:
                return {"sent": False, "reason": "user_not_found"}
            return {"sent": await notifications.notify_welcome(session, ctx.event.id, user)}

    return await ctx.step.run("email-user", _send)


# --- Registration -------------------------------------------------------------
# The handlers above are plain async functions so they can be called directly in
# tests; these thin wrappers are what Inngest triggers.


def _register(fn_id: str, name: str, event: str, handler):
    @inngest_client.create_function(
        fn_id=fn_id, name=name, trigger=inngest.TriggerEvent(event=event), retries=RETRIES
    )
    async def _fn(ctx: inngest.Context) -> dict:
        return await handler(ctx)

    return _fn


functions = [
    _register(
        "ticket-created",
        "Analyze, note and assign a new ticket",
        "ticket/created",
        handle_ticket_created,
    ),
    _register(
        "ticket-assigned",
        "Email the assigned moderator",
        "ticket/assigned",
        handle_ticket_assigned,
    ),
    _register(
        "ticket-status-changed",
        "Email the user about a status change",
        "ticket/status_changed",
        handle_status_changed,
    ),
    _register(
        "ticket-comment-after-resolution",
        "Email the user about a new message",
        "ticket/comment_after_resolution",
        handle_comment_after_resolution,
    ),
    _register("user-created", "Send the welcome email", "user/created", handle_user_created),
]
