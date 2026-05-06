from __future__ import annotations

import logging
from typing import Any

from app.core.formatting import as_list, to_text, unique_texts
from app.pipeline.diagnosis_report import build_claim_checklist, build_evidence_cards
from app.services.customer_service import select_relevant_policies


logger = logging.getLogger(__name__)

PRODUCT_KEYWORDS = {
    "auto": ["자동차", "차량", "자기차량손해", "대인배상", "대물배상", "침수", "수리", "사고"],
    "cancer": ["암", "암진단", "진단비", "고액암", "병리", "조직검사", "악성신생물"],
    "indemnity": ["실손", "실손의료비", "의료비", "도수치료", "비급여", "진료비", "입원", "통원"],
    "dental": ["치아", "치과", "보철", "임플란트", "크라운", "브릿지", "틀니"],
}

CATEGORY_NAME_HINTS = {
    "auto": ("자동차", "차량", "운전자"),
    "cancer": ("암", "진단비", "악성신생물"),
    "indemnity": ("실손", "의료비", "상해", "질병", "입원", "통원"),
    "dental": ("치아", "치과", "보철", "임플란트"),
}

POLICY_SECTION_TITLES = {
    "auto": "자동차보험 기준 검토",
    "indemnity": "실손보험 기준 검토",
    "cancer": "암보험 기준 검토",
    "dental": "치아보험 기준 검토",
    "unknown": "가입상품 기준 검토",
}

POLICY_QUERY_HINTS = {
    "auto": "자동차보험 자기차량손해 대인배상 대물배상 교통사고 차량 수리 견적",
    "indemnity": "실손보험 실손의료비 상해 치료비 진료비 입원 통원 비급여 병원",
    "cancer": "암보험 암진단비 진단확정 병리보고서 조직검사 항암치료",
    "dental": "치아보험 치과치료 임플란트 크라운 보철 치아 손상",
    "unknown": "보험 약관 보상 기준 필요서류",
}


def infer_product_category(product_name: str) -> str:
    normalized = to_text(product_name).lower()
    for category, hints in CATEGORY_NAME_HINTS.items():
        if any(hint.lower() in normalized for hint in hints):
            return category
    return "unknown"


def metadata_text(doc: Any) -> str:
    metadata = getattr(doc, "metadata", None) or {}
    return " ".join(to_text(value) for value in metadata.values())


def query_focus_keywords(query: str) -> list[str]:
    focus_map = {
        ("침수", "태풍", "홍수", "해일", "범람", "잠기", "물에"): [
            "침수",
            "태풍",
            "홍수",
            "해일",
            "자기차량손해",
            "차량단독사고",
            "보장확대",
        ],
        ("차", "자동차", "차량"): ["자동차", "피보험자동차", "자기차량손해", "차량단독사고"],
        ("치아", "치과", "보철", "임플란트"): ["치아", "치과", "보철", "임플란트"],
        ("암", "진단", "항암"): ["암", "진단", "항암"],
        ("도수", "통원", "입원", "비급여"): ["실손", "도수치료", "통원", "입원", "비급여"],
    }
    matched: list[str] = []
    for triggers, keywords in focus_map.items():
        if any(trigger in query for trigger in triggers):
            matched.extend(keywords)
    return unique_texts(matched)


def product_keywords(product_name: str) -> list[str]:
    return PRODUCT_KEYWORDS.get(infer_product_category(product_name), [])


def expanded_policy_query(query: str, product_name: str) -> str:
    hints = unique_texts([*query_focus_keywords(query), *product_keywords(product_name)])
    if not hints:
        return query
    return f"{query}\n핵심검색어: {' '.join(hints)}"


def score_policy_doc(doc: Any, query: str, focus_keywords: list[str]) -> int:
    text = f"{getattr(doc, 'page_content', '')} {metadata_text(doc)}"
    score = 0
    for keyword in focus_keywords:
        if keyword and keyword in text:
            score += 3
    if "침수" in query and "침수" in text:
        score += 8
    if "태풍" in query and ("태풍" in text or "홍수" in text or "해일" in text):
        score += 5
    if ("차" in query or "자동차" in query or "차량" in query) and "자기차량손해" in text:
        score += 5
    if "화재" in text and "화재" not in query and "침수" not in text:
        score -= 4
    return score


