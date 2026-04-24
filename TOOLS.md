# Tools reference — mcp-atlassian-user

65 user-facing tools for Jira Data Center, on top of 51 inherited upstream tools.

Auto-generated from tool registrations. First docstring line = intent-oriented summary (verb-first, user-question style).

**116 tools total across 26 toolsets.**

Tool names below include the `jira_` / `confluence_` prefix that FastMCP mounts automatically.

Kind legend: **read** = read-only · **write** = state-changing · **write (destructive)** = carries `destructiveHint`, MCP clients prompt before executing.

---

## Fork-specific toolsets

### `jira_user_assets` — Insight/Assets CRUD (14)

| Tool | Kind | Description |
|---|---|---|
| `jira_asset_add_reference` | write | Append referenced object ids to a reference attribute (union with existing). |
| `jira_asset_attach_to_issue` | write | Set the Insight custom field on an issue to reference the given asset keys. |
| `jira_asset_create` | write | Create a new Insight object (POST /object/create). |
| `jira_asset_delete` | write (destructive) | Permanently delete an Insight object. |
| `jira_asset_detach_from_issue` | write (destructive) | Clear the Insight custom field on an issue (set to empty array). |
| `jira_asset_get` | read | Fetch a single Insight object by id. |
| `jira_asset_get_history` | read | Change history for an Insight object (ordered oldest → newest). |
| `jira_asset_get_type_attributes` | read | Attribute definitions for an object type — required before building create payloads. |
| `jira_asset_list_schemas` | read | List all Insight object schemas on the instance. |
| `jira_asset_list_types` | read | Flat list of object types in a schema (/objectschema/{id}/objecttypes/flat). |
| `jira_asset_remove_reference` | write (destructive) | Drop referenced object ids from a reference attribute. |
| `jira_asset_search` | read | Search Insight/Assets objects via IQL (GET /aql/objects). |
| `jira_asset_set_attribute` | write | Convenience wrapper — set one attribute without building a full payload. |
| `jira_asset_update` | write | Update an object's attributes (PUT /object/{id}). |

### `jira_user_sprints` — Sprint lifecycle (5)

| Tool | Kind | Description |
|---|---|---|
| `jira_complete_sprint` | write | Close a sprint (state → ``closed``). |
| `jira_delete_sprint` | write (destructive) | Delete a sprint — issues revert to the backlog / previous sprint. |
| `jira_move_issues_to_backlog` | write | POST /rest/agile/1.0/backlog/issue — remove issues from any sprint. |
| `jira_rank_issues` | write | Reorder issues in the backlog / sprint (PUT /rest/agile/1.0/issue/rank). |
| `jira_start_sprint` | write | Activate a sprint. DC requires ``startDate`` + ``endDate`` together with state. |

### `jira_user_issues` — Issue pro-user actions (11)

| Tool | Kind | Description |
|---|---|---|
| `jira_add_vote` | write | Cast the authenticated user's vote on an issue (204 = success). |
| `jira_bulk_add_comment` | write | Add the same comment to every issue matching ``jql``. |
| `jira_bulk_assign` | write | Resolve a JQL and set ``assignee`` on each returned issue. |
| `jira_bulk_label` | write | Add labels to every issue matching ``jql`` via the ``add`` update operation. |
| `jira_clone_issue` | write | Create a new issue with selected fields copied from an existing one. |
| `jira_delete_attachment` | write (destructive) | DELETE /rest/api/2/attachment/{id}. |
| `jira_delete_comment` | write (destructive) | DELETE /rest/api/2/issue/{key}/comment/{id}. |
| `jira_delete_worklog` | write (destructive) | DELETE /rest/api/2/issue/{key}/worklog/{id}. |
| `jira_remove_vote` | write | Withdraw the authenticated user's vote. |
| `jira_update_worklog` | write | PUT /rest/api/2/issue/{key}/worklog/{id} — at least one field required. |
| `jira_upload_attachment` | write | POST /rest/api/2/issue/{key}/attachments (multipart, ``X-Atlassian-Token: no-check``). |

### `jira_user_jsm` — Jira Service Management user flows (8)

