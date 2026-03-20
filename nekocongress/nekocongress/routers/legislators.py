"""Legislator management endpoints — /api/congress/legislators/*"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import congress_legislator, congress_tournament
from nekocongress.schemas.legislator import (
    LegislatorBulkCreate,
    LegislatorCreate,
    LegislatorResponse,
)

router = APIRouter(prefix="/api/congress/legislators", tags=["legislators"])


@router.post("/", response_model=LegislatorResponse, status_code=201)
async def create_legislator(
    body: LegislatorCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    t = (await db.execute(
        select(congress_tournament.c.id)
        .where(congress_tournament.c.id == body.congress_tournament_id)
    )).scalar()
    if not t:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    result = await db.execute(
        congress_legislator.insert()
        .values(**body.model_dump())
        .returning(congress_legislator)
    )
    await db.commit()
    row = result.fetchone()
    return LegislatorResponse(**row._mapping)


@router.post("/bulk/", response_model=list[LegislatorResponse], status_code=201)
async def bulk_create_legislators(
    body: LegislatorBulkCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    t = (await db.execute(
        select(congress_tournament.c.id)
        .where(congress_tournament.c.id == body.congress_tournament_id)
    )).scalar()
    if not t:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    rows = []
    for leg in body.legislators:
        result = await db.execute(
            congress_legislator.insert()
            .values(
                congress_tournament_id=body.congress_tournament_id,
                speaker_id=leg.speaker_id,
                display_name=leg.display_name,
                institution_id=leg.institution_id,
                institution_code=leg.institution_code,
            )
            .returning(congress_legislator)
        )
        row = result.fetchone()
        if row:
            rows.append(row)
    await db.commit()
    return [LegislatorResponse(**r._mapping) for r in rows]


@router.get("/", response_model=list[LegislatorResponse])
async def list_legislators(
    tournament_id: int | None = None,
    congress_tournament_id: int | None = None,
    include_withdrawn: bool = False,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    stmt = select(congress_legislator)
    if congress_tournament_id is not None:
        stmt = stmt.where(congress_legislator.c.congress_tournament_id == congress_tournament_id)
    elif tournament_id is not None:
        stmt = stmt.where(
            congress_legislator.c.congress_tournament_id.in_(
                select(congress_tournament.c.id)
                .where(congress_tournament.c.tournament_id == tournament_id)
            )
        )
    if not include_withdrawn:
        stmt = stmt.where(congress_legislator.c.is_withdrawn == False)  # noqa: E712
    stmt = stmt.order_by(congress_legislator.c.display_name)
    rows = (await db.execute(stmt)).fetchall()
    return [LegislatorResponse(**r._mapping) for r in rows]


@router.get("/{legislator_id}/", response_model=LegislatorResponse)
async def get_legislator(
    legislator_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id == legislator_id)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Legislator not found")
    return LegislatorResponse(**row._mapping)


@router.patch("/{legislator_id}/withdraw/", response_model=LegislatorResponse)
async def withdraw_legislator(
    legislator_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id == legislator_id)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Legislator not found")
    await db.execute(
        congress_legislator.update()
        .where(congress_legislator.c.id == legislator_id)
        .values(is_withdrawn=True)
    )
    await db.commit()
    updated = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id == legislator_id)
    )).fetchone()
    return LegislatorResponse(**updated._mapping)


@router.delete("/{legislator_id}/", status_code=204)
async def delete_legislator(
    legislator_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_legislator.c.id)
        .where(congress_legislator.c.id == legislator_id)
    )).scalar()
    if not row:
        raise HTTPException(status_code=404, detail="Legislator not found")
    await db.execute(
        congress_legislator.delete()
        .where(congress_legislator.c.id == legislator_id)
    )
    await db.commit()
