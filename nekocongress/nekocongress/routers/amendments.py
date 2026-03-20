"""Amendment management — /api/congress/amendments/*

Handles amendment submission by legislators, PO germane review,
and retrieval of amendments per docket item.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_amendment,
    congress_chamber,
    congress_docket_item,
    congress_legislator,
    congress_session,
)
from nekocongress.schemas.amendment import (
    AmendmentCreate,
    AmendmentResponse,
    AmendmentReviewRequest,
)
from nekocongress.websocket.events import EventType
from nekocongress.websocket.redis_manager import channel_manager

router = APIRouter(prefix="/api/congress/amendments", tags=["amendments"])


async def _get_chamber_for_docket_item(docket_item_id: int, db: AsyncSession) -> tuple[int, int]:
    """Return (chamber_id, session_id) for a docket item."""
    item = (await db.execute(
        select(congress_docket_item).where(congress_docket_item.c.id == docket_item_id)
    )).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Docket item not found")
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == item.session_id)
    )).fetchone()
    return session.chamber_id, item.session_id


@router.post("/", response_model=AmendmentResponse, status_code=201)
async def submit_amendment(
    body: AmendmentCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    chamber_id, session_id = await _get_chamber_for_docket_item(body.docket_item_id, db)

    # Validate legislator
    leg = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id == body.submitted_by_legislator_id)
    )).fetchone()
    if not leg:
        raise HTTPException(status_code=404, detail="Legislator not found")

    result = await db.execute(
        congress_amendment.insert()
        .values(
            docket_item_id=body.docket_item_id,
            submitted_by_legislator_id=body.submitted_by_legislator_id,
            amendment_text=body.amendment_text,
        )
        .returning(congress_amendment)
    )
    await db.commit()
    row = result.fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber_id,
        event_type=EventType.AMENDMENT_SUBMITTED,
        session_id=session_id,
        data={
            "amendment_id": row.id,
            "submitted_by": leg.display_name,
            "docket_item_id": body.docket_item_id,
        },
    )

    return AmendmentResponse(
        **row._mapping,
        submitted_by_name=leg.display_name,
    )


@router.post("/{amendment_id}/review/", response_model=AmendmentResponse)
async def review_amendment(
    amendment_id: int,
    body: AmendmentReviewRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    amendment = (await db.execute(
        select(congress_amendment).where(congress_amendment.c.id == amendment_id)
    )).fetchone()
    if not amendment:
        raise HTTPException(status_code=404, detail="Amendment not found")

    new_status = "APPROVED" if body.is_germane else "REJECTED"
    await db.execute(
        congress_amendment.update()
        .where(congress_amendment.c.id == amendment_id)
        .values(
            status=new_status,
            reviewed_at=datetime.now(timezone.utc),
            is_germane=body.is_germane,
        )
    )
    await db.commit()

    updated = (await db.execute(
        select(congress_amendment).where(congress_amendment.c.id == amendment_id)
    )).fetchone()

    leg = (await db.execute(
        select(congress_legislator.c.display_name)
        .where(congress_legislator.c.id == updated.submitted_by_legislator_id)
    )).scalar() or ""

    chamber_id, session_id = await _get_chamber_for_docket_item(updated.docket_item_id, db)

    await channel_manager.publish_to_chamber(
        chamber_id=chamber_id,
        event_type=EventType.AMENDMENT_REVIEWED,
        session_id=session_id,
        data={
            "amendment_id": amendment_id,
            "is_germane": body.is_germane,
            "status": new_status,
        },
    )

    return AmendmentResponse(**updated._mapping, submitted_by_name=leg)


@router.get("/docket-item/{docket_item_id}/", response_model=list[AmendmentResponse])
async def list_amendments(
    docket_item_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    rows = (await db.execute(
        select(congress_amendment)
        .where(congress_amendment.c.docket_item_id == docket_item_id)
        .order_by(congress_amendment.c.created_at)
    )).fetchall()

    # Bulk-fetch legislator names
    leg_ids = list({r.submitted_by_legislator_id for r in rows})
    leg_map: dict[int, str] = {}
    if leg_ids:
        legs = (await db.execute(
            select(congress_legislator.c.id, congress_legislator.c.display_name)
            .where(congress_legislator.c.id.in_(leg_ids))
        )).fetchall()
        leg_map = {l.id: l.display_name for l in legs}

    return [
        AmendmentResponse(
            **r._mapping,
            submitted_by_name=leg_map.get(r.submitted_by_legislator_id, ""),
        )
        for r in rows
    ]
