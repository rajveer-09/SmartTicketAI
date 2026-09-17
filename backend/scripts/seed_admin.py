"""Create the first admin account (or promote an existing user to admin).

Usage (from backend/):
    python -m scripts.seed_admin

Reads ADMIN_EMAIL, ADMIN_PASSWORD and ADMIN_NAME from the environment / .env.
Safe to run more than once.
"""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.database import dispose_engine, get_sessionmaker
from app.core.security import hash_password
from app.models import AuthProvider, User, UserRole

MIN_PASSWORD_LENGTH = 8


async def seed_admin() -> str:
    email = settings.admin_email.strip().lower()
    if not email:
        raise SystemExit("ADMIN_EMAIL is not set.")

    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))

        if user:
            if user.role == UserRole.ADMIN:
                return f"{email} is already an admin; nothing to do."
            user.role = UserRole.ADMIN
            await session.commit()
            return f"Promoted existing user {email} to admin."

        if len(settings.admin_password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.")

        session.add(
            User(
                email=email,
                full_name=settings.admin_name,
                hashed_password=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                auth_provider=AuthProvider.EMAIL,
            )
        )
        await session.commit()
        return f"Created admin {email}."


async def main() -> None:
    try:
        print(await seed_admin())
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
