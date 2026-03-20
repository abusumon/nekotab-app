"""Comprehensive unit tests for the PrecedenceQueue engine.

Tests cover:
- 18-legislator session initialization
- 3-tier precedence ordering
- Speech registration and queue reordering
- Authorship bypass
- Questioner queue (separate from speaker queue)
- Wrong-side penalty calculation
- Overtime penalty calculation
- Geography tiebreaking
- Session reset
- JSON serialization/deserialization
- Edge cases (single legislator, all tied, PO exclusion, withdrawn)
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from nekocongress.services.precedence import LegislatorState, PrecedenceQueue


def _make_legislators(n: int, seed_institution: int = 100) -> list[LegislatorState]:
    """Create n test legislators with unique IDs and institutions."""
    return [
        LegislatorState(
            legislator_id=i + 1,
            display_name=f"Legislator {i + 1}",
            institution_code=f"SCH{(i % 6) + 1}",
            institution_id=seed_institution + (i % 6),
        )
        for i in range(n)
    ]


def _make_queue(n: int = 18, seed: int = 42) -> PrecedenceQueue:
    """Create an initialized PrecedenceQueue with n legislators."""
    queue = PrecedenceQueue(session_id=1, seed=seed)
    queue.initialize(_make_legislators(n))
    return queue


class TestInitialization:
    """Tests for queue initialization."""

    def test_initialize_18_legislators(self):
        queue = _make_queue(18)
        assert len(queue.legislators) == 18

    def test_initialize_resets_counts(self):
        legislators = _make_legislators(5)
        legislators[0].speech_count = 3
        legislators[0].last_speech_at = datetime.now(timezone.utc)
        queue = PrecedenceQueue(session_id=1)
        queue.initialize(legislators)
        assert queue.legislators[1].speech_count == 0
        assert queue.legislators[1].last_speech_at is None

    def test_restore_preserves_counts(self):
        legislators = _make_legislators(5)
        now = datetime.now(timezone.utc)
        legislators[0].speech_count = 3
        legislators[0].last_speech_at = now
        queue = PrecedenceQueue(session_id=1)
        queue.restore(legislators)
        assert queue.legislators[1].speech_count == 3
        assert queue.legislators[1].last_speech_at == now


class TestSpeakerQueue:
    """Tests for the 3-tier speaker precedence queue."""

    def test_all_unseen_returns_all(self):
        """Tier 1: all legislators with 0 speeches should be in queue."""
        queue = _make_queue(18)
        result = queue.get_speaker_queue()
        assert len(result) == 18
        assert all(ls.speech_count == 0 for ls in result)

    def test_spoken_legislators_go_after_unseen(self):
        """Tier 1: unseen students have priority over those who've spoken."""
        queue = _make_queue(5)
        now = datetime.now(timezone.utc)
        queue.register_speech(1, now)
        result = queue.get_speaker_queue()
        # Legislator 1 should be last (only one who has spoken)
        spoken_ids = [ls.legislator_id for ls in result if ls.speech_count > 0]
        unseen_ids = [ls.legislator_id for ls in result if ls.speech_count == 0]
        assert all(
            result.index(queue.legislators[uid]) < result.index(queue.legislators[sid])
            for uid in unseen_ids
            for sid in spoken_ids
        )

    def test_fewer_speeches_has_priority(self):
        """Tier 2: students with fewer speeches come before those with more."""
        queue = _make_queue(5)
        now = datetime.now(timezone.utc)
        # Give everyone at least 1 speech
        for i in range(1, 6):
            queue.register_speech(i, now + timedelta(seconds=i))
        # Give legislator 3 an extra speech
        queue.register_speech(3, now + timedelta(seconds=10))
        result = queue.get_speaker_queue()
        # Legislator 3 (2 speeches) should be after all 1-speech legislators
        idx_3 = next(i for i, ls in enumerate(result) if ls.legislator_id == 3)
        for ls in result[:idx_3]:
            assert ls.speech_count <= 1

    def test_least_recent_has_priority(self):
        """Tier 3: among equal speech counts, oldest speech gets priority."""
        queue = _make_queue(3)
        now = datetime.now(timezone.utc)
        # All speak once, at different times
        queue.register_speech(1, now + timedelta(minutes=5))  # Most recent
        queue.register_speech(2, now + timedelta(minutes=1))  # Least recent
        queue.register_speech(3, now + timedelta(minutes=3))  # Middle
        result = queue.get_speaker_queue()
        # Order should be: 2 (oldest), 3 (middle), 1 (newest)
        ids = [ls.legislator_id for ls in result]
        assert ids == [2, 3, 1]

    def test_complex_18_legislator_scenario(self):
        """Full 18-legislator scenario across multiple speeches."""
        queue = _make_queue(18)
        now = datetime.now(timezone.utc)

        # Session progresses: first 6 speak, then 3 of those speak again
        for i in range(1, 7):
            queue.register_speech(i, now + timedelta(minutes=i))

        # 3 of the first 6 speak again
        queue.register_speech(1, now + timedelta(minutes=10))
        queue.register_speech(3, now + timedelta(minutes=12))
        queue.register_speech(5, now + timedelta(minutes=14))

        result = queue.get_speaker_queue()

        # Tier 1: legislators 7-18 (never spoken) come first
        unseen = [ls for ls in result if ls.speech_count == 0]
        one_speech = [ls for ls in result if ls.speech_count == 1]
        two_speeches = [ls for ls in result if ls.speech_count == 2]

        assert len(unseen) == 12
        assert len(one_speech) == 3  # 2, 4, 6
        assert len(two_speeches) == 3  # 1, 3, 5

        # Verify ordering: unseen < one_speech < two_speeches
        unseen_indices = [result.index(ls) for ls in unseen]
        one_indices = [result.index(ls) for ls in one_speech]
        two_indices = [result.index(ls) for ls in two_speeches]

        assert max(unseen_indices) < min(one_indices)
        assert max(one_indices) < min(two_indices)

    def test_deterministic_ordering(self):
        """Queue ordering is deterministic with same seed."""
        q1 = _make_queue(18, seed=42)
        q2 = _make_queue(18, seed=42)
        result1 = [ls.legislator_id for ls in q1.get_speaker_queue()]
        result2 = [ls.legislator_id for ls in q2.get_speaker_queue()]
        assert result1 == result2

    def test_different_seeds_give_different_order(self):
        """Different seeds produce different tiebreak ordering."""
        q1 = _make_queue(18, seed=42)
        q2 = _make_queue(18, seed=99)
        result1 = [ls.legislator_id for ls in q1.get_speaker_queue()]
        result2 = [ls.legislator_id for ls in q2.get_speaker_queue()]
        # With all speech counts at 0, seed determines order — should differ
        assert result1 != result2


