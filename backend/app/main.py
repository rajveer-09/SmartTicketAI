import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.errors import register_error_handlers
from app.inngest.client import inngest_client
from app.inngest.functions import functions as inngest_functions

API_PREFIX = "/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,  # refresh token travels in an httpOnly cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Only used by Authlib to hold the OAuth `state` between redirect and callback.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.jwt_secret,
        session_cookie="oauth_session",
        max_age=600,
        same_site="lax",
        https_only=settings.refresh_cookie_secure,
    )

    register_error_handlers(app)
    # Everything under /api so the frontend can own the plain URL space (/tickets/<id> etc.)
    app.include_router(api_router, prefix=API_PREFIX)

    # Background jobs: AI analysis, assignment and emails (served at /api/inngest).
    inngest.fast_api.serve(app, inngest_client, inngest_functions)
    return app


app = create_app()
