"""Docket/legislation management — /api/congress/docket/*"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_docket_item,
    congress_legislation,
    congress_session,
    congress_tournament,
)
from nekocongress.schemas.legislation import (
    DocketAssignRequest,
    DocketItemResponse,
    DocketReorderRequest,
    DocketResponse,
    LegislationCreate,
    LegislationResponse,
    LegislationUpdate,
)

router = APIRouter(prefix="/api/congress/docket", tags=["docket"])


# ── Legislation CRUD ──────────────────────────────────────────────────


@router.post("/legislation/", response_model=LegislationResponse, status_code=201)
async def create_legislation(
    body: LegislationCreate,
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
        congress_legislation.insert()
        .values(**body.model_dump())
        .returning(congress_legislation)
    )
    await db.commit()
    return LegislationResponse(**result.fetchone()._mapping)


@router.get("/legislation/", response_model=list[LegislationResponse])
async def list_legislation(
    congress_tournament_id: int | None = None,
    tournament_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    stmt = select(congress_legislation)
    if congress_tournament_id is not None:
        stmt = stmt.where(congress_legislation.c.congress_tournament_id == congress_tournament_id)
    elif tournament_id is not None:
        stmt = stmt.where(
            congress_legislation.c.congress_tournament_id.in_(
                select(congress_tournament.c.id)
                .where(congress_tournament.c.tournament_id == tournament_id)
            )
        )
    stmt = stmt.order_by(congress_legislation.c.docket_code)
    rows = (await db.execute(stmt)).fetchall()
    return [LegislationResponse(**r._mapping) for r in rows]


@router.get("/legislation/{legislation_id}/", response_model=LegislationResponse)
async def get_legislation(
    legislation_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_legislation)
        .where(congress_legislation.c.id == legislation_id)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Legislation not found")
    return LegislationResponse(**row._mapping)


@router.patch("/legislation/{legislation_id}/", response_model=LegislationResponse)
async def update_legislation(
    legislation_id: int,
    body: LegislationUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_legislation.c.id)
        .where(congress_legislation.c.id == legislation_id)
    )).scalar()
    if not row:
        raise HTTPException(status_code=404, detail="Legislation not found")

    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.execute(
        congress_legislation.update()
        .where(congress_legislation.c.id == legislation_id)
        .values(**values)
    )
    await db.commit()
    updated = (await db.execute(
        select(congress_legislation)
        .where(congress_legislation.c.id == legislation_id)
    )).fetchone()
    return LegislationResponse(**updated._mapping)


# ── Docket (session → legislation assignment) ─────────────────────────


@router.post("/assign/", response_model=DocketItemResponse, status_code=201)
async def assign_to_docket(
    body: DocketAssignRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    # Validate session
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == body.session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Validate legislation
    leg = (await db.execute(
        select(congress_legislation).where(congress_legislation.c.id == body.legislation_id)
    )).fetchone()
    if not leg:
        raise HTTPException(status_code=404, detail="Legislation not found")

    result = await db.execute(
        congress_docket_item.insert()
        .values(
            session_id=body.session_id,
            legislation_id=body.legislation_id,
            agenda_order=body.agenda_order,
        )
        .returning(congress_docket_item)
    )
    await db.commit()
    row = result.fetchone()
    return DocketItemResponse(
        **row._mapping,
        legislation_title=leg.title,
        legislation_type=leg.legislation_type,
        docket_code=leg.docket_code,
    )


@router.get("/session/{session_id}/", response_model=DocketResponse)
async def get_session_docket(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    items = (await db.execute(
        select(congress_docket_item, congress_legislation)
        .outerjoin(
            congress_legislation,
            congress_legislation.c.id == congress_docket_item.c.legislation_id,
        )
        .where(congress_docket_item.c.session_id == session_id)
        .order_by(congress_docket_item.c.agenda_order)
    )).fetchall()

    return DocketResponse(
        session_id=session_id,
        items=[
            DocketItemResponse(
                id=i.id,
                session_id=i.session_id,
                legislation_id=i.legislation_id,
                agenda_order=i.agenda_order,
                status=i.status,
                vote_result=i.vote_result,
                aff_votes=i.aff_votes,
                neg_votes=i.neg_votes,
                abstain_votes=i.abstain_votes,
                legislation_title=i.title or "",
                legislation_type=i.legislation_type or "",
                docket_code=i.docket_code or "",
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in items
        ],
    )


@router.post("/reorder/", response_model=DocketResponse)
async def reorder_docket(
    body: DocketReorderRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    if not body.item_ids:
        raise HTTPException(status_code=400, detail="item_ids cannot be empty")

    # Fetch all items to get their session_id
    items = (await db.execute(
        select(congress_docket_item)
        .where(congress_docket_item.c.id.in_(body.item_ids))
    )).fetchall()
    if not items:
        raise HTTPException(status_code=404, detail="No docket items found")

    session_ids = {i.session_id for i in items}
    if len(session_ids) != 1:
        raise HTTPException(status_code=400, detail="All items must belong to the same session")
    session_id = session_ids.pop()

    # Update agenda_order for each item
    for order, item_id in enumerate(body.item_ids, start=1):
        await db.execute(
            congress_docket_item.update()
            .where(congress_docket_item.c.id == item_id)
            .values(agenda_order=order)
        )
    await db.commit()

    # Return updated docket
    return await get_session_docket(session_id, db)
