from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import Page

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def _page_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Items per page")] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


PageDep = Annotated[PageParams, Depends(_page_params)]


async def paginate[T](
    session: AsyncSession,
    stmt: Select[Any],
    params: PageParams,
    transform: Callable[[Any], T],
) -> Page[T]:
    """Run `stmt` for one page, count the total, and convert each row with `transform`."""
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = (await session.scalars(stmt.offset(params.offset).limit(params.size))).all()
    return Page[T](
        items=[transform(row) for row in rows],
        total=total or 0,
        page=params.page,
        size=params.size,
    )
