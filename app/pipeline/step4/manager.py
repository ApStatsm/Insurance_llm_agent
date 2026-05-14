from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.pipeline.diagnosis_report import LEGAL_DISCLAIMER
from app.pipeline.step0.validator import build_audit_event, validate_node_entry, validate_node_update


ASSERTIVE_PHRASES = (
    "지급됩니다",
    "보상받으실 수 있습니다",
    "반드시 지급",
    "무조건 지급",
    "100% 지급",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _has_supporting_evidence(content: str, draft: dict[str, Any]) -> bool:
    if draft.get("citations"):
        return True
    diagnosis_result = draft.get("diagnosis_result") or {}
    if diagnosis_result.get("evidence_cards"):
        return True
    multi = diagnosis_result.get("multi_policy_analysis") or {}
    for result in multi.get("policy_results") or []:
        if result.get("evidence_cards"):
            return True
    return False


def _contains_assertive_phrase(content: str) -> bool:
    return any(token in content for token in ASSERTIVE_PHRASES)


def _sanitize_assertive(content: str) -> str:
    text = content
    replacements = {
        "지급됩니다": "지급 가능성이 있습니다",
        "보상받으실 수 있습니다": "보상 가능성이 있습니다",
        "반드시 지급": "요건을 충족하면 지급 가능성이 있습니다",
        "무조건 지급": "약관 요건을 충족하면 지급 가능성이 있습니다",
        "100% 지급": "약관의 한도와 기준에 따라 지급 가능성이 있습니다",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _sanitize_nested_text(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_assertive(value)
    if isinstance(value, list):
        return [_sanitize_nested_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_nested_text(item) for key, item in value.items()}
    return value


def manager_review(state: dict[str, Any]) -> dict[str, Any]:
    validate_node_entry("MANAGER", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()

    draft = updated.get("draft_response") or {}
    content = str(draft.get("content", ""))
    reasons: list[str] = []

    if _contains_assertive_phrase(content):
        reasons.append("확언 금지 룰 위반")
    if not _has_supporting_evidence(content, draft):
        reasons.append("근거 데이터 누락")

    if reasons:
        review_note = {
            "node": "MANAGER",
            "reason": "; ".join(reasons),
            "timestamp": updated["updated_at"],
        }
        patch = {
            "review_notes": [*updated.get("review_notes", []), review_note],
            "retry_count": int(updated.get("retry_count", 0)) + 1,
            "status": "ROUTED",
            "updated_at": updated["updated_at"],
            "error": None,
        }
        validate_node_update("MANAGER", state, patch)
        updated.update(patch)
        updated["audit_log"].append(
            build_audit_event(
                node="MANAGER",
                action="DRAFT_REJECTED",
                note=review_note["reason"],
            )
        )
        return updated

    safe_content = _sanitize_assertive(content)
    diagnosis_result = _sanitize_nested_text(draft.get("diagnosis_result") or {})
    if isinstance(diagnosis_result, dict):
        diagnosis_result["disclaimer"] = LEGAL_DISCLAIMER
    final_text = f"{safe_content}\n\n{LEGAL_DISCLAIMER}"
    final_response = {
        "content": final_text,
        "diagnosis_result": diagnosis_result,
        "disclaimer_appended": True,
        "approved_at": updated["updated_at"],
    }
    patch = {
        "final_response": final_response,
        "status": "FINALIZED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("MANAGER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(
            node="MANAGER",
            action="DRAFT_APPROVED",
            note="manager checks passed",
        )
    )
    return updated
