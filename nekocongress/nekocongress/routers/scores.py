"""Scoring endpoints — /api/congress/scores/*

Handles speech scores, session rankings (regular + parliamentarian),
and PO scoring. All score submissions broadcast WebSocket events.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_chamber,
    congress_legislator,
    congress_po_score,
    congress_ranking,
    congress_score,
    congress_session,
    congress_speech,
    congress_tournament,
)
from nekocongress.schemas.score import (
    ParliamentarianRankingCreate,
    POScoreCreate,
    POScoreResponse,
    RankingCreate,
    RankingResponse,
    SessionScoresResponse,
    SpeechScoreCreate,
    SpeechScoreResponse,
    SpeechScoreUpdate,
)
from nekocongress.websocket.events import EventType
from nekocongress.websocket.redis_manager import channel_manager

router = APIRouter(prefix="/api/congress/scores", tags=["scores"])


# ── Helpers ───────────────────────────────────────────────────────────


async def _get_chamber_id_for_session(session_id: int, db: AsyncSession) -> int:
    session = (await db.execute(
        select(congress_session.c.chamber_id)
        .where(congress_session.c.id == session_id)
    )).scalar()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _validate_score_range(points: int, session_id: int, db: AsyncSession) -> None:
    """Validate score is within tournament's configured range."""
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == chamber.congress_tournament_id)
    )).fetchone()
    if not tournament:
        return
    if not (tournament.scoring_range_min <= points <= tournament.scoring_range_max):
        raise HTTPException(
            status_code=400,
            detail=f"Score must be between {tournament.scoring_range_min} and {tournament.scoring_range_max}",
        )


# ── Speech Scores ─────────────────────────────────────────────────────


