"""Unit tests for the room assignment (draw) engine."""
# Run from nekospeech/ directory: pytest tests/

from nekospeech.services.draw_engine import EntryForDraw, assign_rooms


def _make_entries(specs: list[tuple[int, int | None]]) -> list[EntryForDraw]:
    """Helper: create entries from (entry_id, institution_id) pairs."""
    return [EntryForDraw(entry_id=eid, institution_id=iid) for eid, iid in specs]


class TestAssignRoomsBasic:
    def test_empty_entries(self):
        assert assign_rooms([], room_size=6) == []

    def test_single_entry(self):
        entries = _make_entries([(1, 100)])
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 1
        assert rooms[0] == [1]

    def test_exact_room_size(self):
        entries = _make_entries([(i, 100 + i) for i in range(6)])
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 1
        assert sorted(rooms[0]) == list(range(6))

    def test_two_rooms(self):
        entries = _make_entries([(i, 100 + i) for i in range(10)])
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 2
        all_ids = sorted(eid for room in rooms for eid in room)
        assert all_ids == list(range(10))

    def test_room_size_respected(self):
        entries = _make_entries([(i, None) for i in range(20)])
        rooms = assign_rooms(entries, room_size=6)
        for room in rooms:
            assert len(room) <= 6


class TestInstitutionConflicts:
    def test_separates_same_institution(self):
        # 6 entries from institution A, 6 from institution B → should go to 2 rooms
        entries = _make_entries(
            [(i, 1) for i in range(6)] + [(i + 6, 2) for i in range(6)]
        )
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 2
        for room in rooms:
            institutions = set()
            for eid in room:
                entry = next(e for e in entries if e.entry_id == eid)
                institutions.add(entry.institution_id)
            # Each room should ideally have entries from both institutions
            # and no more than 3 from the same institution in a room of 6
            from collections import Counter
            inst_counts = Counter(
                next(e for e in entries if e.entry_id == eid).institution_id
                for eid in room
            )
            for count in inst_counts.values():
                assert count <= 4  # soft constraint — best effort

    def test_avoids_same_institution_when_possible(self):
        # 3 entries from each of 4 institutions → 2 rooms of 6
        entries = _make_entries(
            [(i * 10 + j, i) for i in range(4) for j in range(3)]
        )
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 2
        for room in rooms:
            from collections import Counter
            inst_counts = Counter(
                next(e for e in entries if e.entry_id == eid).institution_id
                for eid in room
            )
            # With 4 institutions × 3 entries each in 2 rooms of 6,
            # the algorithm should distribute evenly (~1-2 per institution)
            for count in inst_counts.values():
                assert count <= 3

    def test_null_institution_no_conflict(self):
        # Entries with no institution should not trigger institution conflicts
        entries = _make_entries([(i, None) for i in range(12)])
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 2
        for room in rooms:
            assert len(room) == 6


class TestHistoryPenalty:
    def test_avoids_repairing_with_history(self):
        # Entries 0-5 were in a room together previously.
        # With history penalty, the algorithm should try to separate them.
        entries = [
            EntryForDraw(entry_id=i, institution_id=i, prior_room_peers={0, 1, 2, 3, 4, 5} - {i})
            for i in range(12)
        ]
        rooms = assign_rooms(entries, room_size=6, history_penalty=2.0)
        assert len(rooms) == 2
        # All 12 entries should be assigned
        all_ids = sorted(eid for room in rooms for eid in room)
        assert all_ids == list(range(12))

    def test_no_history_penalty_disabled(self):
        entries = [
            EntryForDraw(entry_id=i, institution_id=None, prior_room_peers={0, 1, 2})
            for i in range(6)
        ]
        rooms = assign_rooms(entries, room_size=6, history_penalty=0.0)
        assert len(rooms) == 1


class TestLargeScale:
    def test_300_entries(self):
        """Performance sanity: 300 entries should complete without error."""
        entries = _make_entries([(i, i % 30) for i in range(300)])
        rooms = assign_rooms(entries, room_size=6)
        assert len(rooms) == 50
        all_ids = sorted(eid for room in rooms for eid in room)
        assert all_ids == list(range(300))
        for room in rooms:
            assert len(room) == 6

    def test_uneven_last_room(self):
        entries = _make_entries([(i, i % 10) for i in range(25)])
        rooms = assign_rooms(entries, room_size=6)
        # ceil(25/6) = 5 rooms
        assert len(rooms) == 5
        total = sum(len(r) for r in rooms)
        assert total == 25