def rerank_docs_by_customer_product(docs: list[Any], product_name: str, question: str) -> list[Any]:
    category = infer_product_category(product_name)
    product_terms = PRODUCT_KEYWORDS.get(category, [])
    question_terms = query_focus_keywords(question)

    def score(doc: Any) -> int:
        text = f"{getattr(doc, 'page_content', '')} {metadata_text(doc)}"
        value = 0
        for keyword in product_terms:
            if keyword and keyword in text:
                value += 5
        for keyword in question_terms:
            if keyword and keyword in text:
                value += 3
        value += score_policy_doc(doc, question, [*product_terms, *question_terms])
        if category != "unknown":
            unrelated_categories = [
                other
                for other in PRODUCT_KEYWORDS
                if other != category and any(kw in text for kw in PRODUCT_KEYWORDS[other][:4])
            ]
            if unrelated_categories and not any(kw in text for kw in product_terms):
                value -= 8
        return value

    return sorted(docs, key=score, reverse=True)


def dedupe_docs(docs: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    unique: list[Any] = []
    for doc in docs:
        key = (getattr(doc, "page_content", "")[:200], to_text((getattr(doc, "metadata", None) or {}).get("대분류")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def policy_doc_debug_items(docs: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs, start=1):
        metadata = dict(getattr(doc, "metadata", None) or {})
        items.append(
            {
                "rank": idx,
                "metadata": {key: metadata[key] for key in list(metadata.keys())[:5]},
                "preview": to_text(getattr(doc, "page_content", ""))[:140],
            }
        )
    return items


def _policy_public(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_id": policy.get("customer_id"),
        "product_id": policy.get("product_id"),
        "product_name": policy.get("product_name"),
        "joined_year": policy.get("joined_year") or policy.get("join_year"),
        "policy_number": policy.get("policy_number"),
        "riders": policy.get("riders") or policy.get("special_clauses") or [],
        "coverage_limit": policy.get("coverage_limit"),
        "insured_person": policy.get("insured_person"),
        "vehicle_number": policy.get("vehicle_number"),
    }


def _multi_policy_reason(policies: list[dict[str, Any]], question: str) -> str:
    joined = ", ".join([p.get("product_name", "가입상품") for p in policies])
    has_auto = any(token in question for token in ("교통사고", "차 사고", "차량 사고", "차도", "자동차"))
    has_medical = any(token in question for token in ("병원", "치료", "진료비", "치료비", "실손", "실비"))
    if has_auto and has_medical:
        return f"질문에 차량 사고와 병원 치료비가 함께 포함되어 {joined}을 함께 검토했습니다."
    if len(policies) >= 3:
        return f"질문에 여러 보장 영역이 함께 포함되어 {joined}을 상품별로 나누어 검토했습니다."
    return f"질문 내용상 {joined}이 함께 관련될 수 있어 상품별로 나누어 검토했습니다."


def _build_policy_rag_query(question: str, policy: dict[str, Any]) -> str:
    product_name = to_text(policy.get("product_name"))
    category = infer_product_category(product_name)
    return f"{question}\n가입상품:{product_name}\n핵심검색어:{POLICY_QUERY_HINTS.get(category, '')}"


def _text_list(items: Any) -> list[str]:
    labels: list[str] = []
    for item in as_list(items):
        if isinstance(item, dict):
            labels.append(to_text(item.get("label") or item.get("doc") or " 또는 ".join(item.get("any_of") or [])))
        else:
            labels.append(to_text(item))
    return [item for item in labels if item]


def _build_policy_coverage_assessment(
    *,
    question: str,
    route: str,
    policy: dict[str, Any],
    evidence_cards: list[dict[str, Any]],
    claim_checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    product_name = to_text(policy.get("product_name"))
    category = infer_product_category(product_name)
    missing_by_category = {
        "auto": ["사고일시와 장소", "차량 수리견적서", "가입 차량번호와 사고 차량번호 일치 여부"],
        "indemnity": ["진료비 영수증", "진료비 세부내역서", "진단서 또는 진료확인서"],
        "cancer": ["진단서", "병리보고서 또는 조직검사 결과", "진단일과 진단명"],
        "dental": ["진료비 영수증", "치과 진료기록", "치료 전후 사진 또는 엑스레이"],
        "unknown": ["사고 경위", "관련 서류", "담보 가입 여부"],
    }
    summary_by_category = {
        "auto": "자동차보험 기준으로는 차량 손해, 사고 처리, 자기차량손해 담보, 대인/대물 배상 항목을 중심으로 검토할 수 있습니다. 실제 지급 여부는 사고 경위, 담보 가입 여부, 면책 사유 확인 결과에 따라 달라질 수 있습니다.",
        "indemnity": "실손보험 기준으로는 사고 후 발생한 병원 치료비, 입원/통원 진료비, 비급여 항목 등을 중심으로 검토할 수 있습니다. 진료비 영수증과 세부내역서 확인이 필요할 수 있습니다.",
        "cancer": "암보험 기준으로는 암 진단비 지급 요건, 진단 확정 자료, 병리 또는 조직검사 결과를 중심으로 검토할 수 있습니다.",
        "dental": "치아보험 기준으로는 치과 치료 내용, 보철 또는 임플란트 치료 여부, 치료 기록을 중심으로 검토할 수 있습니다.",
        "unknown": "해당 가입상품 기준으로 검토할 수 있으나, 질문과 상품의 관련성 및 약관 근거를 추가 확인해야 합니다.",
    }
    cautions_by_category = {
        "auto": ["자동차보험은 차량 손해와 사고 배상 책임 중심으로 검토됩니다."],
        "indemnity": ["자동차보험에서 처리되는 치료비와 실손보험 청구 가능 항목은 중복 보상 여부 확인이 필요할 수 있습니다."],
        "cancer": ["진단비와 치료비는 서로 다른 담보 기준으로 검토될 수 있습니다."],
        "dental": ["사고 원인과 치과 진료기록이 모두 중요합니다."],
        "unknown": ["본 안내는 입력 정보와 약관 근거를 바탕으로 한 사전 검토입니다."],
    }
    missing_info = unique_texts(
        [
            *missing_by_category.get(category, []),
            *_text_list((claim_checklist or {}).get("missing_docs"))[:3],
        ]
    )
    return {
        "status": "need_more_info" if evidence_cards else "not_enough_evidence",
        "label": "추가 확인 필요" if evidence_cards else "근거 부족",
        "summary": summary_by_category.get(category, summary_by_category["unknown"]),
        "missing_info": missing_info,
        "cautions": cautions_by_category.get(category, cautions_by_category["unknown"]),
        "route": route,
        "product_name": product_name,
    }


def _policy_next_actions(category: str, checklist: dict[str, Any]) -> list[str]:
    missing = _text_list((checklist or {}).get("missing_docs"))
    actions: list[str] = []
    if missing:
        actions.append(f"누락 가능 서류를 확인해 주세요: {', '.join(missing[:3])}")
    category_actions = {
        "auto": "사고일시, 사고장소, 차량번호, 수리견적을 확인해 주세요.",
        "indemnity": "진료비 영수증, 세부내역서, 진단서 또는 진료확인서를 확인해 주세요.",
        "cancer": "진단서와 병리보고서 등 진단 확정 자료를 확인해 주세요.",
        "dental": "치과 진료기록과 치료 전후 확인 자료를 확인해 주세요.",
    }
    actions.append(category_actions.get(category, "담보 가입 여부와 제출 서류를 확인해 주세요."))
    return unique_texts(actions)


def _run_rag_for_policy(
    *,
    question: str,
    policy: dict[str, Any],
    route: str,
    vectorstore: Any | None,
    rule_db: dict[str, Any],
    uploaded_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    product_name = to_text(policy.get("product_name"))
    category = infer_product_category(product_name)
    rag_query = _build_policy_rag_query(question, policy)
    retrieved_docs: list[Any] = []
    debug: dict[str, Any] = {"num_retrieved": 0, "product_filter": product_name, "error": None}
    if vectorstore is not None:
        try:
            retrieved_docs = dedupe_docs(
                [
                    *vectorstore.similarity_search(question, k=5),
                    *vectorstore.similarity_search(rag_query, k=8),
                ]
            )
            retrieved_docs = rerank_docs_by_customer_product(retrieved_docs, product_name, question)[:3]
            debug["num_retrieved"] = len(retrieved_docs)
            debug["documents"] = policy_doc_debug_items(retrieved_docs)
        except Exception as exc:
            logger.exception("Multi-policy RAG failed: %s", product_name)
            debug["error"] = str(exc)
    claim_checklist = build_claim_checklist(product_name, question, uploaded_docs or [], rule_db)
    evidence_cards = build_evidence_cards(retrieved_docs, question, product_name)
    assessment = _build_policy_coverage_assessment(
        question=question,
        route=route,
        policy=policy,
        evidence_cards=evidence_cards,
        claim_checklist=claim_checklist,
    )
    return {
        "policy": _policy_public(policy),
        "policy_category": category,
        "section_title": POLICY_SECTION_TITLES.get(category, POLICY_SECTION_TITLES["unknown"]),
        "rag_query": rag_query,
        "retrieved_doc_count": len(retrieved_docs),
        "evidence_cards": evidence_cards,
        "coverage_assessment": assessment,
        "claim_checklist": claim_checklist,
        "cautions": assessment.get("cautions", []),
        "next_actions": _policy_next_actions(category, claim_checklist),
        "debug": debug,
    }


def _build_cross_policy_cautions(policy_results: list[dict[str, Any]], question: str) -> list[str]:
    categories = {result.get("policy_category") for result in policy_results}
    cautions: list[str] = []
    if {"auto", "indemnity"} <= categories:
        cautions.extend(
            [
                "자동차 사고로 인한 치료비는 자동차보험 처리 여부와 실손보험 청구 가능 여부를 함께 확인해야 합니다.",
                "동일한 치료비에 대해서는 중복 보상 여부 확인이 필요할 수 있습니다.",
                "차량 손해는 자동차보험 기준, 병원 치료비는 실손보험 기준으로 구분해 검토하는 것이 좋습니다.",
            ]
        )
    if {"auto", "dental"} <= categories:
        cautions.extend(
            [
                "교통사고로 인한 치아 손상은 사고 처리와 치아 치료 보장 조건을 함께 확인해야 합니다.",
                "사고 원인과 치과 진료기록이 모두 중요합니다.",
            ]
        )
    if {"cancer", "indemnity"} <= categories:
        cautions.extend(
            [
                "암 진단비는 암보험 기준, 치료비는 실손보험 기준으로 각각 검토해야 합니다.",
                "진단 확정 자료와 진료비 서류가 모두 필요할 수 있습니다.",
            ]
        )
    if len(categories) >= 3:
        cautions.append("여러 상품이 관련될 수 있으므로 상품별 보장 범위와 중복 청구 가능 여부를 상담원 또는 심사자가 확인해야 합니다.")
    if not cautions:
        cautions.append("두 상품 모두 관련될 수 있어 상품별 보장 범위와 제출 서류를 나누어 확인하는 것이 좋습니다.")
    return unique_texts(cautions)


def _recommended_policy_order(policy_results: list[dict[str, Any]]) -> list[str]:
    order_hint = {"auto": 0, "indemnity": 1, "cancer": 2, "dental": 3, "unknown": 9}
    sorted_results = sorted(policy_results, key=lambda item: order_hint.get(item.get("policy_category"), 9))
    return [item.get("section_title", "가입상품 기준 검토") for item in sorted_results]


def build_multi_policy_analysis(
    *,
    customer: dict[str, Any],
    question: str,
    route: str,
    vectorstore: Any | None,
    rule_db: dict[str, Any],
    uploaded_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        selected = customer.get("relevant_policies") or select_relevant_policies(customer, question)
    except Exception:
        logger.exception("Multi-policy selection failed")
        selected = []
    if not selected:
        selected = [customer] if customer.get("product_name") else []
    selected = [dict(policy) for policy in selected if policy.get("product_name")]
    if not selected:
        return {"enabled": False, "reason": "가입상품 정보를 찾지 못했습니다.", "policy_results": []}

    policy_results = [
        _run_rag_for_policy(
            question=question,
            policy=policy,
            route=route,
            vectorstore=vectorstore,
            rule_db=rule_db,
            uploaded_docs=uploaded_docs,
        )
        for policy in selected
    ]
    cross_cautions = _build_cross_policy_cautions(policy_results, question) if len(policy_results) >= 2 else []
    return {
        "enabled": len(policy_results) >= 2,
        "reason": _multi_policy_reason(selected, question) if len(policy_results) >= 2 else "관련 가입상품 1개를 기준으로 검토했습니다.",
        "policy_results": policy_results,
        "combined_summary": {
            "summary": "상품별 보장 범위와 필요서류를 분리해 검토했습니다." if len(policy_results) >= 2 else "",
            "cross_policy_cautions": cross_cautions,
            "recommended_order": _recommended_policy_order(policy_results),
        },
    }


def merge_multi_policy_into_diagnosis(
    diagnosis_result: dict[str, Any],
    multi_policy_analysis: dict[str, Any],
) -> dict[str, Any]:
    if not diagnosis_result:
        diagnosis_result = {}
    policy_results = multi_policy_analysis.get("policy_results") or []
    diagnosis_result["selected_policies"] = [result.get("policy") for result in policy_results if result.get("policy")]
    diagnosis_result["multi_policy_analysis"] = multi_policy_analysis
    if policy_results:
        primary = policy_results[0]
        diagnosis_result.setdefault("evidence_cards", primary.get("evidence_cards") or [])
        diagnosis_result.setdefault("claim_checklist", primary.get("claim_checklist") or {})
        diagnosis_result.setdefault("coverage_assessment", primary.get("coverage_assessment") or {})
    return diagnosis_result


def build_multi_policy_answer(multi_policy_analysis: dict[str, Any]) -> str:
    policy_results = multi_policy_analysis.get("policy_results") or []
    lines = ["[복수 보험상품 기준 사전진단]", "", multi_policy_analysis.get("reason") or "여러 가입상품을 함께 검토했습니다.", ""]
    for idx, result in enumerate(policy_results, start=1):
        policy = result.get("policy") or {}
        assessment = result.get("coverage_assessment") or {}
        checklist = result.get("claim_checklist") or {}
        first_evidence = (result.get("evidence_cards") or [{}])[0]
        evidence_label = (
            first_evidence.get("article_number")
            or first_evidence.get("article_title")
            or first_evidence.get("document_name")
            or "해당 상품 기준 근거를 충분히 찾지 못했습니다"
        )
        required_docs = _text_list(checklist.get("required_docs") or checklist.get("missing_docs"))
        missing_info = _text_list(assessment.get("missing_info"))
        lines.extend(
            [
                f"{idx}. {result.get('section_title', '가입상품 기준 검토')}",
                f"- 검토 대상: {policy.get('product_name', '확인 필요')}",
                f"- 판단 요약: {assessment.get('summary', '현재 정보 기준으로 추가 확인이 필요합니다.')}",
                f"- 주요 근거: {evidence_label} [근거: {evidence_label}]",
                f"- 필요 서류: {', '.join(required_docs[:5]) if required_docs else '상품 기준 필요 서류 확인 필요'}",
                f"- 추가 확인사항: {', '.join(missing_info[:4]) if missing_info else '담보 가입 여부와 제출 서류 확인 필요'}",
                "",
            ]
        )
    cautions = (multi_policy_analysis.get("combined_summary") or {}).get("cross_policy_cautions") or []
    if cautions:
        lines.append("함께 확인할 점")
        for caution in cautions:
            lines.append(f"- {caution}")
        lines.append("")
    lines.append("실제 지급 여부와 금액은 약관, 제출 서류, 보험사 심사 결과에 따라 달라질 수 있습니다.")
    return "\n".join(lines)

