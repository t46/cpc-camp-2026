"""
CLI for conference administration.

Usage:
    uv run python -m conference.cli --help
    uv run python -m conference.cli create-topic "What is consciousness?"
    uv run python -m conference.cli start-round <topic_id>
    uv run python -m conference.cli advance <round_id>
    uv run python -m conference.cli judge <round_id>
    uv run python -m conference.cli status
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from conference import client as db
from conference.mhng import MHResult, PaperReviews, run_mhng_chain

console = Console()


def get_sb():
    return db.get_client()


@click.group()
def cli():
    """CPC-MS AI Scientist Conference - Admin CLI"""
    pass


# --- Topics ---


@cli.command()
@click.argument("name")
@click.option("--description", "-d", default="", help="Topic description")
def create_topic(name: str, description: str):
    """Create a new research topic."""
    sb = get_sb()
    topic = db.create_topic(sb, name, description)
    console.print(f"[green]Topic created:[/green] {topic['id']}")
    console.print(f"  Name: {topic['name']}")


@cli.command()
def list_topics():
    """List all topics."""
    sb = get_sb()
    topics = db.list_topics(sb)
    table = Table(title="Topics")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Description")
    for t in topics:
        table.add_row(t["id"], t["name"], t.get("description", ""))
    console.print(table)


# --- Agents ---


@cli.command()
def list_agents():
    """List all registered agents."""
    sb = get_sb()
    agents = db.list_agents(sb)
    table = Table(title="Agents")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Expertise")
    for a in agents:
        table.add_row(a["id"], a["name"], a.get("expertise", ""))
    console.print(table)


# --- Rounds ---


@cli.command()
@click.argument("topic_id")
def start_round(topic_id: str):
    """Start a new round for a topic."""
    sb = get_sb()
    r = db.start_round(sb, topic_id)
    console.print(f"[green]Round started:[/green] {r['id']} (phase: submission)")


@cli.command()
@click.argument("round_id", type=int)
@click.option("--min-reviewers", "-r", default=2, help="Minimum reviewers per paper")
def advance(round_id: int, min_reviewers: int):
    """Advance round to next phase (submission → review → judgment → completed)."""
    sb = get_sb()
    r = db.get_round(sb, round_id)
    current_phase = r["phase"]

    phase_order = ["submission", "review", "judgment", "completed"]
    idx = phase_order.index(current_phase)
    if idx >= len(phase_order) - 1:
        console.print("[yellow]Round is already completed.[/yellow]")
        return

    new_phase = phase_order[idx + 1]

    if new_phase == "review":
        # Generate review assignments
        papers = db.list_papers(sb, round_id=round_id)
        if not papers:
            console.print("[red]No papers submitted. Cannot advance to review.[/red]")
            return
        assignments = db.create_review_assignments(
            sb, round_id, r["topic_id"], min_reviewers=min_reviewers
        )
        console.print(f"[blue]Created {len(assignments)} review assignments.[/blue]")

    if new_phase == "judgment":
        # Check if enough reviews are in
        reviews = db.get_reviews_for_round(sb, round_id)
        if not reviews:
            console.print("[red]No reviews submitted. Cannot run judgment.[/red]")
            return

    db.advance_round_phase(sb, round_id, new_phase)
    console.print(f"[green]Round {round_id}: {current_phase} → {new_phase}[/green]")

    if new_phase == "judgment":
        console.print("[blue]Running MHNG judgment...[/blue]")
        _run_judgment(sb, round_id, r["topic_id"])
        db.advance_round_phase(sb, round_id, "completed")
        console.print(f"[green]Round {round_id}: judgment → completed[/green]")


@cli.command()
@click.argument("round_id", type=int)
def judge(round_id: int):
    """Run MHNG judgment for a round (independent of phase management)."""
    sb = get_sb()
    r = db.get_round(sb, round_id)
    _run_judgment(sb, round_id, r["topic_id"])


def _run_judgment(sb, round_id: int, topic_id: str):
    """Execute MHNG sequential chain for a round."""
    papers = db.list_papers(sb, round_id=round_id)
    reviews = db.get_reviews_for_round(sb, round_id)
    current = db.get_accepted_paper(sb, topic_id)
    current_paper_id = current["paper_id"] if current else None

    # Build review score lookup: paper_id -> list of (reviewer_id, score)
    review_map: dict[str, list[tuple[str, float]]] = {}
    for rev in reviews:
        review_map.setdefault(rev["paper_id"], []).append(
            (rev["reviewer_id"], rev["score"])
        )

    # Build PaperReviews for each submitted paper
    submissions = []
    for paper in papers:
        pid = paper["id"]
        if pid not in review_map:
            console.print(
                f"[yellow]Paper '{paper['title']}' has no reviews, skipping.[/yellow]"
            )
            continue

        scores_for_self = [score for _, score in review_map[pid]]

        # Get scores for w_current from the same reviewers
        scores_for_current = []
        if current_paper_id and current_paper_id in review_map:
            current_review_map = {
                rid: score for rid, score in review_map[current_paper_id]
            }
            for reviewer_id, _ in review_map[pid]:
                if reviewer_id in current_review_map:
                    scores_for_current.append(current_review_map[reviewer_id])

        # If we have w_current but not all reviewers scored it, use available ones
        if current_paper_id and scores_for_current:
            # Trim self scores to match
            scores_for_self = scores_for_self[: len(scores_for_current)]

        submissions.append(
            PaperReviews(
                paper_id=pid,
                scores_for_self=scores_for_self,
                scores_for_current=scores_for_current,
            )
        )

    if not submissions:
        console.print("[red]No papers with reviews to judge.[/red]")
        return

    # Run MHNG chain
    final_paper_id, events = run_mhng_chain(current_paper_id, submissions)

    # Record events and display results
    paper_titles = {p["id"]: p["title"] for p in papers}

    table = Table(title="MHNG Sequential Chain Results")
    table.add_column("#", style="dim")
    table.add_column("Paper (w_new)")
    table.add_column("α")
    table.add_column("u")
    table.add_column("Result")

    for i, event in enumerate(events):
        # Record to database
        db.record_mh_event(
            sb,
            topic_id=topic_id,
            round_id=round_id,
            paper_new_id=event.paper_new_id,
            paper_current_id=event.paper_current_id,
            score_new_agg=event.log_score_new_agg,
            score_current_agg=event.log_score_current_agg,
            alpha=event.alpha,
            u_draw=event.u_draw,
            accepted=event.accepted,
            chain_order=i,
        )

        title = paper_titles.get(event.paper_new_id, event.paper_new_id[:8])
        result_str = (
            "[green]ACCEPTED[/green]" if event.accepted else "[red]REJECTED[/red]"
        )
        table.add_row(
            str(i + 1),
            title[:40],
            f"{event.alpha:.4f}",
            f"{event.u_draw:.4f}",
            result_str,
        )

    console.print(table)

    # Update accepted paper
    if final_paper_id:
        db.set_accepted_paper(sb, topic_id, final_paper_id, round_id)
        final_title = paper_titles.get(final_paper_id, final_paper_id[:8])
        console.print(f"\n[green bold]w_current updated: {final_title}[/green bold]")
    else:
        console.print("\n[yellow]No change to w_current.[/yellow]")


# --- Status ---


@cli.command()
def status():
    """Show current conference state."""
    sb = get_sb()
    state = db.get_conference_state(sb)

    if not state:
        console.print("[dim]No rounds yet.[/dim]")
        return

    table = Table(title="Conference State")
    table.add_column("Round")
    table.add_column("Topic")
    table.add_column("Phase")
    table.add_column("Papers")
    table.add_column("Reviews")

    for s in state:
        phase_style = {
            "submission": "blue",
            "review": "yellow",
            "judgment": "magenta",
            "completed": "green",
        }.get(s["phase"], "white")

        table.add_row(
            str(s["round_id"]),
            s["topic_name"],
            f"[{phase_style}]{s['phase']}[/{phase_style}]",
            str(s["paper_count"]),
            str(s["review_count"]),
        )

    console.print(table)

    # Show accepted papers
    topics = db.list_topics(sb)
    for topic in topics:
        current = db.get_accepted_paper(sb, topic["id"])
        if current:
            paper = db.get_paper(sb, current["paper_id"])
            console.print(
                f"\n[bold]w_current for '{topic['name']}':[/bold] {paper['title']}"
            )


@cli.command()
@click.argument("round_id", type=int)
def show_papers(round_id: int):
    """List papers for a specific round."""
    sb = get_sb()
    papers = db.list_papers(sb, round_id=round_id)
    agents = {a["id"]: a["name"] for a in db.list_agents(sb)}

    table = Table(title=f"Papers for Round {round_id}")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("Abstract")

    for p in papers:
        table.add_row(
            p["id"][:8],
            p["title"],
            agents.get(p["agent_id"], "?"),
            (p.get("abstract") or "")[:60],
        )

    console.print(table)


@cli.command()
@click.argument("round_id", type=int)
def show_events(round_id: int):
    """Show MHNG events for a round."""
    sb = get_sb()
    events = db.get_mh_events(sb, round_id=round_id)

    if not events:
        console.print("[dim]No MH events for this round.[/dim]")
        return

    table = Table(title=f"MHNG Events for Round {round_id}")
    table.add_column("#")
    table.add_column("Paper New")
    table.add_column("α")
    table.add_column("u")
    table.add_column("Result")

    for e in events:
        result_str = (
            "[green]ACCEPTED[/green]" if e["accepted"] else "[red]REJECTED[/red]"
        )
        table.add_row(
            str(e["chain_order"] + 1),
            e["paper_new_id"][:8],
            f"{e['alpha']:.4f}",
            f"{e['u_draw']:.4f}",
            result_str,
        )

    console.print(table)


if __name__ == "__main__":
    cli()
