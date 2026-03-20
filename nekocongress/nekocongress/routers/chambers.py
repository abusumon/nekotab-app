"""Chamber management endpoints — /api/congress/chambers/*"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_chamber,
    congress_chamber_assignment,
    congress_legislator,
    congress_session,
    congress_tournament,
)
from nekocongress.schemas.chamber import (
    ChamberAssignmentResponse,
    ChamberAssignRequest,
    ChamberCreate,
    ChamberResponse,
    SeatingChartResponse,
)

router = APIRouter(prefix="/api/congress/chambers", tags=["chambers"])


@router.post("/", response_model=ChamberResponse, status_code=201)
async def create_chamber(
    body: ChamberCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    # Validate tournament exists
    t = (await db.execute(
        select(congress_tournament.c.id)
        .where(congress_tournament.c.id == body.congress_tournament_id)
    )).scalar()
    if not t:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    result = await db.execute(
        congress_chamber.insert()
        .values(**body.model_dump())
        .returning(congress_chamber)
    )
    await db.commit()
    row = result.fetchone()
    return ChamberResponse(**row._mapping, legislator_count=0, session_count=0)


@router.get("/", response_model=list[ChamberResponse])
async def list_chambers(
    tournament_id: int | None = None,
    congress_tournament_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    stmt = select(congress_chamber)
    if congress_tournament_id is not None:
        stmt = stmt.where(congress_chamber.c.congress_tournament_id == congress_tournament_id)
    elif tournament_id is not None:
        stmt = stmt.where(
            congress_chamber.c.congress_tournament_id.in_(
                select(congress_tournament.c.id)
                .where(congress_tournament.c.tournament_id == tournament_id)
            )
        )
    stmt = stmt.order_by(congress_chamber.c.chamber_number)
    rows = (await db.execute(stmt)).fetchall()

    # Bulk-fetch counts
    chamber_ids = [r.id for r in rows]
    legislator_counts = {}
    session_counts = {}
    if chamber_ids:
        lc = (await db.execute(
            select(
                congress_chamber_assignment.c.chamber_id,
                func.count().label("cnt"),
            )
            .where(congress_chamber_assignment.c.chamber_id.in_(chamber_ids))
            .group_by(congress_chamber_assignment.c.chamber_id)
        )).fetchall()
        legislator_counts = {r.chamber_id: r.cnt for r in lc}

        sc = (await db.execute(
            select(
                congress_session.c.chamber_id,
                func.count().label("cnt"),
            )
            .where(congress_session.c.chamber_id.in_(chamber_ids))
            .group_by(congress_session.c.chamber_id)
        )).fetchall()
        session_counts = {r.chamber_id: r.cnt for r in sc}

    return [
        ChamberResponse(
            **r._mapping,
            legislator_count=legislator_counts.get(r.id, 0),
            session_count=session_counts.get(r.id, 0),
        )
        for r in rows
    ]


@router.get("/{chamber_id}/", response_model=ChamberResponse)
async def get_chamber(
    chamber_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == chamber_id)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Chamber not found")

    lc = (await db.execute(
        select(func.count())
        .select_from(congress_chamber_assignment)
        .where(congress_chamber_assignment.c.chamber_id == chamber_id)
    )).scalar() or 0

    sc = (await db.execute(
        select(func.count())
        .select_from(congress_session)
        .where(congress_session.c.chamber_id == chamber_id)
    )).scalar() or 0

    return ChamberResponse(**row._mapping, legislator_count=lc, session_count=sc)


@router.post("/{chamber_id}/assign-legislators/", response_model=list[ChamberAssignmentResponse])
async def assign_legislators(
    chamber_id: int,
    body: ChamberAssignRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    # Validate chamber exists
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == chamber_id)
    )).fetchone()
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    # Insert assignments (skip duplicates)
    assignments = []
    for idx, leg_id in enumerate(body.legislator_ids, start=1):
        try:
            result = await db.execute(
                congress_chamber_assignment.insert()
                .values(chamber_id=chamber_id, legislator_id=leg_id, seat_number=idx)
                .returning(congress_chamber_assignment)
            )
            row = result.fetchone()
            if row:
                assignments.append(row)
        except Exception:
            await db.rollback()
            raise HTTPException(status_code=409, detail=f"Legislator {leg_id} already assigned")

    await db.commit()

    # Fetch legislator names
    leg_ids = [a.legislator_id for a in assignments]
    leg_map = {}
    if leg_ids:
        legs = (await db.execute(
            select(congress_legislator)
            .where(congress_legislator.c.id.in_(leg_ids))
        )).fetchall()
        leg_map = {l.id: l for l in legs}

    return [
        ChamberAssignmentResponse(
            id=a.id,
            chamber_id=a.chamber_id,
            legislator_id=a.legislator_id,
            seat_number=a.seat_number,
            legislator_name=leg_map.get(a.legislator_id, type("", (), {"display_name": ""})).display_name,
            institution_code=leg_map.get(a.legislator_id, type("", (), {"institution_code": ""})).institution_code or "",
            created_at=a.created_at,
        )
        for a in assignments
    ]


@router.get("/{chamber_id}/seating-chart/", response_model=SeatingChartResponse)
async def get_seating_chart(
    chamber_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == chamber_id)
    )).fetchone()
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    assignments = (await db.execute(
        select(congress_chamber_assignment, congress_legislator)
        .outerjoin(congress_legislator,
                   congress_legislator.c.id == congress_chamber_assignment.c.legislator_id)
        .where(congress_chamber_assignment.c.chamber_id == chamber_id)
        .order_by(congress_chamber_assignment.c.seat_number)
    )).fetchall()

    return SeatingChartResponse(
        chamber_id=chamber_id,
        chamber_label=chamber.label,
        assignments=[
            ChamberAssignmentResponse(
                id=a.id,
                chamber_id=a.chamber_id,
                legislator_id=a.legislator_id,
                seat_number=a.seat_number,
                legislator_name=a.display_name or "",
                institution_code=a.institution_code or "",
                created_at=a.created_at,
            )
            for a in assignments
        ],
    )
