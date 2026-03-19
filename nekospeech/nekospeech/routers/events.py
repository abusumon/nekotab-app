"""Speech Events CRUD endpoints — /api/ie/events/*"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.auth import require_ie_api_key
from nekospeech.database import get_db
from nekospeech.models.speech_event import ie_entry, ie_room, speech_event
from nekospeech.schemas.event import SpeechEventCreate, SpeechEventResponse, SpeechEventUpdate

router = APIRouter(prefix="/api/ie/events", tags=["events"])


@router.post("/", response_model=SpeechEventResponse, status_code=201)
async def create_event(
    body: SpeechEventCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    result = await db.execute(
        speech_event.insert()
        .values(**body.model_dump())
        .returning(speech_event)
    )
    await db.commit()
    row = result.fetchone()
    return SpeechEventResponse(**row._mapping, entry_count=0, rounds_with_draw=[])


@router.get("/", response_model=list[SpeechEventResponse])
async def list_events(
    tournament_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # Subquery for entry count per event
    entry_count_sq = (
        select(ie_entry.c.event_id, func.count().label("entry_count"))
        .where(ie_entry.c.scratch_status == "ACTIVE")
        .group_by(ie_entry.c.event_id)
        .subquery()
    )
    stmt = (
        select(speech_event, func.coalesce(entry_count_sq.c.entry_count, 0).label("entry_count"))
        .outerjoin(entry_count_sq, speech_event.c.id == entry_count_sq.c.event_id)
        .where(speech_event.c.tournament_id == tournament_id)
        .where(speech_event.c.is_active == True)  # noqa: E712
        .order_by(speech_event.c.id)
    )
    rows = (await db.execute(stmt)).fetchall()

    # Bulk-fetch all rounds that have draws in one query to avoid N+1
    rounds_map: dict[int, list[int]] = {}
    if rows:
        all_event_ids = [row.id for row in rows]
        all_rounds_rows = (await db.execute(
            select(ie_room.c.event_id, ie_room.c.round_number)
            .where(ie_room.c.event_id.in_(all_event_ids))
            .distinct()
            .order_by(ie_room.c.event_id, ie_room.c.round_number)
        )).fetchall()
        for rr in all_rounds_rows:
            rounds_map.setdefault(rr.event_id, []).append(rr.round_number)

    results = []
    for row in rows:
        results.append(
            SpeechEventResponse(
                **{k: v for k, v in row._mapping.items() if k != "entry_count"},
                entry_count=row.entry_count,
                rounds_with_draw=rounds_map.get(row.id, []),
            )
        )
    return results


@router.get("/{event_id}/", response_model=SpeechEventResponse)
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    entry_count_sq = (
        select(func.count())
        .where(ie_entry.c.event_id == event_id)
        .where(ie_entry.c.scratch_status == "ACTIVE")
        .scalar_subquery()
    )
    stmt = select(speech_event, entry_count_sq.label("entry_count")).where(
        speech_event.c.id == event_id
    )
    row = (await db.execute(stmt)).fetchone()
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Event not found")

    rounds_stmt = (
        select(ie_room.c.round_number)
        .where(ie_room.c.event_id == event_id)
        .distinct()
        .order_by(ie_room.c.round_number)
    )
    round_rows = (await db.execute(rounds_stmt)).fetchall()
    return SpeechEventResponse(
        **{k: v for k, v in row._mapping.items() if k != "entry_count"},
        entry_count=row.entry_count,
        rounds_with_draw=[r.round_number for r in round_rows],
    )


@router.patch("/{event_id}/", response_model=SpeechEventResponse)
async def update_event(
    event_id: int,
    body: SpeechEventUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Verify event exists
    evt_tid = (await db.execute(select(speech_event.c.tournament_id).where(speech_event.c.id == event_id))).scalar()
    if evt_tid is None:
        raise HTTPException(status_code=404, detail="Event not found")
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(
        update(speech_event).where(speech_event.c.id == event_id).values(**update_data)
    )
    await db.commit()
    return await get_event(event_id, db)


@router.delete("/{event_id}/", status_code=204)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    evt_tid = (await db.execute(select(speech_event.c.tournament_id).where(speech_event.c.id == event_id))).scalar()
    if evt_tid is None:
        raise HTTPException(status_code=404, detail="Event not found")
    result = await db.execute(
        update(speech_event)
        .where(speech_event.c.id == event_id)
        .where(speech_event.c.is_active == True)  # noqa: E712
        .values(is_active=False)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.commit()
