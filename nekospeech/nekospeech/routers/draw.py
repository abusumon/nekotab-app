"""Room draw endpoints — /api/ie/draw/*"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.auth import require_ie_api_key
from nekospeech.database import get_db
from nekospeech.models.shared import participants_institution, participants_person
from nekospeech.models.speech_event import ie_entry, ie_result, ie_room, ie_room_entry, speech_event
from nekospeech.schemas.entry import IEEntryResponse
from nekospeech.schemas.room import AssignJudgeRequest, DrawGenerateRequest, DrawResponse, IERoomResponse
from nekospeech.services.cache import cache_delete, cache_get, cache_set, draw_key
from nekospeech.services.draw_engine import EntryForDraw, assign_rooms

router = APIRouter(prefix="/api/ie/draw", tags=["draw"])


async def _build_draw_response(
    db: AsyncSession, event_id: int, round_number: int,
) -> DrawResponse:
    """Build full draw response with rooms, entries, and judge info."""
    room_stmt = (
        select(ie_room)
        .where(ie_room.c.event_id == event_id)
        .where(ie_room.c.round_number == round_number)
        .order_by(ie_room.c.room_number)
    )
    room_rows = (await db.execute(room_stmt)).fetchall()

    # Bulk-fetch all judge names in one query to avoid N+1 (previously one query per room)
    judge_ids = [rm.judge_id for rm in room_rows if rm.judge_id]
    judge_name_map: dict[int, str] = {}
    if judge_ids:
        judge_rows = (await db.execute(
            select(participants_person.c.id, participants_person.c.name)
            .where(participants_person.c.id.in_(judge_ids))
        )).fetchall()
        judge_name_map = {jr.id: (jr.name or "") for jr in judge_rows}

    rooms = []
    for rm in room_rows:
        # Get entries for this room with speaker + institution info (single JOIN query)
        entry_stmt = (
            select(
                ie_entry,
                participants_person.c.name.label("speaker_name"),
                participants_institution.c.name.label("institution_name"),
                participants_institution.c.code.label("institution_code"),
            )
            .join(ie_room_entry, ie_room_entry.c.entry_id == ie_entry.c.id)
            .outerjoin(participants_person, participants_person.c.id == ie_entry.c.speaker_id)
            .outerjoin(participants_institution, participants_institution.c.id == ie_entry.c.institution_id)
            .where(ie_room_entry.c.room_id == rm.id)
            .order_by(ie_entry.c.id)
        )
        entry_rows = (await db.execute(entry_stmt)).fetchall()

        entries = [
            IEEntryResponse(
                id=e.id, event_id=e.event_id, speaker_id=e.speaker_id,
                partner_id=e.partner_id, institution_id=e.institution_id,
                scratch_status=e.scratch_status, created_at=e.created_at,
                speaker_name=e.speaker_name or "", institution_name=e.institution_name or "",
                institution_code=e.institution_code or "",
            )
            for e in entry_rows
        ]

        # Judge name resolved from pre-fetched bulk map above
        judge_name = judge_name_map.get(rm.judge_id, "") if rm.judge_id else ""

        rooms.append(IERoomResponse(
            id=rm.id, event_id=rm.event_id, round_number=rm.round_number,
            room_number=rm.room_number, judge_id=rm.judge_id,
            judge_name=judge_name, confirmed=rm.confirmed,
            ballot_status=rm.ballot_status if hasattr(rm, 'ballot_status') else ("confirmed" if rm.confirmed else "no_ballot"),
            created_at=rm.created_at,
            entries=entries,
        ))

    return DrawResponse(event_id=event_id, round_number=round_number, rooms=rooms)


@router.post("/generate/", response_model=DrawResponse, status_code=201)
async def generate_draw(
    body: DrawGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Validate event
    evt = (
        await db.execute(
            select(speech_event).where(speech_event.c.id == body.event_id).where(speech_event.c.is_active == True)  # noqa: E712
        )
    ).fetchone()
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")

    # Acquire advisory lock to prevent concurrent draw generation for same event+round.
    # pg_advisory_xact_lock is released automatically when the transaction commits/rolls back.
    lock_key = body.event_id * 10000 + body.round_number
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    # Idempotency: check if draw already exists for this round
    existing = (
        await db.execute(
            select(ie_room.c.id)
            .where(ie_room.c.event_id == body.event_id)
            .where(ie_room.c.round_number == body.round_number)
            .limit(1)
        )
    ).scalar()
    if existing and not body.force:
        return await _build_draw_response(db, body.event_id, body.round_number)

    # If force, delete existing draw for this round (only if no confirmed rooms)
    if existing and body.force:
        # Safety check: refuse to destroy confirmed results
        confirmed_room = (
            await db.execute(
                select(ie_room.c.id)
                .where(ie_room.c.event_id == body.event_id)
                .where(ie_room.c.round_number == body.round_number)
                .where(ie_room.c.confirmed == True)  # noqa: E712
                .limit(1)
            )
        ).scalar()
        if confirmed_room:
            raise HTTPException(
                status_code=409,
                detail="Cannot regenerate draw: round has confirmed rooms. Un-confirm rooms first.",
            )

        # Delete results first (FK constraint)
        existing_rooms = (
            await db.execute(
                select(ie_room.c.id)
                .where(ie_room.c.event_id == body.event_id)
                .where(ie_room.c.round_number == body.round_number)
            )
        ).scalars().all()
        if existing_rooms:
            await db.execute(ie_result.delete().where(ie_result.c.room_id.in_(existing_rooms)))
            await db.execute(ie_room_entry.delete().where(ie_room_entry.c.room_id.in_(existing_rooms)))
            await db.execute(
                ie_room.delete()
                .where(ie_room.c.event_id == body.event_id)
                .where(ie_room.c.round_number == body.round_number)
            )

    # Get active entries
    entry_rows = (
        await db.execute(
            select(ie_entry.c.id, ie_entry.c.institution_id)
            .where(ie_entry.c.event_id == body.event_id)
            .where(ie_entry.c.scratch_status == "ACTIVE")
        )
    ).fetchall()
    if not entry_rows:
        raise HTTPException(status_code=400, detail="No active entries for this event")

    # Build prior room history for round 2+
    prior_peers: dict[int, set[int]] = {}
    if body.round_number > 1:
        history_stmt = (
            select(ie_room_entry.c.room_id, ie_room_entry.c.entry_id)
            .join(ie_room, ie_room.c.id == ie_room_entry.c.room_id)
            .where(ie_room.c.event_id == body.event_id)
            .where(ie_room.c.round_number < body.round_number)
        )
        history_rows = (await db.execute(history_stmt)).fetchall()
        # Group by room, then build peer sets
        room_members: dict[int, list[int]] = {}
        for h in history_rows:
            room_members.setdefault(h.room_id, []).append(h.entry_id)
        for members in room_members.values():
            for eid in members:
                prior_peers.setdefault(eid, set()).update(m for m in members if m != eid)

    entries = [
        EntryForDraw(
            entry_id=r.id,
            institution_id=r.institution_id,
            prior_room_peers=prior_peers.get(r.id, set()),
        )
        for r in entry_rows
    ]

    # Run the draw algorithm
    room_assignments = assign_rooms(entries, room_size=evt.room_size)

    # Write rooms + room_entry rows
    for room_num, entry_ids in enumerate(room_assignments, start=1):
        room_result = await db.execute(
            ie_room.insert()
            .values(
                event_id=body.event_id,
                round_number=body.round_number,
                room_number=room_num,
            )
            .returning(ie_room.c.id)
        )
        room_id = room_result.scalar_one()
        await db.execute(
            ie_room_entry.insert(),
            [{"room_id": room_id, "entry_id": eid} for eid in entry_ids],
        )

    await db.commit()
    await cache_delete(draw_key(body.event_id, body.round_number))
    return await _build_draw_response(db, body.event_id, body.round_number)


@router.get("/{event_id}/round/{round_number}/", response_model=DrawResponse)
async def get_draw(event_id: int, round_number: int, db: AsyncSession = Depends(get_db)):
    # Try cache first
    cache_k = draw_key(event_id, round_number)
    cached = await cache_get(cache_k)
    if cached:
        return DrawResponse(**cached)

    resp = await _build_draw_response(db, event_id, round_number)
    if resp.rooms:
        await cache_set(cache_k, resp.model_dump(mode="json"), ttl=60)
    return resp


@router.post("/assign-judge/", response_model=IERoomResponse)
async def assign_judge(
    body: AssignJudgeRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    room = (await db.execute(select(ie_room).where(ie_room.c.id == body.room_id))).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    await db.execute(
        ie_room.update().where(ie_room.c.id == body.room_id).values(judge_id=body.judge_id)
    )
    await db.commit()

    # Invalidate cache
    await cache_delete(draw_key(room.event_id, room.round_number))

    # Return updated room
    draw_resp = await _build_draw_response(db, room.event_id, room.round_number)
    for r in draw_resp.rooms:
        if r.id == body.room_id:
            return r
    raise HTTPException(status_code=500, detail="Room not found after update")


@router.get("/{event_id}/round/{round_number}/judge/{judge_id}/", response_model=IERoomResponse)
async def get_judge_room(
    event_id: int, round_number: int, judge_id: int,
    db: AsyncSession = Depends(get_db),
):
    room = (
        await db.execute(
            select(ie_room)
            .where(ie_room.c.event_id == event_id)
            .where(ie_room.c.round_number == round_number)
            .where(ie_room.c.judge_id == judge_id)
        )
    ).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="No room assigned to this judge for this round")

    draw_resp = await _build_draw_response(db, event_id, round_number)
    for r in draw_resp.rooms:
        if r.id == room.id:
            return r
    raise HTTPException(status_code=404, detail="Room not found")
