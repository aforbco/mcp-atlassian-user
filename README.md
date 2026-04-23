# MCP Atlassian

![PyPI Version](https://img.shields.io/pypi/v/mcp-atlassian)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mcp-atlassian)
![PePy - Total Downloads](https://static.pepy.tech/personalized-badge/mcp-atlassian?period=total&units=international_system&left_color=grey&right_color=blue&left_text=Total%20Downloads)
[![Run Tests](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml/badge.svg)](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml)
![License](https://img.shields.io/github/license/sooperset/mcp-atlassian)
[![Docs](https://img.shields.io/badge/docs-mintlify-blue)](https://mcp-atlassian.soomiles.com)

Model Context Protocol (MCP) server for Atlassian products (Confluence and Jira). Supports both Cloud and Server/Data Center deployments.

https://github.com/user-attachments/assets/35303504-14c6-4ae4-913b-7c25ea511c3e

<details>
<summary>Confluence Demo</summary>

https://github.com/user-attachments/assets/7fe9c488-ad0c-4876-9b54-120b666bb785

</details>

## Quick Start

### 1. Get Your API Token

Go to https://id.atlassian.com/manage-profile/security/api-tokens and create a token.

> For Server/Data Center, use a Personal Access Token instead. See [Authentication](https://mcp-atlassian.soomiles.com/docs/authentication).

### 2. Configure Your IDE

Add to your Claude Desktop or Cursor MCP configuration:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

> **Server/Data Center users**: Use `JIRA_PERSONAL_TOKEN` instead of `JIRA_USERNAME` + `JIRA_API_TOKEN`. See [Authentication](https://mcp-atlassian.soomiles.com/docs/authentication) for details.

### 3. Start Using

Ask your AI assistant to:
- **"Find issues assigned to me in PROJ project"**
- **"Search Confluence for onboarding docs"**
- **"Create a bug ticket for the login issue"**
- **"Update the status of PROJ-123 to Done"**

## Documentation

Full documentation is available at **[mcp-atlassian.soomiles.com](https://mcp-atlassian.soomiles.com)**.

Documentation is also available in [llms.txt format](https://llmstxt.org/), which LLMs can consume easily:
- [`llms.txt`](https://mcp-atlassian.soomiles.com/llms.txt) — documentation sitemap
- [`llms-full.txt`](https://mcp-atlassian.soomiles.com/llms-full.txt) — complete documentation

| Topic | Description |
|-------|-------------|
| [Installation](https://mcp-atlassian.soomiles.com/docs/installation) | uvx, Docker, pip, from source |
| [Authentication](https://mcp-atlassian.soomiles.com/docs/authentication) | API tokens, PAT, OAuth 2.0 |
| [Configuration](https://mcp-atlassian.soomiles.com/docs/configuration) | IDE setup, environment variables |
| [HTTP Transport](https://mcp-atlassian.soomiles.com/docs/http-transport) | SSE, streamable-http, multi-user |
| [Tools Reference](https://mcp-atlassian.soomiles.com/docs/tools-reference) | All Jira & Confluence tools |
| [Troubleshooting](https://mcp-atlassian.soomiles.com/docs/troubleshooting) | Common issues & debugging |

## Compatibility

| Product | Deployment | Support |
|---------|------------|---------|
| Confluence | Cloud | Fully supported |
| Confluence | Server/Data Center | Supported (v6.0+) |
| Jira | Cloud | Fully supported |
| Jira | Server/Data Center | Supported (v8.14+) |

## Key Tools

| Jira | Confluence |
|------|------------|
| `jira_search` - Search with JQL | `confluence_search` - Search with CQL |
| `jira_get_issue` - Get issue details | `confluence_get_page` - Get page content |
| `jira_create_issue` - Create issues | `confluence_create_page` - Create pages |
| `jira_update_issue` - Update issues | `confluence_update_page` - Update pages |
| `jira_transition_issue` - Change status | `confluence_add_comment` - Add comments |

**72 tools total** — See [Tools Reference](https://mcp-atlassian.soomiles.com/docs/tools-reference) for the complete list.

## Jira DC User toolset (this fork)

This fork adds **60 write-capable user-facing tools** for Jira Data Center — everything a day-to-day user needs that isn't in the upstream surface. All write operations honour `READ_ONLY_MODE=true` and carry `destructiveHint` annotations where appropriate.

| Toolset | Tools | What it exposes |
|---------|-------|-----------------|
| `jira_user_assets` | 14 | Insight/Assets full CRUD: IQL search, get/create/update/delete object, attribute/reference helpers, attach/detach Assets to Jira issues |
| `jira_user_sprints` | 5 | Sprint lifecycle: `start_sprint`, `complete_sprint`, `delete_sprint`, `move_issues_to_backlog`, `rank_issues` — complements upstream `create_sprint` / `update_sprint` / `add_issues_to_sprint` |
| `jira_user_issues` | 11 | `add_vote` / `remove_vote`, `upload_attachment` (base64) / `delete_attachment`, `delete_comment`, `delete_worklog`, `update_worklog`, JQL-driven `bulk_assign` / `bulk_label` / `bulk_add_comment`, `clone_issue` |
| `jira_user_jsm` | 8 | JSM user flows: `jsm_create_request`, `jsm_answer_approval`, `jsm_add_request_comment`, `jsm_list_service_desks`, `jsm_list_request_types`, `jsm_list_participants`, `jsm_add_participants`, `jsm_remove_participants` |
| `jira_user_filters` | 7 | Personal filters (create/update/delete/share) + dashboards (create/update/copy) |
| `jira_user_versions` | 6 | Version lifecycle: `update_version`, `release_version`, `archive_version`, `move_version`, `merge_version`, `delete_version` |
| `jira_user_components` | 3 | Component extensions over upstream: `update_component`, `delete_component` (with `moveIssuesTo`), `get_component_related_issue_counts` |
| `jira_user_agile` | 3 | Board extras: `get_backlog_issues`, `get_epics_from_board`, `rank_epics` (dedicated DC endpoint) |
| `jira_user_me` | 3 | Current user context: `get_myself` (with groups/roles expand), `list_favourite_filters`, `get_my_preference` |

### Verified against official DC documentation

Every endpoint was verified against the Atlassian DC docs before coding — key shape details that trip up naive implementations are honoured:

* Insight/Assets IQL search is `GET /aql/objects?qlQuery=…`, not a POST — base path defaults to `/rest/assets/1.0` with `JIRA_INSIGHT_BASE_PATH` for older JSM mounts.
* Each Insight attribute payload includes `operationType: 0` (ADD); list-types uses the mandatory `/flat` suffix.
* Sprint state transitions require `startDate` + `endDate` together with `state:"active"`.
* Rank endpoint is `PUT /rest/agile/1.0/issue/rank` (not POST); filter share permission uses `groupname` (DC) not `group.name` (Cloud).
* Attachment upload sends `X-Atlassian-Token: no-check` to pass XSRF protection.
* JSM uses DC usernames (not Cloud accountIds).

### Omitted endpoints (documented as non-existent in DC REST)

* **Bulk edit** — no `/rest/api/2/issue/bulk/edit` on DC; `bulk_*` tools here loop per-issue with a 500-cap.
* **Move issue to another project** — UI-only per the platform docs.
* **Convert issue ↔ subtask** — [JRASERVER-27893](https://jira.atlassian.com/browse/JRASERVER-27893) tracks the missing endpoint; only achievable via ScriptRunner.
* **JSM notification subscribe/unsubscribe** — `/rest/servicedeskapi/request/{key}/notification` is Cloud-only; on DC use the core watcher API (`add_watcher` / `remove_watcher`, already upstream).
* **`/filter/my` and `/filter/search`** — Cloud-only; use `list_favourite_filters` or the `creator = currentUser()` JQL pattern.

### Enabling it

1. Authenticate as usual (`JIRA_URL` + `JIRA_PERSONAL_TOKEN`). The Insight client re-uses mcp-atlassian's authenticated session.
2. Set `TOOLSETS` to include what you need, e.g.:
   `TOOLSETS=default,jira_user_assets,jira_user_sprints,jira_user_issues`
3. All user toolsets are **opt-in** (`default=false`) and won't appear unless enabled.

## Security

Never share API tokens. Keep `.env` files secure. See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## License

MIT - See [LICENSE](LICENSE). Not an official Atlassian product.
