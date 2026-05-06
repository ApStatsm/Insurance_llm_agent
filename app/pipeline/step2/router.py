from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.pipeline.step0.validator import build_audit_event, validate_node_entry, validate_node_update


ROUTE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "precedent_dispute": ("판례", "분쟁", "면책", "소송", "거절", "이의", "재심", "타사 사례", "금감원"),
    "document_claim": (
        "청구",
        "서류",
        "영수증",
        "진단서",
        "견적서",
        "첨부",
        "업로드",
        "지급 요청",
        "접수",
        "보험금 신청",
        "신청",
    ),
    "cs_complaint": ("불만", "민원", "상담원", "사람 연결", "짜증", "화가", "항의", "컴플레인"),
    "policy_diagnosis": ("보상", "가능", "될까요", "약관", "사고", "진단", "담보", "면책조항"),
}

# 데모 라우팅 대표 케이스. scripts/test_routing.py에서 같은 케이스를 검증한다.
ROUTING_TEST_CASES = [
    {
        "question": "태풍 때문에 차가 침수됐는데 보상 가능해?",
        "expected_route": "policy_diagnosis",
    },
    {
        "question": "암 진단비 지급 관련해서 비슷한 분쟁 사례나 판례가 있어?",
        "expected_route": "precedent_dispute",
    },
    {
        "question": "진료비 영수증이랑 진단서 첨부했는데 청구 가능해?",
        "expected_route": "document_claim",
    },
    {
        "question": "상담원 연결해줘. 처리 결과가 너무 불만이야.",
        "expected_route": "cs_complaint",
    },
]

# 민원/상담원 연결 의도가 섞인 질문은 데모 중 오분기 비용이 커서 최우선 처리한다.
ROUTE_PRIORITY = ("cs_complaint", "precedent_dispute", "document_claim", "policy_diagnosis")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _score_route(text: str, route: str) -> int:
    normalized = text.lower()
    return sum(1 for kw in ROUTE_KEYWORDS[route] if kw.lower() in normalized)


def _select_route(user_query: str) -> str:
    scores = {route: _score_route(user_query, route) for route in ROUTE_KEYWORDS}
    if scores["cs_complaint"] > 0:
        return "cs_complaint"
    best = max(scores.values())
    if best <= 0:
        return "policy_diagnosis"
    # deterministic tie break by business priority
    candidates = [route for route, score in scores.items() if score == best]
    for route in ROUTE_PRIORITY:
        if route in candidates:
            return route
    return "policy_diagnosis"


def select_route(user_query: str) -> str:
    """Public helper for lightweight routing checks and demo smoke tests."""
    return _select_route(user_query)


def run_router(state: dict[str, Any]) -> dict[str, Any]:
    validate_node_entry("ROUTER", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()

    route = select_route(str(updated.get("user_query", "")))
    patch = {
        "next_route": route,
        "status": "ROUTED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("ROUTER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(node="ROUTER", action="ROUTE_SELECTED", note=f"next_route={route}")
    )
    return updated
