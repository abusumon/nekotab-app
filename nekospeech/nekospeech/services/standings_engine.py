"""Truncated rank standings calculator for Individual Speech Events.

Computes standings using a single SQL query with window functions,
avoiding N+1 queries entirely.

Time complexity analysis
========================
The standings computation is dominated by the SQL query, which runs
in the Postgres query planner at approximately:
  O(R * log R) where R = total number of IEResult rows for the event.

For 300 entries across 3 rounds with 6 entries/room:
  R ≈ 300 * 3 = 900 result rows
  The query aggregates, sorts, and windows over 900 rows — trivially
  under the 100ms target even on modest hardware.

The Python post-processing is O(N) where N = number of entries,
assembling the final StandingsRow objects from the query result.

The truncated rank approach is standard for IE tournaments:
  - If 3+ results: drop highest and lowest rank, sum the rest
  - If <3 results:  sum all ranks (no truncation)
  - Tiebreak: (1) lowest truncated sum, (2) highest total SP,
              (3) lowest single-round rank
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nekospeech.schemas.standings import StandingsResponse, StandingsRow

# Single SQL query that computes truncated rank standings.
# Uses CTEs + window functions so everything runs in one Postgres round-trip.
STANDINGS_SQL = text("""
WITH entry_results AS (
    -- Gather all confirmed results for this event up to the given round
    SELECT
        e.id            AS entry_id,
        e.speaker_id,
        e.institution_id,
        r.rank,
        r.speaker_points,
        rm.round_number,
        COUNT(*) OVER (PARTITION BY e.id) AS total_rounds
    FROM speech_events.ie_entry e
    JOIN speech_events.ie_room_entry re ON re.entry_id = e.id
    JOIN speech_events.ie_room rm ON rm.id = re.room_id
    JOIN speech_events.ie_result r ON r.room_id = rm.id AND r.entry_id = e.id
    WHERE e.event_id = :event_id
      AND rm.round_number <= :round_number
      AND rm.confirmed = TRUE
      AND e.scratch_status = 'ACTIVE'
),
truncated AS (
    -- Compute truncated rank sum: drop min and max rank if 3+ results
    SELECT
        entry_id,
        speaker_id,
        institution_id,
        total_rounds,
        -- Full rank sum
        SUM(rank) AS full_rank_sum,
        -- Truncated: subtract best and worst if 3+ rounds
        CASE
            WHEN total_rounds >= 3
            THEN SUM(rank) - MIN(rank) - MAX(rank)
            ELSE SUM(rank)
        END AS truncated_rank_sum,
        SUM(speaker_points) AS total_speaker_points,
        MIN(rank) AS lowest_single_rank
    FROM entry_results
    GROUP BY entry_id, speaker_id, institution_id, total_rounds
)
SELECT
    t.entry_id,
    t.speaker_id,
    t.institution_id,
    t.truncated_rank_sum,
    t.total_speaker_points,
    t.lowest_single_rank,
    t.total_rounds AS rounds_competed,
    pp.name AS speaker_name,
    pi.name AS institution_name,
    COALESCE(pi.code, '') AS institution_code,
    ROW_NUMBER() OVER (
        ORDER BY
            t.truncated_rank_sum ASC,
            t.total_speaker_points DESC,
            t.lowest_single_rank ASC,
            t.entry_id ASC
    ) AS rank
FROM truncated t
LEFT JOIN public.participants_person pp ON pp.id = t.speaker_id
LEFT JOIN public.participants_institution pi ON pi.id = t.institution_id
ORDER BY rank
""")


async def compute_standings(
    session: AsyncSession,
    event_id: int,
    round_number: int,
) -> StandingsResponse:
    """Compute truncated-rank standings for an event through a given round.

    Executes a single SQL query with CTEs and window functions.
    Returns a fully-formed StandingsResponse ready for caching/return.
    """
    result = await session.execute(
        STANDINGS_SQL,
        {"event_id": event_id, "round_number": round_number},
    )
    rows = result.fetchall()

    entries = [
        StandingsRow(
            rank=row.rank,
            entry_id=row.entry_id,
            speaker_id=row.speaker_id,
            speaker_name=row.speaker_name or "",
            institution_name=row.institution_name or "",
            institution_code=row.institution_code or "",
            truncated_rank_sum=float(row.truncated_rank_sum),
            total_speaker_points=float(row.total_speaker_points),
            lowest_single_rank=row.lowest_single_rank,
            rounds_competed=row.rounds_competed,
        )
        for row in rows
    ]

    return StandingsResponse(
        event_id=event_id,
        rounds_complete=round_number,
        entries=entries,
    )
