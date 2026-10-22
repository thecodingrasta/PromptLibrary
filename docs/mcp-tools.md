# MCP tool reference

Generated with `python scripts/generate_mcp_reference.py`.
Use runtime `tools/list` for complete JSON schemas and current defaults.

## `search_library`

Search prompts and workflows together. Returns at most 100 items, total and page.

Parameters: `query`, `item_type`, `status`, `project_id`, `category_id`, `tag`, `favourites_only`, `page`.

## `search_prompts`

Find prompts, up to 100 per page. Use get_prompt to retrieve full content.

Parameters: `query`, `tag`, `status`, `favourites_only`, `project_id`, `category_id`, `page`.

## `get_prompt`

Read a prompt's complete content, notes and metadata.

Parameters: `id` (required).

## `get_prompt_by_title`

Resolve an exact or unique partial title. Ambiguous matches are refused.

Parameters: `title` (required).

## `create_prompt`

Create a prompt and its initial version. Category names can be created on demand.

Parameters: `title` (required), `body` (required), `notes`, `status`, `tags`, `category`, `category_id`, `project_id`, `label_ids`.

## `update_prompt`

Update supplied fields and create a version. Empty project/category IDs unassign them. Pass
expected_updated_at to reject stale edits.

Parameters: `id` (required), `title`, `body`, `notes`, `status`, `tags`, `message`, `category_id`, `project_id`, `label_ids`, `expected_updated_at`.

## `delete_prompt`

Delete a prompt and history. Linked workflow stages must be detached first.

Parameters: `id` (required).

## `publish_prompt`

Set the stable published status and record a new version.

Parameters: `id` (required).

## `bulk_update_status`

Update up to 100 prompts atomically. A missing prompt rolls back the entire batch.

Parameters: `ids` (required), `status` (required).

## `toggle_favourite`

Toggle a prompt's favourite flag and return its current state.

Parameters: `id` (required).

## `get_version_history`

Read saved prompt body, notes and status versions, newest first.

Parameters: `id` (required).

## `get_version_diff`

Compare a saved version with its predecessor.

Parameters: `id` (required), `version` (required).

## `restore_version`

Restore body, notes and status, keeping a new version of the restoration.

Parameters: `id` (required), `version` (required).

## `clear_version_history`

Permanently clear history without altering the current prompt. Backups are unchanged.

Parameters: `id` (required).

## `list_categories`

List categories and their stable IDs.

Parameters: none.

## `create_category`

Create a category, optionally beneath an existing category.

Parameters: `name` (required), `colour`, `parent_id`.

## `update_category`

Update a category. Empty parent_id makes it a root category.

Parameters: `id` (required), `name` (required), `colour`, `parent_id`.

## `delete_category`

Delete a category; its items and children remain, without that category/parent.

Parameters: `id` (required).

## `list_tags`

List tags used by prompts and workflows.

Parameters: none.

## `rename_tag`

Rename a tag across both prompts and workflows.

Parameters: `old_name` (required), `new_name` (required).

## `delete_tag`

Remove a tag and all its assignments. Prompts and workflows remain.

Parameters: `name` (required).

## `list_statuses`

List default and custom status keys, names, colours and order.

Parameters: none.

## `save_status`

Create a status, or edit its name/colour/order by stable key.

Parameters: `name` (required), `colour`, `sort_order`, `key`.

## `delete_status`

Delete an unused custom status. Default or referenced statuses are protected.

Parameters: `key` (required).

## `list_projects`

List projects with prompt and workflow counts.

Parameters: `include_archived`.

## `create_project`

Create a project to organise prompts and workflows.

Parameters: `name` (required), `description`, `colour`, `icon`.

## `update_project`

Edit, archive or unarchive a project without changing its items.

Parameters: `id` (required), `name`, `description`, `colour`, `icon`, `is_archived`.

## `delete_project`

Delete a project. Its prompts and workflows remain unassigned.

Parameters: `id` (required).

## `list_labels`

List labels, optionally filtered by language, framework, platform, model or custom.

Parameters: `type`.

## `create_label`

Create a typed label for prompts and workflows.

Parameters: `name` (required), `label_type`, `colour`, `icon`.

