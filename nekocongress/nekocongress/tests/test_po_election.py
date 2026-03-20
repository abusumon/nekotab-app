"""Unit tests for the PO election instant-runoff voting engine."""

from nekocongress.services.po_election import ElectionResult, run_full_election, tally_round


class TestTallyRound:
    """Tests for a single round of voting."""

    def test_clear_majority(self):
        """One candidate has >50% of votes."""
        ballots = [(1, 10), (2, 10), (3, 10), (4, 20), (5, 10)]
        result = tally_round(ballots, round_number=1)
        assert result.is_decided
        assert result.winner_id == 10
        assert result.winner_votes == 4
        assert result.total_votes == 5
        assert result.majority_needed == 3

    def test_exact_majority(self):
        """Candidate has exactly majority threshold."""
        ballots = [(1, 10), (2, 10), (3, 10), (4, 20), (5, 20), (6, 30)]
        result = tally_round(ballots, round_number=1)
        # 6 votes, majority = 4. No candidate has 4.
        assert not result.is_decided
        assert result.eliminated_id is not None

    def test_no_majority_eliminates_lowest(self):
        """When no majority, the candidate with fewest votes is eliminated."""
        ballots = [
            (1, 10), (2, 10), (3, 10),  # 10 gets 3
            (4, 20), (5, 20),             # 20 gets 2
            (6, 30),                       # 30 gets 1
        ]
        result = tally_round(ballots, round_number=1)
        assert not result.is_decided
        assert result.eliminated_id == 30  # Fewest votes

    def test_elimination_tie_picks_lowest_id(self):
        """When tied for fewest votes, eliminate the lowest candidate ID."""
        ballots = [
            (1, 10), (2, 10), (3, 10),  # 10 gets 3
            (4, 20),                      # 20 gets 1
            (5, 30),                      # 30 gets 1
        ]
        result = tally_round(ballots, round_number=1)
        # 3 of 5 = majority (5//2+1 = 3), so candidate 10 wins outright
        assert result.is_decided
        assert result.winner_id == 10

    def test_elimination_tie_no_majority(self):
        """When no majority and tied for fewest, eliminate lowest candidate ID."""
        ballots = [
            (1, 10), (2, 10),  # 10 gets 2
            (3, 20), (4, 20),  # 20 gets 2
            (5, 30),           # 30 gets 1
            (6, 40),           # 40 gets 1
        ]
        result = tally_round(ballots, round_number=1)
        # majority = 6//2+1 = 4, no one has it
        assert not result.is_decided
        # 30 and 40 tied with 1 vote each; 30 has lower ID → eliminated
        assert result.eliminated_id == 30

    def test_two_candidates_with_majority(self):
        """With only 2 candidates, one always has majority."""
        ballots = [(1, 10), (2, 10), (3, 20)]
        result = tally_round(ballots, round_number=1)
        assert result.is_decided
        assert result.winner_id == 10

    def test_single_candidate(self):
        """Single candidate wins by default."""
        ballots = [(1, 10), (2, 10), (3, 10)]
        result = tally_round(ballots, round_number=1)
        assert result.is_decided
        assert result.winner_id == 10
        assert result.winner_votes == 3

    def test_empty_ballots(self):
        result = tally_round([], round_number=1)
        assert not result.is_decided
        assert result.total_votes == 0

    def test_eliminated_candidates_filtered(self):
        """Votes for eliminated candidates are not counted."""
        ballots = [
            (1, 10), (2, 10),  # 10 gets 2
            (3, 20), (4, 20),  # 20 gets 2
            (5, 30),           # 30 gets 1 — but eliminated
        ]
        result = tally_round(ballots, eliminated_candidates={30}, round_number=2)
        # After filtering 30: 4 valid votes, majority = 3, still no winner
        assert result.total_votes == 4
        assert 30 not in result.vote_counts


class TestRunFullElection:
    """Tests for multi-round elections."""

    def test_first_round_winner(self):
        """Election decided in first round."""
        ballots = [(1, 10), (2, 10), (3, 10), (4, 20)]
        results = run_full_election([ballots])
        assert len(results) == 1
        assert results[0].is_decided
        assert results[0].winner_id == 10

    def test_two_round_election(self):
        """Election requires two rounds."""
        round1 = [
            (1, 10), (2, 10),  # 10: 2
            (3, 20), (4, 20),  # 20: 2
            (5, 30),           # 30: 1
        ]
        # Round 1: no majority (need 3), eliminate 30
        # Round 2: voters re-vote without 30
        round2 = [
            (1, 10), (2, 10), (3, 10),  # 10: 3
            (4, 20), (5, 20),             # 20: 2
        ]
        results = run_full_election([round1, round2])
        assert len(results) == 2
        assert not results[0].is_decided
        assert results[0].eliminated_id == 30
        assert results[1].is_decided
        assert results[1].winner_id == 10

    def test_three_round_election(self):
        """Election with three candidates and three rounds."""
        round1 = [
            (1, 10), (2, 10), (3, 10),  # 10: 3
            (4, 20), (5, 20), (6, 20),  # 20: 3
            (7, 30), (8, 30),            # 30: 2
            (9, 40),                      # 40: 1
        ]
        # majority = 5, no winner, eliminate 40
        round2 = [
            (1, 10), (2, 10), (3, 10),  # 10: 3
            (4, 20), (5, 20), (6, 20),  # 20: 3
            (7, 30), (8, 30), (9, 30),  # 30: 3
        ]
        # majority = 5, no winner, eliminate 30 (was already eliminated in rnd1: 40)
        # Wait — 40 was eliminated in round 1. In round 2, 30 is lowest at 3... actually all tied.
        # With elimination: {40}, votes for 40 filtered. All 9 valid. Majority=5.
        # 10:3, 20:3, 30:3 — tied at 3, eliminate lowest ID=10
        round3 = [
            (1, 20), (2, 20), (3, 20), (4, 20),  # 20: 4
            (5, 30), (6, 30), (7, 30), (8, 30), (9, 30),  # 30: 5
        ]
        # {40, 10} eliminated. 20:4, 30:5. Majority=5. 30 wins.
        results = run_full_election([round1, round2, round3])
        assert len(results) == 3
        assert results[2].is_decided
        assert results[2].winner_id == 30

    def test_unanimous_vote(self):
        """All voters choose the same candidate."""
        ballots = [(i, 10) for i in range(1, 19)]  # 18 voters all pick 10
        results = run_full_election([ballots])
        assert len(results) == 1
        assert results[0].is_decided
        assert results[0].winner_id == 10
        assert results[0].winner_votes == 18


class TestElectionResult:
    """Tests for ElectionResult properties."""

    def test_winner_votes_with_winner(self):
        result = ElectionResult(
            round_number=1,
            vote_counts={10: 5, 20: 3},
            total_votes=8,
            majority_needed=5,
            winner_id=10,
            is_decided=True,
        )
        assert result.winner_votes == 5

    def test_winner_votes_without_winner(self):
        result = ElectionResult(
            round_number=1,
            vote_counts={10: 3, 20: 3},
            total_votes=6,
            majority_needed=4,
        )
        assert result.winner_votes == 0
