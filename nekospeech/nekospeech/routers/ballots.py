"""Ballot submission endpoints — /api/ie/ballots/*"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.auth import require_ie_api_key
from nekospeech.database import get_db
from nekospeech.models.shared import participants_institution, participants_person
from nekospeech.models.speech_event import ie_entry, ie_result, ie_room, ie_room_entry, speech_event
from nekospeech.schemas.ballot import BallotSubmit, BallotSubmitResponse, IEResultResponse, IEResultUpdate
from nekospeech.websocket.manager import connection_manager

router = APIRouter(prefix="/api/ie/ballots", tags=["ballots"])

logger = logging.getLogger(__name__)

async def _get_tournament_id(db: AsyncSession, event_id: int) -> int | None:
    """Resolve tournament_id from an event_id."""
    return (
        await db.execute(
            select(speech_event.c.tournament_id).where(speech_event.c.id == event_id)
        )
    ).scalar()


async def _check_round_complete(db: AsyncSession, event_id: int, round_number: int) -> bool:
    """Return True if all rooms in this round are confirmed."""
    unconfirmed = (
        await db.execute(
            select(ie_room.c.id)
            .where(ie_room.c.event_id == event_id)
            .where(ie_room.c.round_number == round_number)
            .where(ie_room.c.confirmed == False)  # noqa: E712
            .limit(1)
        )
    ).scalar()
    return unconfirmed is None


@router.post("/submit/", response_model=BallotSubmitResponse)
async def submit_ballot(
    body: BallotSubmit,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Lock the room row to prevent concurrent submit/confirm races
    room = (await db.execute(
        select(ie_room).where(ie_room.c.id == body.room_id).with_for_update()
    )).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.confirmed:
        raise HTTPException(status_code=400, detail="Room is already confirmed")

    # Use the room's assigned judge as the submitter
    judge_id = room.judge_id

    # Validate all entry_ids belong to this room
    room_entry_ids = (
        await db.execute(
            select(ie_room_entry.c.entry_id).where(ie_room_entry.c.room_id == body.room_id)
        )
    ).scalars().all()
    submitted_ids = {r.entry_id for r in body.results}
    if not submitted_ids.issubset(set(room_entry_ids)):
        raise HTTPException(status_code=400, detail="Some entry_ids do not belong to this room")
    if len(body.results) != len(room_entry_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Expected {len(room_entry_ids)} results, got {len(body.results)}",
        )

    # Atomic transaction: delete existing results for this room, then insert new ones
    await db.execute(ie_result.delete().where(ie_result.c.room_id == body.room_id))
    await db.execute(
        ie_result.insert(),
        [
            {
                "room_id": body.room_id,
                "entry_id": r.entry_id,
                "rank": r.rank,
                "speaker_points": r.speaker_points,
                "submitted_by_judge_id": judge_id,
            }
            for r in body.results
        ],
    )
    # Update ballot_status to 'submitted'
    await db.execute(
        update(ie_room).where(ie_room.c.id == body.room_id).values(ballot_status="submitted")
    )
    await db.commit()

    # Broadcast ballot submission via WebSocket
    tournament_id = await _get_tournament_id(db, room.event_id)
    if tournament_id:
        await connection_manager.broadcast_to_tournament(tournament_id, {
            "type": "ballot_submitted",
            "room_id": body.room_id,
            "ballot_status": "submitted",
        })

    # Check if round is complete (currently unreachable: submit_ballot doesn't
    # set confirmed=True, so _check_round_complete always returns False here.
    # Kept as a safety net in case flow changes.)
    round_complete = await _check_round_complete(db, room.event_id, room.round_number)
    if round_complete:
        try:
            from nekospeech.workers.tasks import recalc_standings
            recalc_standings.delay(room.event_id, room.round_number)
        except Exception:
            logger.warning("Failed to enqueue recalc_standings from submit_ballot for event=%d round=%d",
                           room.event_id, room.round_number)

    return BallotSubmitResponse(submitted=True, round_complete=round_complete)


@router.get("/{room_id}/", response_model=list[IEResultResponse])
async def get_room_results(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    stmt = (
        select(
            ie_result,
            participants_person.c.name.label("speaker_name"),
            participants_institution.c.code.label("institution_code"),
        )
        .join(ie_entry, ie_entry.c.id == ie_result.c.entry_id)
        .outerjoin(participants_person, participants_person.c.id == ie_entry.c.speaker_id)
        .outerjoin(participants_institution, participants_institution.c.id == ie_entry.c.institution_id)
        .where(ie_result.c.room_id == room_id)
        .order_by(ie_result.c.rank)
    )
    rows = (await db.execute(stmt)).fetchall()
    return [
        IEResultResponse(
            id=r.id, room_id=r.room_id, entry_id=r.entry_id,
            rank=r.rank, speaker_points=float(r.speaker_points),
            submitted_by_judge_id=r.submitted_by_judge_id,
            confirmed=r.confirmed, submitted_at=r.submitted_at,
            speaker_name=r.speaker_name or "",
            institution_code=r.institution_code or "",
        )
        for r in rows
    ]


@router.post("/{room_id}/confirm/", status_code=200)
async def confirm_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Lock the room row to prevent concurrent submit/confirm races
    room = (await db.execute(
        select(ie_room).where(ie_room.c.id == room_id).with_for_update()
    )).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.confirmed:
        return {"detail": "Already confirmed"}

    # Ensure results exist
    result_count = (
        await db.execute(
            select(ie_result.c.id).where(ie_result.c.room_id == room_id).limit(1)
        )
    ).scalar()
    if not result_count:
        raise HTTPException(status_code=400, detail="No results submitted for this room")

    await db.execute(
        update(ie_room).where(ie_room.c.id == room_id).values(confirmed=True, ballot_status="confirmed")
    )
    await db.execute(
        update(ie_result).where(ie_result.c.room_id == room_id).values(confirmed=True)
    )
    await db.commit()

    # Broadcast room confirmed via WebSocket
    tournament_id = await _get_tournament_id(db, room.event_id)
    if tournament_id:
        await connection_manager.broadcast_to_tournament(tournament_id, {
            "type": "room_confirmed",
            "room_id": room_id,
            "ballot_status": "confirmed",
        })

    # Check if all rooms in this round are now confirmed
    round_complete = await _check_round_complete(db, room.event_id, room.round_number)
    if round_complete:
        # Invalidate stale standings cache BEFORE broadcasting, so clients
        # that fetch standings on receiving the WS event get fresh data.
        from nekospeech.services.cache import cache_delete, standings_key
        await cache_delete(standings_key(room.event_id))
        await cache_delete(standings_key(room.event_id, room.round_number))

        try:
            from nekospeech.workers.tasks import recalc_standings
            recalc_standings.delay(room.event_id, room.round_number)
        except Exception:
            logger.warning("Failed to enqueue recalc_standings for event=%d round=%d",
                           room.event_id, room.round_number)

        # Broadcast standings_updated from the web process (Celery worker
        # runs in a separate process and cannot reach WS clients).
        if tournament_id:
            await connection_manager.broadcast_to_tournament(tournament_id, {
                "type": "standings_updated",
                "event_id": room.event_id,
            })

    return {"detail": "Confirmed", "round_complete": round_complete}


@router.patch("/{result_id}/", response_model=IEResultResponse)
async def edit_result(
    result_id: int,
    body: IEResultUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Get the result and its room
    res = (await db.execute(select(ie_result).where(ie_result.c.id == result_id))).fetchone()
    if not res:
        raise HTTPException(status_code=404, detail="Result not found")

    # Lock the room row — prevents a concurrent confirm_room from confirming
    # the room between our confirmed-check read and the result UPDATE.
    room = (await db.execute(
        select(ie_room).where(ie_room.c.id == res.room_id).with_for_update()
    )).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.confirmed:
        raise HTTPException(status_code=400, detail="Cannot edit results for a confirmed room")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.execute(
        update(ie_result).where(ie_result.c.id == result_id).values(**update_data)
    )
    await db.commit()

    # Invalidate standings cache so edited result is reflected immediately
    try:
        # Get the event_id via the room
        room_result = await db.execute(
            select(ie_room.c.event_id, ie_room.c.round_number)
            .where(ie_room.c.id == res.room_id)
        )
        room_row = room_result.first()
        if room_row:
            from nekospeech.services.cache import cache_delete, standings_key
            await cache_delete(standings_key(room_row.event_id))
            await cache_delete(standings_key(room_row.event_id, room_row.round_number))
    except Exception:
        pass  # Cache invalidation failure should never break the edit response

    # Return updated result
    stmt = (
        select(
            ie_result,
            participants_person.c.name.label("speaker_name"),
            participants_institution.c.code.label("institution_code"),
        )
        .join(ie_entry, ie_entry.c.id == ie_result.c.entry_id)
        .outerjoin(participants_person, participants_person.c.id == ie_entry.c.speaker_id)
        .outerjoin(participants_institution, participants_institution.c.id == ie_entry.c.institution_id)
        .where(ie_result.c.id == result_id)
    )
    row = (await db.execute(stmt)).fetchone()
    return IEResultResponse(
        id=row.id, room_id=row.room_id, entry_id=row.entry_id,
        rank=row.rank, speaker_points=float(row.speaker_points),
        submitted_by_judge_id=row.submitted_by_judge_id,
        confirmed=row.confirmed, submitted_at=row.submitted_at,
        speaker_name=row.speaker_name or "",
        institution_code=row.institution_code or "",
    )
