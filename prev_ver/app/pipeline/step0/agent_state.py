from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import uuid
from typing import Any


SCHEMA_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_initial_state(
    *,
    user_id: str,
    user_query: str,
    user_docs: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    Build initial AgentState.

    Step 0 owner fields:
    - request_id / trace_id lifecycle metadata
    - basic user payload and empty slots for downstream nodes
    """
    now = _utc_now_iso()
    req_id = request_id or f"REQ-{uuid.uuid4().hex[:12].upper()}"
    trc_id = trace_id or f"TRC-{uuid.uuid4().hex[:12].upper()}"
    docs = deepcopy(user_docs) if user_docs else []

    return {
        "state_version": SCHEMA_VERSION,
        "request_id": req_id,
        "trace_id": trc_id,
        "status": "INIT",
        "created_at": now,
        "updated_at": now,
        "user_id": user_id,
        "user_query": user_query,
        "user_docs": docs,
        "customer_db_info": None,
        "next_route": None,
        "draft_response": None,
        "final_response": None,
        "citations": [],
        "review_notes": [],
        "retry_count": 0,
        "audit_log": [
            {
                "timestamp": now,
                "node": "SYSTEM",
                "action": "STATE_CREATED",
                "note": "Initial AgentState was created.",
            }
        ],
        "error": None,
    }

