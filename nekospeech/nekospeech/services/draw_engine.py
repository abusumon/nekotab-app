"""Room assignment algorithm for Individual Speech Events.

Uses a greedy bin-packing approach with institution-conflict penalties
and optional round-history re-pairing avoidance.

Time complexity analysis
========================
Let N = number of entries, K = room_size, R = number of rooms = ceil(N/K).

assign_rooms():
  - Sort entries by institution frequency:   O(N log N)
  - For each entry, score against R rooms:   O(N * R)
  - R = N/K, so total:                       O(N^2 / K)
  - For typical IE tournaments (N=300, K=6): O(15 000) — well under 50ms.

This greedy approach is chosen over a full constraint solver because IE
tournaments rarely exceed 500 entries, and the greedy heuristic produces
good-enough assignments (minimal institution conflicts) in sub-linear
wall-clock time. A CSP solver would guarantee optimality but at O(N^3)
or worse, which is unnecessary for this use case.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class EntryForDraw:
    """Minimal entry representation used by the draw engine."""
    entry_id: int
    institution_id: int | None
    prior_room_peers: set[int] = field(default_factory=set)


def assign_rooms(
    entries: list[EntryForDraw],
    room_size: int = 6,
    history_penalty: float = 1.0,
) -> list[list[int]]:
    """Assign entries to rooms, minimising institution conflicts.

    Args:
        entries: Active entries with institution info and optional history.
        room_size: Target entries per room (will create smaller last room).
        history_penalty: Weight for penalising re-pairing from prior rounds.
                         Set to 0.0 to disable history avoidance.

    Returns:
        List of rooms, each room being a list of entry_ids.
        Room order is deterministic for idempotency checks.

    Algorithm — greedy bin-packing with penalty scoring:
      1. Sort entries by descending institution frequency (most-constrained first).
      2. For each entry, pick the room with lowest conflict score.
      3. Conflict score = (same-institution count in room) * 10
                        + (re-paired peer count) * history_penalty
      4. Always prefer rooms with fewer entries to balance sizes.

    O(N^2 / K) time, O(N) space.
    """
    if not entries:
        return []

    num_rooms = max(1, -(-len(entries) // room_size))  # ceil division

    # Sort by institution frequency descending — place most constrained first.
    inst_freq: Counter[int | None] = Counter(e.institution_id for e in entries)
    sorted_entries = sorted(
        entries,
        key=lambda e: (-inst_freq.get(e.institution_id, 0), e.entry_id),
    )

    # Room state
    rooms: list[list[EntryForDraw]] = [[] for _ in range(num_rooms)]
    room_inst_counts: list[dict[int | None, int]] = [defaultdict(int) for _ in range(num_rooms)]
    room_entry_sets: list[set[int]] = [set() for _ in range(num_rooms)]

    for entry in sorted_entries:
        best_room = _pick_best_room(
            entry, rooms, room_inst_counts, room_entry_sets,
            room_size, history_penalty,
        )
        rooms[best_room].append(entry)
        room_inst_counts[best_room][entry.institution_id] += 1
        room_entry_sets[best_room].add(entry.entry_id)

    return [[e.entry_id for e in room] for room in rooms]


def _pick_best_room(
    entry: EntryForDraw,
    rooms: list[list[EntryForDraw]],
    room_inst_counts: list[dict[int | None, int]],
    room_entry_sets: list[set[int]],
    room_size: int,
    history_penalty: float,
) -> int:
    """Return the index of the best room for this entry.

    Scoring (lower is better):
      - 10 points per same-institution entry already in room
      - history_penalty points per prior-round peer already in room
      - 0.1 points per entry already in room (prefer balanced sizes)
      - 1000 points if room is already full (hard cap)
    """
    best_idx = 0
    best_score = float("inf")

    for i, room in enumerate(rooms):
        if len(room) >= room_size:
            score = 1000.0  # effectively full
        else:
            inst_conflict = room_inst_counts[i].get(entry.institution_id, 0) if entry.institution_id else 0
            history_conflict = len(entry.prior_room_peers & room_entry_sets[i]) if history_penalty else 0
            score = inst_conflict * 10.0 + history_conflict * history_penalty + len(room) * 0.1

        if score < best_score:
            best_score = score
            best_idx = i

    return best_idx
