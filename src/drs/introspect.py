#
# Copyright (C) 2017-2026 Dremio Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Runtime schema introspection for drs commands.

Provides machine-readable descriptions of command parameters, types, and
constraints. Agents call `drs describe <command>` to self-serve schema info
instead of relying on pre-stuffed documentation (cheaper on token budget,
always up to date).
"""

from __future__ import annotations

from drs.utils import VALID_JOB_STATES

# Command registry — one entry per CLI command with full parameter schema.
# This is the canonical source of truth for what each command accepts.

COMMAND_SCHEMAS: dict[str, dict] = {
    "query.run": {
        "group": "query",
        "command": "run",
        "description": "Execute a SQL query against Dremio Cloud, wait for completion, return results as JSON.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/sql", "GET /v0/projects/{pid}/job/{id}", "GET /v0/projects/{pid}/job/{id}/results"],
        "parameters": [
            {"name": "sql", "type": "string", "required": True, "positional": True, "description": "SQL query to execute"},
            {"name": "context", "type": "string", "required": False, "description": "Dot-separated default schema context (e.g., myspace.folder)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"], "description": "Output format"},
            {"name": "fields", "type": "string", "required": False, "flag": "--fields/-f", "description": "Comma-separated fields to include in output (reduces context window usage)"},
        ],
    },
    "query.status": {
        "group": "query",
        "command": "status",
        "description": "Check the status of a Dremio job by UUID.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/job/{id}"],
        "parameters": [
            {"name": "job_id", "type": "string", "required": True, "positional": True, "format": "uuid", "description": "Job ID (UUID)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "query.cancel": {
        "group": "query",
        "command": "cancel",
        "description": "Cancel a running Dremio job. No effect if already completed.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/job/{id}/cancel"],
        "mutating": True,
        "parameters": [
            {"name": "job_id", "type": "string", "required": True, "positional": True, "format": "uuid", "description": "Job ID (UUID) to cancel"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "flag": "--dry-run", "description": "Check job status without cancelling"},
        ],
    },
    "catalog.list": {
        "group": "catalog",
        "command": "list",
        "description": "List top-level catalog entities: sources, spaces, and home folder.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog"],
        "parameters": [
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "catalog.get": {
        "group": "catalog",
        "command": "get",
        "description": "Get full metadata for a catalog entity by dot-separated path.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}"],
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path (e.g., myspace.folder.table)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "catalog.search": {
        "group": "catalog",
        "command": "search",
        "description": "Full-text search for tables, views, and sources by keyword.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/search"],
        "parameters": [
            {"name": "term", "type": "string", "required": True, "positional": True, "description": "Search term"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "schema.describe": {
        "group": "schema",
        "command": "describe",
        "description": "Get column names, data types, and nullability for a table or view.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}"],
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated table/view path"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include (e.g., 'columns.name,columns.type')"},
        ],
    },
    "schema.lineage": {
        "group": "schema",
        "command": "lineage",
        "description": "Get upstream and downstream dependency graph for a table or view.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "GET /v0/projects/{pid}/catalog/{id}/graph"],
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated table/view path"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "schema.wiki": {
        "group": "schema",
        "command": "wiki",
        "description": "Get wiki documentation text and tags for a catalog entity.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "GET /v0/projects/{pid}/catalog/{id}/collaboration/wiki", "GET /v0/projects/{pid}/catalog/{id}/collaboration/tag"],
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "schema.sample": {
        "group": "schema",
        "command": "sample",
        "description": "Return sample rows from a table or view.",
        "mechanism": "SQL",
        "sql_template": "SELECT * FROM {path} LIMIT {limit}",
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated table/view path"},
            {"name": "limit", "type": "integer", "required": False, "default": 10, "description": "Number of sample rows"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "reflect.list": {
        "group": "reflect",
        "command": "list",
        "description": "List all reflections defined on a dataset.",
        "mechanism": "SQL",
        "sql_template": "SELECT * FROM sys.project.reflections WHERE dataset_id = '{dataset_id}'",
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated dataset path"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "reflect.status": {
        "group": "reflect",
        "command": "status",
        "description": "Get detailed status of a reflection by ID.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/reflection/{id}"],
        "parameters": [
            {"name": "reflection_id", "type": "string", "required": True, "positional": True, "description": "Reflection ID (get from 'drs reflect list')"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "reflect.refresh": {
        "group": "reflect",
        "command": "refresh",
        "description": "Trigger an immediate refresh of a reflection.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/reflection/{id}/refresh"],
        "mutating": True,
        "parameters": [
            {"name": "reflection_id", "type": "string", "required": True, "positional": True, "description": "Reflection ID to refresh"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Validate without executing"},
        ],
    },
    "reflect.drop": {
        "group": "reflect",
        "command": "drop",
        "description": "Permanently delete a reflection. Cannot be undone.",
        "mechanism": "REST",
        "endpoints": ["DELETE /v0/projects/{pid}/reflection/{id}"],
        "mutating": True,
        "parameters": [
            {"name": "reflection_id", "type": "string", "required": True, "positional": True, "description": "Reflection ID to delete"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Validate without executing"},
        ],
    },
    "jobs.list": {
        "group": "jobs",
        "command": "list",
        "description": "List recent query jobs, optionally filtered by status.",
        "mechanism": "SQL",
        "sql_template": "SELECT job_id, user_name, query_type, status, submitted_ts, final_state_ts FROM sys.project.jobs WHERE ... ORDER BY submitted_ts DESC LIMIT {limit}",
        "parameters": [
            {"name": "status", "type": "enum", "required": False, "enum": sorted(VALID_JOB_STATES), "description": "Filter by job state"},
            {"name": "limit", "type": "integer", "required": False, "default": 25, "description": "Max jobs to return"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "jobs.get": {
        "group": "jobs",
        "command": "get",
        "description": "Get detailed status and metadata for a specific job.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/job/{id}"],
        "parameters": [
            {"name": "job_id", "type": "string", "required": True, "positional": True, "format": "uuid", "description": "Job ID (UUID)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "flag": "--fields/-f", "description": "Comma-separated fields to include in output"},
        ],
    },
    "jobs.profile": {
        "group": "jobs",
        "command": "profile",
        "description": "Get operator-level execution profile for a completed job.",
        "mechanism": "SQL",
        "sql_template": "SELECT job_id, status, query_type, query, planner_estimated_cost, rows_scanned, bytes_scanned, rows_returned, bytes_returned, accelerated, engine, submitted_ts, final_state_ts, error_msg FROM sys.project.jobs WHERE job_id = '{job_id}'",
        "parameters": [
            {"name": "job_id", "type": "string", "required": True, "positional": True, "format": "uuid", "description": "Job ID (UUID)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "access.grants": {
        "group": "access",
        "command": "grants",
        "description": "Get ACL grants on a catalog entity.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}"],
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "access.roles": {
        "group": "access",
        "command": "roles",
        "description": "List all roles in the organization.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/roles"],
        "parameters": [
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "access.whoami": {
        "group": "access",
        "command": "whoami",
        "description": "Get current authenticated user info (best-effort).",
        "mechanism": "REST",
        "endpoints": ["GET /v1/users"],
        "parameters": [
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "access.audit": {
        "group": "access",
        "command": "audit",
        "description": "Audit a user's roles and effective permissions by username.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/users/name/{userName}"],
        "parameters": [
            {"name": "username", "type": "string", "required": True, "positional": True, "description": "Username to audit"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Catalog CRUD additions --

    "catalog.create-space": {
        "group": "catalog",
        "command": "create-space",
        "description": "Create a new space in the catalog.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/catalog"],
        "mutating": True,
        "parameters": [
            {"name": "name", "type": "string", "required": True, "positional": True, "description": "Name for the new space"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "catalog.create-folder": {
        "group": "catalog",
        "command": "create-folder",
        "description": "Create a folder inside a space or another folder.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/catalog"],
        "mutating": True,
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated path for new folder (e.g., myspace.newfolder)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "catalog.delete": {
        "group": "catalog",
        "command": "delete",
        "description": "Delete a catalog entity (space, folder, view, etc.). Cannot be undone.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "DELETE /v0/projects/{pid}/catalog/{id}"],
        "mutating": True,
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path to delete"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Show what would be deleted without deleting"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Schema CRUD additions --

    "schema.set-wiki": {
        "group": "schema",
        "command": "set-wiki",
        "description": "Set or update the wiki description for a catalog entity.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "POST /v0/projects/{pid}/catalog/{id}/collaboration/wiki"],
        "mutating": True,
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path"},
            {"name": "text", "type": "string", "required": True, "positional": True, "description": "Wiki text to set (Markdown supported)"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "schema.set-tags": {
        "group": "schema",
        "command": "set-tags",
        "description": "Set tags on a catalog entity. Replaces all existing tags.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "POST /v0/projects/{pid}/catalog/{id}/collaboration/tag"],
        "mutating": True,
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated entity path"},
            {"name": "tags", "type": "string", "required": True, "positional": True, "description": 'Comma-separated list of tags (e.g., "pii,finance,daily")'},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Reflection creation --

    "reflect.create": {
        "group": "reflect",
        "command": "create",
        "description": "Create a new reflection on a dataset.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/catalog/by-path/{path}", "POST /v0/projects/{pid}/reflection"],
        "mutating": True,
        "parameters": [
            {"name": "path", "type": "string", "required": True, "positional": True, "description": "Dot-separated dataset path"},
            {"name": "type", "type": "enum", "required": False, "default": "raw", "enum": ["raw", "aggregation"], "flag": "--type/-t", "description": "Reflection type"},
            {"name": "fields", "type": "string", "required": False, "flag": "--fields/-f", "description": "Comma-separated field names to include"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Engine management --

    "engine.list": {
        "group": "engine",
        "command": "list",
        "description": "List all engines in the project.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/engines"],
        "parameters": [
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "engine.get": {
        "group": "engine",
        "command": "get",
        "description": "Get details for a specific engine.",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/engines/{id}"],
        "parameters": [
            {"name": "engine_id", "type": "string", "required": True, "positional": True, "description": "Engine ID"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "engine.create": {
        "group": "engine",
        "command": "create",
        "description": "Create a new engine.",
        "mechanism": "REST",
        "endpoints": ["POST /v0/projects/{pid}/engines"],
        "mutating": True,
        "parameters": [
            {"name": "name", "type": "string", "required": True, "positional": True, "description": "Name for the new engine"},
            {"name": "size", "type": "enum", "required": False, "default": "SMALL", "enum": ["SMALL", "MEDIUM", "LARGE", "XLARGE", "XXLARGE"], "flag": "--size/-s", "description": "Engine size"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "engine.update": {
        "group": "engine",
        "command": "update",
        "description": "Update engine configuration (name, size).",
        "mechanism": "REST",
        "endpoints": ["GET /v0/projects/{pid}/engines/{id}", "PUT /v0/projects/{pid}/engines/{id}"],
        "mutating": True,
        "parameters": [
            {"name": "engine_id", "type": "string", "required": True, "positional": True, "description": "Engine ID to update"},
            {"name": "name", "type": "string", "required": False, "flag": "--name", "description": "New engine name"},
            {"name": "size", "type": "string", "required": False, "flag": "--size/-s", "description": "New engine size"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "engine.delete": {
        "group": "engine",
        "command": "delete",
        "description": "Delete an engine. Cannot be undone.",
        "mechanism": "REST",
        "endpoints": ["DELETE /v0/projects/{pid}/engines/{id}"],
        "mutating": True,
        "parameters": [
            {"name": "engine_id", "type": "string", "required": True, "positional": True, "description": "Engine ID to delete"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Show engine details without deleting"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "engine.enable": {
        "group": "engine",
        "command": "enable",
        "description": "Enable a disabled engine.",
        "mechanism": "REST",
        "endpoints": ["PUT /v0/projects/{pid}/engines/{id}/enable"],
        "mutating": True,
        "parameters": [
            {"name": "engine_id", "type": "string", "required": True, "positional": True, "description": "Engine ID to enable"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "engine.disable": {
        "group": "engine",
        "command": "disable",
        "description": "Disable a running engine.",
        "mechanism": "REST",
        "endpoints": ["PUT /v0/projects/{pid}/engines/{id}/disable"],
        "mutating": True,
        "parameters": [
            {"name": "engine_id", "type": "string", "required": True, "positional": True, "description": "Engine ID to disable"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- User management --

    "user.list": {
        "group": "user",
        "command": "list",
        "description": "List all users in the organization.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/users"],
        "parameters": [
            {"name": "limit", "type": "integer", "required": False, "default": 100, "flag": "--limit/-n", "description": "Max users to return"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "user.get": {
        "group": "user",
        "command": "get",
        "description": "Get user details by name or ID.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/users/name/{userName}", "GET /v1/users/{userId}"],
        "parameters": [
            {"name": "identifier", "type": "string", "required": True, "positional": True, "description": "Username or user ID"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "user.invite": {
        "group": "user",
        "command": "invite",
        "description": "Invite a new user by email address.",
        "mechanism": "REST",
        "endpoints": ["POST /v1/users/invite"],
        "mutating": True,
        "parameters": [
            {"name": "email", "type": "string", "required": True, "positional": True, "description": "Email address to invite"},
            {"name": "role_id", "type": "string", "required": False, "flag": "--role-id", "description": "Role ID to assign"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "user.update": {
        "group": "user",
        "command": "update",
        "description": "Update a user's properties.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/users/{userId}", "PUT /v1/users/{userId}"],
        "mutating": True,
        "parameters": [
            {"name": "user_id", "type": "string", "required": True, "positional": True, "description": "User ID to update"},
            {"name": "name", "type": "string", "required": False, "flag": "--name", "description": "New display name"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "user.delete": {
        "group": "user",
        "command": "delete",
        "description": "Delete a user from the organization. Cannot be undone.",
        "mechanism": "REST",
        "endpoints": ["DELETE /v1/users/{userId}"],
        "mutating": True,
        "parameters": [
            {"name": "user_id", "type": "string", "required": True, "positional": True, "description": "User ID to delete"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Show user details without deleting"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Role management --

    "role.list": {
        "group": "role",
        "command": "list",
        "description": "List all roles in the organization.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/roles"],
        "parameters": [
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "role.get": {
        "group": "role",
        "command": "get",
        "description": "Get role details by name or ID.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/roles/name/{roleName}", "GET /v1/roles/{roleId}"],
        "parameters": [
            {"name": "identifier", "type": "string", "required": True, "positional": True, "description": "Role name or role ID"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
            {"name": "fields", "type": "string", "required": False, "description": "Comma-separated fields to include"},
        ],
    },
    "role.create": {
        "group": "role",
        "command": "create",
        "description": "Create a new role.",
        "mechanism": "REST",
        "endpoints": ["POST /v1/roles"],
        "mutating": True,
        "parameters": [
            {"name": "name", "type": "string", "required": True, "positional": True, "description": "Name for the new role"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "role.update": {
        "group": "role",
        "command": "update",
        "description": "Update a role's name.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/roles/{roleId}", "PUT /v1/roles/{roleId}"],
        "mutating": True,
        "parameters": [
            {"name": "role_id", "type": "string", "required": True, "positional": True, "description": "Role ID to update"},
            {"name": "name", "type": "string", "required": True, "flag": "--name", "description": "New role name"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "role.delete": {
        "group": "role",
        "command": "delete",
        "description": "Delete a role. Cannot be undone.",
        "mechanism": "REST",
        "endpoints": ["DELETE /v1/roles/{roleId}"],
        "mutating": True,
        "parameters": [
            {"name": "role_id", "type": "string", "required": True, "positional": True, "description": "Role ID to delete"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Show role details without deleting"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },

    # -- Grant management --

    "grant.get": {
        "group": "grant",
        "command": "get",
        "description": "Get grants for a user or role on a resource.",
        "mechanism": "REST",
        "endpoints": ["GET /v1/{scope}/{scopeId}/grants/{granteeType}/{granteeId}"],
        "parameters": [
            {"name": "scope", "type": "string", "required": True, "positional": True, "description": "Resource scope (projects, orgs, clouds)"},
            {"name": "scope_id", "type": "string", "required": True, "positional": True, "description": "Resource ID"},
            {"name": "grantee_type", "type": "string", "required": True, "positional": True, "description": "Grantee type (user or role)"},
            {"name": "grantee_id", "type": "string", "required": True, "positional": True, "description": "Grantee ID"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "grant.set": {
        "group": "grant",
        "command": "set",
        "description": "Set grants (privileges) for a user or role on a resource.",
        "mechanism": "REST",
        "endpoints": ["PUT /v1/{scope}/{scopeId}/grants/{granteeType}/{granteeId}"],
        "mutating": True,
        "parameters": [
            {"name": "scope", "type": "string", "required": True, "positional": True, "description": "Resource scope (projects, orgs, clouds)"},
            {"name": "scope_id", "type": "string", "required": True, "positional": True, "description": "Resource ID"},
            {"name": "grantee_type", "type": "string", "required": True, "positional": True, "description": "Grantee type (user or role)"},
            {"name": "grantee_id", "type": "string", "required": True, "positional": True, "description": "Grantee ID"},
            {"name": "privileges", "type": "string", "required": True, "positional": True, "description": "Comma-separated privileges"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
    "grant.remove": {
        "group": "grant",
        "command": "remove",
        "description": "Remove all grants for a user or role on a resource.",
        "mechanism": "REST",
        "endpoints": ["DELETE /v1/{scope}/{scopeId}/grants/{granteeType}/{granteeId}"],
        "mutating": True,
        "parameters": [
            {"name": "scope", "type": "string", "required": True, "positional": True, "description": "Resource scope"},
            {"name": "scope_id", "type": "string", "required": True, "positional": True, "description": "Resource ID"},
            {"name": "grantee_type", "type": "string", "required": True, "positional": True, "description": "Grantee type (user or role)"},
            {"name": "grantee_id", "type": "string", "required": True, "positional": True, "description": "Grantee ID"},
            {"name": "dry_run", "type": "boolean", "required": False, "default": False, "description": "Show current grants without removing"},
            {"name": "output", "type": "enum", "required": False, "default": "json", "enum": ["json", "csv", "pretty"]},
        ],
    },
}


def describe_command(command: str) -> dict | None:
    """Return the schema for a command, or None if not found."""
    return COMMAND_SCHEMAS.get(command)


def list_commands() -> list[str]:
    """Return all available command names."""
    return sorted(COMMAND_SCHEMAS.keys())
