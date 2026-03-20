"""Floor management — /api/congress/floor/*

The core real-time management router for Congressional Debate.
Handles: recognize speakers, start/end speeches, open/close questioning,
change legislation, call/record votes.

Every mutation publishes WebSocket events via RedisChannelManager.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nekocongress.auth import require_congress_api_key
from nekocongress.database import get_db
from nekocongress.models.congress import (
    congress_chamber,
    congress_docket_item,
    congress_legislation,
    congress_legislator,
    congress_question_period,
    congress_questioner,
    congress_session,
    congress_speech,
    congress_tournament,
)
from nekocongress.schemas.floor import (
    CallVoteRequest,
    ChangeLegislationRequest,
    CloseQuestionsRequest,
    EndSpeechRequest,
    OpenQuestionsRequest,
    QuestionerResponse,
    QuestionPeriodResponse,
    RecognizeQuestionerRequest,
    RecognizeSpeakerRequest,
    RecordVoteRequest,
    SpeechResponse,
    StartSpeechRequest,
)
from nekocongress.services.cache import redis_pool
from nekocongress.services.precedence import PrecedenceQueue
from nekocongress.websocket.events import EventType
from nekocongress.websocket.redis_manager import channel_manager

router = APIRouter(prefix="/api/congress/floor", tags=["floor"])


# ── Helpers ───────────────────────────────────────────────────────────


async def _load_session_with_tournament(session_id: int, db: AsyncSession):
    """Load session, chamber, and tournament config in a single helper."""
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Session is {session.status}")

    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()

    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == chamber.congress_tournament_id)
    )).fetchone()

    return session, chamber, tournament


async def _get_precedence_queue(session_id: int, db: AsyncSession) -> PrecedenceQueue:
    """Load precedence queue from Redis (import sessions helper to build if missing)."""
    from nekocongress.routers.sessions import _get_or_build_precedence_queue

    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == session_id)
    )).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await _get_or_build_precedence_queue(session_id, session.chamber_id, db)


def _build_speech_response(speech, legislator_name: str = "", institution_code: str = "") -> SpeechResponse:
    return SpeechResponse(
        id=speech.id,
        session_id=speech.session_id,
        docket_item_id=speech.docket_item_id,
        legislator_id=speech.legislator_id,
        legislator_name=legislator_name,
        institution_code=institution_code,
        speech_number=speech.speech_number,
        session_speech_number=speech.session_speech_number,
        side=speech.side,
        speech_type=speech.speech_type,
        started_at=speech.started_at,
        ended_at=speech.ended_at,
        duration_seconds=speech.duration_seconds,
        is_overtime=speech.is_overtime,
        overtime_seconds=speech.overtime_seconds,
        overtime_penalty=speech.overtime_penalty,
        wrong_side=speech.wrong_side,
        wrong_side_penalty=speech.wrong_side_penalty,
        created_at=speech.created_at,
    )


# ── Recognize Speaker ─────────────────────────────────────────────────


@router.post("/recognize-speaker/", response_model=SpeechResponse, status_code=201)
async def recognize_speaker(
    body: RecognizeSpeakerRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    """Recognize a legislator to speak. Creates a speech record.

    If legislator_id is None, auto-selects from the precedence queue.
    """
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    if not session.current_docket_item_id:
        raise HTTPException(status_code=409, detail="No legislation is currently on the floor")

    queue = await _get_precedence_queue(body.session_id, db)

    # Determine speaker
    legislator_id = body.legislator_id
    if legislator_id is None:
        # Auto-select: check authorship first for first speech on legislation
        if body.speech_type == "AUTHORSHIP":
            docket_item = (await db.execute(
                select(congress_docket_item, congress_legislation)
                .outerjoin(congress_legislation,
                           congress_legislation.c.id == congress_docket_item.c.legislation_id)
                .where(congress_docket_item.c.id == session.current_docket_item_id)
            )).fetchone()
            if docket_item and docket_item.author_institution_id:
                author = queue.get_authorship_speaker(docket_item.author_institution_id)
                if author:
                    legislator_id = author.legislator_id

        if legislator_id is None:
            next_speaker = queue.get_next_speaker()
            if not next_speaker:
                raise HTTPException(status_code=409, detail="No eligible speakers in queue")
            legislator_id = next_speaker.legislator_id

    # Validate legislator is in queue
    if legislator_id not in queue.legislators:
        raise HTTPException(status_code=400, detail="Legislator not in this session")

    # Get legislator info
    leg = (await db.execute(
        select(congress_legislator).where(congress_legislator.c.id == legislator_id)
    )).fetchone()
    if not leg:
        raise HTTPException(status_code=404, detail="Legislator not found")

    # Determine side
    side = body.side or session.next_side

    # Calculate speech numbers
    speech_count_on_item = (await db.execute(
        select(func.coalesce(func.max(congress_speech.c.speech_number), 0))
        .where(congress_speech.c.docket_item_id == session.current_docket_item_id)
    )).scalar() or 0

    session_speech_count = session.current_speech_number

    new_speech_number = speech_count_on_item + 1
    new_session_speech = session_speech_count + 1

    # Check wrong side
    wrong_side = body.is_wrong_side
    wrong_side_penalty = tournament.wrong_side_penalty if wrong_side else 0

    # Create speech record
    result = await db.execute(
        congress_speech.insert()
        .values(
            session_id=body.session_id,
            docket_item_id=session.current_docket_item_id,
            legislator_id=legislator_id,
            speech_number=new_speech_number,
            session_speech_number=new_session_speech,
            side=side,
            speech_type=body.speech_type,
            wrong_side=wrong_side,
            wrong_side_penalty=wrong_side_penalty,
        )
        .returning(congress_speech)
    )

    # Update session speech counter and flip side
    next_side = "NEG" if side == "AFF" else "AFF"
    await db.execute(
        congress_session.update()
        .where(congress_session.c.id == body.session_id)
        .values(
            current_speech_number=new_session_speech,
            next_side=next_side,
        )
    )
    await db.commit()
    speech = result.fetchone()

    # Publish event
    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.SPEAKER_RECOGNIZED,
        session_id=body.session_id,
        data={
            "speech_id": speech.id,
            "legislator_id": legislator_id,
            "legislator_name": leg.display_name,
            "side": side,
            "speech_type": body.speech_type,
            "speech_number": new_speech_number,
        },
    )

    return _build_speech_response(speech, leg.display_name, leg.institution_code or "")


# ── Start / End Speech ────────────────────────────────────────────────


@router.post("/start-speech/", response_model=SpeechResponse)
async def start_speech(
    body: StartSpeechRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")
    if speech.started_at:
        raise HTTPException(status_code=409, detail="Speech already started")

    now = datetime.now(timezone.utc)
    await db.execute(
        congress_speech.update()
        .where(congress_speech.c.id == body.speech_id)
        .values(started_at=now)
    )
    await db.commit()

    updated = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()

    leg = (await db.execute(
        select(congress_legislator).where(congress_legislator.c.id == speech.legislator_id)
    )).fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.SPEECH_STARTED,
        session_id=body.session_id,
        data={
            "speech_id": body.speech_id,
            "legislator_name": leg.display_name if leg else "",
            "started_at": now.isoformat(),
        },
    )

    return _build_speech_response(
        updated,
        leg.display_name if leg else "",
        leg.institution_code if leg else "",
    )


@router.post("/end-speech/", response_model=SpeechResponse)
async def end_speech(
    body: EndSpeechRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")
    if not speech.started_at:
        raise HTTPException(status_code=409, detail="Speech has not started yet")
    if speech.ended_at:
        raise HTTPException(status_code=409, detail="Speech already ended")

    now = datetime.now(timezone.utc)
    duration = int((now - speech.started_at).total_seconds())

    # Calculate overtime penalty
    speech_time = tournament.speech_time_seconds
    if speech.speech_type in ("AUTHORSHIP", "SPONSORSHIP"):
        speech_time = tournament.authorship_speech_time_seconds

    is_overtime, overtime_seconds, overtime_penalty = PrecedenceQueue.calculate_overtime_penalty(
        duration_seconds=duration,
        speech_time_seconds=speech_time,
        grace_seconds=tournament.overtime_grace_seconds,
        penalty_per_interval=tournament.overtime_penalty_per_interval,
        interval_seconds=tournament.overtime_interval_seconds,
    )

    await db.execute(
        congress_speech.update()
        .where(congress_speech.c.id == body.speech_id)
        .values(
            ended_at=now,
            duration_seconds=duration,
            is_overtime=is_overtime,
            overtime_seconds=overtime_seconds,
            overtime_penalty=overtime_penalty,
        )
    )
    await db.commit()

    # Register speech in precedence queue
    queue = await _get_precedence_queue(body.session_id, db)
    queue.register_speech(speech.legislator_id, now)
    await queue.save_to_redis(redis_pool)

    updated = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()

    leg = (await db.execute(
        select(congress_legislator).where(congress_legislator.c.id == speech.legislator_id)
    )).fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.SPEECH_ENDED,
        session_id=body.session_id,
        data={
            "speech_id": body.speech_id,
            "duration_seconds": duration,
            "is_overtime": is_overtime,
            "overtime_penalty": overtime_penalty,
        },
    )

    # Also publish queue update
    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.QUEUE_UPDATED,
        session_id=body.session_id,
        data={"reason": "speech_ended"},
    )

    return _build_speech_response(
        updated,
        leg.display_name if leg else "",
        leg.institution_code if leg else "",
    )


# ── Question Period ───────────────────────────────────────────────────


@router.post("/open-questions/", response_model=QuestionPeriodResponse, status_code=201)
async def open_questions(
    body: OpenQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")

    # Get session and tournament config for questioning time
    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == speech.session_id)
    )).fetchone()
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()
    tournament = (await db.execute(
        select(congress_tournament)
        .where(congress_tournament.c.id == chamber.congress_tournament_id)
    )).fetchone()

    q_time = tournament.questioning_time_seconds
    if speech.speech_type in ("AUTHORSHIP", "SPONSORSHIP"):
        q_time = tournament.authorship_questioning_time_seconds

    result = await db.execute(
        congress_question_period.insert()
        .values(
            speech_id=body.speech_id,
            total_time_seconds=q_time,
            started_at=datetime.now(timezone.utc),
        )
        .returning(congress_question_period)
    )
    await db.commit()
    qp = result.fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.QUESTIONS_OPENED,
        session_id=speech.session_id,
        data={
            "question_period_id": qp.id,
            "speech_id": body.speech_id,
            "total_time_seconds": q_time,
        },
    )

    return QuestionPeriodResponse(
        id=qp.id,
        speech_id=qp.speech_id,
        total_time_seconds=qp.total_time_seconds,
        started_at=qp.started_at,
        ended_at=qp.ended_at,
    )


@router.post("/recognize-questioner/", response_model=QuestionerResponse, status_code=201)
async def recognize_questioner(
    body: RecognizeQuestionerRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    """Recognize a legislator to ask a question during a question period."""
    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")

    # Find the open question period
    qp = (await db.execute(
        select(congress_question_period)
        .where(
            congress_question_period.c.speech_id == body.speech_id,
            congress_question_period.c.ended_at == None,  # noqa: E711
        )
        .order_by(congress_question_period.c.id.desc())
    )).fetchone()
    if not qp:
        raise HTTPException(status_code=409, detail="No open question period for this speech")

    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == body.session_id)
    )).fetchone()
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()

    queue = await _get_precedence_queue(body.session_id, db)

    # Determine questioner
    legislator_id = body.legislator_id
    if legislator_id is None:
        next_q = queue.get_next_questioner(exclude_current_speaker_id=speech.legislator_id)
        if not next_q:
            raise HTTPException(status_code=409, detail="No eligible questioners")
        legislator_id = next_q.legislator_id

    leg = (await db.execute(
        select(congress_legislator).where(congress_legislator.c.id == legislator_id)
    )).fetchone()
    if not leg:
        raise HTTPException(status_code=404, detail="Legislator not found")

    # Get next segment number
    max_seg = (await db.execute(
        select(func.coalesce(func.max(congress_questioner.c.segment_number), 0))
        .where(congress_questioner.c.question_period_id == qp.id)
    )).scalar() or 0

    result = await db.execute(
        congress_questioner.insert()
        .values(
            question_period_id=qp.id,
            legislator_id=legislator_id,
            segment_number=max_seg + 1,
            started_at=datetime.now(timezone.utc),
        )
        .returning(congress_questioner)
    )
    await db.commit()
    q = result.fetchone()

    # Register question in precedence queue
    queue.register_question(legislator_id, datetime.now(timezone.utc))
    await queue.save_to_redis(redis_pool)

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.QUESTIONER_RECOGNIZED,
        session_id=body.session_id,
        data={
            "questioner_id": q.id,
            "legislator_id": legislator_id,
            "legislator_name": leg.display_name,
            "segment_number": q.segment_number,
        },
    )

    return QuestionerResponse(
        id=q.id,
        legislator_id=q.legislator_id,
        legislator_name=leg.display_name,
        segment_number=q.segment_number,
        started_at=q.started_at,
        ended_at=q.ended_at,
    )


@router.post("/close-questions/", response_model=QuestionPeriodResponse)
async def close_questions(
    body: CloseQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    speech = (await db.execute(
        select(congress_speech).where(congress_speech.c.id == body.speech_id)
    )).fetchone()
    if not speech:
        raise HTTPException(status_code=404, detail="Speech not found")

    qp = (await db.execute(
        select(congress_question_period)
        .where(
            congress_question_period.c.speech_id == body.speech_id,
            congress_question_period.c.ended_at == None,  # noqa: E711
        )
        .order_by(congress_question_period.c.id.desc())
    )).fetchone()
    if not qp:
        raise HTTPException(status_code=409, detail="No open question period")

    now = datetime.now(timezone.utc)
    await db.execute(
        congress_question_period.update()
        .where(congress_question_period.c.id == qp.id)
        .values(ended_at=now)
    )

    # End any open questioner segments
    await db.execute(
        congress_questioner.update()
        .where(
            congress_questioner.c.question_period_id == qp.id,
            congress_questioner.c.ended_at == None,  # noqa: E711
        )
        .values(ended_at=now)
    )
    await db.commit()

    session = (await db.execute(
        select(congress_session).where(congress_session.c.id == speech.session_id)
    )).fetchone()
    chamber = (await db.execute(
        select(congress_chamber).where(congress_chamber.c.id == session.chamber_id)
    )).fetchone()

    # Fetch questioners for response
    questioners = (await db.execute(
        select(congress_questioner, congress_legislator.c.display_name)
        .outerjoin(congress_legislator,
                   congress_legislator.c.id == congress_questioner.c.legislator_id)
        .where(congress_questioner.c.question_period_id == qp.id)
        .order_by(congress_questioner.c.segment_number)
    )).fetchall()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.QUESTIONS_CLOSED,
        session_id=speech.session_id,
        data={"speech_id": body.speech_id, "question_period_id": qp.id},
    )

    # Also publish queue update
    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.QUEUE_UPDATED,
        session_id=speech.session_id,
        data={"reason": "questions_closed"},
    )

    return QuestionPeriodResponse(
        id=qp.id,
        speech_id=qp.speech_id,
        total_time_seconds=qp.total_time_seconds,
        started_at=qp.started_at,
        ended_at=now,
        questioners=[
            QuestionerResponse(
                id=q.id,
                legislator_id=q.legislator_id,
                legislator_name=q.display_name or "",
                segment_number=q.segment_number,
                started_at=q.started_at,
                ended_at=q.ended_at,
            )
            for q in questioners
        ],
    )


# ── Change Legislation ────────────────────────────────────────────────


@router.post("/change-legislation/", response_model=dict)
async def change_legislation(
    body: ChangeLegislationRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    """Advance to the next docket item, or jump to a specific one."""
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    if body.docket_item_id is not None:
        # Jump to specific item
        item = (await db.execute(
            select(congress_docket_item)
            .where(congress_docket_item.c.id == body.docket_item_id)
        )).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Docket item not found")
        target_id = item.id
    else:
        # Auto-advance: find next PENDING item in agenda order
        current_order = 0
        if session.current_docket_item_id:
            current = (await db.execute(
                select(congress_docket_item.c.agenda_order)
                .where(congress_docket_item.c.id == session.current_docket_item_id)
            )).scalar()
            current_order = current or 0

        next_item = (await db.execute(
            select(congress_docket_item)
            .where(
                congress_docket_item.c.session_id == body.session_id,
                congress_docket_item.c.agenda_order > current_order,
                congress_docket_item.c.status == "PENDING",
            )
            .order_by(congress_docket_item.c.agenda_order)
            .limit(1)
        )).fetchone()
        if not next_item:
            raise HTTPException(status_code=409, detail="No more docket items")
        target_id = next_item.id

    # Mark current item as CARRIED_OVER if moving away
    if session.current_docket_item_id and session.current_docket_item_id != target_id:
        await db.execute(
            congress_docket_item.update()
            .where(
                congress_docket_item.c.id == session.current_docket_item_id,
                congress_docket_item.c.status == "PENDING",
            )
            .values(status="CARRIED_OVER")
        )

    # Set new current item to DEBATING
    await db.execute(
        congress_docket_item.update()
        .where(congress_docket_item.c.id == target_id)
        .values(status="DEBATING")
    )

    # Update session
    await db.execute(
        congress_session.update()
        .where(congress_session.c.id == body.session_id)
        .values(current_docket_item_id=target_id, next_side="AFF")
    )
    await db.commit()

    # Get legislation info for the event
    item = (await db.execute(
        select(congress_docket_item, congress_legislation)
        .outerjoin(congress_legislation,
                   congress_legislation.c.id == congress_docket_item.c.legislation_id)
        .where(congress_docket_item.c.id == target_id)
    )).fetchone()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.LEGISLATION_CHANGED,
        session_id=body.session_id,
        data={
            "docket_item_id": target_id,
            "legislation_title": item.title if item else "",
            "docket_code": item.docket_code if item else "",
        },
    )

    return {
        "docket_item_id": target_id,
        "legislation_title": item.title if item else "",
        "docket_code": item.docket_code if item else "",
    }


# ── Voting ────────────────────────────────────────────────────────────


@router.post("/call-vote/", response_model=dict)
async def call_vote(
    body: CallVoteRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    item = (await db.execute(
        select(congress_docket_item)
        .where(congress_docket_item.c.id == body.docket_item_id)
    )).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Docket item not found")

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.VOTE_CALLED,
        session_id=body.session_id,
        data={"docket_item_id": body.docket_item_id},
    )

    return {"status": "vote_called", "docket_item_id": body.docket_item_id}


@router.post("/record-vote/", response_model=dict)
async def record_vote(
    body: RecordVoteRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    session, chamber, tournament = await _load_session_with_tournament(body.session_id, db)

    item = (await db.execute(
        select(congress_docket_item)
        .where(congress_docket_item.c.id == body.docket_item_id)
    )).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Docket item not found")

    await db.execute(
        congress_docket_item.update()
        .where(congress_docket_item.c.id == body.docket_item_id)
        .values(
            vote_result=body.result,
            aff_votes=body.aff_votes,
            neg_votes=body.neg_votes,
            abstain_votes=body.abstain_votes,
            status="VOTED",
        )
    )
    await db.commit()

    await channel_manager.publish_to_chamber(
        chamber_id=chamber.id,
        event_type=EventType.VOTE_RECORDED,
        session_id=body.session_id,
        data={
            "docket_item_id": body.docket_item_id,
            "result": body.result,
            "aff_votes": body.aff_votes,
            "neg_votes": body.neg_votes,
            "abstain_votes": body.abstain_votes,
        },
    )

    return {
        "status": "vote_recorded",
        "docket_item_id": body.docket_item_id,
        "result": body.result,
    }


# ── Read endpoints ────────────────────────────────────────────────────


@router.get("/speeches/{session_id}/", response_model=list[SpeechResponse])
async def list_speeches(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    rows = (await db.execute(
        select(congress_speech, congress_legislator)
        .outerjoin(congress_legislator,
                   congress_legislator.c.id == congress_speech.c.legislator_id)
        .where(congress_speech.c.session_id == session_id)
        .order_by(congress_speech.c.session_speech_number)
    )).fetchall()

    return [
        _build_speech_response(r, r.display_name or "", r.institution_code or "")
        for r in rows
    ]


@router.get("/speech/{speech_id}/questions/", response_model=QuestionPeriodResponse | None)
async def get_speech_questions(
    speech_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_congress_api_key),
):
    qp = (await db.execute(
        select(congress_question_period)
        .where(congress_question_period.c.speech_id == speech_id)
        .order_by(congress_question_period.c.id.desc())
    )).fetchone()
    if not qp:
        return None

    questioners = (await db.execute(
        select(congress_questioner, congress_legislator.c.display_name)
        .outerjoin(congress_legislator,
                   congress_legislator.c.id == congress_questioner.c.legislator_id)
        .where(congress_questioner.c.question_period_id == qp.id)
        .order_by(congress_questioner.c.segment_number)
    )).fetchall()

    return QuestionPeriodResponse(
        id=qp.id,
        speech_id=qp.speech_id,
        total_time_seconds=qp.total_time_seconds,
        started_at=qp.started_at,
        ended_at=qp.ended_at,
        questioners=[
            QuestionerResponse(
                id=q.id,
                legislator_id=q.legislator_id,
                legislator_name=q.display_name or "",
                segment_number=q.segment_number,
                started_at=q.started_at,
                ended_at=q.ended_at,
            )
            for q in questioners
        ],
    )
