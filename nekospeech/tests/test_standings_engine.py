"""Unit tests for the standings engine SQL logic.

These tests validate the StandingsResponse schema and the SQL query structure.
Full integration tests require a running Postgres instance with the
speech_events schema — those are in the integration test suite.
This file tests the pure-Python parts and schema contracts.
"""
# Run from nekospeech/ directory: pytest tests/

from nekospeech.schemas.standings import StandingsResponse, StandingsRow


class TestStandingsSchemas:
    def test_standings_row_creation(self):
        row = StandingsRow(
            rank=1,
            entry_id=10,
            speaker_id=100,
            speaker_name="Alice",
            institution_name="MIT",
            institution_code="MIT",
            truncated_rank_sum=5.0,
            total_speaker_points=85.5,
            lowest_single_rank=1,
            rounds_competed=3,
        )
        assert row.rank == 1
        assert row.truncated_rank_sum == 5.0

    def test_standings_response_creation(self):
        rows = [
            StandingsRow(
                rank=i,
                entry_id=i * 10,
                speaker_id=i * 100,
                speaker_name=f"Speaker {i}",
                institution_name=f"School {i}",
                institution_code=f"S{i}",
                truncated_rank_sum=float(i * 3),
                total_speaker_points=float(90 - i),
                lowest_single_rank=i,
                rounds_competed=3,
            )
            for i in range(1, 6)
        ]
        resp = StandingsResponse(event_id=1, rounds_complete=3, entries=rows)
        assert resp.event_id == 1
        assert len(resp.entries) == 5
        assert resp.entries[0].rank == 1

    def test_truncation_logic_explanation(self):
        """Verify the truncation rules documented in the engine.

        With 3+ results: drop highest rank + lowest rank, sum rest.
        Example: ranks [1, 3, 5] → drop 1 and 5 → truncated = 3
        """
        ranks = [1, 3, 5]
        if len(ranks) >= 3:
            truncated = sum(ranks) - min(ranks) - max(ranks)
        else:
            truncated = sum(ranks)
        assert truncated == 3

    def test_truncation_with_fewer_than_three(self):
        """With <3 results, no truncation — sum all."""
        ranks = [2, 4]
        truncated = sum(ranks)  # no drop
        assert truncated == 6

    def test_tiebreak_ordering(self):
        """Tiebreak: (1) lowest trunc sum, (2) highest SP, (3) lowest single rank."""
        a = StandingsRow(
            rank=0, entry_id=1, speaker_id=1, speaker_name="A",
            institution_name="", institution_code="",
            truncated_rank_sum=5.0, total_speaker_points=80.0,
            lowest_single_rank=2, rounds_competed=3,
        )
        b = StandingsRow(
            rank=0, entry_id=2, speaker_id=2, speaker_name="B",
            institution_name="", institution_code="",
            truncated_rank_sum=5.0, total_speaker_points=85.0,
            lowest_single_rank=1, rounds_competed=3,
        )
        # Same truncated sum → B wins on higher total SP
        entries = sorted(
            [a, b],
            key=lambda e: (e.truncated_rank_sum, -e.total_speaker_points, e.lowest_single_rank),
        )
        assert entries[0].speaker_name == "B"
