"""
CLI for conference administration.

Usage:
    uv run python -m conference.cli --help
    uv run python -m conference.cli create-topic "What is consciousness?"
    uv run python -m conference.cli judge <paper_id>
    uv run python -m conference.cli status
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from conference import client as db
from conference.mhng import PaperReviews, compute_mh_acceptance

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


# --- Judgment ---


@cli.command()
@click.argument("paper_id")
@click.option("--min-reviewers", "-r", default=2, help="Minimum reviewers per paper")
def judge(paper_id: str, min_reviewers: int):
    """Run MHNG judgment for a single paper (w_new vs w_current)."""
    sb = get_sb()
    paper = db.get_paper(sb, paper_id)
    topic_id = paper["topic_id"]

    # Get reviews for this paper
    reviews = db.get_reviews_for_paper(sb, paper_id)
    if not reviews:
        console.print("[red]No reviews for this paper. Cannot judge.[/red]")
        return

    # Get current w_current
    current = db.get_accepted_paper(sb, topic_id)
    current_paper_id = current["paper_id"] if current else None

    # Build scores
    scores_new = [r["score"] for r in reviews]
    scores_current = []

    if current_paper_id:
        current_reviews = db.get_reviews_for_paper(sb, current_paper_id)
        current_review_map = {r["reviewer_id"]: r["score"] for r in current_reviews}
        # Match reviewers: only use scores from reviewers who scored both
        matched_new = []
        for r in reviews:
            if r["reviewer_id"] in current_review_map:
                matched_new.append(r["score"])
                scores_current.append(current_review_map[r["reviewer_id"]])
        if scores_current:
            scores_new = matched_new

    # Run single MH step
    result = compute_mh_acceptance(
        paper_new_id=paper_id,
        paper_current_id=current_paper_id,
        scores_new=scores_new,
        scores_current=scores_current,
    )

    # Get next chain order
    chain_order = db.get_next_chain_order(sb, topic_id)

    # Record event
    db.record_mh_event(
        sb,
        topic_id=topic_id,
        paper_new_id=result.paper_new_id,
        paper_current_id=result.paper_current_id,
        score_new_agg=result.log_score_new_agg,
        score_current_agg=result.log_score_current_agg,
        alpha=result.alpha,
        u_draw=result.u_draw,
        accepted=result.accepted,
        chain_order=chain_order,
    )

    # Update paper status
    db.update_paper_status(sb, paper_id, "judged")

    # Update w_current if accepted
    result_str = (
        "[green]ACCEPTED[/green]" if result.accepted else "[red]REJECTED[/red]"
    )
    console.print(f"\n  Paper: {paper['title']}")
    console.print(f"  α = {result.alpha:.4f}, u = {result.u_draw:.4f}")
    console.print(f"  Result: {result_str}")

    if result.accepted:
        db.set_accepted_paper(sb, topic_id, paper_id)
        console.print(f"\n[green bold]w_current updated: {paper['title']}[/green bold]")
    else:
        console.print("\n[yellow]w_current unchanged.[/yellow]")


# --- Status ---


@cli.command()
def status():
    """Show current conference state."""
    sb = get_sb()

    # Show topics and their w_current
    topics = db.list_topics(sb)
    if not topics:
        console.print("[dim]No topics yet.[/dim]")
        return

    for topic in topics:
        console.print(f"\n[bold]{topic['name']}[/bold]")
        current = db.get_accepted_paper(sb, topic["id"])
        if current:
            paper = db.get_paper(sb, current["paper_id"])
            console.print(f"  w_current: {paper['title']}")
        else:
            console.print("  w_current: [dim]None[/dim]")

        # Show paper counts
        papers = db.list_papers(sb, topic_id=topic["id"])
        pending = sum(1 for p in papers if p.get("status") == "pending")
        judged = sum(1 for p in papers if p.get("status") == "judged")
        console.print(f"  Papers: {len(papers)} total, {pending} pending, {judged} judged")

    # Show recent MH events
    console.print()
    events = db.get_mh_events(sb)
    if events:
        table = Table(title="Recent MH Events (last 10)")
        table.add_column("#", style="dim")
        table.add_column("Paper New")
        table.add_column("α")
        table.add_column("u")
        table.add_column("Result")

        for e in events[-10:]:
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


@cli.command()
@click.argument("topic_id")
def show_papers(topic_id: str):
    """List papers for a topic."""
    sb = get_sb()
    papers = db.list_papers(sb, topic_id=topic_id)
    agents = {a["id"]: a["name"] for a in db.list_agents(sb)}

    table = Table(title="Papers")
    table.add_column("ID", style="dim")
    table.add_column("Title")
    table.add_column("Author")
    table.add_column("Status")
    table.add_column("Abstract")

    for p in papers:
        table.add_row(
            p["id"][:8],
            p["title"],
            agents.get(p["agent_id"], "?"),
            p.get("status", "?"),
            (p.get("abstract") or "")[:60],
        )

    console.print(table)


@cli.command()
@click.argument("topic_id")
def show_events(topic_id: str):
    """Show MHNG events for a topic."""
    sb = get_sb()
    events = db.get_mh_events(sb, topic_id=topic_id)

    if not events:
        console.print("[dim]No MH events for this topic.[/dim]")
        return

    table = Table(title="MHNG Events")
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
