"""Tournament configuration endpoints — /api/congress/tournaments/*"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key, require_director
from nekocongress.database import get_db
from nekocongress.models.congress import congress_tournament
from nekocongress.schemas.tournament import (
    CongressTournamentCreate,
    CongressTournamentResponse,
    CongressTournamentUpdate,
)

router = APIRouter(prefix="/api/congress/tournaments", tags=["tournaments"])


@router.post("/", response_model=CongressTournamentResponse, status_code=201)
async def create_tournament(
    body: CongressTournamentCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    """Create a new congress tournament configuration."""
    # Check uniqueness
    existing = (
        await db.execute(
            select(congress_tournament.c.id)
            .where(congress_tournament.c.tournament_id == body.tournament_id)
        )
    ).scalar()
    if existing:
        raise HTTPException(status_code=409, detail="Congress config already exists for this tournament")

    result = await db.execute(
        congress_tournament.insert()
        .values(**body.model_dump())
        .returning(congress_tournament)
    )
    await db.commit()
    row = result.fetchone()
    return CongressTournamentResponse(**row._mapping)


@router.get("/", response_model=list[CongressTournamentResponse])
async def list_tournaments(
    tournament_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    stmt = select(congress_tournament)
    if tournament_id is not None:
        stmt = stmt.where(congress_tournament.c.tournament_id == tournament_id)
    stmt = stmt.where(congress_tournament.c.is_active == True).order_by(congress_tournament.c.id)  # noqa: E712
    rows = (await db.execute(stmt)).fetchall()
    return [CongressTournamentResponse(**r._mapping) for r in rows]


@router.get("/{config_id}/", response_model=CongressTournamentResponse)
async def get_tournament(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (
        await db.execute(
            select(congress_tournament).where(congress_tournament.c.id == config_id)
        )
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Congress config not found")
    return CongressTournamentResponse(**row._mapping)


@router.patch("/{config_id}/", response_model=CongressTournamentResponse)
async def update_tournament(
    config_id: int,
    body: CongressTournamentUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.execute(
        update(congress_tournament)
        .where(congress_tournament.c.id == config_id)
        .values(**updates)
        .returning(congress_tournament)
    )
    await db.commit()
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Congress config not found")
    return CongressTournamentResponse(**row._mapping)
