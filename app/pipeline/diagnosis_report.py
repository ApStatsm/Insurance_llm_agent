from __future__ import annotations

import re
from typing import Any


LEGAL_DISCLAIMER = (
    "안내드린 내용은 현재 확인된 약관과 제출 정보를 바탕으로 한 사전 안내입니다. "
    "실제 지급 여부와 금액은 약관 원문, 제출 서류, 손해사정 결과에 따라 달라질 수 있습니다."
)

COVERAGE_LABELS = {
    "likely_covered": "보상 가능성 있음",
    "need_more_info": "추가 확인 필요",
    "possibly_excluded": "면책 가능성 있음",
    "not_enough_evidence": "근거 부족",
    "out_of_scope": "가입상품과 무관할 수 있음",
}

DOC_TYPE_LABELS = {
    "receipt": "진료비 영수증",
    "medical_statement": "진료확인서 또는 진단서",
    "treatment_detail": "진료비 세부내역서",
    "diagnosis_certificate": "진단서",
    "pathology_report": "병리보고서",
    "dental_treatment_record": "치과 진료기록",
    "xray_image": "엑스레이 자료",
    "repair_estimate": "수리견적서",
    "accident_report": "사고사실확인서",
    "vehicle_registration": "차량등록증",
    "flood_photo": "침수 사진",
    "estimate": "수리견적서",
    "pdf": "PDF 서류",
    "misc": "기타 서류",
    "기타/판별불가": "기타/판별불가",
}

CATEGORY_HINTS = {
    "auto": ("자동차", "차량", "운전자", "침수", "수리", "대물", "대인"),
    "cancer": ("암", "암진단", "진단비", "고액암", "병리", "악성신생물"),
    "indemnity": ("실손", "의료비", "도수치료", "비급여", "진료비", "입원", "통원"),
    "dental": ("치아", "치과", "보철", "임플란트", "크라운", "브릿지"),
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys([item for item in items if item]))


def _money(value: Any) -> str:
    if value is None or value == "":
        return "확인 필요"
    try:
        return f"{int(value):,}원"
    except (TypeError, ValueError):
        return _to_text(value)


def infer_product_category(product_name: str, question: str = "") -> str:
    text = f"{_to_text(product_name)} {_to_text(question)}".lower()
    for category, hints in CATEGORY_HINTS.items():
        if any(hint.lower() in text for hint in hints):
            return category
    return "unknown"


def build_customer_summary(customer_info: dict[str, Any] | None, customer_id: str) -> dict[str, Any]:
    info = customer_info or {}
    coverage_items = []
    for item in info.get("coverage_limits") or []:
        if not isinstance(item, dict):
            continue
        name = _to_text(item.get("coverage_name")) or "담보"
        amount = item.get("display_amount") or _money(item.get("limit_amount"))
        coverage_items.append(f"{name}: {amount}")

    policies = []
    for policy in info.get("policies") or []:
        if not isinstance(policy, dict):
            continue
        policies.append(
            {
                "product_id": policy.get("product_id"),
                "product_name": policy.get("product_name"),
                "joined_year": policy.get("joined_year") or policy.get("join_year"),
                "policy_number": policy.get("policy_number"),
            }
        )
    relevant_policies = []
    for policy in info.get("relevant_policies") or []:
        if not isinstance(policy, dict):
            continue
        relevant_policies.append(
            {
                "product_id": policy.get("product_id"),
                "product_name": policy.get("product_name"),
                "joined_year": policy.get("joined_year") or policy.get("join_year"),
                "policy_number": policy.get("policy_number"),
            }
        )

    return {
        "customer_id": customer_id,
        "product_name": _to_text(info.get("product_name")) or "확인 필요",
        "joined_year": _to_text(info.get("join_year")) or "확인 필요",
        "policy_number": _to_text(info.get("policy_number")) or "확인 필요",
        "riders": list(info.get("special_clauses") or []),
        "coverage_limit": ", ".join(coverage_items) if coverage_items else "확인 필요",
        "selected_policy": info.get("selected_policy") or {},
        "relevant_policies": relevant_policies,
        "policies": policies,
    }


