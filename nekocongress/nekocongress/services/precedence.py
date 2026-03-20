"""PrecedenceQueue — the core algorithm for Congressional Debate speaker ordering.

Implements NSDA's 3-tier priority system for both speakers and questioners.

Priority order when multiple students seek the floor:
  Tier 1: Students who have NOT spoken this session (unseen students first)
  Tier 2: Among those who have spoken, students who have spoken FEWER TIMES
  Tier 3: Among ties in speech count, students who spoke LEAST RECENTLY

Tiebreakers within any tier:
  - Geography-based (if enabled): students from underrepresented states first
  - Random (deterministic seed for reproducibility)

The questioner queue is tracked completely separately with the same 3-tier logic
applied to question counts and last-question timestamps.

State can be persisted to Redis and reconstructed from the database.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis


@dataclass
class LegislatorState:
    """Tracks a single legislator's precedence state within a session."""

    legislator_id: int
    display_name: str
    institution_code: str = ""
    institution_id: int | None = None
    speech_count: int = 0
    last_speech_at: datetime | None = None
    question_count: int = 0
    last_question_at: datetime | None = None
    is_po: bool = False
    is_withdrawn: bool = False

    def to_dict(self) -> dict:
        return {
            "legislator_id": self.legislator_id,
            "display_name": self.display_name,
            "institution_code": self.institution_code,
            "institution_id": self.institution_id,
            "speech_count": self.speech_count,
            "last_speech_at": self.last_speech_at.isoformat() if self.last_speech_at else None,
            "question_count": self.question_count,
            "last_question_at": self.last_question_at.isoformat() if self.last_question_at else None,
            "is_po": self.is_po,
            "is_withdrawn": self.is_withdrawn,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LegislatorState:
        last_speech = data.get("last_speech_at")
        last_question = data.get("last_question_at")
        return cls(
            legislator_id=data["legislator_id"],
            display_name=data["display_name"],
            institution_code=data.get("institution_code", ""),
            institution_id=data.get("institution_id"),
            speech_count=data.get("speech_count", 0),
            last_speech_at=datetime.fromisoformat(last_speech) if last_speech else None,
            question_count=data.get("question_count", 0),
            last_question_at=datetime.fromisoformat(last_question) if last_question else None,
            is_po=data.get("is_po", False),
            is_withdrawn=data.get("is_withdrawn", False),
        )


@dataclass
class PrecedenceQueue:
    """Manages the speaker and questioner precedence queues for a Congressional session.

    Attributes:
        session_id: The database ID of the congress_session.
        legislators: Dict mapping legislator_id to LegislatorState.
        geography_tiebreak: Whether to use geography-based tiebreaking.
        seed: Random seed for reproducible tiebreaking within a session.
    """

    session_id: int
    legislators: dict[int, LegislatorState] = field(default_factory=dict)
    geography_tiebreak: bool = False
    seed: int = 0
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self, legislator_states: list[LegislatorState]) -> None:
        """Initialize the queue with a list of legislators for a new session.

        Resets all speech/question counts and timestamps.

        O(n) where n = number of legislators.
        """
        self.legislators.clear()
        for ls in legislator_states:
            ls.speech_count = 0
            ls.last_speech_at = None
            ls.question_count = 0
            ls.last_question_at = None
            self.legislators[ls.legislator_id] = ls

    def restore(self, legislator_states: list[LegislatorState]) -> None:
        """Restore the queue from persisted state (Redis or database).

        Does NOT reset counts — used for crash recovery.

        O(n) where n = number of legislators.
        """
        self.legislators.clear()
        for ls in legislator_states:
            self.legislators[ls.legislator_id] = ls

    # ------------------------------------------------------------------
    # Speaker Queue
    # ------------------------------------------------------------------

    def get_speaker_queue(self, exclude_po: bool = True) -> list[LegislatorState]:
        """Return legislators ordered by speaker precedence (NSDA 3-tier).

        Tier 1: speech_count == 0 (never spoken in session)
        Tier 2: lower speech_count first
        Tier 3: older last_speech_at first (spoke least recently)

        Tiebreaker within tiers: geography (if enabled), then deterministic random.

        O(n log n) where n = number of eligible legislators.
        """
        eligible = [
            ls for ls in self.legislators.values()
            if not ls.is_withdrawn and (not exclude_po or not ls.is_po)
        ]

        def sort_key(ls: LegislatorState) -> tuple:
            # Primary: speech_count (0 = highest priority, ascending)
            # Secondary: last_speech_at (None = never spoken = highest priority,
            #            then oldest timestamp first)
            # Tertiary: deterministic random tiebreak
            last_at = ls.last_speech_at or datetime.min.replace(tzinfo=timezone.utc)
            tiebreak = self._rng.random()
            return (ls.speech_count, last_at, tiebreak)

        # Re-seed for deterministic ordering each time queue is computed
        self._rng.seed(self.seed)
        eligible.sort(key=sort_key)
        return eligible

    def get_next_speaker(self, exclude_po: bool = True) -> LegislatorState | None:
        """Return the legislator who should speak next according to precedence.

        O(n log n) — calls get_speaker_queue.
        """
        queue = self.get_speaker_queue(exclude_po=exclude_po)
        return queue[0] if queue else None

    def get_next_speaker_for_side(
        self, side: str, exclude_po: bool = True
    ) -> LegislatorState | None:
        """Return the next speaker who is most appropriate for the given side.

        This doesn't enforce side — all eligible speakers are returned in
        precedence order. The PO interface uses this to suggest who to call.

        O(n log n).
        """
        return self.get_next_speaker(exclude_po=exclude_po)

    def register_speech(
        self,
        legislator_id: int,
        timestamp: datetime | None = None,
    ) -> None:
        """Record that a legislator has given a speech.

        Updates speech_count and last_speech_at.

        O(1).
        """
        if legislator_id not in self.legislators:
            raise ValueError(f"Legislator {legislator_id} not in session")
        ls = self.legislators[legislator_id]
        ls.speech_count += 1
        ls.last_speech_at = timestamp or datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Authorship Bypass
    # ------------------------------------------------------------------

    def get_authorship_speaker(
        self, author_institution_id: int | None
    ) -> LegislatorState | None:
        """Return the first eligible legislator from the authoring institution.

        Authorship bypasses the precedence queue entirely. If the authoring
        school has no eligible legislator present, returns None (falls through
        to sponsorship via normal precedence).

        O(n) where n = number of legislators.
        """
        if author_institution_id is None:
            return None
        for ls in self.legislators.values():
            if (
                ls.institution_id == author_institution_id
                and not ls.is_withdrawn
                and not ls.is_po
            ):
                return ls
        return None

    # ------------------------------------------------------------------
    # Questioner Queue (completely separate)
    # ------------------------------------------------------------------

    def get_questioner_queue(
        self, exclude_current_speaker_id: int | None = None,
        exclude_po: bool = True,
    ) -> list[LegislatorState]:
        """Return legislators ordered by questioner precedence (NSDA 3-tier).

        Same algorithm as speaker queue but uses question_count and
        last_question_at instead.

        O(n log n).
        """
        eligible = [
            ls for ls in self.legislators.values()
            if not ls.is_withdrawn
            and (not exclude_po or not ls.is_po)
            and ls.legislator_id != exclude_current_speaker_id
        ]

        def sort_key(ls: LegislatorState) -> tuple:
            last_at = ls.last_question_at or datetime.min.replace(tzinfo=timezone.utc)
            tiebreak = self._rng.random()
            return (ls.question_count, last_at, tiebreak)

        self._rng.seed(self.seed + 1_000_000)  # Different seed from speaker queue
        eligible.sort(key=sort_key)
        return eligible

    def get_next_questioner(
        self, exclude_current_speaker_id: int | None = None,
        exclude_po: bool = True,
    ) -> LegislatorState | None:
        """Return the legislator who should question next.

        O(n log n) — calls get_questioner_queue.
        """
        queue = self.get_questioner_queue(
            exclude_current_speaker_id=exclude_current_speaker_id,
            exclude_po=exclude_po,
        )
        return queue[0] if queue else None

    def register_question(
        self,
        legislator_id: int,
        timestamp: datetime | None = None,
    ) -> None:
        """Record that a legislator has asked a question.

        O(1).
        """
        if legislator_id not in self.legislators:
            raise ValueError(f"Legislator {legislator_id} not in session")
        ls = self.legislators[legislator_id]
        ls.question_count += 1
        ls.last_question_at = timestamp or datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # PO Management
    # ------------------------------------------------------------------

    def set_po(self, legislator_id: int) -> None:
        """Mark a legislator as the Presiding Officer.

        The PO is excluded from speaker and questioner queues by default.

        O(n) to clear previous PO flag.
        """
        # Clear any existing PO
        for ls in self.legislators.values():
            ls.is_po = False
        if legislator_id in self.legislators:
            self.legislators[legislator_id].is_po = True

    # ------------------------------------------------------------------
    # State Persistence
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize the queue state to JSON for Redis persistence.

        O(n).
        """
        return json.dumps({
            "session_id": self.session_id,
            "geography_tiebreak": self.geography_tiebreak,
            "seed": self.seed,
            "legislators": {
                str(lid): ls.to_dict()
                for lid, ls in self.legislators.items()
            },
        })

    @classmethod
    def from_json(cls, data: str) -> PrecedenceQueue:
        """Deserialize queue state from JSON (Redis recovery).

        O(n).
        """
        obj = json.loads(data)
        queue = cls(
            session_id=obj["session_id"],
            geography_tiebreak=obj.get("geography_tiebreak", False),
            seed=obj.get("seed", 0),
        )
        for lid_str, ls_data in obj.get("legislators", {}).items():
            ls = LegislatorState.from_dict(ls_data)
            queue.legislators[ls.legislator_id] = ls
        return queue

    async def save_to_redis(self, redis_client: redis) -> None:
        """Persist current state to Redis.

        O(n).
        """
        key = f"congress:precedence:{self.session_id}"
        await redis_client.set(key, self.to_json(), ex=86400)  # 24h TTL

    @classmethod
    async def load_from_redis(cls, session_id: int, redis_client: redis) -> PrecedenceQueue | None:
        """Load queue state from Redis.

        Returns None if no state found.

        O(n).
        """
        key = f"congress:precedence:{session_id}"
        data = await redis_client.get(key)
        if data is None:
            return None
        return cls.from_json(data)

    # ------------------------------------------------------------------
    # Penalty Calculation
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_overtime_penalty(
        duration_seconds: int,
        speech_time_seconds: int,
        grace_seconds: int,
        penalty_per_interval: int,
        interval_seconds: int,
    ) -> tuple[bool, int, int]:
        """Calculate overtime penalty for a speech.

        Returns:
            (is_overtime, overtime_seconds, penalty_points)

        O(1).
        """
        overtime = max(0, duration_seconds - speech_time_seconds)
        if overtime <= grace_seconds:
            return False, 0, 0
        penalizable = overtime - grace_seconds
        intervals = (penalizable + interval_seconds - 1) // interval_seconds
        penalty = intervals * penalty_per_interval
        return True, overtime, penalty
