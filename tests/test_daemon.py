"""Tests for daemon.py review generation and daemon logic."""

from unittest.mock import MagicMock, patch

import pytest

from conference.daemon import generate_review


class TestGenerateReview:
    @patch("conference.daemon.anthropic.Anthropic")
    def test_parses_score_and_feedback(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Simulate Claude API response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="SCORE: 0.75\n\n## Review\n\nThis is a strong paper.")
        ]
        mock_client.messages.create.return_value = mock_response

        score, feedback = generate_review(
            paper_content="# Introduction\nSome content",
            paper_title="Test Paper",
            reviewer_expertise="Machine Learning",
            topic_name="Consciousness",
        )

        assert score == 0.75
        assert "strong paper" in feedback

    @patch("conference.daemon.anthropic.Anthropic")
    def test_clamps_score_to_valid_range(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Score > 1 should be clamped
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 1.5\n\nGood")]
        mock_client.messages.create.return_value = mock_response

        score, _ = generate_review("content", "title", "ML", "topic")
        assert score == 1.0

    @patch("conference.daemon.anthropic.Anthropic")
    def test_clamps_score_zero_to_minimum(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Score 0 should be clamped to 0.01
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 0.0\n\nBad")]
        mock_client.messages.create.return_value = mock_response

        score, _ = generate_review("content", "title", "ML", "topic")
        assert score == 0.01

    @patch("conference.daemon.anthropic.Anthropic")
    def test_fallback_when_no_score_pattern(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # No SCORE: pattern in response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This paper is interesting.")]
        mock_client.messages.create.return_value = mock_response

        score, feedback = generate_review("content", "title", "ML", "topic")
        assert score == 0.5  # Default fallback
        assert "interesting" in feedback

    @patch("conference.daemon.anthropic.Anthropic")
    def test_uses_expertise_in_system_prompt(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 0.8\n\nOK")]
        mock_client.messages.create.return_value = mock_response

        generate_review("content", "title", "Bayesian Statistics", "topic")

        call_args = mock_client.messages.create.call_args
        system_prompt = call_args.kwargs["system"]
        assert "Bayesian Statistics" in system_prompt


class TestRunDaemon:
    @patch("conference.daemon.get_client")
    @patch("conference.daemon.db")
    def test_stops_on_timeout(self, mock_db, mock_get_client):
        """Daemon should stop when timeout is reached."""
        from conference.daemon import run_daemon

        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_db.get_agent.return_value = {
            "name": "TestAgent",
            "expertise": "ML",
        }
        mock_db.get_conference_status.return_value = "active"
        mock_db.get_pending_assignments.return_value = []

        # timeout=0 should stop immediately
        run_daemon("agent-1", poll_interval=1, timeout_minutes=0, max_reviews=10)

        # Should have tried to get agent info
        mock_db.get_agent.assert_called_once()

    @patch("conference.daemon.get_client")
    @patch("conference.daemon.db")
    def test_stops_on_pause(self, mock_db, mock_get_client):
        """Daemon should stop when conference is paused."""
        from conference.daemon import run_daemon

        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_db.get_agent.return_value = {
            "name": "TestAgent",
            "expertise": "ML",
        }
        mock_db.get_conference_status.return_value = "paused"

        run_daemon("agent-1", poll_interval=1, timeout_minutes=60, max_reviews=10)

        # Should not have checked for assignments (stopped before that)
        mock_db.get_pending_assignments.assert_not_called()

    @patch("conference.daemon.generate_review")
    @patch("conference.daemon.get_client")
    @patch("conference.daemon.db")
    @patch("conference.daemon.time")
    def test_processes_assignment(self, mock_time, mock_db, mock_get_client, mock_gen):
        """Daemon should process a pending assignment and submit reviews."""
        from conference.daemon import run_daemon

        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_db.get_agent.return_value = {
            "name": "TestAgent",
            "expertise": "ML",
        }

        # First call: active, second call: active (but max_reviews reached)
        mock_db.get_conference_status.return_value = "active"

        assignment = {
            "id": "assign-1",
            "paper_id": "paper-new",
            "current_paper_id": "paper-current",
            "papers": {
                "id": "paper-new",
                "title": "New Paper",
                "content": "Content",
                "topic_id": "topic-1",
            },
        }
        # Return assignment first time, empty second time
        mock_db.get_pending_assignments.side_effect = [[assignment], []]
        mock_db.list_topics.return_value = [{"id": "topic-1", "name": "Test Topic"}]
        mock_db.get_paper.return_value = {
            "id": "paper-current",
            "title": "Current Paper",
            "content": "Old content",
        }

        mock_gen.return_value = (0.8, "Good paper")

        # Track time to trigger timeout after first loop
        elapsed = [0]

        def fake_time():
            elapsed[0] += 1
            return elapsed[0]

        mock_time.time = fake_time
        mock_time.sleep = MagicMock()

        # max_reviews=1 so it stops after one review
        run_daemon("agent-1", poll_interval=1, timeout_minutes=9999, max_reviews=1)

        # Should have submitted review for w_new
        mock_db.submit_review.assert_any_call(
            mock_sb, "agent-1", "paper-new", 0.8, "Good paper"
        )
        # Should have submitted review for w_current
        mock_db.submit_review.assert_any_call(
            mock_sb, "agent-1", "paper-current", 0.8, "Good paper"
        )
        # Should have marked assignment as completed
        mock_db.mark_assignment_completed.assert_called_once_with(mock_sb, "assign-1")


class TestRunAdminDaemon:
    @patch("conference.daemon.get_client")
    @patch("conference.daemon.db")
    def test_stops_on_timeout(self, mock_db, mock_get_client):
        from conference.daemon import run_admin_daemon

        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_db.get_conference_status.return_value = "active"
        mock_db.list_papers.return_value = []

        run_admin_daemon(poll_interval=1, timeout_minutes=0, min_reviewers=2)

    @patch("conference.daemon.get_client")
    @patch("conference.daemon.db")
    def test_stops_on_pause(self, mock_db, mock_get_client):
        from conference.daemon import run_admin_daemon

        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_db.get_conference_status.return_value = "paused"

        run_admin_daemon(poll_interval=1, timeout_minutes=60, min_reviewers=2)

        mock_db.list_papers.assert_not_called()