| Tool | Kind | Description |
|---|---|---|
| `jira_jsm_add_participants` | write | POST /rest/servicedeskapi/request/{key}/participant with {usernames}. |
| `jira_jsm_add_request_comment` | write | POST /rest/servicedeskapi/request/{key}/comment with ``{body, public}``. |
| `jira_jsm_answer_approval` | write | POST /rest/servicedeskapi/request/{key}/approval/{id} with ``{decision}``. |
| `jira_jsm_create_request` | write | POST /rest/servicedeskapi/request (DC — uses usernames, not accountIds). |
| `jira_jsm_list_participants` | read | GET /rest/servicedeskapi/request/{key}/participant. |
| `jira_jsm_list_request_types` | read | GET /rest/servicedeskapi/servicedesk/{id}/requesttype. |
| `jira_jsm_list_service_desks` | read | GET /rest/servicedeskapi/servicedesk — lists SDs the user can see. |
| `jira_jsm_remove_participants` | write (destructive) | DELETE /rest/servicedeskapi/request/{key}/participant with {usernames}. |

### `jira_user_filters` — Personal filters & dashboards (8)

| Tool | Kind | Description |
|---|---|---|
| `jira_copy_dashboard` | write | POST /rest/api/2/dashboard/{id}/copy. |
| `jira_create_dashboard` | write | POST /rest/api/2/dashboard. |
| `jira_create_filter` | write | POST /rest/api/2/filter. |
| `jira_delete_filter` | write (destructive) | DELETE /rest/api/2/filter/{id}. |
| `jira_list_dashboards` | read | Find dashboards by name — supports substring search client-side. |
| `jira_share_filter` | write | POST /rest/api/2/filter/{id}/permission — add a share permission. |
| `jira_update_dashboard` | write | PUT /rest/api/2/dashboard/{id}. |
| `jira_update_filter` | write | PUT /rest/api/2/filter/{id} — full replace of name/jql/description. |

### `jira_user_versions` — Version lifecycle (6)

| Tool | Kind | Description |
|---|---|---|
| `jira_archive_version` | write | Flip the ``archived`` flag on a version. |
| `jira_delete_version` | write (destructive) | DELETE /rest/api/2/version/{id} (reassigning via query params). |
| `jira_merge_version` | write (destructive) | PUT /rest/api/2/version/{id}/mergeto/{moveIssuesTo} — source is deleted. |
| `jira_move_version` | write | POST /rest/api/2/version/{id}/move — reorder within project. |
| `jira_release_version` | write | Mark a version as released — thin wrapper around PUT /version/{id}. |
| `jira_update_version` | write | PUT /rest/api/2/version/{id} — partial update (only included fields change). |

### `jira_user_components` — Component extensions (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_delete_component` | write (destructive) | DELETE /rest/api/2/component/{id}?moveIssuesTo=…. |
| `jira_get_component_related_issue_counts` | read | Count of issues using this component — safety check before delete. |
| `jira_update_component` | write | PUT /rest/api/2/component/{id} — partial update. |

### `jira_user_agile` — Board extras (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_backlog_issues` | read | GET /rest/agile/1.0/board/{id}/backlog. |
| `jira_get_epics_from_board` | read | GET /rest/agile/1.0/board/{id}/epic. |
| `jira_rank_epics` | write | PUT /rest/agile/1.0/epic/{id}/rank — dedicated epic rank endpoint (DC). |

### `jira_user_me` — Current user context (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_my_preference` | read | GET /rest/api/2/mypreferences?key=… — one key per call (raw string). |
| `jira_get_myself` | read | GET /rest/api/2/myself — current user profile + (expanded) groups/roles. |
| `jira_list_favourite_filters` | read | GET /rest/api/2/filter/favourite — user's starred filters (DC). |

### `jira_user_git` — Git dev-panel view (4)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_issue_git_panel` | read | Everything the issue view's Git panel displays, unified across |
| `jira_get_issue_git_summary` | read | Short Git panel summary for an issue — counts of pull requests, |
| `jira_list_issue_branches` | read | List Git branches linked to a Jira issue via the BigBrassBand plugin. |
| `jira_list_issue_commits` | read | List Git commits linked to a Jira issue via the BigBrassBand plugin. |

### `jira_user_structure` — ALM Works Structure (public REST) (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_structure` | read | Get one ALM Works Structure by id — name, description, owner, archived flag, permissions. |
| `jira_list_structures` | read | Find ALM Works Structures by name — substring search client-side. |

---

## Upstream toolsets (inherited from `sooperset/mcp-atlassian`)

Listed for completeness — this fork does not modify these tools.

### `jira_agile` (7)

| Tool | Kind | Description |
|---|---|---|
| `jira_add_issues_to_sprint` | write | Add issues to a Jira sprint. |
| `jira_create_sprint` | write (destructive) | Create Jira sprint for a board. |
| `jira_get_agile_boards` | read | Get jira agile boards by name, project key, or type. |
| `jira_get_board_issues` | read | Get all issues linked to a specific board filtered by JQL. |
| `jira_get_sprint_issues` | read | Get jira issues from sprint. |
| `jira_get_sprints_from_board` | read | Get jira sprints from board by state. |
| `jira_update_sprint` | write (destructive) | Update jira sprint. |

