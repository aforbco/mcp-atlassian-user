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

    # =====================================================================
    # Worklog update (complements upstream add + this fork's delete)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_issues"},
        annotations={"title": "Update Worklog"},
    )
    @check_write_access
    async def update_worklog(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Jira issue key.")],
        worklog_id: Annotated[str, Field(description="Worklog id.")],
        time_spent: Annotated[
            str,
            Field(
                description=(
                    "New time in Jira format (e.g. '2h 30m'). "
                    "Mutually exclusive with time_spent_seconds."
                )
            ),
        ] = "",
        time_spent_seconds: Annotated[
            str,
            Field(description="New time in seconds (integer string)."),
        ] = "",
        comment: Annotated[str, Field(description="New comment body.")] = "",
        started: Annotated[
            str,
            Field(
                description=(
                    "ISO 8601 with ms+offset, e.g. '2026-04-24T10:17:53.145+0000'."
                )
            ),
        ] = "",
        visibility_json: Annotated[
            str,
            Field(
                description=(
                    'Optional JSON visibility, e.g. '
                    '\'{"type":"group","value":"jira-developers"}\'. '
                    "type must be 'group' or 'role' on DC."
                )
            ),
        ] = "",
        adjust_estimate: Annotated[
            str,
            Field(
                description=(
                    "Estimate adjustment: 'new' (requires new_estimate), "
                    "'leave', or 'auto' (default on server)."
                )
            ),
        ] = "",
        new_estimate: Annotated[
            str,
            Field(
                description="Required when adjust_estimate='new' (e.g. '1d')."
            ),
        ] = "",
    ) -> str:
        """PUT /rest/api/2/issue/{key}/worklog/{id} — at least one field required."""
        if time_spent and time_spent_seconds:
            return _err("pass only one of time_spent / time_spent_seconds")
        body: dict[str, Any] = {}
        if time_spent:
            body["timeSpent"] = time_spent
        if time_spent_seconds:
            try:
                body["timeSpentSeconds"] = int(time_spent_seconds)
            except ValueError:
                return _err("time_spent_seconds must be an integer")
        if comment:
            body["comment"] = comment
        if started:
            body["started"] = started
        if visibility_json:
            try:
                vis = json.loads(visibility_json)
            except json.JSONDecodeError as exc:
                return _err(f"visibility_json invalid: {exc}")
            if not isinstance(vis, dict):
                return _err("visibility_json must be a JSON object")
            body["visibility"] = vis
        if not body:
            return _err("at least one field must be provided")
        query_parts: list[str] = []
        if adjust_estimate:
            if adjust_estimate not in ("new", "leave", "auto"):
                return _err(
                    "adjust_estimate must be 'new', 'leave', or 'auto' (DC)"
                )
            query_parts.append(f"adjustEstimate={adjust_estimate}")
            if adjust_estimate == "new":
                if not new_estimate:
                    return _err(
                        "new_estimate is required when adjust_estimate='new'"
                    )
                query_parts.append(f"newEstimate={new_estimate}")
        path = f"/rest/api/2/issue/{issue_key}/worklog/{worklog_id}"
        if query_parts:
            path = f"{path}?{'&'.join(query_parts)}"
        client = await _client(ctx)
        try:
            return _fmt(client.put(path, body))
        except InsightError as exc:
            return _err(f"update_worklog failed: {exc}", status=exc.status)

    # =====================================================================
    # Version lifecycle
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Update Version"},
    )
    @check_write_access
    async def update_version(
        ctx: Context,
        version_id: Annotated[str, Field(description="Version id.")],
        name: Annotated[str, Field(description="New name (optional).")] = "",
        description: Annotated[str, Field(description="New description.")] = "",
        user_start_date: Annotated[
            str,
            Field(
                description=(
                    "Start date in user format, e.g. '6/Jul/2010'. "
                    "DC schema uses userStartDate, not startDate."
                )
            ),
        ] = "",
        user_release_date: Annotated[
            str, Field(description="Release date in user format.")
        ] = "",
        archived: Annotated[
            str,
            Field(
                description="'true' or 'false' to change archived flag (omit to keep)."
            ),
        ] = "",
        released: Annotated[
            str, Field(description="'true' or 'false'.")
        ] = "",
    ) -> str:
        """PUT /rest/api/2/version/{id} — partial update (only included fields change)."""
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        if user_start_date:
            body["userStartDate"] = user_start_date
        if user_release_date:
            body["userReleaseDate"] = user_release_date
        if archived:
            body["archived"] = archived.lower() == "true"
        if released:
            body["released"] = released.lower() == "true"
        if not body:
            return _err("at least one field must be provided")
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/api/2/version/{version_id}", body))
        except InsightError as exc:
            return _err(f"update_version failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Release Version"},
    )
    @check_write_access
    async def release_version(
        ctx: Context,
        version_id: Annotated[str, Field(description="Version id.")],
        user_release_date: Annotated[
            str,
            Field(
                description=(
                    "Release date in user format, e.g. '6/Jul/2010'. "
                    "Server sets today's date if omitted."
                )
            ),
        ] = "",
    ) -> str:
        """Mark a version as released — thin wrapper around PUT /version/{id}."""
        body: dict[str, Any] = {"released": True}
        if user_release_date:
            body["userReleaseDate"] = user_release_date
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/api/2/version/{version_id}", body))
        except InsightError as exc:
            return _err(f"release_version failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Archive Version"},
    )
    @check_write_access
    async def archive_version(
        ctx: Context,
        version_id: Annotated[str, Field(description="Version id.")],
        archived: Annotated[
            bool,
            Field(description="True to archive, False to unarchive."),
        ] = True,
    ) -> str:
        """Flip the ``archived`` flag on a version."""
        client = await _client(ctx)
        try:
            return _fmt(
                client.put(
                    f"/rest/api/2/version/{version_id}",
                    {"archived": bool(archived)},
                )
            )
        except InsightError as exc:
            return _err(f"archive_version failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Move Version"},
    )
    @check_write_access
    async def move_version(
        ctx: Context,
        version_id: Annotated[str, Field(description="Version id to reposition.")],
        position: Annotated[
            str,
            Field(
                description=(
                    "Relative position: 'First', 'Last', 'Earlier', 'Later'. "
                    "Mutually exclusive with 'after'."
                )
            ),
        ] = "",
        after: Annotated[
            str,
            Field(
                description=(
                    "Self-URI of the version to move AFTER. "
                    "Mutually exclusive with 'position'."
                )
            ),
        ] = "",
    ) -> str:
        """POST /rest/api/2/version/{id}/move — reorder within project."""
        if bool(position) == bool(after):
            return _err("provide exactly one of 'position' or 'after'")
        body: dict[str, Any] = (
            {"position": position} if position else {"after": after}
        )
        if position and position not in ("First", "Last", "Earlier", "Later"):
            return _err(
                "position must be 'First', 'Last', 'Earlier' or 'Later'"
            )
        client = await _client(ctx)
        try:
            return _fmt(client.post(f"/rest/api/2/version/{version_id}/move", body))
        except InsightError as exc:
            return _err(f"move_version failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Merge Version", "destructiveHint": True},
    )
    @check_write_access
    async def merge_version(
        ctx: Context,
        source_version_id: Annotated[
            str, Field(description="Version id that will be removed.")
        ],
        target_version_id: Annotated[
            str,
            Field(
                description="Version id that will absorb issues from source."
            ),
        ],
    ) -> str:
        """PUT /rest/api/2/version/{id}/mergeto/{moveIssuesTo} — source is deleted."""
        client = await _client(ctx)
        try:
            client.put(
                f"/rest/api/2/version/{source_version_id}/mergeto/{target_version_id}",
                {},
            )
        except InsightError as exc:
            return _err(f"merge_version failed: {exc}", status=exc.status)
        return _ok(
            source_version_id=source_version_id,
            target_version_id=target_version_id,
            merged=True,
        )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_versions"},
        annotations={"title": "Delete Version", "destructiveHint": True},
    )
    @check_write_access
    async def delete_version(
        ctx: Context,
        version_id: Annotated[str, Field(description="Version id to delete.")],
        move_fix_issues_to: Annotated[
            str,
            Field(
                description=(
                    "Optional target version id to receive fixVersion refs. "
                    "Omit to simply strip the version from those issues."
                )
            ),
        ] = "",
        move_affected_issues_to: Annotated[
            str,
            Field(
                description=(
                    "Optional target version id to receive affectedVersion refs."
                )
            ),
        ] = "",
    ) -> str:
        """DELETE /rest/api/2/version/{id} (reassigning via query params)."""
        path = f"/rest/api/2/version/{version_id}"
        query_parts: list[str] = []
        if move_fix_issues_to:
            query_parts.append(f"moveFixIssuesTo={move_fix_issues_to}")
        if move_affected_issues_to:
            query_parts.append(f"moveAffectedIssuesTo={move_affected_issues_to}")
        if query_parts:
            path = f"{path}?{'&'.join(query_parts)}"
        client = await _client(ctx)
        try:
            client.delete(path)
        except InsightError as exc:
            return _err(f"delete_version failed: {exc}", status=exc.status)
        return _ok(version_id=version_id, deleted=True)

    # =====================================================================
    # Component extensions (update, delete, related-issue counts)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_components"},
        annotations={"title": "Update Component"},
    )
    @check_write_access
    async def update_component(
        ctx: Context,
        component_id: Annotated[str, Field(description="Component id.")],
        name: Annotated[str, Field(description="New name (optional).")] = "",
        description: Annotated[str, Field(description="New description.")] = "",
        lead_user_name: Annotated[
            str,
            Field(
                description=(
                    "DC username for the component lead. Pass empty string to "
                    "explicitly remove the lead (documented behaviour)."
                )
            ),
        ] = "",
        assignee_type: Annotated[
            str,
            Field(
                description=(
                    "One of 'PROJECT_DEFAULT', 'COMPONENT_LEAD', "
                    "'PROJECT_LEAD', 'UNASSIGNED'."
                )
            ),
        ] = "",
        is_assignee_type_valid: Annotated[
            bool,
            Field(
                description=(
                    "Required by the DC schema. Set to True unless you know "
                    "the target assignee type is disabled for the project."
                )
            ),
        ] = True,
    ) -> str:
        """PUT /rest/api/2/component/{id} — partial update."""
        body: dict[str, Any] = {"isAssigneeTypeValid": bool(is_assignee_type_valid)}
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        if lead_user_name or lead_user_name == "":
            # "" is a documented signal to remove the lead; keep it explicit
            # by only sending the key when the caller passed something.
            if lead_user_name != "":
                body["leadUserName"] = lead_user_name
            else:
                # caller wants to clear — but docstring asked for explicit empty
                # by default we skip this to avoid accidental clears.
                pass
        if assignee_type:
            valid = {
                "PROJECT_DEFAULT",
                "COMPONENT_LEAD",
                "PROJECT_LEAD",
                "UNASSIGNED",
            }
            if assignee_type not in valid:
                return _err(f"assignee_type must be one of {sorted(valid)}")
            body["assigneeType"] = assignee_type
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/api/2/component/{component_id}", body))
        except InsightError as exc:
            return _err(f"update_component failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_components"},
        annotations={"title": "Delete Component", "destructiveHint": True},
    )
    @check_write_access
    async def delete_component(
        ctx: Context,
        component_id: Annotated[str, Field(description="Component id to delete.")],
        move_issues_to: Annotated[
            str,
            Field(
                description=(
                    "Optional target component id to receive the issues. "
                    "Omit to simply strip the component from affected issues."
                )
            ),
        ] = "",
    ) -> str:
        """DELETE /rest/api/2/component/{id}?moveIssuesTo=…."""
        path = f"/rest/api/2/component/{component_id}"
        if move_issues_to:
            path = f"{path}?moveIssuesTo={move_issues_to}"
        client = await _client(ctx)
        try:
            client.delete(path)
        except InsightError as exc:
            return _err(f"delete_component failed: {exc}", status=exc.status)
        return _ok(component_id=component_id, deleted=True)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_components"},
        annotations={"title": "Component Related Issue Count", "readOnlyHint": True},
    )
    async def get_component_related_issue_counts(
        ctx: Context,
        component_id: Annotated[str, Field(description="Component id.")],
    ) -> str:
        """Count of issues using this component — safety check before delete."""
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(f"/rest/api/2/component/{component_id}/relatedIssueCounts")
            )
        except InsightError as exc:
            return _err(
                f"get_component_related_issue_counts failed: {exc}",
                status=exc.status,
            )

    # =====================================================================
    # JSM extras
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_jsm"},
        annotations={"title": "List JSM Service Desks", "readOnlyHint": True},
    )
    async def jsm_list_service_desks(
        ctx: Context,
        include_archived: Annotated[
            bool, Field(description="Include archived service desks.")
        ] = False,
        start: Annotated[int, Field(description="Pagination start (0-based).")] = 0,
        limit: Annotated[int, Field(description="Page size (default 50).")] = 50,
    ) -> str:
        """GET /rest/servicedeskapi/servicedesk — lists SDs the user can see."""
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(
                    "/rest/servicedeskapi/servicedesk",
                    params={
                        "includeArchived": "true" if include_archived else "false",
                        "start": max(0, int(start)),
                        "limit": max(1, min(int(limit), 100)),
                    },
                )
            )
        except InsightError as exc:
            return _err(
                f"jsm_list_service_desks failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_jsm"},
        annotations={"title": "List JSM Request Types", "readOnlyHint": True},
    )
    async def jsm_list_request_types(
        ctx: Context,
        service_desk_id: Annotated[str, Field(description="Service desk id.")],
        group_id: Annotated[
            str, Field(description="Optional group id to filter by.")
        ] = "",
        start: Annotated[int, Field(description="Pagination start (0-based).")] = 0,
        limit: Annotated[int, Field(description="Page size (default 100).")] = 100,
    ) -> str:
        """GET /rest/servicedeskapi/servicedesk/{id}/requesttype."""
        params: dict[str, Any] = {
            "start": max(0, int(start)),
            "limit": max(1, min(int(limit), 100)),
        }
        if group_id:
            params["groupId"] = group_id
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(
                    f"/rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype",
                    params=params,
                )
            )
        except InsightError as exc:
            return _err(
                f"jsm_list_request_types failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_jsm"},
        annotations={"title": "List JSM Participants", "readOnlyHint": True},
    )
    async def jsm_list_participants(
        ctx: Context,
        issue_key: Annotated[str, Field(description="JSM request issue key.")],
        start: Annotated[int, Field(description="Pagination start.")] = 0,
        limit: Annotated[int, Field(description="Page size.")] = 50,
    ) -> str:
        """GET /rest/servicedeskapi/request/{key}/participant."""
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(
                    f"/rest/servicedeskapi/request/{issue_key}/participant",
                    params={
                        "start": max(0, int(start)),
                        "limit": max(1, min(int(limit), 100)),
                    },
                )
            )
        except InsightError as exc:
            return _err(
                f"jsm_list_participants failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_jsm"},
        annotations={"title": "Add JSM Participants"},
    )
    @check_write_access
    async def jsm_add_participants(
        ctx: Context,
        issue_key: Annotated[str, Field(description="JSM request issue key.")],
        usernames: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated DC usernames to add as participants. "
                    "DC shape — Cloud uses accountIds instead."
                )
            ),
        ],
    ) -> str:
        """POST /rest/servicedeskapi/request/{key}/participant with {usernames}."""
        users = _split_csv(usernames)
        if not users:
            return _err("usernames is required")
        client = await _client(ctx)
        try:
            return _fmt(
                client.post(
                    f"/rest/servicedeskapi/request/{issue_key}/participant",
                    {"usernames": users},
                )
            )
        except InsightError as exc:
            return _err(
                f"jsm_add_participants failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_jsm"},
        annotations={"title": "Remove JSM Participants", "destructiveHint": True},
    )
    @check_write_access
    async def jsm_remove_participants(
        ctx: Context,
        issue_key: Annotated[str, Field(description="JSM request issue key.")],
        usernames: Annotated[
            str,
            Field(description="Comma-separated DC usernames to remove."),
        ],
    ) -> str:
        """DELETE /rest/servicedeskapi/request/{key}/participant with {usernames}.

        DC requires a JSON body on DELETE — some HTTP clients strip bodies from
        DELETE by default; we send it via the underlying requests.Session which
        preserves it.
        """
        users = _split_csv(usernames)
        if not users:
            return _err("usernames is required")
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        path = f"/rest/servicedeskapi/request/{issue_key}/participant"
        try:
            # requests.Session supports a json= body on DELETE; use the raw
            # session so we preserve it (InsightClient.delete has no body arg).
            resp = client._session.request(
                "DELETE",
                client._url(path),
                json={"usernames": users},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=client._timeout,
            )
        except Exception as exc:  # noqa: BLE001 — wraps transport errors
            return _err(f"jsm_remove_participants transport error: {exc}")
        if not resp.ok:
            return _err(
                f"jsm_remove_participants returned HTTP {resp.status_code}",
                status=resp.status_code,
                body=(resp.text or "")[:500],
            )
        return _fmt(resp.json() if resp.content else {"removed": users})

    # =====================================================================
    # Agile extras (backlog, epics, epic rank)
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_agile"},
        annotations={"title": "Get Board Backlog", "readOnlyHint": True},
    )
    async def get_backlog_issues(
        ctx: Context,
        board_id: Annotated[str, Field(description="Board id (scrum).")],
        jql: Annotated[str, Field(description="Optional JQL filter.")] = "",
        fields: Annotated[
            str,
            Field(description="Comma-separated fields to include (e.g. 'summary,status')."),
        ] = "",
        start_at: Annotated[int, Field(description="Pagination start (0-based).")] = 0,
        max_results: Annotated[
            int, Field(description="Page size (default 50).")
        ] = 50,
    ) -> str:
        """GET /rest/agile/1.0/board/{id}/backlog."""
        params: dict[str, Any] = {
            "startAt": max(0, int(start_at)),
            "maxResults": max(1, min(int(max_results), 100)),
        }
        if jql:
            params["jql"] = jql
        if fields:
            params["fields"] = fields
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(f"/rest/agile/1.0/board/{board_id}/backlog", params=params)
            )
        except InsightError as exc:
            return _err(f"get_backlog_issues failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_agile"},
        annotations={"title": "Get Epics From Board", "readOnlyHint": True},
    )
    async def get_epics_from_board(
        ctx: Context,
        board_id: Annotated[str, Field(description="Board id.")],
        done: Annotated[
            str,
            Field(
                description=(
                    "'true' to fetch only done epics, 'false' for active only. "
                    "Leave empty for server default (usually both)."
                )
            ),
        ] = "",
        start_at: Annotated[int, Field(description="Pagination start (0-based).")] = 0,
        max_results: Annotated[
            int, Field(description="Page size (default 50).")
        ] = 50,
    ) -> str:
        """GET /rest/agile/1.0/board/{id}/epic."""
        params: dict[str, Any] = {
            "startAt": max(0, int(start_at)),
            "maxResults": max(1, min(int(max_results), 100)),
        }
        if done:
            if done not in ("true", "false"):
                return _err("done must be 'true' or 'false'")
            params["done"] = done
        client = await _client(ctx)
        try:
            return _fmt(
                client.get(f"/rest/agile/1.0/board/{board_id}/epic", params=params)
            )
        except InsightError as exc:
            return _err(f"get_epics_from_board failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "write", "toolset:jira_user_agile"},
        annotations={"title": "Rank Epic"},
    )
    @check_write_access
    async def rank_epics(
        ctx: Context,
        epic_id: Annotated[
            str,
            Field(description="Epic id or key to reposition."),
        ],
        rank_before_epic: Annotated[
            str,
            Field(
                description="Epic key to rank BEFORE. Mutually exclusive with rank_after_epic."
            ),
        ] = "",
        rank_after_epic: Annotated[
            str,
            Field(
                description="Epic key to rank AFTER. Mutually exclusive with rank_before_epic."
            ),
        ] = "",
        rank_custom_field_id: Annotated[
            str,
            Field(
                description="Optional rank custom field id (usually 10100)."
            ),
        ] = "",
    ) -> str:
        """PUT /rest/agile/1.0/epic/{id}/rank — dedicated epic rank endpoint (DC)."""
        if bool(rank_before_epic) == bool(rank_after_epic):
            return _err(
                "provide exactly one of rank_before_epic / rank_after_epic"
            )
        body: dict[str, Any] = {}
        if rank_before_epic:
            body["rankBeforeEpic"] = rank_before_epic
        if rank_after_epic:
            body["rankAfterEpic"] = rank_after_epic
        if rank_custom_field_id:
            try:
                body["rankCustomFieldId"] = int(rank_custom_field_id)
            except ValueError:
                return _err("rank_custom_field_id must be numeric")
        client = await _client(ctx)
        try:
            return _fmt(client.put(f"/rest/agile/1.0/epic/{epic_id}/rank", body))
        except InsightError as exc:
            return _err(f"rank_epics failed: {exc}", status=exc.status)

    # =====================================================================
    # Current-user context
    # =====================================================================

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_me"},
        annotations={"title": "Get Myself", "readOnlyHint": True},
    )
    async def get_myself(
        ctx: Context,
        expand: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated expand values, e.g. 'groups,applicationRoles'. "
                    "Hidden by default."
                )
            ),
        ] = "groups,applicationRoles",
    ) -> str:
        """GET /rest/api/2/myself — current user profile + (expanded) groups/roles."""
        client = await _client(ctx)
        params = {"expand": expand} if expand else None
        try:
            return _fmt(client.get("/rest/api/2/myself", params=params))
        except InsightError as exc:
            return _err(f"get_myself failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_me"},
        annotations={"title": "List Favourite Filters", "readOnlyHint": True},
    )
    async def list_favourite_filters(
        ctx: Context,
        expand: Annotated[
            str, Field(description="Optional expand, e.g. 'sharedUsers'.")
        ] = "",
    ) -> str:
        """GET /rest/api/2/filter/favourite — user's starred filters (DC)."""
        client = await _client(ctx)
        params = {"expand": expand} if expand else None
        try:
            return _fmt(client.get("/rest/api/2/filter/favourite", params=params))
        except InsightError as exc:
            return _err(
                f"list_favourite_filters failed: {exc}", status=exc.status
            )

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_me"},
        annotations={"title": "Get My Preference", "readOnlyHint": True},
    )
    async def get_my_preference(
        ctx: Context,
        key: Annotated[
            str,
            Field(
                description=(
                    "Preference key. DC requires ?key= (no bulk read). Common: "
                    "'user.notifications.mimetype' ('html'/'text'), "
                    "'user.default.share.private', 'user.locale', "
                    "'user.notify.own.changes', 'user.notifications.watcher', "
                    "'user.notifications.own', 'jira.user.timezone'."
                )
            ),
        ],
    ) -> str:
        """GET /rest/api/2/mypreferences?key=… — one key per call (raw string)."""
        if not key:
            return _err("key is required")
        client = await _client(ctx)
        try:
            data = client.get("/rest/api/2/mypreferences", params={"key": key})
        except InsightError as exc:
            return _err(f"get_my_preference failed: {exc}", status=exc.status)
        return _fmt({"key": key, "value": data})

    # =====================================================================
    # Git dev-panel view
    #
    # Answers user questions like "how many MRs are open for HR-123", "which
    # repo is this ticket touching", "who pushed commits against it". Uses:
    #
    #   * ``/rest/dev-status/1.0/issue/summary`` + ``/detail`` — the internal
    #     API the issue view itself calls to render its Git panel. Official
    #     KB: "Access Git Repo Commit Data via Jira REST API in Development
    #     Panel (Data Center)". Requires a numeric issue id (not key) and a
    #     case-sensitive ``applicationType`` (``stash`` / ``GitHub`` /
    #     ``githube`` / ``gitlab`` / ``bitbucket``). We look up providers
    #     dynamically from ``/summary`` and then iterate ``/detail``.
    #
    #   * ``/rest/gitplugin/1.0/`` — BigBrassBand Git Integration for Jira
    #     (Marketplace app 4984). Gives richer commit data (full SHAs,
    #     author emails, optional file diffs) than dev-status. Not to be
    #     confused with ``/rest/jgitplugin/1.0/``, which is an unrelated
    #     older plugin.
    # =====================================================================

    async def _resolve_issue_id(client: InsightClient, issue_key_or_id: str) -> str:
        """Return the numeric issue id for an issue key/id.

        Dev-status ``/issue/summary`` and ``/issue/detail`` both require a
        numeric id, not a key. Accept either and resolve lazily when a key
        is supplied.
        """
        key = issue_key_or_id.strip()
        if key.isdigit():
            return key
        meta = client.get(f"/rest/api/2/issue/{key}", params={"fields": "id"})
        issue_id = (meta or {}).get("id")
        if not issue_id:
            raise InsightError(f"could not resolve issue id for '{key}'")
        return str(issue_id)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_git"},
        annotations={"title": "Issue Git Panel — Summary", "readOnlyHint": True},
    )
    async def get_issue_git_summary(
        ctx: Context,
        issue_key: Annotated[
            str,
            Field(description="Issue key, e.g. 'HR-123'. Numeric ids also work."),
        ],
    ) -> str:
        """Short Git panel summary for an issue — counts of pull requests,
        branches, commits and repositories across all connected providers.

        Calls ``/rest/dev-status/1.0/issue/summary?issueId=<id>``. The
        response also contains a ``byInstanceType`` map whose keys are the
        exact provider codes wired up on this instance — useful when the
        team can't remember whether "gitlab" or "GitLabServer" is the
        right ``application_type`` for follow-up detail calls.
        """
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        try:
            issue_id = await _resolve_issue_id(client, issue_key)
            return _fmt(
                client.get(
                    "/rest/dev-status/1.0/issue/summary",
                    params={"issueId": issue_id},
                )
            )
        except InsightError as exc:
            return _err(f"get_issue_git_summary failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_git"},
        annotations={"title": "Issue Git Panel — Full", "readOnlyHint": True},
    )
    async def get_issue_git_panel(
        ctx: Context,
        issue_key: Annotated[
            str,
            Field(description="Issue key (or numeric id)."),
        ],
        data_types: Annotated[
            str,
            Field(
                description=(
                    "Comma-separated dev-status data types to fetch: "
                    "'repository', 'branch', 'pullrequest' (singular). "
                    "Default gets all three."
                )
            ),
        ] = "repository,branch,pullrequest",
    ) -> str:
        """Everything the issue view's Git panel displays, unified across
        providers. Discovers providers dynamically from ``/summary`` and
        then loops ``/detail`` across each ``applicationType`` × selected
        ``dataType``. Returns a single object of the shape:

        ``{"issue_key": "...", "providers": [...], "sections": {
            "repository": {...}, "branch": {...}, "pullrequest": {...}}}``

        so the LLM can answer "how many open MRs / which repo / which
        branch does this ticket touch" in one call.
        """
        requested_types = _split_csv(data_types) or [
            "repository",
            "branch",
            "pullrequest",
        ]
        allowed = {"repository", "branch", "pullrequest"}
        bad = [t for t in requested_types if t not in allowed]
        if bad:
            return _err(
                f"unknown data_types: {bad}. Use 'repository', 'branch', 'pullrequest'."
            )
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        try:
            issue_id = await _resolve_issue_id(client, issue_key)
            summary = client.get(
                "/rest/dev-status/1.0/issue/summary",
                params={"issueId": issue_id},
            )
        except InsightError as exc:
            return _err(f"get_issue_git_panel summary failed: {exc}", status=exc.status)

        providers_map = (
            (summary.get("summary") or {}).get("byInstanceType") or {}
        ) if isinstance(summary, dict) else {}
        providers = sorted(providers_map.keys())
        if not providers:
            return _fmt(
                {
                    "issue_key": issue_key,
                    "providers": [],
                    "note": (
                        "No Git providers wired up for this issue — dev-status "
                        "returned an empty byInstanceType map."
                    ),
                    "raw_summary": summary,
                }
            )

        sections: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        for data_type in requested_types:
            per_provider: dict[str, Any] = {}
            for provider in providers:
                try:
                    per_provider[provider] = client.get(
                        "/rest/dev-status/1.0/issue/detail",
                        params={
                            "issueId": issue_id,
                            "applicationType": provider,
                            "dataType": data_type,
                        },
                    )
                except InsightError as exc:
                    errors.append(
                        {
                            "provider": provider,
                            "data_type": data_type,
                            "error": str(exc),
                            "status": exc.status,
                        }
                    )
            sections[data_type] = per_provider

        return _fmt(
            {
                "issue_key": issue_key,
                "issue_id": issue_id,
                "providers": providers,
                "sections": sections,
                "errors": errors,
                "summary": summary,
            }
        )

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_git"},
        annotations={"title": "List Issue Commits (GIJ)", "readOnlyHint": True},
    )
    async def list_issue_commits(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Issue key, e.g. 'HR-123'.")],
        show_files: Annotated[
            bool,
            Field(
                description=(
                    "Include each commit's changed files + change type. "
                    "Much larger response; leave false for a quick list."
                )
            ),
        ] = False,
    ) -> str:
        """``GET /rest/gitplugin/1.0/issues/{key}/commits`` — commits the
        BigBrassBand Git Integration plugin has linked to this issue.
        Richer than dev-status: full SHAs, author name + email,
        authorTimestamp, message, repository and branch, optional file diff.

        Requires the BigBrassBand Git Integration plugin to be installed
        (Marketplace app 4984). Returns an error payload if the plugin
        isn't present or the caller can't view the issue.
        """
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        try:
            return _fmt(
                client.get(
                    f"/rest/gitplugin/1.0/issues/{issue_key}/commits",
                    params={"showfiles": "true" if show_files else "false"},
                )
            )
        except InsightError as exc:
            return _err(f"list_issue_commits failed: {exc}", status=exc.status)

    @jira_mcp.tool(
        tags={"jira", "read", "toolset:jira_user_git"},
        annotations={"title": "List Issue Branches (GIJ)", "readOnlyHint": True},
    )
    async def list_issue_branches(
        ctx: Context,
        issue_key: Annotated[str, Field(description="Issue key.")],
    ) -> str:
        """``GET /rest/gitplugin/1.0/issues/branches?key=<key>`` — branches
        linked to this issue by the BigBrassBand Git Integration plugin.

        Returns branch name, repo reference, and (usually) last commit
        pointer. Use this when `get_issue_git_panel` doesn't surface a
        branch that developers are actually working on — the plugin's
        index can be ahead of the dev-status snapshot.
        """
        fetcher = await get_jira_fetcher(ctx)
        client = InsightClient(fetcher)
        try:
            return _fmt(
                client.get(
                    "/rest/gitplugin/1.0/issues/branches",
                    params={"key": issue_key},
                )
            )
        except InsightError as exc:
            return _err(f"list_issue_branches failed: {exc}", status=exc.status)
