"""Jira DC user-level tool registrations.

Adds 39 write-capable, user-facing tools to the ``jira_mcp`` FastMCP
instance — Insight/Assets CRUD, sprint lifecycle, vote/rank/attachment/bulk
issue actions, Jira Service Management user flows, and personal
filters/dashboards.

All endpoint shapes are taken from the verified Atlassian DC documentation:

* Assets REST (DC) — ``/rest/assets/1.0`` with legacy
  ``/rest/insight/1.0`` fallback via ``JIRA_INSIGHT_BASE_PATH``.
  https://docs.atlassian.com/assets/REST/10.4.4/
* Jira Agile REST (DC) — ``/rest/agile/1.0``.
  https://docs.atlassian.com/jira-software/REST/9.17.0/
* Jira Service Management (DC) — ``/rest/servicedeskapi``.
  https://developer.atlassian.com/cloud/jira/service-desk/rest/
  (DC shape identical; DC takes usernames, not accountIds)
* Jira Core REST (DC) — ``/rest/api/2``.
  https://developer.atlassian.com/server/jira/platform/rest/v10000/

Tools that don't have a documented DC REST path are intentionally omitted:
``move_issue`` (project move, UI-only), ``bulk_edit`` (Cloud-only endpoint
in v3), ``convert_to_subtask`` (JRASERVER-27893, UI-only) — flagged in the
verification report that drove this implementation.
"""

import base64
import binascii
import json
import logging
import mimetypes
from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from mcp_atlassian.jira.user_tools.insight_client import InsightClient, InsightError
from mcp_atlassian.servers.dependencies import get_jira_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger("mcp-atlassian.servers.jira_user")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(msg: str, **extra: Any) -> str:
    payload: dict[str, Any] = {"success": False, "error": msg}
    payload.update(extra)
    return _fmt(payload)


def _ok(**data: Any) -> str:
    return _fmt({"success": True, **data})


async def _client(ctx: Context) -> InsightClient:
    fetcher = await get_jira_fetcher(ctx)
    return InsightClient(fetcher)


def _parse_attributes(raw: str | list) -> list[dict[str, Any]]:
    """Normalise the ``attributes`` argument accepted by Insight CRUD tools.

    Accepts either a JSON string or a parsed list. Each entry must be:
      ``{"objectTypeAttributeId": int, "objectAttributeValues": [{"value": ...}]}``
    ``operationType: 0`` is injected by the client if missing.
    """
    if isinstance(raw, list):
        parsed = raw
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"attributes must be valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError("attributes must be a JSON array of attribute objects")
    for entry in parsed:
        if not isinstance(entry, dict):
            raise ValueError("each attribute entry must be an object")
        if "objectTypeAttributeId" not in entry:
            raise ValueError(
                "each attribute entry requires 'objectTypeAttributeId'"
            )
        if "objectAttributeValues" not in entry:
            raise ValueError(
                "each attribute entry requires 'objectAttributeValues'"
            )
    return parsed


def _split_csv(raw: str) -> list[str]:
    return [token.strip() for token in (raw or "").split(",") if token.strip()]


# ---------------------------------------------------------------------------
# Registration entry point
# ---------------------------------------------------------------------------


