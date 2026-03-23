"""
Agent daemon for automated review polling and submission.

Each participant runs this on their PC. The daemon:
- Polls Supabase for review assignments
- Generates reviews using Claude API
- Submits reviews automatically
- Sends heartbeat to indicate active status
"""

from __future__ import annotations

import re
import time

import anthropic
from rich.console import Console

from conference import client as db
from conference.client import get_client

console = Console()


def generate_review(
    paper_content: str,
    paper_title: str,
    reviewer_expertise: str,
    topic_name: str,
) -> tuple[float, str]:
    """Generate a review using Claude API.

    Returns (score, feedback) where score is in (0, 1].
    """
    api = anthropic.Anthropic()

    system_prompt = f"""\
あなたはAI科学会議のレビュアーです。
あなたの専門分野: {reviewer_expertise}
研究トピック: {topic_name}

CPC-MS（Collective Predictive Coding as Model of Science）フレームワークに基づいてレビューを行います。

スコアは p(z^{{k'}}|w) を表します:
- この論文が自分の世界モデル（専門知識・信念）とどれだけ整合するか
- 1.0 = 完全に整合（自分の理解と完全に一致）
- 0.7 = 概ね整合（大部分は一致するが一部疑問がある）
- 0.5 = 部分的に整合
- 0.3 = あまり整合しない
- 0.1 = ほぼ整合しない
- 0 は不可。必ず (0, 1] の範囲でスコアをつけてください。

回答は以下の形式で出力してください:
SCORE: <0から1の間の数値>

<Markdownでのレビューコメント>"""

    response = api.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"以下の論文をレビューしてください。\n\n# {paper_title}\n\n{paper_content}",
            }
        ],
    )

    text = response.content[0].text

    # Parse score from response
    match = re.search(r"SCORE:\s*([\d.]+)", text)
    if match:
        score = float(match.group(1))
        score = max(0.01, min(1.0, score))  # Clamp to (0, 1]
        feedback = text[match.end() :].strip()
    else:
        score = 0.5
        feedback = text

    return score, feedback


def run_daemon(
    agent_id: str,
    poll_interval: int = 30,
    timeout_minutes: int = 60,
    max_reviews: int = 20,
) -> None:
    """Run the agent daemon loop."""
    sb = get_client()

    # Verify agent exists
    try:
        agent = db.get_agent(sb, agent_id)
    except Exception:
        console.print(f"[red]エージェント {agent_id} が見つかりません。[/red]")
        return

    agent_name = agent["name"]
    expertise = agent.get("expertise", "")

    # Show startup info
    console.print()
    console.print("[bold]=== エージェントデーモン起動 ===[/bold]")
    console.print(f"エージェント: {agent_name} ({expertise})")
    console.print(f"ポーリング間隔: {poll_interval}秒")
    console.print(f"自動停止: {timeout_minutes}分後 / レビュー{max_reviews}件完了時")
    console.print("停止方法: Ctrl+C でいつでも安全に停止できます")
    console.print()

    start_time = time.time()
    review_count = 0
    stop_reason = None

    try:
        while True:
            elapsed = time.time() - start_time
            elapsed_minutes = elapsed / 60

            # Check timeout
            if elapsed_minutes >= timeout_minutes:
                stop_reason = f"タイムアウト（{timeout_minutes}分経過）"
                break

            # Check review limit
            if review_count >= max_reviews:
                stop_reason = f"レビュー上限に達しました（{max_reviews}件）"
                break

            # Check admin pause signal
            try:
                status = db.get_conference_status(sb)
                if status == "paused":
                    stop_reason = "管理者により会議が一時停止されました"
                    break
            except Exception:
                pass  # Config table may not exist yet

            # Update heartbeat
            try:
                db.update_heartbeat(sb, agent_id)
            except Exception as e:
                console.print(f"[yellow]ハートビート更新エラー: {e}[/yellow]")

            # Check for pending assignments
            try:
                assignments = db.get_pending_assignments(sb, agent_id)
            except Exception as e:
                console.print(f"[yellow]接続エラー。次のサイクルで再試行します: {e}[/yellow]")
                time.sleep(poll_interval)
                continue

            if not assignments:
                console.print("[dim]割り当てなし。待機中...[/dim]")
                time.sleep(poll_interval)
                continue

            # Process each assignment
            for assignment in assignments:
                if review_count >= max_reviews:
                    break

                paper = assignment.get("papers")
                if not paper:
                    continue

                paper_id = assignment["paper_id"]
                current_paper_id = assignment.get("current_paper_id")

                console.print(
                    f"[green]レビュー割り当てを検知: {paper['title']}[/green]"
                )

                try:
                    # Get topic name
                    topics = db.list_topics(sb)
                    topic_name = ""
                    for t in topics:
                        if t["id"] == paper.get("topic_id"):
                            topic_name = t["name"]
                            break

                    # Review w_new
                    console.print("  w_new をレビュー中...")
                    score_new, feedback_new = generate_review(
                        paper_content=paper.get("content", ""),
                        paper_title=paper.get("title", ""),
                        reviewer_expertise=expertise,
                        topic_name=topic_name,
                    )
                    db.submit_review(sb, agent_id, paper_id, score_new, feedback_new)
                    console.print(
                        f"  w_new レビュー完了: スコア={score_new:.2f}"
                    )

                    # Review w_current if exists
                    if current_paper_id:
                        try:
                            current_paper = db.get_paper(sb, current_paper_id)
                            console.print("  w_current をレビュー中...")
                            score_cur, feedback_cur = generate_review(
                                paper_content=current_paper.get("content", ""),
                                paper_title=current_paper.get("title", ""),
                                reviewer_expertise=expertise,
                                topic_name=topic_name,
                            )
                            db.submit_review(
                                sb, agent_id, current_paper_id, score_cur, feedback_cur
                            )
                            console.print(
                                f"  w_current レビュー完了: スコア={score_cur:.2f}"
                            )
                        except Exception as e:
                            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                                console.print("  w_current は既にレビュー済み")
                            else:
                                raise

                    # Mark assignment as completed
                    db.mark_assignment_completed(sb, assignment["id"])
                    review_count += 1
                    console.print(
                        f"  [green]割り当て完了[/green] (レビュー {review_count}/{max_reviews})"
                    )

                except Exception as e:
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                        console.print(f"  [yellow]既にレビュー済みです[/yellow]")
                        try:
                            db.mark_assignment_completed(sb, assignment["id"])
                        except Exception:
                            pass
                    else:
                        console.print(f"  [red]レビューエラー: {e}[/red]")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        stop_reason = "ユーザーによる手動停止（Ctrl+C）"

    # Show shutdown info
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    console.print()
    console.print("[bold]=== デーモン停止 ===[/bold]")
    console.print(f"理由: {stop_reason}")
    console.print(f"完了レビュー数: {review_count}件")
    console.print(f"稼働時間: {minutes}分{seconds}秒")
