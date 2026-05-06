from __future__ import annotations

from typing import Any


ROUTE_LABELS = {
    "policy_diagnosis": "보상 가능성 문의",
    "document_claim": "청구 서류 점검",
    "precedent_dispute": "분쟁/사례 확인",
    "cs_complaint": "민원/상담 연결",
}

STATUS_LABELS = {
    "created": "접수 생성",
    "ai_reviewed": "AI 사전진단 완료",
    "waiting_for_documents": "추가 서류 대기",
    "needs_human_review": "상담원 확인 필요",
    "ready_for_submission": "기본 청구 준비 완료",
    "transferred_to_agent": "상담원 전달 완료",
    "closed": "종료",
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _next_steps(route: str, human_review: dict[str, Any], claim_checklist: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if claim_checklist.get("missing_docs"):
        steps.append("누락 서류 추가 제출 안내")
    if route == "policy_diagnosis":
        steps.append("담보 가입 여부 내부 확인")
        steps.append("면책 사유 해당 여부 확인")
    if route == "cs_complaint":
        steps.append("민원성 문의는 상담원 즉시 연결")
    if human_review.get("reasons"):
        steps.append("상담원 확인 사유를 기준으로 고객 추가 확인")
    return list(dict.fromkeys(steps or ["AI 사전진단 결과를 상담원이 확인"]))


def build_agent_handoff_summary(
    ticket_id: str,
    state: dict[str, Any],
    diagnosis_result: dict[str, Any],
    customer_info: dict[str, Any],
    human_review: dict[str, Any],
) -> dict[str, Any]:
    result = diagnosis_result or {}
    final_response = state.get("final_response") or {}
    route = _to_text(state.get("next_route"))
    customer_summary = result.get("customer_summary") or {}
    incident = result.get("incident_summary") or {}
    assessment = result.get("coverage_assessment") or {}
    checklist = result.get("claim_checklist") or {}
    evidence_cards = result.get("evidence_cards") or []
    status = state.get("ticket_status") or "ai_reviewed"
    key_evidence = [
        {
            "document_name": card.get("document_name"),
            "article_number": card.get("article_number"),
            "article_title": card.get("article_title"),
            "summary": card.get("ai_interpretation") or card.get("source_text", "")[:160],
        }
        for card in evidence_cards[:3]
    ]
    return {
        "notice": "본 요약은 AI 사전진단 결과를 상담원이 이어서 확인할 수 있도록 정리한 참고 자료입니다.",
        "ticket_info": {
            "ticket_id": ticket_id,
            "created_at": state.get("updated_at") or state.get("created_at"),
            "route": route,
            "route_label": ROUTE_LABELS.get(route, route or "기타"),
            "status": status,
            "status_label": STATUS_LABELS.get(status, "AI 사전진단 완료"),
            "priority": human_review.get("priority", "medium"),
            "priority_label": human_review.get("priority_label", "보통"),
        },
        "customer_summary": customer_summary,
        "inquiry_summary": {
            "original_question": incident.get("raw_question") or state.get("user_query"),
            "incident_type": incident.get("incident_type"),
            "customer_claim": state.get("user_query"),
            "current_stage": incident.get("stage"),
        },
        "ai_assessment": {
            "coverage_status": assessment.get("status"),
            "coverage_label": assessment.get("label"),
            "assessment_summary": assessment.get("summary") or final_response.get("content", "")[:240],
            "key_evidence": key_evidence,
            "missing_info": assessment.get("missing_info") or [],
            "cautions": assessment.get("cautions") or [],
        },
        "document_status": {
            "submitted_docs": checklist.get("submitted_docs") or [],
            "missing_docs": checklist.get("missing_docs") or [],
            "needs_review_docs": checklist.get("needs_review_docs") or [],
            "readiness_percent": checklist.get("readiness_percent", 0),
            "readiness_label": checklist.get("readiness_label", "청구 서류 준비 전"),
        },
        "human_review": {
            "required": human_review.get("human_review_required", False),
            "priority": human_review.get("priority", "medium"),
            "priority_label": human_review.get("priority_label", "보통"),
            "reasons": human_review.get("reasons") or [],
            "recommended_questions": human_review.get("recommended_questions") or [],
        },
        "recommended_next_steps": _next_steps(route, human_review, checklist),
    }
