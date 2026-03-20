"""Standings calculation engine.

Aggregates speech scores, rankings, penalties, and PO scores across
sessions to produce final standings for a congress tournament.

Supports per-chamber and cross-chamber (normalized) standings.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from nekocongress.services.normalization import normalize_scores


@dataclass
class LegislatorAggregation:
    """Intermediate aggregation for a single legislator."""

    legislator_id: int
    display_name: str = ""
    institution_code: str = ""
    chamber_label: str = ""

    total_points: float = 0.0
    total_penalties: int = 0
    speech_count: int = 0

    # Sum of rank positions (lower = better)
    ranking_sum: float = 0.0
    ranking_count: int = 0

    # Best parliamentarian rank across sessions (lowest = best)
    parliamentarian_rank: int | None = None

    # PO scoring (per-session hourly scores)
    po_points: float = 0.0

    # For normalization
    chamber_id: int | None = None


@dataclass
class StandingsEngine:
    """Computes standings from raw score data.

    Usage:
        engine = StandingsEngine(method="ZSCORE")
        engine.add_speech_score(legislator_id, points, penalties)
        engine.add_ranking(legislator_id, rank_position, is_parliamentarian)
        engine.add_po_score(legislator_id, points)
        standings = engine.compute()
    """

    normalization_method: str = "ZSCORE"
    _agg: dict[int, LegislatorAggregation] = field(default_factory=dict)

    def _ensure(self, legislator_id: int) -> LegislatorAggregation:
        if legislator_id not in self._agg:
            self._agg[legislator_id] = LegislatorAggregation(legislator_id=legislator_id)
        return self._agg[legislator_id]

    def set_legislator_info(
        self,
        legislator_id: int,
        display_name: str,
        institution_code: str = "",
        chamber_label: str = "",
        chamber_id: int | None = None,
    ) -> None:
        agg = self._ensure(legislator_id)
        agg.display_name = display_name
        agg.institution_code = institution_code
        agg.chamber_label = chamber_label
        agg.chamber_id = chamber_id

    def add_speech_score(
        self, legislator_id: int, points: float, penalties: int = 0
    ) -> None:
        agg = self._ensure(legislator_id)
        agg.total_points += points
        agg.total_penalties += penalties
        agg.speech_count += 1

    def add_ranking(
        self,
        legislator_id: int,
        rank_position: int,
        is_parliamentarian: bool = False,
    ) -> None:
        agg = self._ensure(legislator_id)
        if is_parliamentarian:
            if agg.parliamentarian_rank is None or rank_position < agg.parliamentarian_rank:
                agg.parliamentarian_rank = rank_position
        else:
            agg.ranking_sum += rank_position
            agg.ranking_count += 1

    def add_po_score(self, legislator_id: int, points: float) -> None:
        agg = self._ensure(legislator_id)
        agg.po_points += points

    def compute(self) -> list[dict]:
        """Compute final standings with optional cross-chamber normalization.

        Returns a list of dicts matching LegislatorStanding schema, sorted by
        net_points descending (highest first).
        """
        if not self._agg:
            return []

        entries = list(self._agg.values())

        # Compute net_points (total_points - total_penalties + po_points)
        for e in entries:
            e._net_points = e.total_points - e.total_penalties + e.po_points  # type: ignore

        # Compute average
        for e in entries:
            e._avg = e._net_points / e.speech_count if e.speech_count > 0 else 0.0  # type: ignore

        # Normalize across chambers if there are multiple chambers
        chambers = {e.chamber_id for e in entries if e.chamber_id is not None}
        if len(chambers) > 1:
            # Normalize net_points per chamber
            by_chamber: dict[int | None, list[LegislatorAggregation]] = defaultdict(list)
            for e in entries:
                by_chamber[e.chamber_id].append(e)

            for chamber_id, chamber_entries in by_chamber.items():
                raw_scores = [e._net_points for e in chamber_entries]  # type: ignore
                normalized = normalize_scores(raw_scores, self.normalization_method)
                for e, norm in zip(chamber_entries, normalized):
                    e._normalized = norm  # type: ignore
        else:
            for e in entries:
                e._normalized = None  # type: ignore

        # Sort: normalized_score desc (if available), else net_points desc
        def sort_key(e: LegislatorAggregation) -> tuple:
            norm = e._normalized if e._normalized is not None else float("-inf")  # type: ignore
            return (-norm, -e._net_points, e.ranking_sum, -(e.parliamentarian_rank or 999))  # type: ignore

        entries.sort(key=sort_key)

        # Build output
        results = []
        for rank, e in enumerate(entries, start=1):
            results.append({
                "legislator_id": e.legislator_id,
                "display_name": e.display_name,
                "institution_code": e.institution_code,
                "chamber_label": e.chamber_label,
                "total_points": e.total_points,
                "total_penalties": e.total_penalties,
                "net_points": e._net_points,  # type: ignore
                "speech_count": e.speech_count,
                "avg_points_per_speech": round(e._avg, 3),  # type: ignore
                "ranking_sum": e.ranking_sum,
                "ranking_count": e.ranking_count,
                "parliamentarian_rank": e.parliamentarian_rank,
                "po_points": e.po_points,
                "normalized_score": round(e._normalized, 4) if e._normalized is not None else None,  # type: ignore
                "advancement_rank": rank,
            })

        return results

    def compute_chamber(self, chamber_id: int) -> list[dict]:
        """Compute standings for a single chamber (no normalization).

        Returns results sorted by net_points descending.
        """
        chamber_entries = [
            e for e in self._agg.values() if e.chamber_id == chamber_id
        ]
        if not chamber_entries:
            return []

        for e in chamber_entries:
            e._net_points = e.total_points - e.total_penalties + e.po_points  # type: ignore
            e._avg = e._net_points / e.speech_count if e.speech_count > 0 else 0.0  # type: ignore

        chamber_entries.sort(key=lambda e: (-e._net_points, e.ranking_sum))  # type: ignore

        results = []
        for rank, e in enumerate(chamber_entries, start=1):
            results.append({
                "legislator_id": e.legislator_id,
                "display_name": e.display_name,
                "institution_code": e.institution_code,
                "chamber_label": e.chamber_label,
                "total_points": e.total_points,
                "total_penalties": e.total_penalties,
                "net_points": e._net_points,  # type: ignore
                "speech_count": e.speech_count,
                "avg_points_per_speech": round(e._avg, 3),  # type: ignore
                "ranking_sum": e.ranking_sum,
                "ranking_count": e.ranking_count,
                "parliamentarian_rank": e.parliamentarian_rank,
                "po_points": e.po_points,
                "normalized_score": None,
                "advancement_rank": rank,
            })

        return results