def build_incident_summary(question: str, route: str) -> dict[str, str]:
    text = _to_text(question)
    if any(token in text for token in ("침수", "태풍", "홍수", "차", "차량")):
        incident_type, cause, target = "차량 침수", "태풍/집중호우", "가입 차량"
    elif any(token in text for token in ("암", "진단", "고액암")):
        incident_type, cause, target = "암 진단비", "질병 진단", "피보험자"
    elif any(token in text for token in ("도수치료", "비급여", "실손", "진료비")):
        incident_type, cause, target = "실손 의료비", "의료비 발생", "피보험자"
    elif any(token in text for token in ("치아", "임플란트", "크라운", "보철")):
        incident_type, cause, target = "치아 치료", "치과 치료", "피보험자"
    else:
        incident_type, cause, target = "확인 필요", "확인 필요", "확인 필요"

    if route == "document_claim" or any(token in text for token in ("서류", "청구", "영수증", "진단서", "첨부")):
        stage = "청구 서류 점검"
    elif route == "precedent_dispute" or any(token in text for token in ("분쟁", "판례", "사례", "거절")):
        stage = "분쟁 사례 확인"
    elif route == "cs_complaint" or any(token in text for token in ("상담원", "민원", "불만")):
        stage = "상담 연결 요청"
    else:
        stage = "보상 가능 여부 문의"

    return {
        "raw_question": text,
        "incident_type": incident_type,
        "cause": cause,
        "target": target,
        "stage": stage,
    }


def _extract_article_reference(text: str, fallback: str = "") -> str:
    article = re.search(r"(제\s*\d+\s*조(?:의\s*\d+)?)", text)
    paragraph = re.search(r"(제\s*\d+\s*항)", text)
    article_text = article.group(1).replace(" ", "") if article else ""
    paragraph_text = paragraph.group(1).replace(" ", "") if paragraph else ""
    if article_text and paragraph_text:
        return f"{article_text} {paragraph_text}"
    return article_text or fallback or "확인 필요"


def _extract_article_title(text: str) -> str:
    match = re.search(r"제\s*\d+\s*조(?:의\s*\d+)?\s*\(([^)]+)\)", text)
    return match.group(1).strip() if match else "확인 필요"


def _truncate(text: str, limit: int = 450) -> str:
    clean = re.sub(r"\s+", " ", _to_text(text)).strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def _evidence_template(question: str, product_name: str) -> tuple[str, str]:
    category = infer_product_category(product_name, question)
    if category == "auto":
        return (
            "이 조항은 차량 자체에 발생한 손해의 보상 가능성을 판단할 때 참고할 수 있는 약관 근거입니다.",
            "고객님이 설명한 침수 사고가 보장 대상에 해당하는지는 자기차량손해 담보와 면책 사유 확인이 필요합니다.",
        )
    if category == "cancer":
        return (
            "이 조항은 암 진단비 지급 요건과 진단 확정 기준을 확인할 때 참고할 수 있습니다.",
            "고객님의 암 진단비 청구 가능성은 진단서, 병리보고서 등 진단 확정 자료 확인이 중요합니다.",
        )
    if category == "indemnity":
        return (
            "이 조항은 실손의료비 또는 비급여 치료비 청구 조건을 확인할 때 참고할 수 있습니다.",
            "도수치료 비용 청구는 특약 가입 여부, 치료 목적, 세부내역서 제출 여부에 따라 달라질 수 있습니다.",
        )
    if category == "dental":
        return (
            "이 조항은 치아 치료와 보철 치료의 보장 조건을 확인할 때 참고할 수 있습니다.",
            "치과 치료 청구 가능성은 치료 종류, 면책기간, 보철 한도 확인에 따라 달라질 수 있습니다.",
        )
    return (
        "이 근거는 입력하신 상황과 약관 내용을 비교할 때 참고할 수 있습니다.",
        "고객님 상황에 실제 적용되는지는 가입 담보, 사고 경위, 제출 서류 확인이 필요합니다.",
    )


