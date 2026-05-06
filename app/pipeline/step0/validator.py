from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .error_codes import (
    E_ENTRY_GATE_BLOCKED,
    E_INVALID_FIELD_TYPE,
    E_INVALID_ROUTE,
    E_INVALID_STATUS,
    E_MISSING_REQUIRED_FIELD,
    E_STATE_SCHEMA_INVALID,
    E_UNAUTHORIZED_FIELD_WRITE,
    E_UNKNOWN_FIELD,
)
from .state_rules import (
    ALLOWED_STATUS_TRANSITIONS,
    ENTRY_RULES,
    ROUTES,
    STATE_STATUSES,
    WRITABLE_FIELDS_BY_NODE,
)


REQUIRED_TOP_LEVEL_FIELDS = {
    "state_version",
    "request_id",
    "trace_id",
    "status",
    "created_at",
    "updated_at",
    "user_id",
    "user_query",
    "user_docs",
    "customer_db_info",
    "next_route",
    "draft_response",
    "final_response",
    "citations",
    "review_notes",
    "retry_count",
    "audit_log",
    "error",
}

ALLOWED_TOP_LEVEL_FIELDS = REQUIRED_TOP_LEVEL_FIELDS


class Step0ValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _validate_iso_utc(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, f"{field_name} must be string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, f"{field_name} must be ISO-8601 format") from exc


def _validate_list_of_dicts(value: Any, field_name: str) -> None:
    if not isinstance(value, list):
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, f"{field_name} must be list")
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise Step0ValidationError(E_INVALID_FIELD_TYPE, f"{field_name}[{idx}] must be object")


def validate_state_shape(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise Step0ValidationError(E_STATE_SCHEMA_INVALID, "State must be a dictionary")

    missing = REQUIRED_TOP_LEVEL_FIELDS - set(state.keys())
    if missing:
        raise Step0ValidationError(
            E_MISSING_REQUIRED_FIELD, f"Missing required fields: {sorted(missing)}"
        )

    unknown = set(state.keys()) - ALLOWED_TOP_LEVEL_FIELDS
    if unknown:
        raise Step0ValidationError(E_UNKNOWN_FIELD, f"Unknown fields: {sorted(unknown)}")

    if state["status"] not in STATE_STATUSES:
        raise Step0ValidationError(E_INVALID_STATUS, f"Invalid status: {state['status']}")

    if state["next_route"] is not None and state["next_route"] not in ROUTES:
        raise Step0ValidationError(E_INVALID_ROUTE, f"Invalid next_route: {state['next_route']}")

    _validate_iso_utc(state["created_at"], "created_at")
    _validate_iso_utc(state["updated_at"], "updated_at")

    if not isinstance(state["user_id"], str) or not state["user_id"].strip():
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, "user_id must be a non-empty string")
    if not isinstance(state["user_query"], str) or not state["user_query"].strip():
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, "user_query must be a non-empty string")

    _validate_list_of_dicts(state["user_docs"], "user_docs")
    _validate_list_of_dicts(state["citations"], "citations")
    _validate_list_of_dicts(state["review_notes"], "review_notes")
    _validate_list_of_dicts(state["audit_log"], "audit_log")

    if not isinstance(state["retry_count"], int) or state["retry_count"] < 0:
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, "retry_count must be a non-negative integer")

    if state["error"] is not None and not isinstance(state["error"], dict):
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, "error must be object or null")


def validate_node_entry(node: str, state: dict[str, Any]) -> None:
    validate_state_shape(state)
    if node not in ENTRY_RULES:
        raise Step0ValidationError(E_ENTRY_GATE_BLOCKED, f"Unknown node: {node}")

    rule = ENTRY_RULES[node]
    allowed_statuses = rule["allowed_statuses"]
    if state["status"] not in allowed_statuses:
        raise Step0ValidationError(
            E_ENTRY_GATE_BLOCKED,
            f"{node} cannot enter from status={state['status']}, allowed={sorted(allowed_statuses)}",
        )

    for required_key in rule["required_fields"]:
        value = state.get(required_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise Step0ValidationError(
                E_ENTRY_GATE_BLOCKED, f"{node} requires non-empty {required_key}"
            )

    required_route = rule.get("required_route")
    if required_route and state.get("next_route") != required_route:
        raise Step0ValidationError(
            E_ENTRY_GATE_BLOCKED,
            f"{node} requires next_route={required_route}, got={state.get('next_route')}",
        )


def validate_node_update(node: str, before_state: dict[str, Any], patch: dict[str, Any]) -> None:
    if node not in WRITABLE_FIELDS_BY_NODE:
        raise Step0ValidationError(E_UNAUTHORIZED_FIELD_WRITE, f"Unknown node: {node}")
    if not isinstance(patch, dict):
        raise Step0ValidationError(E_INVALID_FIELD_TYPE, "patch must be a dictionary")

    unauthorized = set(patch.keys()) - WRITABLE_FIELDS_BY_NODE[node]
    if unauthorized:
        raise Step0ValidationError(
            E_UNAUTHORIZED_FIELD_WRITE,
            f"{node} cannot write fields: {sorted(unauthorized)}",
        )

    if "status" in patch:
        current = before_state["status"]
        nxt = patch["status"]
        allowed_next = ALLOWED_STATUS_TRANSITIONS.get(current, set())
        if nxt not in allowed_next:
            raise Step0ValidationError(
                E_INVALID_STATUS,
                f"Invalid status transition {current} -> {nxt}. allowed={sorted(allowed_next)}",
            )

    if "next_route" in patch and patch["next_route"] not in ROUTES:
        raise Step0ValidationError(E_INVALID_ROUTE, f"Invalid next_route in patch: {patch['next_route']}")

    if "updated_at" in patch:
        _validate_iso_utc(patch["updated_at"], "updated_at")


def build_audit_event(*, node: str, action: str, note: str = "") -> dict[str, str]:
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "timestamp": ts,
        "node": node,
        "action": action,
        "note": note,
    }

