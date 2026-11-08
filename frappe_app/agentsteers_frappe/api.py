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
