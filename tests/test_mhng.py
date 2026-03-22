"""Tests for MHNG acceptance logic."""

import math

from conference.mhng import (
    MHResult,
    PaperReviews,
    compute_mh_acceptance,
    run_mhng_chain,
)


class TestComputeMHAcceptance:
    def test_first_round_auto_accepts(self):
        result = compute_mh_acceptance(
            paper_new_id="paper-1",
            paper_current_id=None,
            scores_new=[0.8, 0.7],
            scores_current=[],
        )
        assert result.accepted is True
        assert result.alpha == 1.0
        assert result.paper_current_id is None

    def test_higher_scores_give_alpha_1(self):
        """When w_new scores higher than w_current, α = 1 (always accept)."""
        result = compute_mh_acceptance(
            paper_new_id="paper-new",
            paper_current_id="paper-old",
            scores_new=[0.9, 0.8],
            scores_current=[0.3, 0.4],
        )
        assert result.alpha == 1.0
        assert result.accepted is True

    def test_lower_scores_give_alpha_less_than_1(self):
        """When w_new scores lower, α < 1 (probabilistic acceptance)."""
        result = compute_mh_acceptance(
            paper_new_id="paper-new",
            paper_current_id="paper-old",
            scores_new=[0.3, 0.4],
            scores_current=[0.9, 0.8],
        )
        assert 0 < result.alpha < 1
        # α = exp(log(0.3)+log(0.4) - log(0.9)-log(0.8))
        expected = math.exp(
            math.log(0.3) + math.log(0.4) - math.log(0.9) - math.log(0.8)
        )
        assert abs(result.alpha - expected) < 1e-10

    def test_equal_scores_give_alpha_1(self):
        """When scores are equal, α = 1."""
        result = compute_mh_acceptance(
            paper_new_id="paper-new",
            paper_current_id="paper-old",
            scores_new=[0.5, 0.5],
            scores_current=[0.5, 0.5],
        )
        assert result.alpha == 1.0

    def test_single_reviewer(self):
        result = compute_mh_acceptance(
            paper_new_id="new",
            paper_current_id="old",
            scores_new=[0.6],
            scores_current=[0.8],
        )
        expected_alpha = 0.6 / 0.8
        assert abs(result.alpha - expected_alpha) < 1e-10

    def test_invalid_score_raises(self):
        import pytest

        with pytest.raises(ValueError):
            compute_mh_acceptance("a", "b", [0.0], [0.5])
        with pytest.raises(ValueError):
            compute_mh_acceptance("a", "b", [1.1], [0.5])
        with pytest.raises(ValueError):
            compute_mh_acceptance("a", "b", [-0.1], [0.5])

    def test_mismatched_reviewer_count_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Each reviewer must score both"):
            compute_mh_acceptance("a", "b", [0.5, 0.6], [0.5])


class TestRunMHNGChain:
    def test_first_round_accepts_first_paper(self):
        subs = [
            PaperReviews("p1", [0.8], []),
            PaperReviews("p2", [0.6], []),
        ]
        final, events = run_mhng_chain(None, subs, seed=42)
        # First paper in shuffled order is auto-accepted
        assert events[0].accepted is True
        assert final is not None

    def test_chain_updates_w_current(self):
        """When a paper is accepted, subsequent papers compare against it."""
        subs = [
            PaperReviews("p1", [0.9], [0.1]),
            PaperReviews("p2", [0.9], [0.1]),
            PaperReviews("p3", [0.9], [0.1]),
        ]
        final, events = run_mhng_chain("p0", subs, seed=0)
        # All papers score much higher than current -> all should be accepted
        for e in events:
            assert e.alpha == 1.0
            assert e.accepted is True

    def test_deterministic_with_seed(self):
        subs = [
            PaperReviews("p1", [0.5], [0.6]),
            PaperReviews("p2", [0.4], [0.6]),
        ]
        final1, events1 = run_mhng_chain("p0", subs, seed=123)
        final2, events2 = run_mhng_chain("p0", subs, seed=123)
        assert final1 == final2
        assert [e.accepted for e in events1] == [e.accepted for e in events2]

    def test_empty_submissions(self):
        final, events = run_mhng_chain("p0", [], seed=0)
        assert final == "p0"
        assert events == []