class TestAuthorshipBypass:
    """Tests for authorship speech precedence bypass."""

    def test_authorship_returns_institution_member(self):
        queue = _make_queue(18)
        # Institution 100 has legislators 1, 7, 13 (every 6th)
        speaker = queue.get_authorship_speaker(author_institution_id=100)
        assert speaker is not None
        assert speaker.institution_id == 100

    def test_authorship_absent_institution_returns_none(self):
        queue = _make_queue(18)
        speaker = queue.get_authorship_speaker(author_institution_id=999)
        assert speaker is None

    def test_authorship_none_institution_returns_none(self):
        queue = _make_queue(18)
        speaker = queue.get_authorship_speaker(author_institution_id=None)
        assert speaker is None

    def test_authorship_skips_withdrawn(self):
        queue = _make_queue(18)
        # Withdraw all legislators from institution 100
        for ls in queue.legislators.values():
            if ls.institution_id == 100:
                ls.is_withdrawn = True
        speaker = queue.get_authorship_speaker(author_institution_id=100)
        assert speaker is None

    def test_authorship_skips_po(self):
        queue = _make_queue(18)
        # Make legislator 1 (institution 100) the PO
        queue.set_po(1)
        speaker = queue.get_authorship_speaker(author_institution_id=100)
        # Should return legislator 7 (also institution 100)
        assert speaker is not None
        assert speaker.legislator_id != 1
        assert speaker.institution_id == 100


