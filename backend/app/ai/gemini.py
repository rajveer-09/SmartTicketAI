"""Gemini calls with model fallback.

Models are tried strongest first (GEMINI_MODELS). A model that returns a quota or
rate-limit error (429) is recorded in `model_quota_state` and skipped until it resets,
so later tickets don't waste a call on it. If every model fails, the caller marks the
ticket Pending Review for an admin to assign by hand.
"""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import utcnow
from app.models import ModelQuotaState

logger = logging.getLogger(__name__)

QUOTA_STATUSES = (429,)
TRANSIENT_STATUSES = (500, 502, 503, 504)


class AIUnavailableError(Exception):
    """Every configured model failed or is out of quota."""

    def __init__(self, attempts: dict[str, str]) -> None:
        super().__init__(f"No Gemini model available: {attempts}")
        self.attempts = attempts


@dataclass
class Generation:
    text: str
    model: str

    def json(self) -> Any:
        return json.loads(self.text)


_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise AIUnavailableError({"config": "GEMINI_API_KEY is not set"})
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def exhausted_models(session: AsyncSession) -> set[str]:
    now = utcnow()
    rows = await session.execute(ModelQuotaState.__table__.select())
    return {r.model_name for r in rows if r.exhausted_until and r.exhausted_until > now}


async def mark_exhausted(session: AsyncSession, model: str, error: str) -> None:
    until = utcnow() + timedelta(minutes=settings.model_backoff_minutes)
    stmt = insert(ModelQuotaState).values(
        model_name=model, exhausted_until=until, last_error=error[:500], updated_at=utcnow()
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["model_name"],
            set_={"exhausted_until": until, "last_error": error[:500], "updated_at": utcnow()},
        )
    )
    await session.commit()


async def generate(
    session: AsyncSession,
    prompt: str,
    *,
    system: str | None = None,
    schema: dict[str, Any] | None = None,
    max_output_tokens: int = 2048,
) -> Generation:
    """Try each configured model in order. Raises AIUnavailableError if none worked."""
    models = settings.gemini_model_list
    if not models:
        raise AIUnavailableError({"config": "GEMINI_MODELS is not set"})

    skip = await exhausted_models(session)
    attempts: dict[str, str] = {m: "skipped (out of quota)" for m in models if m in skip}

    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json" if schema else None,
        response_schema=schema,
        http_options=types.HttpOptions(timeout=settings.ai_timeout_seconds * 1000),
    )

    for model in models:
        if model in skip:
            continue
        try:
            response = await client().aio.models.generate_content(
                model=model, contents=prompt, config=config
            )
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None)
            attempts[model] = f"{status}: {str(exc)[:120]}"
            if status in QUOTA_STATUSES:
                logger.warning("Model %s is out of quota; falling back", model)
                await mark_exhausted(session, model, str(exc))
            elif status in TRANSIENT_STATUSES or status == 404:
                logger.warning("Model %s unavailable (%s); falling back", model, status)
            else:
                raise
            continue
        except Exception as exc:  # network/timeout: try the next model
            attempts[model] = f"{type(exc).__name__}: {str(exc)[:120]}"
            logger.warning("Model %s failed (%s); falling back", model, type(exc).__name__)
            continue

        text = (response.text or "").strip()
        if not text:
            attempts[model] = "empty response"
            continue
        return Generation(text=text, model=model)

    raise AIUnavailableError(attempts)