def build_evidence_cards(retrieved_docs: list[Any], question: str, product_name: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    ai_interpretation, application = _evidence_template(question, product_name)
    for doc in retrieved_docs[:3]:
        metadata = dict(getattr(doc, "metadata", None) or {})
        source_text = _to_text(getattr(doc, "page_content", ""))
        clause = _to_text(metadata.get("대분류") or metadata.get("category") or "약관 원문 기준")
        cards.append(
            {
                "document_name": _to_text(
                    metadata.get("source")
                    or metadata.get("file_name")
                    or metadata.get("문서명")
                    or f"{clause} 약관"
                ),
                "product_name": product_name or _to_text(metadata.get("product_name")) or "확인 필요",
                "article_number": _extract_article_reference(source_text, clause),
                "article_title": _extract_article_title(source_text),
                "clause_type": clause or "약관 원문 기준",
                "relevance_score": metadata.get("relevance_score"),
                "source_text": _truncate(source_text),
                "ai_interpretation": ai_interpretation,
                "application_to_customer": application,
                "metadata": metadata,
            }
        )
    return cards


def build_case_evidence_cards(cases: list[dict[str, Any]], question: str, product_name: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    _, application = _evidence_template(question, product_name)
    for case in cases[:3]:
        source_text = f"{case.get('issue', '')} {case.get('summary', '')} {case.get('decision', '')}"
        cards.append(
            {
                "document_name": "분쟁조정례",
                "product_name": product_name or "확인 필요",
                "article_number": _to_text(case.get("case_id")) or "확인 필요",
                "article_title": _to_text(case.get("title")) or "확인 필요",
                "clause_type": "유사 분쟁 사례",
                "relevance_score": None,
                "source_text": _truncate(source_text),
                "ai_interpretation": "이 사례는 유사한 보험 분쟁에서 어떤 쟁점이 검토됐는지 참고할 수 있는 자료입니다.",
                "application_to_customer": application,
                "metadata": case,
            }
        )
    return cards


def infer_uploaded_doc_type(filename: str) -> str:
    text = _to_text(filename).lower()
    if any(token in text for token in ("receipt", "영수증", "진료비")):
        return "진료비 영수증"
    if any(token in text for token in ("diagnosis", "진단서")):
        return "진단서"
    if any(token in text for token in ("confirm", "확인서", "진료확인")):
        return "진료확인서"
    if any(token in text for token in ("detail", "세부내역", "세부산정")):
        return "진료비 세부내역서"
    if any(token in text for token in ("estimate", "견적", "수리견적")):
        return "수리견적서"
    if any(token in text for token in ("accident", "사고사실", "사고확인")):
        return "사고사실확인서"
    if any(token in text for token in ("registration", "차량등록", "등록증")):
        return "차량등록증"
    if any(token in text for token in ("pathology", "병리", "조직검사")):
        return "병리보고서"
    if any(token in text for token in ("photo", "침수사진", "사진", "flood")):
        return "침수 사진"
    if text.endswith(".pdf"):
        return "PDF 서류"
    return "기타/판별불가"


def _doc_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(_to_text(doc_type), _to_text(doc_type) or "기타 서류")


def _required_doc_codes(product_name: str, question: str, required_docs_rules: dict[str, Any]) -> list[str]:
    rules = required_docs_rules.get("rules", []) if isinstance(required_docs_rules, dict) else []
    for rule in rules:
        keyword = _to_text(rule.get("product_keyword"))
        if keyword and keyword in _to_text(product_name):
            docs = list(rule.get("required_docs", []))
            break
    else:
        docs = list(required_docs_rules.get("default", [])) if isinstance(required_docs_rules, dict) else []

    if infer_product_category(product_name, question) == "auto" and any(
        token in _to_text(question) for token in ("침수", "태풍", "홍수")
    ):
        docs.append("flood_photo")
    return _unique([_to_text(doc) for doc in docs])


def calculate_claim_readiness(required_docs: list[str], submitted_docs: list[str]) -> tuple[int, str]:
    if not required_docs:
        return 0, "청구 서류 준비 전"
    submitted_set = set(submitted_docs)
    matched_count = len([doc for doc in required_docs if doc in submitted_set])
    percent = int(matched_count / len(required_docs) * 100)
    if percent <= 0:
        return 0, "청구 서류 준비 전"
    if percent < 50:
        return percent, "서류 준비 필요"
    if percent < 80:
        return percent, "일부 준비 완료"
    if percent < 100:
        return percent, "거의 준비 완료"
    return 100, "기본 서류 준비 완료"


def build_claim_checklist(
    product_name: str,
    question: str,
    uploaded_files: list[dict[str, Any]] | None,
    required_docs_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    rules = required_docs_rules or {}
    required_docs = [_doc_label(code) for code in _required_doc_codes(product_name, question, rules)]
    submitted_docs: list[str] = []
    for file_info in uploaded_files or []:
        filename = _to_text(file_info.get("doc_name") or file_info.get("name") or file_info.get("storage_path"))
        doc_type = _to_text(file_info.get("doc_type"))
        label = _doc_label(doc_type) if doc_type else ""
        filename_label = infer_uploaded_doc_type(filename)
        if label and label not in ("기타 서류", "PDF 서류"):
            submitted_docs.append(label)
        submitted_docs.append(filename_label)

    required_docs = _unique(required_docs)
    submitted_docs = _unique(submitted_docs)
    missing_docs = [doc for doc in required_docs if doc not in set(submitted_docs)] if required_docs else []
    readiness_percent, readiness_label = calculate_claim_readiness(required_docs, submitted_docs)
    return {
        "required_docs": required_docs,
        "submitted_docs": submitted_docs,
        "missing_docs": missing_docs,
        "readiness_percent": readiness_percent,
        "readiness_label": readiness_label,
    }


def _product_matches_incident(customer_summary: dict[str, Any], incident_summary: dict[str, str]) -> bool:
    product_category = infer_product_category(_to_text(customer_summary.get("product_name")))
    incident_category = infer_product_category("", _to_text(incident_summary.get("incident_type")))
    return product_category == "unknown" or incident_category == "unknown" or product_category == incident_category


def build_coverage_assessment(
    question: str,
    route: str,
    customer_summary: dict[str, Any],
    evidence_cards: list[dict[str, Any]],
    claim_checklist: dict[str, Any] | None = None,
    incident_summary: dict[str, str] | None = None,
) -> dict[str, Any]:
    checklist = claim_checklist or {}
    incident = incident_summary or build_incident_summary(question, route)
    has_customer = customer_summary.get("product_name") not in ("", "확인 필요", None)
    has_evidence = bool(evidence_cards)

    if route == "cs_complaint":
        status = "out_of_scope"
    elif not has_customer:
        status = "not_enough_evidence"
    elif not _product_matches_incident(customer_summary, incident):
        status = "out_of_scope"
    elif not has_evidence and route in ("policy_diagnosis", "precedent_dispute"):
        status = "not_enough_evidence"
    else:
        status = "need_more_info"

    missing_info = []
    if incident.get("incident_type") == "확인 필요":
        missing_info.append("사고 또는 치료 유형")
    if route in ("policy_diagnosis", "precedent_dispute"):
        missing_info.extend(["정확한 사고 발생일", "사고 장소 또는 치료 일자"])
    missing_info.extend(checklist.get("missing_docs") or [])

    summaries = {
        "need_more_info": "현재 입력된 정보와 확인된 근거를 기준으로 보상 가능성을 검토할 수 있습니다. 다만 실제 지급 여부는 담보 가입 여부, 사고 원인, 제출 서류, 면책 사유 확인 결과에 따라 달라질 수 있습니다.",
        "likely_covered": "확인된 근거와 고객님의 가입상품이 관련되어 보상 가능성을 검토해볼 수 있습니다. 단, 최종 판단에는 추가 심사가 필요합니다.",
        "possibly_excluded": "입력 내용 중 면책 또는 제한 사유가 함께 검토될 수 있습니다. 약관 원문과 사고 경위 확인이 필요합니다.",
        "not_enough_evidence": "현재 정보만으로는 보상 가능성을 판단할 근거가 충분하지 않습니다. 사고 상황과 관련 서류를 더 구체적으로 확인해야 합니다.",
        "out_of_scope": "현재 요청은 가입상품의 보장 범위와 직접 연결되지 않을 수 있습니다. 상담원 또는 담당자 확인이 필요합니다.",
    }
    return {
        "status": status,
        "label": COVERAGE_LABELS.get(status, "추가 확인 필요"),
        "summary": summaries.get(status, summaries["need_more_info"]),
        "missing_info": _unique(missing_info),
        "cautions": [
            "본 안내는 약관과 입력 정보를 바탕으로 한 사전 안내입니다.",
            "실제 지급 여부는 보험사의 심사 결과에 따라 달라질 수 있습니다.",
            "청구 서류 준비율은 지급 가능성이 아니라 제출 서류 준비 상태를 뜻합니다.",
        ],
    }


def build_next_actions(route: str, claim_checklist: dict[str, Any], incident_summary: dict[str, str]) -> list[str]:
    missing_docs = claim_checklist.get("missing_docs") or []
    if route == "cs_complaint":
        return ["불편 내용과 원하는 조치 사항을 한 문장으로 정리해 주세요.", "상담원이 이어서 확인할 수 있도록 문의 내용을 정리해 주세요."]
    actions = []
    if missing_docs:
        actions.append(f"추가 필요 서류를 준비해 주세요: {', '.join(missing_docs)}")
    if incident_summary.get("stage") == "분쟁 사례 확인":
        actions.append("보험사의 지급 거절 사유서나 안내 문구가 있다면 함께 확인해 주세요.")
    else:
        actions.append("사고 일자, 장소, 치료명 또는 손해 항목을 구체적으로 정리해 주세요.")
    actions.append("준비된 서류를 첨부하면 청구 서류 준비율을 다시 점검할 수 있습니다.")
    return actions


def build_diagnosis_result(
    *,
    customer_info: dict[str, Any] | None,
    customer_id: str,
    question: str,
    route: str,
    evidence_cards: list[dict[str, Any]] | None = None,
    claim_checklist: dict[str, Any] | None = None,
    uploaded_documents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    customer_summary = build_customer_summary(customer_info, customer_id)
    incident_summary = build_incident_summary(question, route)
    cards = evidence_cards or []
    checklist = claim_checklist or {
        "required_docs": [],
        "submitted_docs": [],
        "missing_docs": [],
        "readiness_percent": 0,
        "readiness_label": "청구 서류 준비 전",
    }
    assessment = build_coverage_assessment(
        question,
        route,
        customer_summary,
        cards,
        checklist,
        incident_summary,
    )
    return {
        "customer_summary": customer_summary,
        "incident_summary": incident_summary,
        "coverage_assessment": assessment,
        "evidence_cards": cards,
        "claim_checklist": checklist,
        "uploaded_documents": uploaded_documents
        or {
            "files": [],
            "extraction_results": [],
            "comparison_result": {},
            "missing_key_fields": [],
            "mismatches": [],
        },
        "next_actions": build_next_actions(route, checklist, incident_summary),
        "disclaimer": LEGAL_DISCLAIMER,
    }
