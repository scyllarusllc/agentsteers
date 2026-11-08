"""Read-only authenticated dashboard queries for the AgentSteers Frappe app.

This is not a public MCP endpoint or Codex execution API. Frappe User
is the canonical identity store. Public/Guest requests are denied.
"""
import frappe

def _current_user():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Authentication required", frappe.PermissionError)
    return user

@frappe.whitelist(methods=["GET"])
def get_dashboard():
    user = _current_user()
    counts = frappe.get_all(
        "AgentSteers Task",
        filters={"owner_user": user},
        fields=["status", "count(name) as count"],
        group_by="status",
    )
    return {
        "tasks_by_status": {row.status: row.count for row in counts},
        "connection_count": frappe.db.count("AgentSteers Connection", {"owner_user": user}),
    }

@frappe.whitelist(methods=["GET"])
def get_my_tasks(limit=20):
    user = _current_user()
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        frappe.throw("Invalid limit", frappe.ValidationError)
    return frappe.get_all(
        "AgentSteers Task",
        filters={"owner_user": user},
        fields=["name", "repository", "status", "creation", "finished_at", "result_summary"],
        order_by="creation desc",
        limit_page_length=limit,
    )

@frappe.whitelist(methods=["GET"])
def get_my_connections():
    user = _current_user()
    return frappe.get_all(
        "AgentSteers Connection",
        filters={"owner_user": user},
        fields=["name", "label", "connection_type", "status", "last_seen_at"],
        order_by="creation desc",
    )

@frappe.whitelist(methods=["GET"])
def get_my_settings():
    user = _current_user()
    rows = frappe.get_all(
        "AgentSteers User Settings",
        filters={"owner_user": user},
        fields=["default_repository", "voice_updates", "notification_preference"],
        limit_page_length=1,
    )
    return rows[0] if rows else {}


# Minimal persistent task APIs. Authentication is provided by Frappe session/API token;
# the owner is always derived from that identity, never from caller parameters.
import re

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_INSTRUCTION = 2000


def _allowed_repositories():
    """Site-owned configuration, e.g. agentsteers_allowed_repositories."""
    value = frappe.conf.get("agentsteers_allowed_repositories") or []
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)):
        return frozenset()
    return frozenset(item.strip() for item in value if isinstance(item, str) and item.strip())


@frappe.whitelist(methods=["POST"])
def create_task(repository, instruction):
    """Persist a queued, inert task; this endpoint NEVER starts a worker."""
    user = _current_user()
    if not frappe.has_permission("AgentSteers Task", "create", user=user):
        frappe.throw("Not permitted to create tasks", frappe.PermissionError)
    if (not isinstance(repository, str) or
            not _REPOSITORY.fullmatch(repository) or
            repository not in _allowed_repositories()):
        frappe.throw("Repository is not allowed", frappe.PermissionError)
    if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > _MAX_INSTRUCTION:
        frappe.throw("Invalid task instruction", frappe.ValidationError)
    doc = frappe.get_doc({
        "doctype": "AgentSteers Task",
        "owner_user": user,
        "repository": repository,
        "instruction": instruction.strip(),
        "status": "Queued",
        "created_via": "MCP",
    })
    doc.insert()
    return {"ok": True, "task_id": doc.name, "status": "Queued"}


@frappe.whitelist(methods=["GET"])
def get_task_status(task_id):
    """Return only a task belonging to the authenticated Frappe user."""
    user = _current_user()
    if not isinstance(task_id, str) or not task_id or len(task_id) > 140:
        frappe.throw("Invalid task identifier", frappe.ValidationError)
    row = frappe.db.get_value(
        "AgentSteers Task", {"name": task_id, "owner_user": user},
        ["name", "status", "creation", "finished_at", "result_summary"],
        as_dict=True,
    )
    if not row:
        # Identical response for unknown and other users' identifiers.
        frappe.throw("Task not found", frappe.DoesNotExistError)
    return {
        "ok": True,
        "task_id": row.name,
        "status": row.status,
        "created_at": str(row.creation),
        "finished_at": str(row.finished_at) if row.finished_at else None,
        "result_summary": row.result_summary if row.status in ("Completed", "Failed") else None,
    }
