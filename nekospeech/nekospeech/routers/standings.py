"""Standings endpoints — /api/ie/standings/*"""

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.database import get_db
from nekospeech.models.speech_event import ie_room, speech_event
from nekospeech.schemas.standings import StandingsResponse
from nekospeech.services.cache import cache_get, cache_set, standings_key
from nekospeech.services.standings_engine import compute_standings

router = APIRouter(prefix="/api/ie/standings", tags=["standings"])


async def _get_latest_confirmed_round(db: AsyncSession, event_id: int) -> int:
    """Return the highest round number that has at least one confirmed room."""
    result = (
        await db.execute(
            select(ie_room.c.round_number)
            .where(ie_room.c.event_id == event_id)
            .where(ie_room.c.confirmed == True)  # noqa: E712
            .order_by(ie_room.c.round_number.desc())
            .limit(1)
        )
    ).scalar()
    return result or 0


@router.get("/{event_id}/", response_model=StandingsResponse)
async def get_standings(event_id: int, db: AsyncSession = Depends(get_db)):
    # Try cache
    cache_k = standings_key(event_id)
    cached = await cache_get(cache_k)
    if cached:
        return StandingsResponse(**cached)

    latest_round = await _get_latest_confirmed_round(db, event_id)
    if latest_round == 0:
        return StandingsResponse(event_id=event_id, rounds_complete=0, entries=[])

    resp = await compute_standings(db, event_id, latest_round)
    await cache_set(cache_k, resp.model_dump(mode="json"), ttl=30)
    return resp


@router.get("/{event_id}/round/{round_number}/", response_model=StandingsResponse)
async def get_standings_by_round(
    event_id: int, round_number: int, db: AsyncSession = Depends(get_db),
):
    cache_k = standings_key(event_id, round_number)
    cached = await cache_get(cache_k)
    if cached:
        return StandingsResponse(**cached)

    resp = await compute_standings(db, event_id, round_number)
    await cache_set(cache_k, resp.model_dump(mode="json"), ttl=30)
    return resp


@router.get("/{event_id}/export/")
async def export_standings(
    event_id: int,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
):
    latest_round = await _get_latest_confirmed_round(db, event_id)
    if latest_round == 0:
        resp = StandingsResponse(event_id=event_id, rounds_complete=0, entries=[])
    else:
        resp = await compute_standings(db, event_id, latest_round)

    if format == "json":
        return resp

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Name", "School", "School Code",
        "Truncated Rank Sum", "Total Speaker Points",
        "Lowest Single Rank", "Rounds Competed",
    ])
    for row in resp.entries:
        writer.writerow([
            row.rank, row.speaker_name, row.institution_name, row.institution_code,
            row.truncated_rank_sum, row.total_speaker_points,
            row.lowest_single_rank, row.rounds_competed,
        ])
    output.seek(0)

    # Fetch event name for filename
    evt = (await db.execute(select(speech_event.c.abbreviation).where(speech_event.c.id == event_id))).scalar()
    filename = f"standings_{evt or event_id}_round{latest_round}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
