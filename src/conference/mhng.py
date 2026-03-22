"""
Metropolis-Hastings Naming Game (MHNG) acceptance logic.

Faithful implementation of the CPC-MS paper (Section 2.2, Step 4):

In MHNG, reviewer k' evaluates a proposed paper w_new against the current
accepted paper w_current. The acceptance probability is:

    α = min(1, Π_i p(z^{k'_i}|w_new) / Π_i p(z^{k'_i}|w_current))

where each reviewer i provides scores (0, 1] representing p(z^{k'_i}|w),
i.e., how compatible the paper is with their internal world model.

Multiple papers per round are processed as a sequential Markov chain
(random shuffle, each compared to w_current in order).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class MHResult:
    """Result of a single Metropolis-Hastings acceptance decision."""

    paper_new_id: str
    paper_current_id: str | None
    scores_new: list[float]
    scores_current: list[float]
    log_score_new_agg: float
    log_score_current_agg: float | None
    alpha: float
    u_draw: float
    accepted: bool


def compute_mh_acceptance(
    paper_new_id: str,
    paper_current_id: str | None,
    scores_new: list[float],
    scores_current: list[float],
) -> MHResult:
    """
    Compute MH acceptance for a proposed paper against w_current.

    Args:
        paper_new_id: ID of the proposed paper (w_new)
        paper_current_id: ID of the current accepted paper (w_current), or None if first
        scores_new: Reviewer scores for w_new. Each in (0, 1].
                    Represents p(z^{k'_i}|w_new).
        scores_current: Reviewer scores for w_current from the SAME reviewers.
                       Empty if no w_current exists (first round).

    Returns:
        MHResult with the acceptance decision and all intermediate values.
    """
    # Validate scores
    for s in scores_new:
        if not (0 < s <= 1):
            raise ValueError(f"Score must be in (0, 1], got {s}")
    for s in scores_current:
        if not (0 < s <= 1):
            raise ValueError(f"Score must be in (0, 1], got {s}")

    # Log-transform: log p(z^{k'_i}|w)
    log_score_new_agg = sum(math.log(s) for s in scores_new)

    # First round: no w_current -> auto-accept
    if paper_current_id is None or not scores_current:
        return MHResult(
            paper_new_id=paper_new_id,
            paper_current_id=None,
            scores_new=scores_new,
            scores_current=[],
            log_score_new_agg=log_score_new_agg,
            log_score_current_agg=None,
            alpha=1.0,
            u_draw=0.0,
            accepted=True,
        )

    if len(scores_new) != len(scores_current):
        raise ValueError(
            f"Each reviewer must score both papers. "
            f"Got {len(scores_new)} scores for w_new, {len(scores_current)} for w_current."
        )

    log_score_current_agg = sum(math.log(s) for s in scores_current)

    # MH ratio: α = min(1, exp(Σ log(s_new_i) - Σ log(s_current_i)))
    log_ratio = log_score_new_agg - log_score_current_agg
    # Clamp to avoid overflow
    alpha = min(1.0, math.exp(min(log_ratio, 700)))

    # Stochastic acceptance: u ~ Uniform(0, 1)
    u_draw = random.random()
    accepted = u_draw < alpha

    return MHResult(
        paper_new_id=paper_new_id,
        paper_current_id=paper_current_id,
        scores_new=scores_new,
        scores_current=scores_current,
        log_score_new_agg=log_score_new_agg,
        log_score_current_agg=log_score_current_agg,
        alpha=alpha,
        u_draw=u_draw,
        accepted=accepted,
    )


@dataclass
class PaperReviews:
    """A paper with its review scores and the scores for w_current."""

    paper_id: str
    scores_for_self: list[float]  # p(z^{k'_i}|w_new) for each reviewer i
    scores_for_current: list[float]  # p(z^{k'_i}|w_current) from same reviewers


def run_mhng_chain(
    current_paper_id: str | None,
    submissions: list[PaperReviews],
    seed: int | None = None,
) -> tuple[str | None, list[MHResult]]:
    """
    Run one round of MHNG as a sequential Markov chain.

    Papers are randomly shuffled, then each is proposed against w_current
    in sequence. If accepted, w_current is updated.

    Args:
        current_paper_id: Current w_current paper ID, or None if first round.
        submissions: List of papers with their review scores.
        seed: Random seed for reproducibility (shuffle + MH draws).

    Returns:
        Tuple of (final w_current paper_id, list of MHResult for each step).
    """
    if seed is not None:
        random.seed(seed)

    # Shuffle for random ordering (faithful to MHNG Markov chain)
    shuffled = list(submissions)
    random.shuffle(shuffled)

    events: list[MHResult] = []
    w_current = current_paper_id

    for paper in shuffled:
        result = compute_mh_acceptance(
            paper_new_id=paper.paper_id,
            paper_current_id=w_current,
            scores_new=paper.scores_for_self,
            scores_current=paper.scores_for_current if w_current else [],
        )
        events.append(result)

        if result.accepted:
            w_current = paper.paper_id

    return w_current, events