@router.post("/speech/", response_model=SpeechScoreResponse, status_code=201)
async def submit_speech_score(
    body: SpeechScoreCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")

    await _validate_score_range(body.points, speech.session_id, db)

    # Check no duplicate score from same scorer for same speech
    existing = (await db.execute(
        select(congress_score.c.id)
        .where(
            congress_score.c.speech_id == body.speech_id,
            congress_score.c.scorer_id == body.scorer_id,
        )
    )).scalar()
    if existing:
        raise HTTPException(status_code=409, detail="Score already submitted for this speech by this scorer")

    from datetime import datetime, timezone

    result = await db.execute(
        congress_score.insert()
        .values(
            speech_id=body.speech_id,
            scorer_id=body.scorer_id,
            points=body.points,
            feedback=body.feedback,
            submitted_at=datetime.now(timezone.utc),
        )
        .returning(congress_score)
    )
    await db.commit()
    row = result.fetchone()

    chamber_id = await _get_chamber_id_for_session(speech.session_id, db)
    await channel_manager.publish_to_chamber(
        chamber_id=chamber_id,
        event_type=EventType.SCORE_SUBMITTED,
        session_id=speech.session_id,
        data={
            "score_id": row.id,
            "speech_id": body.speech_id,
            "scorer_id": body.scorer_id,
        },
    )

    return SpeechScoreResponse(**row._mapping)


@router.patch("/speech/{score_id}/", response_model=SpeechScoreResponse)
async def update_speech_score(
    score_id: int,
    body: SpeechScoreUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    score = (await db.execute(
        select(congress_score).where(congress_score.c.id == score_id)
    )).fetchone()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")

    values = body.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "points" in values:
        speech = (await db.execute(
            select(congress_speech).where(congress_speech.c.id == score.speech_id)
        )).fetchone()
        if speech:
            await _validate_score_range(values["points"], speech.session_id, db)

    await db.execute(
        congress_score.update()
        .where(congress_score.c.id == score_id)
        .values(**values)
    )
    await db.commit()

    updated = (await db.execute(
        select(congress_score).where(congress_score.c.id == score_id)
    )).fetchone()
    return SpeechScoreResponse(**updated._mapping)


# ── Session Rankings ──────────────────────────────────────────────────


@router.post("/rankings/", response_model=list[RankingResponse], status_code=201)
async def submit_rankings(
    body: RankingCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == body.session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete existing rankings from this scorer for this session (replace mode)
    await db.execute(
        congress_ranking.delete()
        .where(
            congress_ranking.c.session_id == body.session_id,
            congress_ranking.c.scorer_id == body.scorer_id,
            congress_ranking.c.is_parliamentarian_ranking == False,  # noqa: E712
        )
    )

    rows = []
    for entry in body.rankings:
        result = await db.execute(
            congress_ranking.insert()
            .values(
                session_id=body.session_id,
                scorer_id=body.scorer_id,
                legislator_id=entry.legislator_id,
                rank_position=entry.rank_position,
                is_parliamentarian_ranking=False,
            )
            .returning(congress_ranking)
        )
        row = result.fetchone()
        if row:
            rows.append(row)
    await db.commit()

    chamber_id = await _get_chamber_id_for_session(body.session_id, db)
    await channel_manager.publish_to_chamber(
        chamber_id=chamber_id,
        event_type=EventType.RANKING_SUBMITTED,
        session_id=body.session_id,
        data={"scorer_id": body.scorer_id, "ranking_count": len(rows)},
    )

    # Enrich with legislator names
    responses = []
    for row in rows:
        leg = (await db.execute(
            select(congress_legislator.c.display_name)
            .where(congress_legislator.c.id == row.legislator_id)
        )).scalar()
        responses.append(RankingResponse(
            **row._mapping,
            legislator_name=leg or "",
        ))
    return responses


@router.post("/rankings/parliamentarian/", response_model=list[RankingResponse], status_code=201)
async def submit_parliamentarian_rankings(
    body: ParliamentarianRankingCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == body.session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete existing parliamentarian rankings from this scorer
    await db.execute(
        congress_ranking.delete()
        .where(
            congress_ranking.c.session_id == body.session_id,
            congress_ranking.c.scorer_id == body.scorer_id,
            congress_ranking.c.is_parliamentarian_ranking == True,  # noqa: E712
        )
    )

    rows = []
    for entry in body.rankings:
        result = await db.execute(
            congress_ranking.insert()
            .values(
                session_id=body.session_id,
                scorer_id=body.scorer_id,
                legislator_id=entry.legislator_id,
                rank_position=entry.rank_position,
                is_parliamentarian_ranking=True,
            )
            .returning(congress_ranking)
        )
        row = result.fetchone()
        if row:
            rows.append(row)
    await db.commit()

    responses = []
    for row in rows:
        leg = (await db.execute(
            select(congress_legislator.c.display_name)
            .where(congress_legislator.c.id == row.legislator_id)
        )).scalar()
        responses.append(RankingResponse(
            **row._mapping,
            legislator_name=leg or "",
        ))
    return responses


# ── PO Scoring ────────────────────────────────────────────────────────


@router.post("/po/", response_model=POScoreResponse, status_code=201)
async def submit_po_score(
    body: POScoreCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == body.session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.po_legislator_id:
        raise HTTPException(status_code=409, detail="No PO assigned to this session")

    # Validate PO score range
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == chamber.congress_tournament_id)
    )).fetchone()
    if tournament:
        if not (tournament.po_scoring_range_min <= body.points <= tournament.po_scoring_range_max):
            raise HTTPException(
                status_code=400,
                detail=f"PO score must be between {tournament.po_scoring_range_min} and {tournament.po_scoring_range_max}",
            )

    # Check no duplicate
    existing = (await db.execute(
        select(congress_po_score.c.id)
        .where(
            congress_po_score.c.session_id == body.session_id,
            congress_po_score.c.scorer_id == body.scorer_id,
            congress_po_score.c.hour_number == body.hour_number,
        )
    )).scalar()
    if existing:
        raise HTTPException(status_code=409, detail="PO score already submitted for this hour")

    result = await db.execute(
        congress_po_score.insert()
        .values(
            session_id=body.session_id,
            scorer_id=body.scorer_id,
            hour_number=body.hour_number,
            points=body.points,
            feedback=body.feedback,
        )
        .returning(congress_po_score)
    )
    await db.commit()
    row = result.fetchone()
    return POScoreResponse(**row._mapping)


# ── Read Endpoints ────────────────────────────────────────────────────


@router.get("/session/{session_id}/", response_model=SessionScoresResponse)
async def get_session_scores(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Speech scores
    scores = (await db.execute(
        select(congress_score)
        .where(congress_score.c.speech_id.in_(
            select(congress_speech.c.id)
            .where(congress_speech.c.session_id == session_id)
        ))
        .order_by(congress_score.c.submitted_at)
    )).fetchall()

    # Rankings
    rankings_rows = (await db.execute(
        select(congress_ranking)
        .where(congress_ranking.c.session_id == session_id)
        .order_by(congress_ranking.c.rank_position)
    )).fetchall()

    # Enrich ranking names
    ranking_responses = []
    for r in rankings_rows:
        leg_name = (await db.execute(
            select(congress_legislator.c.display_name)
            .where(congress_legislator.c.id == r.legislator_id)
        )).scalar()
        ranking_responses.append(RankingResponse(
            **r._mapping,
            legislator_name=leg_name or "",
        ))

    # PO scores
    po_scores = (await db.execute(
        select(congress_po_score)
        .where(congress_po_score.c.session_id == session_id)
        .order_by(congress_po_score.c.hour_number)
    )).fetchall()

    return SessionScoresResponse(
        session_id=session_id,
        speech_scores=[SpeechScoreResponse(**s._mapping) for s in scores],
        rankings=ranking_responses,
        po_scores=[POScoreResponse(**p._mapping) for p in po_scores],
    )
