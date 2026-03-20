"""Instant-runoff voting (IRV) engine for Presiding Officer elections.

Congressional Debate PO elections use majority vote with elimination:
1. All legislators vote for one candidate
2. If a candidate has a majority (>50%), they win
3. If no majority, the candidate with the fewest votes is eliminated
4. A new vote is held without the eliminated candidate
5. Repeat until a majority is achieved

This engine handles a single round of voting at a time, since each round
requires new ballots from voters.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class ElectionResult:
    """Result of processing one round of a PO election."""

    round_number: int
    vote_counts: dict[int, int]  # candidate_id → vote count
    total_votes: int
    majority_needed: int
    winner_id: int | None = None
    eliminated_id: int | None = None
    is_decided: bool = False

    @property
    def winner_votes(self) -> int:
        if self.winner_id is None:
            return 0
        return self.vote_counts.get(self.winner_id, 0)


def tally_round(
    ballots: list[tuple[int, int]],
    eliminated_candidates: set[int] | None = None,
    round_number: int = 1,
) -> ElectionResult:
    """Process one round of a PO election.

    Args:
        ballots: List of (voter_id, candidate_id) tuples.
        eliminated_candidates: Set of candidate IDs already eliminated.
        round_number: Current round number.

    Returns:
        ElectionResult with either a winner or a candidate to eliminate.

    O(n) where n = number of ballots.
    """
    eliminated = eliminated_candidates or set()

    # Filter out votes for eliminated candidates
    valid_ballots = [
        (voter, candidate)
        for voter, candidate in ballots
        if candidate not in eliminated
    ]

    if not valid_ballots:
        return ElectionResult(
            round_number=round_number,
            vote_counts={},
            total_votes=0,
            majority_needed=0,
            is_decided=False,
        )

    # Count votes
    counts: Counter[int] = Counter()
    for _, candidate in valid_ballots:
        counts[candidate] += 1

    total = len(valid_ballots)
    majority = total // 2 + 1

    # Check for majority winner
    for candidate_id, vote_count in counts.most_common():
        if vote_count >= majority:
            return ElectionResult(
                round_number=round_number,
                vote_counts=dict(counts),
                total_votes=total,
                majority_needed=majority,
                winner_id=candidate_id,
                is_decided=True,
            )

    # No majority: find candidate with fewest votes to eliminate
    # In case of tie for fewest, eliminate the one with the lowest ID (deterministic)
    min_votes = min(counts.values())
    candidates_with_min = sorted(
        [cid for cid, cnt in counts.items() if cnt == min_votes]
    )
    eliminated_candidate = candidates_with_min[0]

    return ElectionResult(
        round_number=round_number,
        vote_counts=dict(counts),
        total_votes=total,
        majority_needed=majority,
        eliminated_id=eliminated_candidate,
        is_decided=False,
    )


def run_full_election(
    rounds_ballots: list[list[tuple[int, int]]],
) -> list[ElectionResult]:
    """Run a complete multi-round PO election.

    Each element of rounds_ballots is the full set of ballots for that round.
    In practice, after an elimination, the chamber re-votes, so each round
    has fresh ballots.

    Args:
        rounds_ballots: List of ballot lists, one per round.

    Returns:
        List of ElectionResults, one per round processed.

    O(r * n) where r = number of rounds, n = ballots per round.
    """
    results: list[ElectionResult] = []
    eliminated: set[int] = set()

    for round_num, ballots in enumerate(rounds_ballots, start=1):
        result = tally_round(ballots, eliminated, round_number=round_num)
        results.append(result)

        if result.is_decided:
            break

        if result.eliminated_id is not None:
            eliminated.add(result.eliminated_id)

    return results
