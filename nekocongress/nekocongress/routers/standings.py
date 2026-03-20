"""Standings and advancement — /api/congress/standings/*

Aggregates scores across sessions and chambers, applies normalization
for cross-chamber comparison, and computes advancement.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_chamber,
    congress_chamber_assignment,
    congress_docket_item,
    congress_legislator,
    congress_po_score,
    congress_ranking,
    congress_score,
    congress_session,
    congress_speech,
    congress_tournament,
)
from nekocongress.schemas.standings import (
    AdvancementResponse,
    ChamberStandingsResponse,
    LegislatorStanding,
    StandingsResponse,
)
from nekocongress.services.standings_engine import StandingsEngine

router = APIRouter(prefix="/api/congress/standings", tags=["standings"])


async def _build_engine(congress_tournament_id: int, db: AsyncSession) -> StandingsEngine:
    """Build a StandingsEngine with all data for a congress tournament."""
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == congress_tournament_id)
    )).fetchone()
    if not tournament:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    engine = StandingsEngine(normalization_method=tournament.normalization_method)

    # Get all chambers
    chambers = (await db.execute(
        select(congress_chamber)
        .where(congress_chamber.c.congress_tournament_id == congress_tournament_id)
    )).fetchall()
    chamber_map = {c.id: c for c in chambers}

    # Get all legislators and their chamber assignments
    legislators = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.congress_tournament_id == congress_tournament_id)
    )).fetchall()

    assignments = (await db.execute(
        select(congress_chamber_assignment)
        .where(congress_chamber_assignment.c.chamber_id.in_(
            [c.id for c in chambers]
        ))
    )).fetchall()

    # Map legislator → primary chamber (first assignment)
    leg_chamber = {}
    for a in assignments:
        if a.legislator_id not in leg_chamber:
            leg_chamber[a.legislator_id] = a.chamber_id

    for leg in legislators:
        ch_id = leg_chamber.get(leg.id)
        ch = chamber_map.get(ch_id) if ch_id else None
        engine.set_legislator_info(
            legislator_id=leg.id,
            display_name=leg.display_name,
            institution_code=leg.institution_code or "",
            chamber_label=ch.label if ch else "",
            chamber_id=ch_id,
        )

    # Get all sessions for this tournament
    session_ids = []
    for chamber in chambers:
        sessions = (await db.execute(
            select(congress_session.c.id)
            .where(congress_session.c.chamber_id == chamber.id)
        )).scalars().all()
        session_ids.extend(sessions)

    if not session_ids:
        return engine

    # Get all speeches + their scores
    speeches = (await db.execute(
        select(congress_speech)
        .where(congress_speech.c.session_id.in_(session_ids))
    )).fetchall()

    speech_ids = [s.id for s in speeches]
    scores = []
    if speech_ids:
        scores = (await db.execute(
            select(congress_score)
            .where(congress_score.c.speech_id.in_(speech_ids))
        )).fetchall()

    # Build speech → scores map
    speech_scores: dict[int, list[int]] = {}
    for s in scores:
        speech_scores.setdefault(s.speech_id, []).append(s.points)

    # Add speech scores to engine
    for speech in speeches:
        pts = speech_scores.get(speech.id, [])
        avg_pts = sum(pts) / len(pts) if pts else 0.0
        penalties = speech.overtime_penalty + speech.wrong_side_penalty
        engine.add_speech_score(speech.legislator_id, avg_pts, penalties)

    # Get all rankings
    rankings = (await db.execute(
        select(congress_ranking)
        .where(congress_ranking.c.session_id.in_(session_ids))
    )).fetchall()

    for r in rankings:
        engine.add_ranking(r.legislator_id, r.rank_position, r.is_parliamentarian_ranking)

    # Get all PO scores
    po_scores = (await db.execute(
        select(congress_po_score)
        .where(congress_po_score.c.session_id.in_(session_ids))
    )).fetchall()

    # PO scores: group by session, get PO for that session
    session_po: dict[int, int] = {}
    for sess_id in session_ids:
        sess = (await db.execute(
            select(congress_session.c.po_legislator_id)
            .where(congress_session.c.id == sess_id)
        )).scalar()
        if sess:
            session_po[sess_id] = sess

    po_by_legislator: dict[int, list[int]] = {}
    for ps in po_scores:
        po_leg = session_po.get(ps.session_id)
        if po_leg:
            po_by_legislator.setdefault(po_leg, []).append(ps.points)

    for leg_id, pts in po_by_legislator.items():
        avg = sum(pts) / len(pts) if pts else 0.0
        engine.add_po_score(leg_id, avg)

    return engine


@router.get("/tournament/{congress_tournament_id}/", response_model=StandingsResponse)
async def get_tournament_standings(
    congress_tournament_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == congress_tournament_id)
    )).fetchone()
    if not tournament:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    engine = await _build_engine(congress_tournament_id, db)
    results = engine.compute()

    return StandingsResponse(
        tournament_id=tournament.tournament_id,
        standings=[LegislatorStanding(**r) for r in results],
        last_updated=datetime.now(timezone.utc),
    )


@router.get("/chamber/{chamber_id}/", response_model=ChamberStandingsResponse)
async def get_chamber_standings(
    chamber_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == chamber_id)
    )).fetchone()
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    engine = await _build_engine(chamber.congress_tournament_id, db)
    results = engine.compute_chamber(chamber_id)

    return ChamberStandingsResponse(
        chamber_id=chamber_id,
        chamber_label=chamber.label,
        standings=[LegislatorStanding(**r) for r in results],
    )


@router.post(
    "/tournament/{congress_tournament_id}/advancement/",
    response_model=AdvancementResponse,
)
async def compute_advancement(
    congress_tournament_id: int,
    cutoff_count: int = 24,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    """Compute which legislators advance to elimination rounds.

    cutoff_count: Number of legislators to advance (default 24 for
    typical 2-day NSDA tournaments).
    """
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == congress_tournament_id)
    )).fetchone()
    if not tournament:
        raise HTTPException(status_code=404, detail="Congress tournament not found")

    engine = await _build_engine(congress_tournament_id, db)
    results = engine.compute()

    advancing = results[:cutoff_count]

    return AdvancementResponse(
        tournament_id=tournament.tournament_id,
        advancement_method=tournament.advancement_method,
        normalization_method=tournament.normalization_method,
        advancing=[LegislatorStanding(**r) for r in advancing],
        cutoff_rank=cutoff_count,
    )
