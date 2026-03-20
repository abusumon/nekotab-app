"""Session management — /api/congress/sessions/*

Includes session lifecycle (PENDING → ACTIVE → CLOSED),
PO election handling (IRV), and precedence queue queries.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_chamber,
    congress_chamber_assignment,
    congress_legislator,
    congress_po_ballot,
    congress_po_election,
    congress_session,
    congress_speech,
    congress_tournament,
)
from nekocongress.schemas.session import (
    CandidateTally,
    POElectionBallot,
    POElectionTally,
    PrecedenceEntry,
    PrecedenceQueueResponse,
    QuestionerQueueResponse,
    SessionCreate,
    SessionResponse,
)
from nekocongress.services.cache import redis_pool
from nekocongress.services.po_election import tally_round
from nekocongress.services.precedence import LegislatorState, PrecedenceQueue
from nekocongress.websocket.events import EventType
from nekocongress.websocket.redis_manager import channel_manager

router = APIRouter(prefix="/api/congress/sessions", tags=["sessions"])


# ── Helpers ───────────────────────────────────────────────────────────


async def _build_session_response(row, db: AsyncSession) -> SessionResponse:
    """Enrich a session row with PO name."""
    po_name = ""
    if row.po_legislator_id:
        po = (await db.execute(
            select(congress_legislator.c.display_name)
            .where(congress_legislator.c.id == row.po_legislator_id)
        )).scalar()
        po_name = po or ""
    return SessionResponse(**row._mapping, po_name=po_name)


async def _get_or_build_precedence_queue(
    session_id: int, chamber_id: int, db: AsyncSession
) -> PrecedenceQueue:
    """Load precedence queue from Redis or build from DB state."""
    queue = await PrecedenceQueue.load_from_redis(session_id, redis_pool)
    if queue:
        return queue

    # Build from scratch: get all legislators assigned to this chamber
    assignments = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id.in_(
            select(congress_chamber_assignment.c.legislator_id)
            .where(congress_chamber_assignment.c.chamber_id == chamber_id)
        ))
    )).fetchall()

    # Get tournament config for geography setting
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == chamber_id)
    )).fetchone()
    tournament = None
    if chamber:
        tournament = (await db.execute(
            select(congress_tournament)
            .where(congress_tournament.c.id == chamber.congress_tournament_id)
        )).fetchone()

    queue = PrecedenceQueue(
        session_id=session_id,
        geography_tiebreak=tournament.geography_tiebreak_enabled if tournament else False,
        seed=session_id,
    )

    states = [
        LegislatorState(
            legislator_id=a.id,
            display_name=a.display_name,
            institution_code=a.institution_code or "",
            institution_id=a.institution_id,
            is_withdrawn=a.is_withdrawn,
        )
        for a in assignments
    ]
    queue.initialize(states)

    # Restore speech/question counts from existing speeches in this session
    speeches = (await db.execute(
        select(congress_speech)
        .where(congress_speech.c.session_id == session_id)
        .order_by(congress_speech.c.session_speech_number)
    )).fetchall()

    for speech in speeches:
        if speech.legislator_id in queue.legislators:
            queue.register_speech(speech.legislator_id, speech.ended_at or speech.started_at)

    # Check if PO is set on session
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if session and session.po_legislator_id:
        queue.set_po(session.po_legislator_id)

    await queue.save_to_redis(redis_pool)
    return queue


# ── Session CRUD ──────────────────────────────────────────────────────


@router.post("/", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == body.chamber_id)
    )).fetchone()
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber not found")

    result = await db.execute(
        congress_session.insert()
        .values(**body.model_dump())
        .returning(congress_session)
    )
    await db.commit()
    row = result.fetchone()
    return await _build_session_response(row, db)


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    chamber_id: int | None = None,
    tournament_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    stmt = select(congress_session)
    if chamber_id is not None:
        stmt = stmt.where(congress_session.c.chamber_id == chamber_id)
    if tournament_id is not None:
        stmt = stmt.where(
            congress_session.c.chamber_id.in_(
                select(congress_chamber.c.id).where(
                    congress_chamber.c.congress_tournament_id.in_(
                        select(congress_tournament.c.id).where(
                            congress_tournament.c.tournament_id == tournament_id
                        )
                    )
                )
            )
        )
    stmt = stmt.order_by(congress_session.c.session_number)
    rows = (await db.execute(stmt)).fetchall()
    return [await _build_session_response(r, db) for r in rows]


@router.get("/{session_id}/", response_model=SessionResponse)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    row = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return await _build_session_response(row, db)


@router.post("/{session_id}/start/", response_model=SessionResponse)
async def start_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Session is {session.status}, cannot start")

    await db.execute(
        congress_session.update()
        .where(congress_session.c.id == session_id)
        .values(status="ACTIVE", started_at=datetime.now(timezone.utc))
    )
    await db.commit()

    updated = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()

    # Initialize precedence queue
    await _get_or_build_precedence_queue(session_id, session.chamber_id, db)

    # Broadcast session started
    await channel_manager.publish_to_chamber(
        chamber_id=session.chamber_id,
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
        data={"session_number": session.session_number},
    )

    return await _build_session_response(updated, db)


@router.post("/{session_id}/close/", response_model=SessionResponse)
async def close_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Session is {session.status}, cannot close")

    await db.execute(
        congress_session.update()
        .where(congress_session.c.id == session_id)
        .values(status="CLOSED", closed_at=datetime.now(timezone.utc))
    )
    await db.commit()

    updated = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=session.chamber_id,
        event_type=EventType.SESSION_CLOSED,
        session_id=session_id,
        data={"session_number": session.session_number},
    )

    return await _build_session_response(updated, db)


# ── PO Election ───────────────────────────────────────────────────────


@router.post("/{session_id}/po-election/start/", response_model=POElectionTally)
async def start_po_election(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check no active election
    active = (await db.execute(
        select(congress_po_election)
        .where(
            congress_po_election.c.session_id == session_id,
            congress_po_election.c.status == "OPEN",
        )
    )).fetchone()
    if active:
        raise HTTPException(status_code=409, detail="An election is already open")

    # Get current round number
    max_round = (await db.execute(
        select(func.coalesce(func.max(congress_po_election.c.round_number), 0))
        .where(congress_po_election.c.session_id == session_id)
    )).scalar() or 0
    next_round = max_round + 1

    result = await db.execute(
        congress_po_election.insert()
        .values(session_id=session_id, round_number=next_round, status="OPEN")
        .returning(congress_po_election)
    )
    await db.commit()
    election = result.fetchone()

    # Get candidates (all non-withdrawn legislators in this chamber)
    legislators = (await db.execute(
        select(congress_legislator)
        .where(congress_legislator.c.id.in_(
            select(congress_chamber_assignment.c.legislator_id)
            .where(congress_chamber_assignment.c.chamber_id == session.chamber_id)
        ))
        .where(congress_legislator.c.is_withdrawn == False)  # noqa: E712
    )).fetchall()

    await channel_manager.publish_to_chamber(
        chamber_id=session.chamber_id,
        event_type=EventType.PO_ELECTION_UPDATE,
        session_id=session_id,
        data={"round_number": next_round, "status": "OPEN"},
    )

    return POElectionTally(
        session_id=session_id,
        round_number=next_round,
        status="OPEN",
        candidates=[
            CandidateTally(
                legislator_id=l.id,
                display_name=l.display_name,
                votes=0,
            )
            for l in legislators
        ],
        total_votes=0,
        majority_needed=0,
    )


@router.post("/{session_id}/po-election/vote/", status_code=201)
async def cast_po_vote(
    session_id: int,
    body: POElectionBallot,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    # Find the open election
    election = (await db.execute(
        select(congress_po_election)
        .where(
            congress_po_election.c.session_id == session_id,
            congress_po_election.c.status == "OPEN",
        )
        .order_by(congress_po_election.c.round_number.desc())
    )).fetchone()
    if not election:
        raise HTTPException(status_code=404, detail="No open election for this session")

    # Check voter hasn't already voted in this round
    existing = (await db.execute(
        select(congress_po_ballot.c.id)
        .where(
            congress_po_ballot.c.election_id == election.id,
            congress_po_ballot.c.voter_legislator_id == body.voter_legislator_id,
        )
    )).scalar()
    if existing:
        raise HTTPException(status_code=409, detail="Voter already cast a ballot in this round")

    await db.execute(
        congress_po_ballot.insert()
        .values(
            election_id=election.id,
            voter_legislator_id=body.voter_legislator_id,
            candidate_legislator_id=body.candidate_legislator_id,
        )
    )
    await db.commit()
    return {"status": "ballot_cast"}


@router.post("/{session_id}/po-election/tally/", response_model=POElectionTally)
async def tally_po_election(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    election = (await db.execute(
        select(congress_po_election)
        .where(
            congress_po_election.c.session_id == session_id,
            congress_po_election.c.status == "OPEN",
        )
        .order_by(congress_po_election.c.round_number.desc())
    )).fetchone()
    if not election:
        raise HTTPException(status_code=404, detail="No open election for this session")

    # Fetch all ballots for this election
    ballots_rows = (await db.execute(
        select(congress_po_ballot)
        .where(congress_po_ballot.c.election_id == election.id)
    )).fetchall()

    ballots = [(b.voter_legislator_id, b.candidate_legislator_id) for b in ballots_rows]

    # Get previously eliminated candidates
    eliminated = set()
    prev_elections = (await db.execute(
        select(congress_po_election)
        .where(
            congress_po_election.c.session_id == session_id,
            congress_po_election.c.status == "CLOSED",
        )
    )).fetchall()
    # Candidates who received fewest votes in previous rounds are NOT automatically
    # eliminated in NSDA rules — each round is a fresh vote. But we track who was
    # eliminated across rounds for multi-round disambiguation.

    result = tally_round(ballots, eliminated, election.round_number)

    # Build candidate display info
    candidate_ids = list(result.vote_counts.keys())
    candidates_map = {}
    if candidate_ids:
        rows = (await db.execute(
            select(congress_legislator)
            .where(congress_legislator.c.id.in_(candidate_ids))
        )).fetchall()
        candidates_map = {r.id: r for r in rows}

    if result.is_decided and result.winner_id:
        # Set PO on session
        await db.execute(
            congress_session.update()
            .where(congress_session.c.id == session_id)
            .values(po_legislator_id=result.winner_id)
        )
        # Close election
        await db.execute(
            congress_po_election.update()
            .where(congress_po_election.c.id == election.id)
            .values(
                status="CLOSED",
                winner_legislator_id=result.winner_id,
            )
        )
        await db.commit()

        # Update precedence queue
        queue = await _get_or_build_precedence_queue(session_id, session.chamber_id, db)
        queue.set_po(result.winner_id)
        await queue.save_to_redis(redis_pool)

        winner_name = candidates_map.get(result.winner_id)
        winner_display = winner_name.display_name if winner_name else ""

        await channel_manager.publish_to_chamber(
            chamber_id=session.chamber_id,
            event_type=EventType.PO_ELECTED,
            session_id=session_id,
            data={
                "winner_id": result.winner_id,
                "winner_name": winner_display,
                "round_number": election.round_number,
            },
        )
    else:
        # Close this round
        await db.execute(
            congress_po_election.update()
            .where(congress_po_election.c.id == election.id)
            .values(status="CLOSED")
        )
        await db.commit()

    winner_name_str = ""
    if result.winner_id and result.winner_id in candidates_map:
        winner_name_str = candidates_map[result.winner_id].display_name

    return POElectionTally(
        session_id=session_id,
        round_number=election.round_number,
        status="DECIDED" if result.is_decided else "CLOSED",
        candidates=[
            CandidateTally(
                legislator_id=cid,
                display_name=candidates_map.get(cid, type("", (), {"display_name": ""})).display_name,
                votes=votes,
                eliminated=cid == result.eliminated_id,
            )
            for cid, votes in sorted(result.vote_counts.items(), key=lambda x: -x[1])
        ],
        total_votes=result.total_votes,
        majority_needed=result.majority_needed,
        winner_id=result.winner_id,
        winner_name=winner_name_str,
    )


# ── Precedence Queue Queries ─────────────────────────────────────────


@router.get("/{session_id}/precedence/", response_model=PrecedenceQueueResponse)
async def get_precedence_queue(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = await _get_or_build_precedence_queue(session_id, session.chamber_id, db)
    speaker_queue = queue.get_speaker_queue()

    return PrecedenceQueueResponse(
        session_id=session_id,
        next_side=session.next_side,
        queue=[
            PrecedenceEntry(
                legislator_id=ls.legislator_id,
                display_name=ls.display_name,
                institution_code=ls.institution_code,
                speech_count=ls.speech_count,
                last_speech_at=ls.last_speech_at,
                queue_position=idx + 1,
            )
            for idx, ls in enumerate(speaker_queue)
        ],
    )


@router.get("/{session_id}/questioner-queue/", response_model=QuestionerQueueResponse)
async def get_questioner_queue(
    session_id: int,
    current_speaker_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = await _get_or_build_precedence_queue(session_id, session.chamber_id, db)
    q_queue = queue.get_questioner_queue(exclude_current_speaker_id=current_speaker_id)

    return QuestionerQueueResponse(
        session_id=session_id,
        queue=[
            PrecedenceEntry(
                legislator_id=ls.legislator_id,
                display_name=ls.display_name,
                institution_code=ls.institution_code,
                speech_count=ls.question_count,
                last_speech_at=ls.last_question_at,
                queue_position=idx + 1,
            )
            for idx, ls in enumerate(q_queue)
        ],
    )
