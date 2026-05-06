from __future__ import annotations


ROUTE_LABELS = {
    "policy_diagnosis": "보상 가능성 문의",
    "document_claim": "청구 서류 점검",
    "precedent_dispute": "분쟁/사례 확인",
    "cs_complaint": "민원/상담 연결",
    "unknown": "기타",
}

ROUTE_TICKET_PREFIXES = {
    "policy_diagnosis": "CLM",
    "document_claim": "DOC",
    "precedent_dispute": "DSP",
    "cs_complaint": "CSQ",
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

PRIORITY_LABELS = {
    "low": "낮음",
    "medium": "보통",
    "high": "높음",
    "urgent": "긴급",
}

PRIORITY_ORDER = ["low", "medium", "high", "urgent"]


def priority_max(current: str, candidate: str) -> str:
    current_index = PRIORITY_ORDER.index(current) if current in PRIORITY_ORDER else 0
    candidate_index = PRIORITY_ORDER.index(candidate) if candidate in PRIORITY_ORDER else 0
    return PRIORITY_ORDER[max(current_index, candidate_index)]

