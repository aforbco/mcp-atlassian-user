"""Insight/Assets REST client for Jira DC.

Thin wrapper around the authenticated ``requests.Session`` already configured
on a ``JiraFetcher``. Implements the Insight/Assets REST surface verified
against the official DC docs:

* Atlassian DC API reference (v10000):
  https://developer.atlassian.com/server/jira/platform/rest/v10000/
* Assets REST API 10.4.4 reference:
  https://docs.atlassian.com/assets/REST/10.4.4/
* Assets REST docs (JSM DC 11.2):
  https://confluence.atlassian.com/servicemanagementserver/insight-rest-api-documentation-1044101761.html

Base path: defaults to ``/rest/assets/1.0`` (the modern DC path introduced in
JSM 5.3+ / Assets 8.10.12+). Older instances that still run the legacy
``/rest/insight/1.0`` mount can override via ``JIRA_INSIGHT_BASE_PATH``.

Key shape points (from the verified docs):

* IQL search is **GET** ``/aql/objects`` with query parameter ``qlQuery``
  (not a POST body) and DC-specific pagination params.
* Create / update object request body requires ``operationType`` on every
  attribute entry (``0`` = ADD).
* List types in a schema uses ``/objectschema/{id}/objecttypes/flat`` — the
  ``/flat`` suffix is mandatory on DC.
"""

import logging
import os
from typing import Any

import requests

from mcp_atlassian.jira import JiraFetcher

logger = logging.getLogger("mcp-atlassian.jira.user_tools.insight")

# Prefer the modern DC Assets mount. ``JIRA_INSIGHT_BASE_PATH`` lets admins
# pin the legacy ``/rest/insight/1.0`` path for older JSM deployments.
DEFAULT_INSIGHT_BASE = "/rest/assets/1.0"
LEGACY_INSIGHT_BASE = "/rest/insight/1.0"
DEFAULT_TIMEOUT = 60.0