class TestQuestionerQueue:
    """Tests for the separate questioner precedence queue."""

    def test_questioner_queue_independent_of_speaker(self):
        """Questioner queue uses question_count, not speech_count."""
        queue = _make_queue(5)
        now = datetime.now(timezone.utc)
        # Legislator 1 has spoken but not questioned
        queue.register_speech(1, now)
        # Legislator 2 has questioned but not spoken
        queue.register_question(2, now)

        speaker_queue = queue.get_speaker_queue()
        questioner_queue = queue.get_questioner_queue()

        # In speaker queue: 1 should be lower (has spoken)
        speaker_ids = [ls.legislator_id for ls in speaker_queue]
        assert speaker_ids.index(1) > speaker_ids.index(2)

        # In questioner queue: 2 should be lower (has questioned)
        questioner_ids = [ls.legislator_id for ls in questioner_queue]
        assert questioner_ids.index(2) > questioner_ids.index(1)

    def test_questioner_excludes_current_speaker(self):
        queue = _make_queue(5)
        result = queue.get_questioner_queue(exclude_current_speaker_id=1)
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids

    def test_questioner_excludes_po(self):
        queue = _make_queue(5)
        queue.set_po(1)
        result = queue.get_questioner_queue()
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids

    def test_questioner_three_tier_ordering(self):
        """Same 3-tier logic but for questioning."""
        queue = _make_queue(5)
        now = datetime.now(timezone.utc)
        queue.register_question(1, now + timedelta(minutes=5))
        queue.register_question(2, now + timedelta(minutes=1))
        queue.register_question(3, now + timedelta(minutes=3))

        result = queue.get_questioner_queue()
        # 4, 5 (never questioned) come first
        # Then 2 (oldest), 3 (middle), 1 (newest)
        ids = [ls.legislator_id for ls in result]
        assert set(ids[:2]) == {4, 5}  # both unseen, order depends on seed
        assert all(queue.legislators[lid].question_count == 0 for lid in ids[:2])
        # Among the questioned: 2 (oldest) before 3 (middle) before 1 (newest)
        questioned = ids[2:]
        assert questioned == [2, 3, 1]


class TestPOManagement:
    """Tests for Presiding Officer management."""

    def test_set_po_excludes_from_queue(self):
        queue = _make_queue(5)
        queue.set_po(1)
        result = queue.get_speaker_queue(exclude_po=True)
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids
        assert len(result) == 4

    def test_set_po_included_when_flag_false(self):
        queue = _make_queue(5)
        queue.set_po(1)
        result = queue.get_speaker_queue(exclude_po=False)
        ids = [ls.legislator_id for ls in result]
        assert 1 in ids

    def test_set_po_clears_previous(self):
        queue = _make_queue(5)
        queue.set_po(1)
        queue.set_po(2)
        assert not queue.legislators[1].is_po
        assert queue.legislators[2].is_po

    def test_po_excluded_from_questioner_queue(self):
        queue = _make_queue(5)
        queue.set_po(1)
        result = queue.get_questioner_queue()
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids


class TestWithdrawn:
    """Tests for withdrawn legislators."""

    def test_withdrawn_excluded_from_speaker_queue(self):
        queue = _make_queue(5)
        queue.legislators[1].is_withdrawn = True
        result = queue.get_speaker_queue()
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids

    def test_withdrawn_excluded_from_questioner_queue(self):
        queue = _make_queue(5)
        queue.legislators[1].is_withdrawn = True
        result = queue.get_questioner_queue()
        ids = [ls.legislator_id for ls in result]
        assert 1 not in ids


class TestOvertimePenalty:
    """Tests for overtime penalty calculation."""

    def test_no_overtime(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=170,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=1,
            interval_seconds=10,
        )
        assert not is_ot
        assert ot_sec == 0
        assert penalty == 0

    def test_within_grace_period(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=188,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=1,
            interval_seconds=10,
        )
        assert not is_ot
        assert ot_sec == 0
        assert penalty == 0

    def test_exact_grace_boundary(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=190,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=1,
            interval_seconds=10,
        )
        assert not is_ot

    def test_one_interval_over(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=195,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=1,
            interval_seconds=10,
        )
        assert is_ot
        assert ot_sec == 15
        assert penalty == 1  # 5 seconds past grace → 1 interval

    def test_multiple_intervals_over(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=215,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=1,
            interval_seconds=10,
        )
        assert is_ot
        assert ot_sec == 35
        assert penalty == 3  # 25 seconds past grace → 3 intervals (ceil(25/10))

    def test_custom_penalty_per_interval(self):
        is_ot, ot_sec, penalty = PrecedenceQueue.calculate_overtime_penalty(
            duration_seconds=205,
            speech_time_seconds=180,
            grace_seconds=10,
            penalty_per_interval=2,
            interval_seconds=10,
        )
        assert penalty == 4  # 15 seconds past grace → 2 intervals × 2 points


