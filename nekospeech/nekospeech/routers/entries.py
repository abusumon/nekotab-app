"""IE Entry endpoints — /api/ie/entries/*"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.auth import require_ie_api_key
from nekospeech.database import get_db
from nekospeech.models.shared import participants_institution, participants_person, participants_speaker, participants_team
from nekospeech.models.speech_event import ie_entry, speech_event
from nekospeech.schemas.entry import IEEntryBulkCreate, IEEntryCreate, IEEntryResponse

router = APIRouter(prefix="/api/ie/entries", tags=["entries"])


async def _enrich_entry(row, db: AsyncSession) -> IEEntryResponse:
    """Attach speaker name + institution info from Django tables."""
    speaker_name = ""
    institution_name = ""
    institution_code = ""
    if row.speaker_id:
        person = (
            await db.execute(
                select(participants_person.c.name).where(participants_person.c.id == row.speaker_id)
            )
        ).scalar()
        speaker_name = person or ""
    if row.institution_id:
        inst = (
            await db.execute(
                select(participants_institution.c.name, participants_institution.c.code)
                .where(participants_institution.c.id == row.institution_id)
            )
        ).fetchone()
        if inst:
            institution_name = inst.name
            institution_code = inst.code
    return IEEntryResponse(
        id=row.id,
        event_id=row.event_id,
        speaker_id=row.speaker_id,
        partner_id=row.partner_id,
        institution_id=row.institution_id,
        scratch_status=row.scratch_status,
        created_at=row.created_at,
        speaker_name=speaker_name,
        institution_name=institution_name,
        institution_code=institution_code,
    )


@router.post("/", response_model=IEEntryResponse, status_code=201)
async def create_entry(
    body: IEEntryCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Validate event exists
    evt = (await db.execute(select(speech_event.c.id, speech_event.c.tournament_id).where(speech_event.c.id == body.event_id))).fetchone()
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")

    # Check for duplicate
    existing = (
        await db.execute(
            select(ie_entry.c.id)
            .where(ie_entry.c.event_id == body.event_id)
            .where(ie_entry.c.speaker_id == body.speaker_id)
        )
    ).scalar()
    if existing:
        raise HTTPException(status_code=409, detail="Speaker already registered for this event")

    # Resolve institution_id via Speaker → Team → Institution FK chain
    inst_row = (
        await db.execute(
            select(participants_team.c.institution_id)
            .join(
                participants_speaker,
                participants_speaker.c.team_id == participants_team.c.id,
            )
            .where(participants_speaker.c.person_ptr_id == body.speaker_id)
        )
    ).scalar()
    institution_id = inst_row if inst_row else None

    result = await db.execute(
        ie_entry.insert()
        .values(
            event_id=body.event_id,
            speaker_id=body.speaker_id,
            partner_id=body.partner_id,
            institution_id=institution_id,
        )
        .returning(ie_entry)
    )
    await db.commit()
    row = result.fetchone()
    return await _enrich_entry(row, db)


@router.get("/", response_model=list[IEEntryResponse])
async def list_entries(event_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    # Single query with JOINs to get speaker name + institution in one go
    stmt = (
        select(
            ie_entry,
            participants_person.c.name.label("speaker_name"),
            participants_institution.c.name.label("institution_name"),
            participants_institution.c.code.label("institution_code"),
        )
        .outerjoin(participants_person, participants_person.c.id == ie_entry.c.speaker_id)
        .outerjoin(participants_institution, participants_institution.c.id == ie_entry.c.institution_id)
        .where(ie_entry.c.event_id == event_id)
        .order_by(ie_entry.c.id)
    )
    rows = (await db.execute(stmt)).fetchall()
    return [
        IEEntryResponse(
            id=r.id,
            event_id=r.event_id,
            speaker_id=r.speaker_id,
            partner_id=r.partner_id,
            institution_id=r.institution_id,
            scratch_status=r.scratch_status,
            created_at=r.created_at,
            speaker_name=r.speaker_name or "",
            institution_name=r.institution_name or "",
            institution_code=r.institution_code or "",
        )
        for r in rows
    ]


@router.delete("/{entry_id}/", status_code=204)
async def scratch_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Verify entry exists
    entry_evt = (await db.execute(
        select(speech_event.c.tournament_id)
        .join(ie_entry, ie_entry.c.event_id == speech_event.c.id)
        .where(ie_entry.c.id == entry_id)
    )).scalar()
    if entry_evt is None:
        raise HTTPException(status_code=404, detail="Entry not found or already scratched")
    result = await db.execute(
        update(ie_entry)
        .where(ie_entry.c.id == entry_id)
        .where(ie_entry.c.scratch_status == "ACTIVE")
        .values(scratch_status="SCRATCHED")
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Entry not found or already scratched")
    await db.commit()


@router.post("/bulk/", response_model=list[IEEntryResponse], status_code=201)
async def bulk_create_entries(
    body: IEEntryBulkCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_ie_api_key),
):
    # Validate event exists
    evt = (await db.execute(select(speech_event.c.id, speech_event.c.tournament_id).where(speech_event.c.id == body.event_id))).fetchone()
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get all speaker_ids from the request
    speaker_ids = [e.speaker_id for e in body.entries]

    # Find which speakers are already registered for this event
    existing_result = await db.execute(
        select(ie_entry.c.speaker_id)
        .where(ie_entry.c.event_id == body.event_id)
        .where(ie_entry.c.speaker_id.in_(speaker_ids))
    )
    existing_speakers = set(existing_result.scalars().all())

    # Filter to only new entries
    new_entries = [e for e in body.entries if e.speaker_id not in existing_speakers]

    if not new_entries:
        # All speakers already registered — return empty list, not an error
        return []

    # Resolve institution_ids for all new speakers via Speaker → Team → Institution
    new_speaker_ids = [e.speaker_id for e in new_entries]
    inst_result = await db.execute(
        select(participants_speaker.c.person_ptr_id, participants_team.c.institution_id)
        .join(
            participants_team,
            participants_team.c.id == participants_speaker.c.team_id,
        )
        .where(participants_speaker.c.person_ptr_id.in_(new_speaker_ids))
    )
    speaker_institution_map = {row.person_ptr_id: row.institution_id for row in inst_result.fetchall()}

    values_list = [
        {
            "event_id": body.event_id,
            "speaker_id": e.speaker_id,
            "partner_id": getattr(e, 'partner_id', None),
            "institution_id": speaker_institution_map.get(e.speaker_id),
        }
        for e in new_entries
    ]

    result = await db.execute(
        ie_entry.insert().returning(
            ie_entry.c.id, ie_entry.c.event_id, ie_entry.c.speaker_id,
            ie_entry.c.partner_id, ie_entry.c.institution_id,
            ie_entry.c.scratch_status, ie_entry.c.created_at
        ),
        values_list,
    )
    await db.commit()

    rows = result.fetchall()

    # Enrich with speaker names and institution info (bulk lookups — no N+1).
    # Previously this returned empty speaker_name/institution_name/institution_code.
    inserted_speaker_ids = [r.speaker_id for r in rows if r.speaker_id]
    speaker_name_map: dict[int, str] = {}
    if inserted_speaker_ids:
        sn_rows = (await db.execute(
            select(participants_person.c.id, participants_person.c.name)
            .where(participants_person.c.id.in_(inserted_speaker_ids))
        )).fetchall()
        speaker_name_map = {sn.id: (sn.name or "") for sn in sn_rows}

    inserted_inst_ids = [r.institution_id for r in rows if r.institution_id]
    inst_info_map: dict[int, tuple[str, str]] = {}
    if inserted_inst_ids:
        ii_rows = (await db.execute(
            select(
                participants_institution.c.id,
                participants_institution.c.name,
                participants_institution.c.code,
            )
            .where(participants_institution.c.id.in_(inserted_inst_ids))
        )).fetchall()
        inst_info_map = {ii.id: (ii.name or "", ii.code or "") for ii in ii_rows}

    return [
        IEEntryResponse(
            id=r.id,
            event_id=r.event_id,
            speaker_id=r.speaker_id,
            partner_id=r.partner_id,
            institution_id=r.institution_id,
            scratch_status=r.scratch_status,
            created_at=r.created_at,
            speaker_name=speaker_name_map.get(r.speaker_id, "") if r.speaker_id else "",
            institution_name=inst_info_map.get(r.institution_id, ("", ""))[0] if r.institution_id else "",
            institution_code=inst_info_map.get(r.institution_id, ("", ""))[1] if r.institution_id else "",
        )
        for r in rows
    ]
