import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import AuthProvider, UserRole

NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]
Password = Annotated[str, Field(min_length=8, max_length=128)]
OtpCodeStr = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RegisterRequest(BaseModel):
    full_name: FullName
    email: NormalizedEmail
    password: Password


class VerifyOtpRequest(BaseModel):
    email: NormalizedEmail
    code: OtpCodeStr


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: Annotated[str, Field(min_length=1, max_length=128)]


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    code: OtpCodeStr
    new_password: Password


class MessageResponse(BaseModel):
    message: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    auth_provider: AuthProvider
    has_password: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """The refresh token is not in the body; it is set as an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