class InsightError(Exception):
    """Wraps non-2xx responses from the Insight/Assets REST API."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _base_path() -> str:
    return os.getenv("JIRA_INSIGHT_BASE_PATH", DEFAULT_INSIGHT_BASE).rstrip("/")


class InsightClient:
    """Authenticated Insight/Assets REST client (DC).

    Re-uses the requests.Session that ``mcp_atlassian.jira.JiraFetcher``
    already configured for PAT / OAuth / basic auth, so there is no extra
    auth plumbing.
    """

    def __init__(self, fetcher: JiraFetcher) -> None:
        self._fetcher = fetcher
        self._session: requests.Session = fetcher.jira._session
        self._jira_base: str = fetcher.config.url.rstrip("/")
        self._insight_base = f"{self._jira_base}{_base_path()}"
        try:
            self._timeout = float(
                os.getenv(
                    "JIRA_INSIGHT_TIMEOUT",
                    str(fetcher.config.timeout or DEFAULT_TIMEOUT),
                )
            )
        except (TypeError, ValueError):
            self._timeout = DEFAULT_TIMEOUT

    # --- generic HTTP -----------------------------------------------------

    def _raise_for_status(self, resp: requests.Response, where: str) -> None:
        if resp.ok:
            return
        body_preview = (resp.text or "")[:500]
        logger.warning(
            "HTTP %s from %s (%s): %s",
            resp.status_code,
            where,
            resp.request.url if resp.request else "unknown",
            body_preview,
        )
        raise InsightError(
            f"{where} returned HTTP {resp.status_code}",
            status=resp.status_code,
            body=body_preview,
        )

    def _url(self, path: str) -> str:
        """Resolve a path — absolute ``/rest/…`` or relative to Insight base."""
        if path.startswith("/rest/"):
            return f"{self._jira_base}{path}"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._insight_base}{path}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = self._session.get(
                self._url(path),
                params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise InsightError(f"transport error on GET {path}: {exc}") from exc
        self._raise_for_status(resp, f"GET {path}")
        return resp.json() if resp.content else {}

    def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        try:
            resp = self._session.post(
                self._url(path),
                json=json_body or {},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise InsightError(f"transport error on POST {path}: {exc}") from exc
        self._raise_for_status(resp, f"POST {path}")
        return resp.json() if resp.content else {}

    def put(self, path: str, json_body: dict[str, Any]) -> Any:
        try:
            resp = self._session.put(
                self._url(path),
                json=json_body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise InsightError(f"transport error on PUT {path}: {exc}") from exc
        self._raise_for_status(resp, f"PUT {path}")
        return resp.json() if resp.content else {}

    def delete(self, path: str) -> Any:
        try:
            resp = self._session.delete(
                self._url(path),
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise InsightError(f"transport error on DELETE {path}: {exc}") from exc
        self._raise_for_status(resp, f"DELETE {path}")
        return resp.json() if resp.content else {"deleted": True}

    def post_multipart(
        self,
        path: str,
        files: list[tuple[str, tuple[str, bytes, str]]],
    ) -> Any:
        """POST a multipart form (used for Jira attachment uploads).

        Jira DC requires the ``X-Atlassian-Token: no-check`` header on
        attachment endpoints to bypass XSRF protection.
        """
        try:
            resp = self._session.post(
                self._url(path),
                files=files,
                headers={
                    "Accept": "application/json",
                    "X-Atlassian-Token": "no-check",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise InsightError(
                f"transport error on multipart POST {path}: {exc}"
            ) from exc
        self._raise_for_status(resp, f"POST {path}")
        return resp.json() if resp.content else {}

    # --- high-level Insight helpers --------------------------------------

    def search(
        self,
        iql: str,
        *,
        schema_id: str | int | None = None,
        page: int = 1,
        per_page: int = 25,
        include_attributes: bool = True,
        include_attributes_deep: int = 1,
        include_type_attributes: bool = False,
    ) -> Any:
        """IQL search.

        GET ``/aql/objects`` with ``qlQuery``. Note that per the verified DC
        docs the query param is named ``qlQuery`` (not ``iql``).
        """
        params: dict[str, Any] = {
            "qlQuery": iql,
            "page": max(page, 1),
            "resultPerPage": max(1, min(per_page, 500)),
            "includeAttributes": "true" if include_attributes else "false",
            "includeAttributesDeep": max(0, int(include_attributes_deep)),
            "includeTypeAttributes": "true" if include_type_attributes else "false",
        }
        if schema_id:
            params["objectSchemaId"] = int(schema_id)
        return self.get("/aql/objects", params)

    def get_object(self, object_id: str | int) -> Any:
        return self.get(f"/object/{object_id}")

    def object_history(self, object_id: str | int, *, asc: bool = True) -> Any:
        return self.get(
            f"/object/{object_id}/history",
            params={"asc": "true" if asc else "false", "abbreviate": "true"},
        )

    def list_schemas(self) -> Any:
        return self.get("/objectschema/list")

    def list_object_types(self, schema_id: str | int) -> Any:
        # The ``/flat`` suffix is required per the DC docs.
        return self.get(f"/objectschema/{schema_id}/objecttypes/flat")

    def get_type_attributes(self, object_type_id: str | int) -> Any:
        return self.get(f"/objecttype/{object_type_id}/attributes")

    def create_object(
        self,
        object_type_id: str | int,
        attributes: list[dict[str, Any]],
    ) -> Any:
        """Create an object. Attribute entries must include ``operationType``.

        The caller may pass attributes already shaped as
        ``{"objectTypeAttributeId": X, "objectAttributeValues": [...]}`` — this
        helper injects ``operationType: 0`` (ADD) if missing, per the docs.
        """
        return self.post(
            "/object/create",
            {
                "objectTypeId": int(object_type_id),
                "attributes": _with_operation_type(attributes),
            },
        )

    def update_object(
        self, object_id: str | int, attributes: list[dict[str, Any]]
    ) -> Any:
        return self.put(
            f"/object/{object_id}",
            {"attributes": _with_operation_type(attributes)},
        )

    def delete_object(self, object_id: str | int) -> Any:
        return self.delete(f"/object/{object_id}")

    # --- reference convenience -------------------------------------------

    def add_reference(
        self,
        object_id: str | int,
        attribute_id: str | int,
        referenced_object_ids: list[str | int],
    ) -> Any:
        """Union ``referenced_object_ids`` into an existing reference attribute."""
        current = self.get_object(object_id) or {}
        existing = _extract_reference_ids(current, attribute_id)
        merged = existing.union(str(rid) for rid in referenced_object_ids)
        return self.update_object(
            object_id,
            [
                {
                    "objectTypeAttributeId": int(attribute_id),
                    "objectAttributeValues": [
                        {"value": rid} for rid in sorted(merged)
                    ],
                }
            ],
        )

    def remove_reference(
        self,
        object_id: str | int,
        attribute_id: str | int,
        referenced_object_ids: list[str | int],
    ) -> Any:
        """Drop specific referenced IDs from a reference attribute."""
        current = self.get_object(object_id) or {}
        existing = _extract_reference_ids(current, attribute_id)
        drop = {str(rid) for rid in referenced_object_ids}
        remaining = sorted(existing - drop)
        return self.update_object(
            object_id,
            [
                {
                    "objectTypeAttributeId": int(attribute_id),
                    "objectAttributeValues": [{"value": rid} for rid in remaining],
                }
            ],
        )


def _with_operation_type(
    attributes: list[dict[str, Any]], op: int = 0
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for attr in attributes:
        entry = dict(attr)
        entry.setdefault("operationType", op)
        out.append(entry)
    return out


def _extract_reference_ids(obj: dict[str, Any], attribute_id: str | int) -> set[str]:
    out: set[str] = set()
    for attr in obj.get("attributes", []) or []:
        if str(attr.get("objectTypeAttributeId", "")) != str(attribute_id):
            continue
        for val in attr.get("objectAttributeValues", []) or []:
            ref = val.get("referencedObject") or {}
            rid = ref.get("id") or val.get("value")
            if rid is not None:
                out.add(str(rid))
    return out