def register_user_tools(jira_mcp: Any) -> None:  # noqa: C901 — many decorators
    """Attach the user-level toolset to the provided FastMCP instance."""

    # =====================================================================
    # Insight / Assets (CRUD)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "Search Assets (IQL)", "readOnlyHint": True},
    )
    async def asset_search(
        ctx: Context,
        iql: Annotated[
            str,
            Field(
                description=(
                    "IQL/AQL expression, e.g. 'objectType = Server AND "
                    "Name like \"prod\"'. Required."
                )
            ),
        ],
        schema_id: Annotated[
            str,
            Field(description="Optional object-schema id to scope the search."),
        ] = "",
        page: Annotated[int, Field(description="Page number, 1-based.")] = 1,
        per_page: Annotated[int, Field(description="Results per page (1..500).")] = 25,
        include_attributes: Annotated[
            bool, Field(description="Include object attributes in the response.")
        ] = True,
    ) -> str:
        """Search Insight/Assets objects via IQL (GET /aql/objects)."""
        if not iql.strip():
            return _err("iql is required")
        client = await _client(ctx)
        try:
            data = client.search(
                iql.strip(),
                schema_id=schema_id or None,
                page=page,
                per_page=per_page,
                include_attributes=include_attributes,
            )
        except InsightError as exc:
            return _err(f"asset_search failed: {exc}", status=exc.status)
        return _fmt(data)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "Get Asset Object", "readOnlyHint": True},
    )
    async def asset_get(
        ctx: Context,
        object_id: Annotated[str, Field(description="Numeric object id.")],
    ) -> str:
        """Fetch a single Insight object by id."""
        client = await _client(ctx)
        try:
            return _fmt(client.get_object(object_id))
        except InsightError as exc:
            return _err(f"asset_get failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "Get Asset History", "readOnlyHint": True},
    )
    async def asset_get_history(
        ctx: Context,
        object_id: Annotated[str, Field(description="Numeric object id.")],
    ) -> str:
        """Change history for an Insight object (ordered oldest → newest)."""
        client = await _client(ctx)
        try:
            return _fmt(client.object_history(object_id))
        except InsightError as exc:
            return _err(f"asset_get_history failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "List Asset Schemas", "readOnlyHint": True},
    )
    async def asset_list_schemas(ctx: Context) -> str:
        """List all Insight object schemas on the instance."""
        client = await _client(ctx)
        try:
            return _fmt(client.list_schemas())
        except InsightError as exc:
            return _err(f"asset_list_schemas failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "List Asset Object Types", "readOnlyHint": True},
    )
    async def asset_list_types(
        ctx: Context,
        schema_id: Annotated[str, Field(description="Object schema id.")],
    ) -> str:
        """Flat list of object types in a schema (/objectschema/{id}/objecttypes/flat)."""
        client = await _client(ctx)
        try:
            return _fmt(client.list_object_types(schema_id))
        except InsightError as exc:
            return _err(f"asset_list_types failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_assets"},
        annotations={"title": "Get Asset Type Attributes", "readOnlyHint": True},
    )
    async def asset_get_type_attributes(
        ctx: Context,
        object_type_id: Annotated[str, Field(description="Object-type id.")],
    ) -> str:
        """Attribute definitions for an object type — required before building create payloads."""
        client = await _client(ctx)
        try:
            return _fmt(client.get_type_attributes(object_type_id))
        except InsightError as exc:
            return _err(
                f"asset_get_type_attributes failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Create Asset Object"},
    )
    @check_write_access
    async def asset_create(
        ctx: Context,
        object_type_id: Annotated[
            str,
            Field(description="Target object-type id (numeric)."),
        ],
        attributes: Annotated[
            str,
            Field(
                description=(
                    'JSON array of attributes: '
                    '[{"objectTypeAttributeId": 123, '
                    '"objectAttributeValues": [{"value": "foo"}]}]. '
                    "operationType=0 (ADD) is injected automatically."
                )
            ),
        ],
    ) -> str:
        """Create a new Insight object (POST /object/create)."""
        try:
            attrs = _parse_attributes(attributes)
        except ValueError as exc:
            return _err(str(exc))
        client = await _client(ctx)
        try:
            return _fmt(client.create_object(object_type_id, attrs))
        except InsightError as exc:
            return _err(f"asset_create failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Update Asset Object"},
    )
    @check_write_access
    async def asset_update(
        ctx: Context,
        object_id: Annotated[str, Field(description="Object id to update.")],
        attributes: Annotated[
            str,
            Field(
                description=(
                    "JSON array of attribute entries to update — same shape as "
                    "asset_create. Only included attributes are changed."
                )
            ),
        ],
    ) -> str:
        """Update an object's attributes (PUT /object/{id})."""
        try:
            attrs = _parse_attributes(attributes)
        except ValueError as exc:
            return _err(str(exc))
        client = await _client(ctx)
        try:
            return _fmt(client.update_object(object_id, attrs))
        except InsightError as exc:
            return _err(f"asset_update failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Delete Asset Object", "destructiveHint": True},
    )
    @check_write_access
    async def asset_delete(
        ctx: Context,
        object_id: Annotated[str, Field(description="Object id to delete.")],
    ) -> str:
        """Permanently delete an Insight object."""
        client = await _client(ctx)
        try:
            return _fmt(client.delete_object(object_id))
        except InsightError as exc:
            return _err(f"asset_delete failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Set Asset Attribute"},
    )
    @check_write_access
    async def asset_set_attribute(
        ctx: Context,
        object_id: Annotated[str, Field(description="Object id to update.")],
        attribute_id: Annotated[
            str, Field(description="Numeric objectTypeAttributeId to set.")
        ],
        value: Annotated[
            str,
            Field(
                description=(
                    "New value. For reference attributes pass the referenced "
                    "object id as a string. For multi-value attributes pass "
                    "JSON array, e.g. '[\"a\", \"b\"]'."
                )
            ),
        ],
    ) -> str:
        """Convenience wrapper — set one attribute without building a full payload."""
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError
            values = [{"value": v} for v in parsed]
        except (json.JSONDecodeError, ValueError):
            values = [{"value": value}]
        attrs = [
            {"objectTypeAttributeId": int(attribute_id), "objectAttributeValues": values}
        ]
        client = await _client(ctx)
        try:
            return _fmt(client.update_object(object_id, attrs))
        except InsightError as exc:
            return _err(f"asset_set_attribute failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Add Asset Reference"},
    )
    @check_write_access
    async def asset_add_reference(
        ctx: Context,
        object_id: Annotated[str, Field(description="Source object id.")],
        attribute_id: Annotated[
            str, Field(description="Reference-type objectTypeAttributeId.")
        ],
        referenced_object_ids: Annotated[
            str,
            Field(description="Comma-separated list of target object ids."),
        ],
    ) -> str:
        """Append referenced object ids to a reference attribute (union with existing)."""
        ids = _split_csv(referenced_object_ids)
        if not ids:
            return _err("referenced_object_ids is required")
        client = await _client(ctx)
        try:
            return _fmt(client.add_reference(object_id, attribute_id, ids))
        except InsightError as exc:
            return _err(f"asset_add_reference failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Remove Asset Reference", "destructiveHint": True},
    )
    @check_write_access
    async def asset_remove_reference(
        ctx: Context,
        object_id: Annotated[str, Field(description="Source object id.")],
        attribute_id: Annotated[
            str, Field(description="Reference-type objectTypeAttributeId.")
        ],
        referenced_object_ids: Annotated[
            str,
            Field(description="Comma-separated ids to remove from the reference."),
        ],
    ) -> str:
        """Drop referenced object ids from a reference attribute."""
        ids = _split_csv(referenced_object_ids)
        if not ids:
            return _err("referenced_object_ids is required")
        client = await _client(ctx)
        try:
            return _fmt(client.remove_reference(object_id, attribute_id, ids))
        except InsightError as exc:
            return _err(
                f"asset_remove_reference failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Attach Asset to Issue"},
    )
    @check_write_access
    async def asset_attach_to_issue(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key, e.g. 'PROJ-12'.")],
        field_id: Annotated[
            str,
            Field(
                description=(
                    "Insight/Assets custom field id on the issue, e.g. "
                    "'customfield_11001' (instance-specific)."
                )
            ),
        ],
        object_keys: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated object keys (Insight key format, e.g. 'CMDB-42')."
                )
            ),
        ],
    ) -> str:
        """Set the Insight custom field on an issue to reference the given asset keys."""
        keys = _split_csv(object_keys)
        if not keys:
            return _err("object_keys is required")
        client = await _client(ctx)
        payload = {"fields": {field_id: [{"key": key} for key in keys]}}
        try:
            client.put(f"/rest/api/2/issue/{issue_key}", payload)
        except InsightError as exc:
            return _err(
                f"asset_attach_to_issue failed: {exc}", status=exc.status
            )
        return _ok(issue_key=issue_key, field_id=field_id, attached=keys)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_assets"},
        annotations={"title": "Detach Asset from Issue", "destructiveHint": True},
    )
    @check_write_access
    async def asset_detach_from_issue(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
        field_id: Annotated[
            str, Field(description="Insight/Assets custom field id.")
        ],
    ) -> str:
        """Clear the Insight custom field on an issue (set to empty array)."""
        client = await _client(ctx)
        payload = {"fields": {field_id: []}}
        try:
            client.put(f"/rest/api/2/issue/{issue_key}", payload)
        except InsightError as exc:
            return _err(
                f"asset_detach_from_issue failed: {exc}", status=exc.status
            )
        return _ok(issue_key=issue_key, field_id=field_id, cleared=True)

    # =====================================================================
    # Sprint lifecycle (complements upstream's create/update/add_issues)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_sprints"},
        annotations={"title": "Start Sprint"},
    )
    @check_write_access
    async def start_sprint(
        ctx: Context,
        sprint_id: Annotated[str, Field(description="Sprint id.")],
        start_date: Annotated[
            str,
            Field(
                description=(
                    "ISO 8601 start date (required by DC when activating). "
                    "Example: '2026-04-25T09:00:00.000+0000'."
                )
            ),
        ],
        end_date: Annotated[
            str, Field(description="ISO 8601 end date (required by DC).")
        ],
        goal: Annotated[str, Field(description="Optional sprint goal.")] = "",
    ) -> str:
        """Activate a sprint. DC requires ``startDate`` + ``endDate`` together with state."""
        client = await _client(ctx)
        body: dict[str, Any] = {
            "state": "active",
            "startDate": start_date,
            "endDate": end_date,
        }
        if goal:
            body["goal"] = goal
        try:
            data = client.post(f"/rest/agile/1.0/sprint/{sprint_id}", body)
        except InsightError as exc:
            return _err(f"start_sprint failed: {exc}", status=exc.status)
        return _fmt(data)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_sprints"},
        annotations={"title": "Complete Sprint"},
    )
    @check_write_access
    async def complete_sprint(
        ctx: Context,
        sprint_id: Annotated[str, Field(description="Sprint id.")],
    ) -> str:
        """Close a sprint (state → ``closed``)."""
        client = await _client(ctx)
        try:
            data = client.post(
                f"/rest/agile/1.0/sprint/{sprint_id}", {"state": "closed"}
            )
        except InsightError as exc:
            return _err(f"complete_sprint failed: {exc}", status=exc.status)
        return _fmt(data)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_sprints"},
        annotations={"title": "Delete Sprint", "destructiveHint": True},
    )
    @check_write_access
    async def delete_sprint(
        ctx: Context,
        sprint_id: Annotated[str, Field(description="Sprint id.")],
    ) -> str:
        """Delete a sprint — issues revert to the backlog / previous sprint."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/agile/1.0/sprint/{sprint_id}")
        except InsightError as exc:
            return _err(f"delete_sprint failed: {exc}", status=exc.status)
        return _ok(sprint_id=sprint_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_sprints"},
        annotations={"title": "Move Issues to Backlog"},
    )
    @check_write_access
    async def move_issues_to_backlog(
        ctx: Context,
        issue_keys: Annotated[
            str,
            Field(description="Comma-separated issue keys to move to backlog."),
        ],
    ) -> str:
        """POST /rest/agile/1.0/backlog/issue — remove issues from any sprint."""
        keys = _split_csv(issue_keys)
        if not keys:
            return _err("issue_keys is required")
        client = await _client(ctx)
        try:
            client.post("/rest/agile/1.0/backlog/issue", {"issues": keys})
        except InsightError as exc:
            return _err(
                f"move_issues_to_backlog failed: {exc}", status=exc.status
            )
        return _ok(moved=keys)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_sprints"},
        annotations={"title": "Rank Issues"},
    )
    @check_write_access
    async def rank_issues(
        ctx: Context,
        issue_keys: Annotated[
            str,
            Field(description="Comma-separated issue keys to reorder."),
        ],
        rank_before_issue: Annotated[
            str,
            Field(
                description="Anchor issue key — place the provided keys BEFORE this one."
            ),
        ] = "",
        rank_after_issue: Annotated[
            str,
            Field(
                description="Anchor issue key — place the provided keys AFTER this one."
            ),
        ] = "",
        rank_custom_field_id: Annotated[
            str,
            Field(
                description="Rank custom field id (e.g. 10011). Optional; recommended."
            ),
        ] = "",
    ) -> str:
        """Reorder issues in the backlog / sprint (PUT /rest/agile/1.0/issue/rank)."""
        keys = _split_csv(issue_keys)
        if not keys:
            return _err("issue_keys is required")
        if bool(rank_before_issue) == bool(rank_after_issue):
            return _err(
                "provide exactly one of rank_before_issue / rank_after_issue"
            )
        body: dict[str, Any] = {"issues": keys}
        if rank_before_issue:
            body["rankBeforeIssue"] = rank_before_issue
        if rank_after_issue:
            body["rankAfterIssue"] = rank_after_issue
        if rank_custom_field_id:
            try:
                body["rankCustomFieldId"] = int(rank_custom_field_id)
            except ValueError:
                return _err("rank_custom_field_id must be numeric")
        client = await _client(ctx)
        try:
            return _fmt(client.put("/rest/agile/1.0/issue/rank", body))
        except InsightError as exc:
            return _err(f"rank_issues failed: {exc}", status=exc.status)

    # =====================================================================
    # Issue extras (votes, attachments, deletes, bulk, clone)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Add Vote"},
    )
    @check_write_access
    async def add_vote(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
    ) -> str:
        """Cast the authenticated user's vote on an issue (204 = success)."""
        client = await _client(ctx)
        try:
            client.post(f"/rest/api/2/issue/{issue_key}/votes")
        except InsightError as exc:
            return _err(f"add_vote failed: {exc}", status=exc.status)
        return _ok(issue_key=issue_key, voted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Remove Vote"},
    )
    @check_write_access
    async def remove_vote(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
    ) -> str:
        """Withdraw the authenticated user's vote."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/api/2/issue/{issue_key}/votes")
        except InsightError as exc:
            return _err(f"remove_vote failed: {exc}", status=exc.status)
        return _ok(issue_key=issue_key, voted=False)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Upload Attachment"},
    )
    @check_write_access
    async def upload_attachment(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
        filename: Annotated[
            str,
            Field(description="File name to show in Jira (e.g. 'report.pdf')."),
        ],
        content_base64: Annotated[
            str,
            Field(description="File content, base64-encoded (no data: prefix)."),
        ],
        content_type: Annotated[
            str,
            Field(
                description="Optional MIME type. Inferred from filename if omitted."
            ),
        ] = "",
    ) -> str:
        """POST /rest/api/2/issue/{key}/attachments (multipart, ``X-Atlassian-Token: no-check``)."""
        try:
            payload = base64.b64decode(content_base64, validate=True)
        except binascii.Error as exc:
            return _err(f"content_base64 is not valid base64: {exc}")
        mime = content_type or (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )
        client = await _client(ctx)
        try:
            data = client.post_multipart(
                f"/rest/api/2/issue/{issue_key}/attachments",
                files=[("file", (filename, payload, mime))],
            )
        except InsightError as exc:
            return _err(f"upload_attachment failed: {exc}", status=exc.status)
        return _fmt(data)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Delete Attachment", "destructiveHint": True},
    )
    @check_write_access
    async def delete_attachment(
        ctx: Context,
        attachment_id: Annotated[str, Field(description="Attachment id to delete.")],
    ) -> str:
        """DELETE /rest/api/2/attachment/{id}."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/api/2/attachment/{attachment_id}")
        except InsightError as exc:
            return _err(f"delete_attachment failed: {exc}", status=exc.status)
        return _ok(attachment_id=attachment_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Delete Comment", "destructiveHint": True},
    )
    @check_write_access
    async def delete_comment(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
        comment_id: Annotated[str, Field(description="Comment id to delete.")],
    ) -> str:
        """DELETE /rest/api/2/issue/{key}/comment/{id}."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/api/2/issue/{issue_key}/comment/{comment_id}")
        except InsightError as exc:
            return _err(f"delete_comment failed: {exc}", status=exc.status)
        return _ok(issue_key=issue_key, comment_id=comment_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Delete Worklog", "destructiveHint": True},
    )
    @check_write_access
    async def delete_worklog(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
        worklog_id: Annotated[str, Field(description="Worklog id to delete.")],
    ) -> str:
        """DELETE /rest/api/2/issue/{key}/worklog/{id}."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/api/2/issue/{issue_key}/worklog/{worklog_id}")
        except InsightError as exc:
            return _err(f"delete_worklog failed: {exc}", status=exc.status)
        return _ok(issue_key=issue_key, worklog_id=worklog_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Bulk Assign Issues"},
    )
    @check_write_access
    async def bulk_assign(
        ctx: Context,
        jql: Annotated[
            str,
            Field(description="JQL selecting the issues to reassign. Required."),
        ],
        assignee: Annotated[
            str,
            Field(
                description=(
                    "Target assignee username on DC (use '-1' to unassign). "
                    "Cloud accountIds not supported here."
                )
            ),
        ],
        max_issues: Annotated[
            int,
            Field(description="Safety cap on the number of issues (1..500)."),
        ] = 100,
    ) -> str:
        """Resolve a JQL and set ``assignee`` on each returned issue."""
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        limit = max(1, min(int(max_issues), 500))
        try:
            search = client.get(
                "/rest/api/2/search",
                params={"jql": jql, "maxResults": limit, "fields": "summary"},
            )
        except InsightError as exc:
            return _err(f"bulk_assign search failed: {exc}", status=exc.status)
        issues = (search or {}).get("issues") or []
        updated: list[str] = []
        errors: list[dict[str, Any]] = []
        for issue in issues:
            key = issue.get("key")
            if not key:
                continue
            try:
                client.put(
                    f"/rest/api/2/issue/{key}",
                    {"fields": {"assignee": {"name": assignee}}},
                )
                updated.append(key)
            except InsightError as exc:
                errors.append({"key": key, "error": str(exc)})
        return _ok(matched=len(issues), updated=updated, errors=errors)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Bulk Add Labels"},
    )
    @check_write_access
    async def bulk_label(
        ctx: Context,
        jql: Annotated[str, Field(description="JQL selecting target issues.")],
        labels: Annotated[
            str,
            Field(description="Comma-separated labels to ADD (not replace)."),
        ],
        max_issues: Annotated[
            int, Field(description="Safety cap 1..500.")
        ] = 100,
    ) -> str:
        """Add labels to every issue matching ``jql`` via the ``add`` update operation."""
        label_list = _split_csv(labels)
        if not label_list:
            return _err("labels is required")
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        limit = max(1, min(int(max_issues), 500))
        try:
            search = client.get(
                "/rest/api/2/search",
                params={"jql": jql, "maxResults": limit, "fields": "labels"},
            )
        except InsightError as exc:
            return _err(f"bulk_label search failed: {exc}", status=exc.status)
        updates = [{"add": label} for label in label_list]
        issues = (search or {}).get("issues") or []
        updated: list[str] = []
        errors: list[dict[str, Any]] = []
        for issue in issues:
            key = issue.get("key")
            if not key:
                continue
            try:
                client.put(
                    f"/rest/api/2/issue/{key}",
                    {"update": {"labels": updates}},
                )
                updated.append(key)
            except InsightError as exc:
                errors.append({"key": key, "error": str(exc)})
        return _ok(
            matched=len(issues),
            labels_added=label_list,
            updated=updated,
            errors=errors,
        )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Bulk Add Comment"},
    )
    @check_write_access
    async def bulk_add_comment(
        ctx: Context,
        jql: Annotated[str, Field(description="JQL selecting target issues.")],
        body: Annotated[str, Field(description="Comment body (wiki markup).")],
        max_issues: Annotated[
            int, Field(description="Safety cap 1..500.")
        ] = 100,
    ) -> str:
        """Add the same comment to every issue matching ``jql``."""
        if not body.strip():
            return _err("body is required")
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        limit = max(1, min(int(max_issues), 500))
        try:
            search = client.get(
                "/rest/api/2/search",
                params={"jql": jql, "maxResults": limit, "fields": "summary"},
            )
        except InsightError as exc:
            return _err(f"bulk_add_comment search failed: {exc}", status=exc.status)
        issues = (search or {}).get("issues") or []
        updated: list[str] = []
        errors: list[dict[str, Any]] = []
        for issue in issues:
            key = issue.get("key")
            if not key:
                continue
            try:
                client.post(
                    f"/rest/api/2/issue/{key}/comment", {"body": body}
                )
                updated.append(key)
            except InsightError as exc:
                errors.append({"key": key, "error": str(exc)})
        return _ok(matched=len(issues), commented=updated, errors=errors)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Clone Issue"},
    )
    @check_write_access
    async def clone_issue(
        ctx: Context,
        source_issue_key: Annotated[
            str, Field(description="Issue to clone (source).")
        ],
        target_project_key: Annotated[
            str,
            Field(
                description=(
                    "Target project key. Same project = straight clone; "
                    "different project = cross-project clone."
                )
            ),
        ] = "",
        summary_prefix: Annotated[
            str,
            Field(description="Prefix prepended to the source summary."),
        ] = "CLONE - ",
        copy_fields: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated list of extra fields to copy from source, "
                    "e.g. 'priority,labels,components,versions'. "
                    "'summary' and 'issuetype' are always copied."
                )
            ),
        ] = "priority,labels,components,versions",
    ) -> str:
        """Create a new issue with selected fields copied from an existing one."""
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        try:
            source = client.get(f"/rest/api/2/issue/{source_issue_key}")
        except InsightError as exc:
            return _err(f"clone_issue: source fetch failed: {exc}", status=exc.status)
        src_fields = (source or {}).get("fields") or {}
        project_key = target_project_key or (
            (src_fields.get("project") or {}).get("key")
        )
        if not project_key:
            return _err("target_project_key could not be determined")
        summary = f"{summary_prefix}{src_fields.get('summary', '')}".rstrip()
        issuetype = (src_fields.get("issuetype") or {}).get("name", "Task")
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issuetype},
        }
        wanted = {name for name in _split_csv(copy_fields)}
        for name in wanted:
            value = src_fields.get(name)
            if value is None:
                continue
            fields[name] = value
        try:
            created = client.post("/rest/api/2/issue", {"fields": fields})
        except InsightError as exc:
            return _err(f"clone_issue create failed: {exc}", status=exc.status)
        return _fmt(created)

    # =====================================================================
    # Jira Service Management (user flows)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_jsm"},
        annotations={"title": "Create JSM Customer Request"},
    )
    @check_write_access
    async def jsm_create_request(
        ctx: Context,
        service_desk_id: Annotated[
            str, Field(description="Service desk id (numeric string).")
        ],
        request_type_id: Annotated[
            str, Field(description="Request type id (numeric string).")
        ],
        summary: Annotated[str, Field(description="Request summary.")],
        description: Annotated[
            str, Field(description="Request description (wiki markup).")
        ] = "",
        raise_on_behalf_of: Annotated[
            str,
            Field(description="Optional DC username to raise on behalf of."),
        ] = "",
        request_participants: Annotated[
            str,
            Field(description="Comma-separated DC usernames to add as participants."),
        ] = "",
        request_field_values_json: Annotated[
            str,
            Field(
                description=(
                    "Optional JSON object of extra requestFieldValues, merged "
                    "with summary/description. Keys are field IDs."
                )
            ),
        ] = "",
    ) -> str:
        """POST /rest/servicedeskapi/request (DC — uses usernames, not accountIds)."""
        field_values: dict[str, Any] = {"summary": summary}
        if description:
            field_values["description"] = description
        if request_field_values_json:
            try:
                extra = json.loads(request_field_values_json)
            except json.JSONDecodeError as exc:
                return _err(f"request_field_values_json is not valid JSON: {exc}")
            if not isinstance(extra, dict):
                return _err("request_field_values_json must be a JSON object")
            field_values.update(extra)
        body: dict[str, Any] = {
            "serviceDeskId": service_desk_id,
            "requestTypeId": request_type_id,
            "requestFieldValues": field_values,
        }
        if raise_on_behalf_of:
            body["raiseOnBehalfOf"] = raise_on_behalf_of
        participants = _split_csv(request_participants)
        if participants:
            body["requestParticipants"] = participants
        client = await _client(ctx)
        try:
            return _fmt(client.post("/rest/servicedeskapi/request", body))
        except InsightError as exc:
            return _err(f"jsm_create_request failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_jsm"},
        annotations={"title": "Answer JSM Approval"},
    )
    @check_write_access
    async def jsm_answer_approval(
        ctx: Context,
        issue_key: Annotated[str, Field(description="JSM request issue key.")],
        approval_id: Annotated[str, Field(description="Approval id on the request.")],
        decision: Annotated[
            str,
            Field(description="Either 'approve' or 'decline'."),
        ],
    ) -> str:
        """POST /rest/servicedeskapi/request/{key}/approval/{id} with ``{decision}``."""
        if decision not in ("approve", "decline"):
            return _err("decision must be 'approve' or 'decline'")
        client = await _client(ctx)
        try:
            return _fmt(
                client.post(
                    f"/rest/servicedeskapi/request/{issue_key}/approval/{approval_id}",
                    {"decision": decision},
                )
            )
        except InsightError as exc:
            return _err(f"jsm_answer_approval failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_jsm"},
        annotations={"title": "Add JSM Request Comment"},
    )
    @check_write_access
    async def jsm_add_request_comment(
        ctx: Context,
        issue_key: Annotated[str, Field(description="JSM request issue key.")],
        body: Annotated[str, Field(description="Comment body (wiki markup).")],
        public: Annotated[
            bool,
            Field(
                description="True = visible to customer; False = internal/agent-only."
            ),
        ] = True,
    ) -> str:
        """POST /rest/servicedeskapi/request/{key}/comment with ``{body, public}``."""
        if not body.strip():
            return _err("body is required")
        client = await _client(ctx)
        try:
            return _fmt(
                client.post(
                    f"/rest/servicedeskapi/request/{issue_key}/comment",
                    {"body": body, "public": bool(public)},
                )
            )
        except InsightError as exc:
            return _err(f"jsm_add_request_comment failed: {exc}", status=exc.status)

    # =====================================================================
    # Personal filters & dashboards
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Create Filter"},
    )
    @check_write_access
    async def create_filter(
        ctx: Context,
        name: Annotated[str, Field(description="Filter name.")],
        jql: Annotated[str, Field(description="JQL body of the filter.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
        favourite: Annotated[
            bool, Field(description="Mark as favourite for the current user.")
        ] = False,
    ) -> str:
        """POST /rest/api/2/filter."""
        body: dict[str, Any] = {
            "name": name,
            "jql": jql,
            "favourite": bool(favourite),
        }
        if description:
            body["description"] = description
        client = await _client(ctx)
        try:
            return _fmt(client.post("/rest/api/2/filter", body))
        except InsightError as exc:
            return _err(f"create_filter failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Update Filter"},
    )
    @check_write_access
    async def update_filter(
        ctx: Context,
        filter_id: Annotated[str, Field(description="Filter id.")],
        name: Annotated[str, Field(description="New name (pass existing to keep).")],
        jql: Annotated[str, Field(description="New JQL.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
    ) -> str:
        """PUT /rest/api/2/filter/{id} — full replace of name/jql/description."""
        body: dict[str, Any] = {"name": name, "jql": jql}
        if description:
            body["description"] = description
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/api/2/filter/{filter_id}", body))
        except InsightError as exc:
            return _err(f"update_filter failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Delete Filter", "destructiveHint": True},
    )
    @check_write_access
    async def delete_filter(
        ctx: Context,
        filter_id: Annotated[str, Field(description="Filter id to delete.")],
    ) -> str:
        """DELETE /rest/api/2/filter/{id}."""
        client = await _client(ctx)
        try:
            client.delete(f"/rest/api/2/filter/{filter_id}")
        except InsightError as exc:
            return _err(f"delete_filter failed: {exc}", status=exc.status)
        return _ok(filter_id=filter_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Share Filter"},
    )
    @check_write_access
    async def share_filter(
        ctx: Context,
        filter_id: Annotated[str, Field(description="Filter id.")],
        share_type: Annotated[
            str,
            Field(
                description=(
                    "One of 'group', 'project', 'projectRole', 'global', "
                    "'authenticated'. DC-specific shape: group uses 'groupname'."
                )
            ),
        ],
        group_name: Annotated[
            str,
            Field(description="Group name for share_type='group'."),
        ] = "",
        project_id: Annotated[
            str,
            Field(description="Project id for share_type='project' or 'projectRole'."),
        ] = "",
        project_role_id: Annotated[
            str, Field(description="Project role id for 'projectRole'.")
        ] = "",
    ) -> str:
        """POST /rest/api/2/filter/{id}/permission — add a share permission."""
        body: dict[str, Any]
        if share_type == "group":
            if not group_name:
                return _err("group_name is required for share_type='group'")
            body = {"type": "group", "groupname": group_name}
        elif share_type == "project":
            if not project_id:
                return _err("project_id is required for share_type='project'")
            body = {"type": "project", "projectId": project_id}
        elif share_type == "projectRole":
            if not project_id or not project_role_id:
                return _err(
                    "project_id and project_role_id are required for 'projectRole'"
                )
            body = {
                "type": "project",
                "projectId": project_id,
                "projectRoleId": project_role_id,
            }
        elif share_type in ("global", "authenticated"):
            body = {"type": share_type}
        else:
            return _err(f"unknown share_type '{share_type}'")
        client = await _client(ctx)
        try:
            return _fmt(
                client.post(f"/rest/api/2/filter/{filter_id}/permission", body)
            )
        except InsightError as exc:
            return _err(f"share_filter failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Create Dashboard"},
    )
    @check_write_access
    async def create_dashboard(
        ctx: Context,
        name: Annotated[str, Field(description="Dashboard name.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
        share_permissions_json: Annotated[
            str,
            Field(
                description=(
                    "Optional JSON array of share permission objects "
                    '(e.g. [{"type":"global"}]). Default: private to current user.'
                )
            ),
        ] = "",
    ) -> str:
        """POST /rest/api/2/dashboard."""
        body: dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        if share_permissions_json:
            try:
                perms = json.loads(share_permissions_json)
            except json.JSONDecodeError as exc:
                return _err(f"share_permissions_json invalid: {exc}")
            if not isinstance(perms, list):
                return _err("share_permissions_json must be a JSON array")
            body["sharePermissions"] = perms
        client = await _client(ctx)
        try:
            return _fmt(client.post("/rest/api/2/dashboard", body))
        except InsightError as exc:
            return _err(f"create_dashboard failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Update Dashboard"},
    )
    @check_write_access
    async def update_dashboard(
        ctx: Context,
        dashboard_id: Annotated[str, Field(description="Dashboard id.")],
        name: Annotated[str, Field(description="Dashboard name.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
    ) -> str:
        """PUT /rest/api/2/dashboard/{id}."""
        body: dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/api/2/dashboard/{dashboard_id}", body))
        except InsightError as exc:
            return _err(f"update_dashboard failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_filters"},
        annotations={"title": "Copy Dashboard"},
    )
    @check_write_access
    async def copy_dashboard(
        ctx: Context,
        dashboard_id: Annotated[str, Field(description="Source dashboard id.")],
        name: Annotated[str, Field(description="Name for the new dashboard.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
    ) -> str:
        """POST /rest/api/2/dashboard/{id}/copy."""
        body: dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        client = await _client(ctx)
        try:
            return _fmt(
                client.post(f"/rest/api/2/dashboard/{dashboard_id}/copy", body)
            )
        except InsightError as exc:
            return _err(f"copy_dashboard failed: {exc}", status=exc.status)