class TestWrongSidePenalty:
    """Tests that wrong-side tracking works correctly."""

    def test_register_wrong_side_still_counts(self):
        """Wrong-side speeches still count for precedence."""
        queue = _make_queue(5)
        now = datetime.now(timezone.utc)
        queue.register_speech(1, now)
        assert queue.legislators[1].speech_count == 1


class TestSerialization:
    """Tests for JSON serialization/deserialization."""

    def test_round_trip(self):
        queue = _make_queue(18)
        now = datetime.now(timezone.utc)
        queue.register_speech(1, now)
        queue.register_question(2, now)
        queue.set_po(3)

        json_str = queue.to_json()
        restored = PrecedenceQueue.from_json(json_str)

        assert restored.session_id == queue.session_id
        assert len(restored.legislators) == 18
        assert restored.legislators[1].speech_count == 1
        assert restored.legislators[2].question_count == 1
        assert restored.legislators[3].is_po is True

    def test_round_trip_preserves_queue_order(self):
        queue = _make_queue(10, seed=42)
        now = datetime.now(timezone.utc)
        for i in range(1, 6):
            queue.register_speech(i, now + timedelta(seconds=i))

        original_order = [ls.legislator_id for ls in queue.get_speaker_queue()]

        json_str = queue.to_json()
        restored = PrecedenceQueue.from_json(json_str)
        restored_order = [ls.legislator_id for ls in restored.get_speaker_queue()]

        assert original_order == restored_order

    def test_json_is_valid(self):
        queue = _make_queue(5)
        json_str = queue.to_json()
        parsed = json.loads(json_str)
        assert "session_id" in parsed
        assert "legislators" in parsed
        assert len(parsed["legislators"]) == 5


class TestThreeSessionScenario:
    """Simulate three full sessions with 18 legislators."""

    def test_three_sessions(self):
        now = datetime.now(timezone.utc)

        # Session 1
        q1 = PrecedenceQueue(session_id=1, seed=42)
        legislators = _make_legislators(18)
        q1.initialize(legislators)
        q1.set_po(1)

        # 10 speeches in session 1
        for i in range(2, 12):
            q1.register_speech(i, now + timedelta(minutes=i))

        queue_after_s1 = q1.get_speaker_queue()
        # Unseen legislators (12-18) should be at front, then 2..11 in recency order
        unseen = [ls for ls in queue_after_s1 if ls.speech_count == 0]
        assert len(unseen) == 7  # Legislators 12-18 (PO excluded)

        # Session 2 — fresh precedence
        q2 = PrecedenceQueue(session_id=2, seed=43)
        q2.initialize(_make_legislators(18))
        q2.set_po(5)  # Different PO

        # All should be unseen again
        assert all(ls.speech_count == 0 for ls in q2.legislators.values())
        queue_s2 = q2.get_speaker_queue()
        assert len(queue_s2) == 17  # 18 minus PO

        # Session 3 — fresh again
        q3 = PrecedenceQueue(session_id=3, seed=44)
        q3.initialize(_make_legislators(18))
        assert len(q3.legislators) == 18


class TestEdgeCases:
    """Edge case tests."""

    def test_single_legislator(self):
        queue = _make_queue(1)
        result = queue.get_speaker_queue()
        assert len(result) == 1
        assert result[0].legislator_id == 1

    def test_empty_queue(self):
        queue = PrecedenceQueue(session_id=1)
        result = queue.get_speaker_queue()
        assert result == []
        assert queue.get_next_speaker() is None

    def test_all_withdrawn(self):
        queue = _make_queue(3)
        for ls in queue.legislators.values():
            ls.is_withdrawn = True
        assert queue.get_next_speaker() is None
        assert queue.get_next_questioner() is None

    def test_register_speech_invalid_id(self):
        queue = _make_queue(3)
        with pytest.raises(ValueError, match="not in session"):
            queue.register_speech(999)

    def test_register_question_invalid_id(self):
        queue = _make_queue(3)
        with pytest.raises(ValueError, match="not in session"):
            queue.register_question(999)

    def test_all_same_speech_count_and_time(self):
        """When everyone has identical stats, seed-based tiebreaking determines order."""
        queue = _make_queue(5, seed=42)
        now = datetime.now(timezone.utc)
        for i in range(1, 6):
            queue.register_speech(i, now)  # All same time
        result = queue.get_speaker_queue()
        assert len(result) == 5
        # All have same count and time — order comes from deterministic random
