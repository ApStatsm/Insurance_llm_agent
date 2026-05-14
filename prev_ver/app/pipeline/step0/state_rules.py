from __future__ import annotations

from typing import Literal


NodeName = Literal[
    "DB_LOOKUP",
    "ROUTER",
    "POLICY_DIAGNOSIS_WORKER",
    "PRECEDENT_DISPUTE_WORKER",
    "DOCUMENT_CLAIM_WORKER",
    "CS_COMPLAINT_WORKER",
    "MANAGER",
]

RouteName = Literal[
    "policy_diagnosis",
    "precedent_dispute",
    "document_claim",
    "cs_complaint",
]

STATE_STATUSES = {
    "INIT",
    "DB_ENRICHED",
    "ROUTED",
    "WORKER_DRAFTED",
    "MANAGER_REVIEW",
    "FINALIZED",
    "ERROR",
}

ROUTES = {
    "policy_diagnosis",
    "precedent_dispute",
    "document_claim",
    "cs_complaint",
}

WORKER_NODES = {
    "POLICY_DIAGNOSIS_WORKER",
    "PRECEDENT_DISPUTE_WORKER",
    "DOCUMENT_CLAIM_WORKER",
    "CS_COMPLAINT_WORKER",
}

NODE_TO_ROUTE: dict[str, str] = {
    "POLICY_DIAGNOSIS_WORKER": "policy_diagnosis",
    "PRECEDENT_DISPUTE_WORKER": "precedent_dispute",
    "DOCUMENT_CLAIM_WORKER": "document_claim",
    "CS_COMPLAINT_WORKER": "cs_complaint",
}

# Explicit ownership rules to prevent accidental overwrites.
WRITABLE_FIELDS_BY_NODE: dict[str, set[str]] = {
    "DB_LOOKUP": {"customer_db_info", "status", "audit_log", "error", "updated_at"},
    "ROUTER": {"next_route", "status", "audit_log", "error", "updated_at"},
    "POLICY_DIAGNOSIS_WORKER": {"draft_response", "citations", "status", "audit_log", "error", "updated_at"},
    "PRECEDENT_DISPUTE_WORKER": {"draft_response", "citations", "status", "audit_log", "error", "updated_at"},
    "DOCUMENT_CLAIM_WORKER": {"draft_response", "citations", "status", "audit_log", "error", "updated_at"},
    "CS_COMPLAINT_WORKER": {"draft_response", "citations", "status", "audit_log", "error", "updated_at"},
    "MANAGER": {
        "final_response",
        "review_notes",
        "retry_count",
        "status",
        "audit_log",
        "error",
        "updated_at",
    },
}

# Entry gates per node.
ENTRY_RULES: dict[str, dict[str, object]] = {
    "DB_LOOKUP": {
        "allowed_statuses": {"INIT"},
        "required_fields": {"user_id", "user_query"},
    },
    "ROUTER": {
        "allowed_statuses": {"DB_ENRICHED"},
        "required_fields": {"customer_db_info"},
    },
    "POLICY_DIAGNOSIS_WORKER": {
        "allowed_statuses": {"ROUTED"},
        "required_fields": {"next_route"},
        "required_route": "policy_diagnosis",
    },
    "PRECEDENT_DISPUTE_WORKER": {
        "allowed_statuses": {"ROUTED"},
        "required_fields": {"next_route"},
        "required_route": "precedent_dispute",
    },
    "DOCUMENT_CLAIM_WORKER": {
        "allowed_statuses": {"ROUTED"},
        "required_fields": {"next_route"},
        "required_route": "document_claim",
    },
    "CS_COMPLAINT_WORKER": {
        "allowed_statuses": {"ROUTED"},
        "required_fields": {"next_route"},
        "required_route": "cs_complaint",
    },
    "MANAGER": {
        "allowed_statuses": {"WORKER_DRAFTED", "MANAGER_REVIEW"},
        "required_fields": {"draft_response"},
    },
}

# Minimal lifecycle guardrails for predictable orchestration.
ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "INIT": {"DB_ENRICHED", "ERROR"},
    "DB_ENRICHED": {"ROUTED", "ERROR"},
    "ROUTED": {"WORKER_DRAFTED", "ERROR"},
    "WORKER_DRAFTED": {"MANAGER_REVIEW", "ROUTED", "FINALIZED", "ERROR"},
    "MANAGER_REVIEW": {"ROUTED", "FINALIZED", "ERROR"},
    "FINALIZED": set(),
    "ERROR": set(),
}

