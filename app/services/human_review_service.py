from __future__ import annotations

from typing import Any

from app.core.labels import PRIORITY_LABELS, priority_max


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys([item for item in items if item]))


def _incident_questions(incident_type: str) -> list[str]:
    if "차량" in incident_type or "침수" in incident_type:
        return [
            "사고 발생일과 장소를 확인해 주세요.",
            "사고 당시 차량이 주차 중이었는지 운행 중이었는지 확인해 주세요.",
            "가입 차량번호와 사고 차량번호가 일치하는지 확인해 주세요.",
            "자기차량손해 담보 가입 여부를 내부 시스템에서 확인해 주세요.",
        ]
    if "암" in incident_type:
        return [
            "진단일과 진단명을 확인해 주세요.",
            "병리보고서 또는 조직검사 결과 제출 여부를 확인해 주세요.",
            "약관상 암 진단 확정 요건 충족 여부를 확인해 주세요.",
        ]
    if "실손" in incident_type or "도수" in incident_type:
        return [
            "진료비 세부내역서 제출 여부를 확인해 주세요.",
            "도수치료 횟수와 치료 목적을 확인해 주세요.",
            "비급여 항목과 특약 가입 여부를 확인해 주세요.",
        ]
    return ["추가 확인이 필요한 사고 정보와 제출 서류를 고객에게 확인해 주세요."]


def assess_human_review_need(
    route: str,
    diagnosis_result: dict[str, Any],
    customer_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = diagnosis_result or {}
    question = _to_text((result.get("incident_summary") or {}).get("raw_question"))
    incident_type = _to_text((result.get("incident_summary") or {}).get("incident_type"))
    assessment = result.get("coverage_assessment") or {}
    checklist = result.get("claim_checklist") or {}
    uploaded = result.get("uploaded_documents") or {}
    comparison = uploaded.get("comparison_result") or {}
    multi_policy = result.get("multi_policy_analysis") or {}

    reasons: list[str] = []
    priority = "low"
    human_review_required = False

    if multi_policy.get("enabled"):
        human_review_required = True
        priority = "medium"
        reasons.append("여러 가입상품이 함께 관련되어 상품별 보장 범위와 중복 청구 가능 여부 확인이 필요합니다.")
        categories = {item.get("policy_category") for item in (multi_policy.get("policy_results") or [])}
        if {"auto", "indemnity"} <= categories:
            reasons.append("자동차보험 처리 범위와 실손보험 청구 가능 항목 구분이 필요합니다.")

    risk_words = ("불만", "항의", "민원", "소송", "금감원", "상담원", "분쟁")
    if route == "cs_complaint" or any(word in question for word in risk_words):
        human_review_required = True
        priority = "urgent" if route == "cs_complaint" or any(word in question for word in ("불만", "항의", "민원", "상담원")) else "high"
        reasons.append("민원 또는 상담원 연결 의도가 포함되어 있습니다.")
    if route == "precedent_dispute":
        human_review_required = True
        priority = priority_max(priority, "high")
        reasons.append("분쟁/유사사례 확인 요청으로 상담원 검토가 필요합니다.")

    coverage_status = _to_text(assessment.get("status"))
    if coverage_status in ("not_enough_evidence", "possibly_excluded"):
        human_review_required = True
        priority = priority_max(priority, "high")
        reasons.append("AI 사전진단 결과 추가 근거 또는 면책 가능성 확인이 필요합니다.")

    if not result.get("evidence_cards") and route in ("policy_diagnosis", "precedent_dispute"):
        human_review_required = True
        priority = priority_max(priority, "medium")
        reasons.append("약관 근거가 충분히 확인되지 않았습니다.")

    missing_docs = checklist.get("missing_docs") or []
    readiness = checklist.get("readiness_percent")
    if missing_docs:
        human_review_required = True
        priority = priority_max(priority, "medium")
        reasons.append(f"누락 서류가 있습니다: {', '.join(_to_text(doc) for doc in missing_docs[:3])}")
    if readiness is not None and int(readiness or 0) < 80:
        human_review_required = True
        priority = priority_max(priority, "medium")
        reasons.append("청구 서류 준비율이 80% 미만입니다.")

    mismatches = uploaded.get("mismatches") or []
    if mismatches:
        human_review_required = True
        priority = priority_max(priority, "high")
        reasons.append("고객 정보와 제출 서류 정보의 불일치 가능성이 있습니다.")

    missing_fields = [
        item for item in (uploaded.get("missing_key_fields") or []) if item.get("status") == "missing"
    ]
    if missing_fields:
        human_review_required = True
        priority = priority_max(priority, "medium")
        reasons.append("제출 서류에서 핵심 필드 일부가 확인되지 않았습니다.")

    needs_review_docs = comparison.get("needs_review_docs") or checklist.get("needs_review_docs") or []
    low_conf_docs = [
        item for item in (uploaded.get("extraction_results") or []) if float(item.get("confidence") or 0) < 0.6
    ]
    if needs_review_docs or low_conf_docs:
        human_review_required = True
        priority = priority_max(priority, "medium")
        reasons.append("문서 유형 또는 추출 정보 확인이 필요한 서류가 있습니다.")

    if "차량" in incident_type or "침수" in incident_type:
        reasons.append("자기차량손해 담보 가입 여부 확인 필요")
    if "암" in incident_type:
        reasons.append("병리보고서 및 진단 확정 요건 확인 필요")
    if "실손" in incident_type or "도수" in incident_type:
        reasons.append("비급여/도수치료 특약 및 세부내역 확인 필요")

    if not reasons:
        reasons.append("AI 사전진단 결과를 상담원이 최종 확인할 수 있습니다.")

    return {
        "human_review_required": bool(human_review_required),
        "priority": priority,
        "priority_label": PRIORITY_LABELS.get(priority, "보통"),
        "reasons": _unique(reasons),
        "recommended_questions": _incident_questions(incident_type),
    }
