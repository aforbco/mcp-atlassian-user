"""Jira DC user-level extensions for mcp-atlassian.

Adds write-capable, user-facing operations that aren't in the upstream
mcp-atlassian tool surface: Insight/Assets CRUD, vote/rank/attachment/bulk
issue actions, Jira Service Management user workflows, personal
filters/dashboards, subtask hierarchy conversions.

All tools target Jira Data Center. They reuse the authenticated session
already configured on ``JiraFetcher`` by mcp-atlassian — no extra auth.
"""

from .insight_client import InsightClient, InsightError

__all__ = ["InsightClient", "InsightError"]
