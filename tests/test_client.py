"""Tests for client.py helper functions."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from conference import client as db


def _make_chainable_query(data):
    """Create a mock query builder where all methods return self and execute returns data."""
    q = MagicMock()
    for method in ("select", "insert", "update", "eq", "gte", "order", "limit", "single"):
        getattr(q, method).return_value = q
    q.execute.return_value = MagicMock(data=data)
    return q


def _mock_client(table_data: dict[str, object] | None = None):
    """Create a mock Supabase client.

    table_data maps table names to the data that execute() should return.
    """
    table_data = table_data or {}
    client = MagicMock()

    def table(name):
        data = table_data.get(name, [])
        return _make_chainable_query(data)

    client.table = MagicMock(side_effect=table)
    return client


class TestGetAgent:
    def test_returns_agent_data(self):
        agent_data = {"id": "agent-1", "name": "Alice", "expertise": "ML"}
        sb = _mock_client({"agents": agent_data})

        result = db.get_agent(sb, "agent-1")
        assert result == agent_data


class TestListActiveAgents:
    def test_returns_active_agents(self):
        now = datetime.now(timezone.utc)
        active_agents = [
            {"id": "a1", "name": "Alice", "last_seen": now.isoformat()},
        ]
        sb = _mock_client({"agents": active_agents})

        result = db.list_active_agents(sb, timeout_minutes=5)
        assert result == active_agents


class TestUpdateHeartbeat:
    def test_returns_updated_agent(self):
        updated = [{"id": "agent-1", "last_seen": "2026-01-01T00:00:00+00:00"}]
        sb = _mock_client({"agents": updated})

        result = db.update_heartbeat(sb, "agent-1")
        assert result == updated[0]


class TestGetPendingAssignments:
    def test_returns_pending_assignments(self):
        assignments = [
            {"id": "a1", "reviewer_id": "r1", "paper_id": "p1", "status": "pending"}
        ]
        sb = _mock_client({"review_assignments": assignments})

        result = db.get_pending_assignments(sb, "r1")
        assert result == assignments


class TestMarkAssignmentCompleted:
    def test_returns_completed_assignment(self):
        updated = [{"id": "a1", "status": "completed"}]
        sb = _mock_client({"review_assignments": updated})

        result = db.mark_assignment_completed(sb, "a1")
        assert result["status"] == "completed"


class TestConferenceStatus:
    def test_get_conference_status(self):
        sb = _mock_client({"conference_config": {"value": "active"}})

        result = db.get_conference_status(sb)
        assert result == "active"

    def test_set_conference_status(self):
        sb = _mock_client(
            {"conference_config": [{"key": "status", "value": "paused"}]}
        )

        result = db.set_conference_status(sb, "paused")
        assert result["value"] == "paused"


class TestCreateReviewAssignmentsActiveFiltering:
    def test_uses_active_agents_when_enough(self):
        """When enough active agents exist, they should be used instead of all agents."""
        call_count = {"agents": 0}

        sb = MagicMock()

        def table(name):
            if name == "papers":
                return _make_chainable_query(
                    {"id": "p1", "agent_id": "author", "topic_id": "t1"}
                )
            elif name == "agents":
                call_count["agents"] += 1
                if call_count["agents"] == 1:
                    # list_active_agents — 3 agents (enough for min_reviewers=2)
                    return _make_chainable_query([
                        {"id": "author", "name": "Author"},
                        {"id": "r1", "name": "Reviewer1"},
                        {"id": "r2", "name": "Reviewer2"},
                    ])
                else:
                    # list_agents fallback (should not reach here in this test)
                    return _make_chainable_query([])
            elif name == "accepted_papers":
                return _make_chainable_query([])
            elif name == "review_assignments":
                return _make_chainable_query([
                    {"reviewer_id": "r1", "paper_id": "p1", "current_paper_id": None},
                ])
            return _make_chainable_query([])

        sb.table = MagicMock(side_effect=table)

        result = db.create_review_assignments(sb, "p1", "t1", min_reviewers=2)
        assert len(result) >= 1

    def test_falls_back_to_all_agents_when_not_enough_active(self):
        """When not enough active agents, should fall back to list_agents."""
        call_count = {"agents": 0}

        sb = MagicMock()

        def table(name):
            if name == "papers":
                return _make_chainable_query(
                    {"id": "p1", "agent_id": "author", "topic_id": "t1"}
                )
            elif name == "agents":
                call_count["agents"] += 1
                if call_count["agents"] == 1:
                    # list_active_agents — only 1 agent (not enough)
                    return _make_chainable_query([
                        {"id": "r1", "name": "Reviewer1"},
                    ])
                else:
                    # list_agents fallback
                    return _make_chainable_query([
                        {"id": "author", "name": "Author"},
                        {"id": "r1", "name": "Reviewer1"},
                        {"id": "r2", "name": "Reviewer2"},
                    ])
            elif name == "accepted_papers":
                return _make_chainable_query([])
            elif name == "review_assignments":
                return _make_chainable_query([
                    {"reviewer_id": "r1", "paper_id": "p1", "current_paper_id": None},
                ])
            return _make_chainable_query([])

        sb.table = MagicMock(side_effect=table)

        result = db.create_review_assignments(sb, "p1", "t1", min_reviewers=2)
        # Should have called agents table twice (active + fallback)
        assert call_count["agents"] == 2
        assert len(result) >= 1