## `update_label`

Update an existing label's metadata.

Parameters: `id` (required), `name` (required), `label_type`, `colour`, `icon`.

## `delete_label`

Delete a label and assignments, keeping the labelled items.

Parameters: `id` (required).

## `assign_labels`

Add existing labels to a prompt by name. Unknown labels reject the whole change.

Parameters: `prompt_id` (required), `labels` (required).

## `set_labels`

Replace an item's complete label assignment. An empty list removes all labels.

Parameters: `id` (required), `item_type` (required), `label_ids` (required).

## `list_workflows`

List up to 100 matching workflows per page. Use get_workflow for stages and metadata.

Parameters: `search`, `project_id`, `page`.

## `get_workflow`

Read a workflow and its ordered stages, resolving linked prompt bodies.

Parameters: `id` (required).

## `create_workflow`

Create a workflow. Add its stages separately or compose them from existing prompts.

Parameters: `name` (required), `description`, `project_id`, `category_id`, `status`, `tags`, `label_ids`.

## `update_workflow`

Edit supplied workflow fields. Empty project/category IDs unassign them; optional timestamp
guards stale edits.

Parameters: `id` (required), `name`, `description`, `project_id`, `category_id`, `status`, `tags`, `label_ids`, `expected_updated_at`.

## `delete_workflow`

Delete a workflow, its stages and run history. Source prompts remain.

Parameters: `id` (required).

## `toggle_workflow_favourite`

Toggle a workflow's favourite flag.

Parameters: `id` (required).

## `add_workflow_stage`

Append a stage. prompt_id copies its body, or live-links it when link_prompt is true.

Parameters: `workflow_id` (required), `title` (required), `body`, `instructions`, `mode`, `output_type`, `prompt_id`, `link_prompt`.

## `update_workflow_stage`

Edit stage metadata/content. Set detach to turn a live link into a copy before editing its
body.

Parameters: `stage_id` (required), `title`, `body`, `instructions`, `mode`, `output_type`, `detach`.

## `reorder_workflow_stage`

Move a stage to a one-based position. Invalid dependencies are rejected; valid references are
renumbered.

Parameters: `stage_id` (required), `position` (required).

## `delete_workflow_stage`

Delete a stage and renumber safely. Stages whose outputs are referenced cannot be deleted.

Parameters: `stage_id` (required).

## `render_workflow_stage`

Render a stage without running a model. Unprovided placeholders remain visible.

Parameters: `workflow_id` (required), `stage_number` (required), `variables`.

## `start_workflow_run`

Start a guided run with immutable stage/input snapshots. This does not perform inference.

Parameters: `workflow_id` (required), `variables`.

## `get_workflow_run`

Read run history and the currently rendered stage, including prior saved outputs.

Parameters: `id` (required).

## `list_workflow_runs`

List a workflow's running, completed and cancelled runs.

Parameters: `workflow_id` (required).

## `complete_workflow_step`

Capture one stage output. Reject duplicate or stale submissions.

Parameters: `run_id` (required), `expected_stage` (required), `output` (required).

## `cancel_workflow_run`

Cancel a running workflow while preserving saved inputs and outputs.

Parameters: `id` (required).

## `export_library`

Export complete portable content. Machine-local credentials/settings are excluded. Prefer
HTTP downloads for large libraries.

Parameters: `file_format`.

## `import_library`

Import up to 25 MiB atomically. Merge refuses conflicts; replace requires a full v2 snapshot
and creates a safety backup.

Parameters: `content` (required), `file_format`, `mode`.

## `get_sync_config`

Read the selected remote without revealing stored credentials.

Parameters: none.

## `configure_sync`

Save machine-local remote configuration. Credentials are encrypted and never echoed. A new
destination does not inherit old secrets.

Parameters: `remote` (required), `preserve_secrets`.

## `test_sync_connection`

Check the destination using a temporary probe for local folders.

Parameters: none.

## `push_sync`

Overwrite the remote snapshot with current portable library content. This is not a
multi-writer merge.

Parameters: none.

## `pull_sync`

Download a snapshot. Merge refuses conflicts; replace takes a safety backup and mirrors
remote content/deletions.

Parameters: `mode`.
