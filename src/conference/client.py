"""
Supabase client wrapper for the CPC-MS Conference.

Provides typed access to the conference database.
Agents can also use the Supabase REST API directly.
"""

from __future__ import annotations

import os

from supabase import Client, create_client


def get_client() -> Client:
    """Create a Supabase client from environment variables."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_KEY environment variables.\n"
            "Get these from your Supabase project settings > API."
        )
    return create_client(url, key)


# --- Agent operations ---


def register_agent(client: Client, name: str, expertise: str) -> dict:
    """Register a new agent."""
    return (
        client.table("agents").insert({"name": name, "expertise": expertise}).execute()
    ).data[0]


def list_agents(client: Client) -> list[dict]:
    return client.table("agents").select("*").execute().data


# --- Topic operations ---


def create_topic(client: Client, name: str, description: str = "") -> dict:
    return (
        client.table("topics")
        .insert({"name": name, "description": description})
        .execute()
    ).data[0]


def list_topics(client: Client) -> list[dict]:
    return client.table("topics").select("*").execute().data


# --- Round operations ---


def start_round(client: Client, topic_id: str) -> dict:
    return (
        client.table("rounds")
        .insert({"topic_id": topic_id, "phase": "submission"})
        .execute()
    ).data[0]


def get_round(client: Client, round_id: int) -> dict:
    return (
        client.table("rounds").select("*").eq("id", round_id).single().execute()
    ).data


def get_latest_round(client: Client, topic_id: str | None = None) -> dict | None:
    q = client.table("rounds").select("*").order("id", desc=True).limit(1)
    if topic_id:
        q = q.eq("topic_id", topic_id)
    result = q.execute()
    return result.data[0] if result.data else None


def advance_round_phase(client: Client, round_id: int, new_phase: str) -> dict:
    update = {"phase": new_phase}
    if new_phase == "completed":
        from datetime import datetime, timezone

        update["completed_at"] = datetime.now(timezone.utc).isoformat()
    return (
        client.table("rounds").update(update).eq("id", round_id).execute()
    ).data[0]


# --- Paper operations ---


def submit_paper(
    client: Client,
    agent_id: str,
    topic_id: str,
    round_id: int,
    title: str,
    content: str,
    abstract: str = "",
) -> dict:
    return (
        client.table("papers")
        .insert(
            {
                "agent_id": agent_id,
                "topic_id": topic_id,
                "round_id": round_id,
                "title": title,
                "abstract": abstract,
                "content": content,
            }
        )
        .execute()
    ).data[0]


def get_paper(client: Client, paper_id: str) -> dict:
    return (
        client.table("papers").select("*").eq("id", paper_id).single().execute()
    ).data


def list_papers(
    client: Client, round_id: int | None = None, topic_id: str | None = None
) -> list[dict]:
    q = client.table("papers").select("*")
    if round_id is not None:
        q = q.eq("round_id", round_id)
    if topic_id is not None:
        q = q.eq("topic_id", topic_id)
    return q.execute().data


# --- Review operations ---


def submit_review(
    client: Client,
    reviewer_id: str,
    paper_id: str,
    round_id: int,
    score: float,
    feedback: str = "",
) -> dict:
    return (
        client.table("reviews")
        .insert(
            {
                "reviewer_id": reviewer_id,
                "paper_id": paper_id,
                "round_id": round_id,
                "score": score,
                "feedback": feedback,
            }
        )
        .execute()
    ).data[0]


def get_reviews_for_paper(client: Client, paper_id: str) -> list[dict]:
    return client.table("reviews").select("*").eq("paper_id", paper_id).execute().data


def get_reviews_for_round(client: Client, round_id: int) -> list[dict]:
    return client.table("reviews").select("*").eq("round_id", round_id).execute().data


# --- Review assignment operations ---


def create_review_assignments(
    client: Client,
    round_id: int,
    topic_id: str,
    min_reviewers: int = 2,
) -> list[dict]:
    """
    Generate review assignments for a round.

    Each paper gets at least min_reviewers reviewers (who are not the author).
    Each reviewer must also review w_current (if it exists).
    """
    papers = list_papers(client, round_id=round_id)
    agents = list_agents(client)
    current = get_accepted_paper(client, topic_id)
    current_paper_id = current["paper_id"] if current else None

    if not papers or len(agents) < 2:
        return []

    agent_ids = [a["id"] for a in agents]
    assignments = []

    for paper in papers:
        author_id = paper["agent_id"]
        # Eligible reviewers: everyone except the author
        eligible = [a for a in agent_ids if a != author_id]

        # Assign min_reviewers (or all eligible if fewer)
        import random

        reviewers = random.sample(eligible, min(min_reviewers, len(eligible)))

        for reviewer_id in reviewers:
            assignments.append(
                {
                    "reviewer_id": reviewer_id,
                    "paper_id": paper["id"],
                    "round_id": round_id,
                    "current_paper_id": current_paper_id,
                }
            )

    if assignments:
        return client.table("review_assignments").insert(assignments).execute().data
    return []


def get_review_assignments(client: Client, reviewer_id: str, round_id: int) -> list[dict]:
    return (
        client.table("review_assignments")
        .select("*,papers(*)")
        .eq("reviewer_id", reviewer_id)
        .eq("round_id", round_id)
        .execute()
        .data
    )


# --- Accepted paper operations ---


def get_accepted_paper(client: Client, topic_id: str) -> dict | None:
    """Get the current w_current for a topic."""
    result = (
        client.table("accepted_papers")
        .select("*")
        .eq("topic_id", topic_id)
        .order("accepted_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def set_accepted_paper(
    client: Client, topic_id: str, paper_id: str, round_id: int
) -> dict:
    return (
        client.table("accepted_papers")
        .insert({"topic_id": topic_id, "paper_id": paper_id, "round_id": round_id})
        .execute()
    ).data[0]


# --- MH Event operations ---


def record_mh_event(
    client: Client,
    topic_id: str,
    round_id: int,
    paper_new_id: str,
    paper_current_id: str | None,
    score_new_agg: float,
    score_current_agg: float | None,
    alpha: float,
    u_draw: float,
    accepted: bool,
    chain_order: int,
) -> dict:
    return (
        client.table("mh_events")
        .insert(
            {
                "topic_id": topic_id,
                "round_id": round_id,
                "paper_new_id": paper_new_id,
                "paper_current_id": paper_current_id,
                "score_new_agg": score_new_agg,
                "score_current_agg": score_current_agg,
                "alpha": alpha,
                "u_draw": u_draw,
                "accepted": accepted,
                "chain_order": chain_order,
            }
        )
        .execute()
    ).data[0]


def get_mh_events(
    client: Client, round_id: int | None = None, topic_id: str | None = None
) -> list[dict]:
    q = client.table("mh_events").select("*").order("chain_order")
    if round_id is not None:
        q = q.eq("round_id", round_id)
    if topic_id is not None:
        q = q.eq("topic_id", topic_id)
    return q.execute().data


# --- Conference state ---


def get_conference_state(client: Client) -> list[dict]:
    return client.table("conference_state").select("*").execute().data