### `jira_attachments` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_download_attachments` | read | Download attachments from a Jira issue. |
| `jira_get_issue_images` | read | Get all images attached to a Jira issue as inline image content. |

### `jira_comments` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_add_comment` | write (destructive) | Add a comment to a Jira issue. |
| `jira_edit_comment` | write (destructive) | Edit an existing comment on a Jira issue. |

### `jira_development` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_issue_development_info` | read | Get development information (PRs, commits, branches) linked to a Jira issue. |
| `jira_get_issues_development_info` | read | Get development information for multiple Jira issues. |

### `jira_fields` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_field_options` | read | Get allowed option values for a custom field. |
| `jira_search_fields` | read | Search Jira fields by keyword with fuzzy match. |

### `jira_forms` (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_issue_proforma_forms` | read | Get all ProForma forms associated with a Jira issue. |
| `jira_get_proforma_form_details` | read | Get detailed information about a specific ProForma form. |
| `jira_update_proforma_form_answers` | write (destructive) | Update form field answers using the Jira Forms REST API. |

### `jira_issues` (8)

| Tool | Kind | Description |
|---|---|---|
| `jira_batch_create_issues` | write (destructive) | Create multiple Jira issues in a batch. |
| `jira_batch_get_changelogs` | read | Get changelogs for multiple Jira issues (Cloud only). |
| `jira_create_issue` | write (destructive) | Create a new Jira issue with optional Epic link or parent for subtasks. |
| `jira_delete_issue` | write (destructive) | Delete an existing Jira issue. |
| `jira_get_issue` | read | Get details of a specific Jira issue including its Epic links and relationship information. |
| `jira_get_project_issues` | read | Get all issues for a specific Jira project. |
| `jira_search` | read | Search Jira issues using JQL (Jira Query Language). |
| `jira_update_issue` | write (destructive) | Update an existing Jira issue including changing status, adding Epic links, updating fields, etc. |

### `jira_links` (5)

| Tool | Kind | Description |
|---|---|---|
| `jira_create_issue_link` | write (destructive) | Create a link between two Jira issues. |
| `jira_create_remote_issue_link` | write (destructive) | Create a remote issue link (web link or Confluence link) for a Jira issue. |
| `jira_get_link_types` | read | Get all available issue link types. |
| `jira_link_to_epic` | write (destructive) | Link an existing issue to an epic. |
| `jira_remove_issue_link` | write (destructive) | Remove a link between two Jira issues. |

### `jira_metrics` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_issue_dates` | read | Get date information and status transition history for a Jira issue. |
| `jira_get_issue_sla` | read | Calculate SLA metrics for a Jira issue. |

### `jira_projects` (5)

| Tool | Kind | Description |
|---|---|---|
| `jira_batch_create_versions` | write (destructive) | Batch create multiple versions in a Jira project. |
| `jira_create_version` | write (destructive) | Create a new fix version in a Jira project. |
| `jira_get_all_projects` | read | Get all Jira projects accessible to the current user. |
| `jira_get_project_components` | read | Get all components for a specific Jira project. |
| `jira_get_project_versions` | read | Get all fix versions for a specific Jira project. |

### `jira_service_desk` (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_queue_issues` | read | Get issues from a Jira Service Desk queue. |
| `jira_get_service_desk_for_project` | read | Get the Jira Service Desk associated with a project key. |
| `jira_get_service_desk_queues` | read | Get queues for a Jira Service Desk. |

### `jira_transitions` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_transitions` | read | Get available status transitions for a Jira issue. |
| `jira_transition_issue` | write (destructive) | Transition a Jira issue to a new status. |

### `jira_users` (1)

| Tool | Kind | Description |
|---|---|---|
| `jira_get_user_profile` | read | Retrieve profile information for a specific Jira user. |

### `jira_watchers` (3)

| Tool | Kind | Description |
|---|---|---|
| `jira_add_watcher` | write | Add a user as a watcher to a Jira issue. |
| `jira_get_issue_watchers` | read | Get the list of watchers for a Jira issue. |
| `jira_remove_watcher` | write | Remove a user from watching a Jira issue. |

### `jira_worklog` (2)

| Tool | Kind | Description |
|---|---|---|
| `jira_add_worklog` | write (destructive) | Add a worklog entry to a Jira issue. |
| `jira_get_worklog` | read | Get worklog entries for a Jira issue. |
