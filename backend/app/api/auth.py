import logging
from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, BackgroundTasks, Cookie, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import AppError, ServiceUnavailableError
from app.core.oauth import oauth
from app.events import commit_and_publish, queue_event
from app.models import OtpPurpose
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyOtpRequest,
)
from app.services import auth as auth_service
from app.services.email import send_otp_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = "/api/auth"
RefreshCookie = Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
    )


def _token_response(response: Response, tokens: auth_service.IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=auth_service.user_out(tokens.user),
    )


# --- Email registration ---


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    body: RegisterRequest, session: SessionDep, background: BackgroundTasks
) -> MessageResponse:
    """Step 1: send a verification code. Calling it again re-sends a new code."""
    code = await auth_service.start_registration(session, body.full_name, body.email, body.password)
    background.add_task(send_otp_email, body.email, code, OtpPurpose.REGISTRATION)
    return MessageResponse(message="We sent a verification code to your email.")


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
async def verify_registration(
    body: VerifyOtpRequest, session: SessionDep, response: Response
) -> TokenResponse:
    """Step 2: verify the code, create the account and sign the user in."""
    user = await auth_service.complete_registration(session, body.email, body.code)
    tokens = await auth_service.issue_tokens(session, user)
    queue_event(session, "user/created", {"user_id": str(user.id), "source": "email"})
    await commit_and_publish(session)
    return _token_response(response, tokens)


# --- Login / session ---


@router.post("/login")
async def login(body: LoginRequest, session: SessionDep, response: Response) -> TokenResponse:
    user = await auth_service.authenticate(session, body.email, body.password)
    tokens = await auth_service.issue_tokens(session, user)
    await session.commit()
    return _token_response(response, tokens)


@router.post("/refresh")
async def refresh(
    session: SessionDep, response: Response, refresh_token: RefreshCookie = None
) -> TokenResponse:
    try:
        tokens = await auth_service.rotate_refresh_token(session, refresh_token)
    except AppError:
        _clear_refresh_cookie(response)
        raise
    return _token_response(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: SessionDep, refresh_token: RefreshCookie = None) -> Response:
    await auth_service.revoke_refresh_token(session, refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return auth_service.user_out(user)


# --- Password reset ---


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordRequest, session: SessionDep, background: BackgroundTasks
) -> MessageResponse:
    code = await auth_service.start_password_reset(session, body.email)
    if code is not None:
        background.add_task(send_otp_email, body.email, code, OtpPurpose.PASSWORD_RESET)
    return MessageResponse(message="If an account exists for that email, we sent a reset code.")


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, session: SessionDep) -> MessageResponse:
    await auth_service.complete_password_reset(session, body.email, body.code, body.new_password)
    return MessageResponse(message="Your password has been reset. You can now sign in.")


# --- Google OAuth ---


def _frontend_callback(**params: str) -> str:
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.frontend_url}/auth/google/callback{query}"


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    if not settings.google_oauth_enabled:
        raise ServiceUnavailableError("Google sign-in is not configured")
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, session: SessionDep) -> RedirectResponse:
    """Google redirects here. We set the refresh cookie and send the browser to the
    frontend, which then calls POST /auth/refresh to get an access token."""
    try:
        token = await oauth.google.authorize_access_token(request)  # also checks `state`
        userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)
        result = await auth_service.login_with_google(session, dict(userinfo))
        tokens = await auth_service.issue_tokens(session, result.user)
        if result.created:
            queue_event(
                session, "user/created", {"user_id": str(result.user.id), "source": "google"}
            )
        await commit_and_publish(session)
    except OAuthError as exc:
        logger.warning("Google OAuth failed: %s", exc.error)
        return RedirectResponse(_frontend_callback(error="google_auth_failed"), status_code=302)
    except AppError as exc:
        await session.rollback()
        return RedirectResponse(_frontend_callback(error=exc.code), status_code=302)

    response = RedirectResponse(_frontend_callback(), status_code=302)
    _set_refresh_cookie(response, tokens.refresh_token)
    return response
