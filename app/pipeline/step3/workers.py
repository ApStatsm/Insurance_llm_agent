from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any
import uuid

from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate

from app.pipeline.diagnosis_report import (
    build_case_evidence_cards,
    build_claim_checklist,
    build_diagnosis_result,
    build_evidence_cards,
)
from app.pipeline.step0.validator import build_audit_event, validate_node_entry, validate_node_update
from app.services.claim_document_rules import (
    build_claim_checklist_from_comparison,
    check_missing_key_fields,
    compare_extracted_docs_with_required,
    detect_customer_document_mismatches,
    get_required_rule,
)
from app.services.vision_doc_extractor import extract_documents_for_uploaded_files


PRECEDENT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "precedent_cases.json"
PRODUCT_DOC_RULE_DB_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "knowledge" / "product_required_docs.json"
)

ROUTE_TO_WORKER = {
    "policy_diagnosis": "POLICY_DIAGNOSIS_WORKER",
    "precedent_dispute": "PRECEDENT_DISPUTE_WORKER",
    "document_claim": "DOCUMENT_CLAIM_WORKER",
    "cs_complaint": "CS_COMPLAINT_WORKER",
}

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _metadata_text(doc: Any) -> str:
    metadata = getattr(doc, "metadata", None) or {}
    return " ".join(_to_text(value) for value in metadata.values())


def _guardrail_content(content: str, citations: list[dict[str, Any]]) -> str:
    text = content
    replacements = {
        "지급됩니다": "지급 가능성이 있습니다",
        "보상받으실 수 있습니다": "보상 가능성이 있습니다",
        "반드시 지급": "요건을 충족하면 지급 가능성이 있습니다",
        "무조건 지급": "약관 요건을 충족하면 지급 가능성이 있습니다",
        "100% 지급": "약관 기준에 따라 지급 가능성이 있습니다",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    if "[출처:" not in text and "[근거:" not in text and citations:
        first = citations[0]
        marker = _to_text(first.get("cite_tag")) or "출처"
        source_id = first.get("source_id", "DOC1")
        label = first.get("reference") or first.get("clause") or first.get("case_id") or "근거"
        text = f"{text}\n\n[{marker}: {source_id}|{label}]"
    return text


def _extract_claim_amount(text: str) -> int | None:
    number_fragments = re.findall(r"(\d[\d,]{2,})\s*원", text)
    if not number_fragments:
        return None
    as_ints = [int(part.replace(",", "")) for part in number_fragments]
    return max(as_ints) if as_ints else None


def _to_int_amount(value: Any) -> int | None:
    raw = _to_text(value)
    number_only = "".join(ch for ch in raw if ch.isdigit())
    return int(number_only) if number_only else None


def _product_keywords(product_name: str) -> list[str]:
    category = infer_product_category(product_name)
    return PRODUCT_KEYWORDS.get(category, [])


def infer_product_category(product_name: str) -> str:
    normalized = _to_text(product_name).lower()
    for category, hints in CATEGORY_NAME_HINTS.items():
        if any(hint.lower() in normalized for hint in hints):
            return category
    return "unknown"


def _query_focus_keywords(query: str) -> list[str]:
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
    return list(dict.fromkeys(matched))


def _expanded_policy_query(query: str, product_name: str) -> str:
    focus = _query_focus_keywords(query)
    product = _product_keywords(product_name)
    hints = list(dict.fromkeys([*focus, *product]))
    if not hints:
        return query
    return f"{query}\n핵심검색어: {' '.join(hints)}"


def _score_policy_doc(doc: Any, query: str, focus_keywords: list[str]) -> int:
    text = f"{getattr(doc, 'page_content', '')} {_metadata_text(doc)}"
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
    product_keywords = PRODUCT_KEYWORDS.get(category, [])
    question_keywords = _query_focus_keywords(question)

    def score(doc: Any) -> int:
        text = f"{getattr(doc, 'page_content', '')} {_metadata_text(doc)}"
        value = 0
        for keyword in product_keywords:
            if keyword and keyword in text:
                value += 5
        for keyword in question_keywords:
            if keyword and keyword in text:
                value += 3
        value += _score_policy_doc(doc, question, [*product_keywords, *question_keywords])
        if category != "unknown":
            unrelated_categories = [
                other
                for other in PRODUCT_KEYWORDS
                if other != category and any(kw in text for kw in PRODUCT_KEYWORDS[other][:4])
            ]
            if unrelated_categories and not any(kw in text for kw in product_keywords):
                value -= 8
        return value

    return sorted(docs, key=score, reverse=True)


def _dedupe_docs(docs: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    unique: list[Any] = []
    for doc in docs:
        key = (getattr(doc, "page_content", "")[:200], _to_text((getattr(doc, "metadata", None) or {}).get("대분류")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def _extract_article_reference(text: str, fallback_clause: str) -> str:
    article_match = re.search(r"(제\s*\d+\s*조(?:의\s*\d+)?)", text)
    paragraph_match = re.search(r"(제\s*\d+\s*항)", text)
    article = article_match.group(1).replace(" ", "") if article_match else ""
    paragraph = paragraph_match.group(1).replace(" ", "") if paragraph_match else ""
    if article and paragraph:
        return f"{article} {paragraph}"
    if article:
        return article
    return fallback_clause or "약관 해당 조항"


def _extract_article_title(text: str) -> str:
    # Typical form: "제12조(보상하는 손해)" or "제12조 (보상하는 손해)"
    m = re.search(r"제\s*\d+\s*조(?:의\s*\d+)?\s*\(([^)]+)\)", text)
    if m:
        return m.group(1).strip()
    return ""


def _build_reference_display(reference: str, title: str, fallback_clause: str) -> str:
    ref = _to_text(reference).strip()
    ttl = _to_text(title).strip()
    fallback = _to_text(fallback_clause).strip()
    if ref and ttl:
        return f"{ref}({ttl})"
    if ref:
        return ref
    return fallback or "약관 해당 조항"


def _rewrite_policy_citations(content: str, citations: list[dict[str, Any]]) -> str:
    doc_ref_map: dict[str, str] = {}
    for c in citations:
        source_id = _to_text(c.get("source_id"))
        ref = (
            _to_text(c.get("reference_display"))
            or _to_text(c.get("reference"))
            or _to_text(c.get("clause"))
            or "약관 해당 조항"
        )
        doc_ref_map[source_id] = ref

    pattern = re.compile(r"\[(?:출처|근거):\s*(DOC\d+)\|[^\]]*\]")

    def _repl(match: re.Match[str]) -> str:
        doc_id = match.group(1)
        ref = doc_ref_map.get(doc_id, "약관 해당 조항")
        return f"[근거: {ref}]"

    rewritten = pattern.sub(_repl, content)
    # 모델이 [출처: DOC1] 형태로만 낸 경우도 커버
    rewritten = re.sub(
        r"\[(?:출처|근거):\s*(DOC\d+)\]",
        lambda m: f"[근거: {doc_ref_map.get(m.group(1), '약관 해당 조항')}]",
        rewritten,
    )
    return rewritten


def _format_policy_context(docs: list[Any], keyword_hint: str) -> tuple[str, list[dict[str, Any]]]:
    context_blocks: list[str] = []
    citations: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs, start=1):
        meta = dict(doc.metadata or {})
        clause = _to_text(meta.get("대분류", "")).strip()
        reference = _extract_article_reference(doc.page_content, clause)
        title = _extract_article_title(doc.page_content)
        reference_display = _build_reference_display(reference, title, clause)
        src_id = f"DOC{idx}"
        context_blocks.append(f"[{src_id}] {doc.page_content}")
        citations.append(
            {
                "source_id": src_id,
                "clause": clause or "조항 미상",
                "reference": reference,
                "article_title": title,
                "reference_display": reference_display,
                "keyword_hint": keyword_hint,
                "cite_tag": "근거",
            }
        )
    return "\n\n".join(context_blocks), citations


def _policy_doc_debug_items(docs: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs, start=1):
        metadata = dict(getattr(doc, "metadata", None) or {})
        items.append(
            {
                "rank": idx,
                "metadata": {key: metadata[key] for key in list(metadata.keys())[:5]},
                "preview": _to_text(getattr(doc, "page_content", ""))[:140],
            }
        )
    return items


def _run_policy_diagnosis_worker(
    state: dict[str, Any], *, vectorstore: Chroma | None, llm: Any
) -> dict[str, Any]:
    validate_node_entry("POLICY_DIAGNOSIS_WORKER", state)
    if vectorstore is None:
        raise RuntimeError("Policy diagnosis worker requires a vectorstore.")
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()

    customer = updated.get("customer_db_info") or {}
    product_name = _to_text(customer.get("product_name"))
    product_category = infer_product_category(product_name)
    join_year = _to_text(customer.get("join_year"))
    query = _to_text(updated.get("user_query"))
    keyword_hints = list(dict.fromkeys([*_query_focus_keywords(query), *_product_keywords(product_name)]))
    combined_query = f"{_expanded_policy_query(query, product_name)}\n가입상품:{product_name}\n가입연도:{join_year}"
    docs = _dedupe_docs(
        [
            *vectorstore.similarity_search(query, k=6),
            *vectorstore.similarity_search(combined_query, k=12),
        ]
    )
    searched_doc_count = len(docs)

    if keyword_hints:
        filtered = [
            d
            for d in docs
            if any(kw in getattr(d, "page_content", "") for kw in keyword_hints)
            or any(kw in _metadata_text(d) for kw in keyword_hints)
        ]
        docs = filtered if filtered else docs
    docs = rerank_docs_by_customer_product(docs, product_name, query)
    docs = docs[:5]

    debug_info = {
        "product_name": product_name,
        "product_category": product_category,
        "searched_doc_count": searched_doc_count,
        "used_doc_count": len(docs),
        "documents": _policy_doc_debug_items(docs),
    }
    rule_db = _load_product_doc_rules()
    claim_checklist = build_claim_checklist(product_name, query, updated.get("user_docs") or [], rule_db)
    uploaded_documents, vision_checklist, doc_analysis_summary = _build_uploaded_document_analysis(
        docs=updated.get("user_docs") or [],
        customer=customer,
        product_name=product_name,
        question=query,
        rule_db=rule_db,
        llm=llm,
    )
    if vision_checklist:
        claim_checklist = vision_checklist
    evidence_cards = build_evidence_cards(docs, query, product_name)
    diagnosis_result = build_diagnosis_result(
        customer_info=customer,
        customer_id=_to_text(updated.get("user_id")),
        question=query,
        route="policy_diagnosis",
        evidence_cards=evidence_cards,
        claim_checklist=claim_checklist,
        uploaded_documents=uploaded_documents,
    )

    if not docs:
        citations = [
            {
                "source_id": "POLICY_SEARCH",
                "reference": "검색결과없음",
                "reference_display": "검색결과없음",
                "cite_tag": "근거",
            }
        ]
        draft = {
            "worker_type": "policy_diagnosis",
            "content": _append_document_analysis_summary(
                (
                    "관련 약관을 찾지 못했습니다. 사고 상황을 조금 더 구체적으로 입력해 주세요. "
                    "예를 들어 사고 원인, 발생 장소, 치료명, 손해 항목을 함께 적어주시면 다시 확인해보겠습니다. "
                    "[근거: POLICY_SEARCH|검색결과없음]"
                ),
                doc_analysis_summary,
            ),
            "citations": citations,
            "diagnosis_result": diagnosis_result,
            "debug": debug_info,
            "created_at": updated["updated_at"],
        }
        patch = {
            "draft_response": draft,
            "citations": citations,
            "status": "WORKER_DRAFTED",
            "updated_at": updated["updated_at"],
            "error": None,
        }
        validate_node_update("POLICY_DIAGNOSIS_WORKER", state, patch)
        updated.update(patch)
        updated["audit_log"].append(
            build_audit_event(
                node="POLICY_DIAGNOSIS_WORKER",
                action="POLICY_SEARCH_EMPTY",
                note=f"product_category={product_category}, product={product_name or 'N/A'}",
            )
        )
        return updated

    context_text, citations = _format_policy_context(docs, ",".join(keyword_hints) if keyword_hints else "")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """당신은 고객이 안심하고 이해할 수 있게 돕는 보험 보상 안내 어시스턴트입니다.
반드시 제공된 <context> 안의 내용만을 근거로 답변하세요.
표가 일부 쪼개져 있더라도 문맥을 논리적으로 연결해 조건과 기준을 안내하세요.
<context>에 없는 내용은 추정하지 말고, 추가 확인이 필요하다고 안내하세요.

답변 톤 가이드:
- 고객에게 말하듯 부드럽고 쉬운 문장으로 작성
- 결론을 먼저 짧게 말하고, 이어서 조건/예외를 차근차근 설명
- 불안감을 키우는 표현보다 "확인해볼 수 있습니다", "가능성이 있습니다", "추가 확인이 필요합니다"처럼 안내
- 확언 금지(조건부 표현 사용)
- 질문의 핵심 사고 원인에만 집중하세요. 예를 들어 침수/태풍 질문이면 화재 조건은 필요한 경우에만 짧게 언급하고, 화재 사례 중심으로 답하지 마세요.

출력 형식:
1) 먼저 안내드리면: 한 줄 요약
2) 어떤 조건을 봐야 하나요?: 2~4줄
3) 추가로 확인하면 좋은 점: 1~2줄(없으면 생략 가능)
문장 끝에는 가능한 범위에서 [근거: 제n조 제m항(조항명)] 형식으로 붙이세요.
DOC번호/항목/대분류 같은 내부 표시는 답변에 직접 노출하지 마세요.
<context>
{context}
</context>
""",
            ),
            ("user", "고객질문: {query}"),
        ]
    )
    answer = llm.invoke(prompt.format_messages(context=context_text, query=query)).content
    answer = _guardrail_content(_to_text(answer), citations)
    answer = _rewrite_policy_citations(answer, citations)
    answer = _append_document_analysis_summary(answer, doc_analysis_summary)
    draft = {
        "worker_type": "policy_diagnosis",
        "content": answer,
        "citations": citations,
        "diagnosis_result": diagnosis_result,
        "debug": debug_info,
        "created_at": updated["updated_at"],
    }
    patch = {
        "draft_response": draft,
        "citations": citations,
        "status": "WORKER_DRAFTED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("POLICY_DIAGNOSIS_WORKER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(
            node="POLICY_DIAGNOSIS_WORKER",
            action="DRAFT_CREATED",
            note=f"docs={len(docs)}, product_category={product_category}, product={product_name or 'N/A'}",
        )
    )
    return updated


def _load_precedent_cases() -> list[dict[str, Any]]:
    if not PRECEDENT_DB_PATH.exists():
        return []
    try:
        raw = json.loads(PRECEDENT_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load precedent case DB: %s", PRECEDENT_DB_PATH)
        return []
    return raw if isinstance(raw, list) else []


def _load_product_doc_rules() -> dict[str, Any]:
    fallback = {"default": ["receipt", "medical_statement"], "rules": [], "doc_type_aliases": {}}
    if not PRODUCT_DOC_RULE_DB_PATH.exists():
        return fallback
    try:
        raw = json.loads(PRODUCT_DOC_RULE_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load product document rule DB: %s", PRODUCT_DOC_RULE_DB_PATH)
        return fallback
    return {
        "default": raw.get("default", fallback["default"]),
        "rules": raw.get("rules", fallback["rules"]),
        "doc_type_aliases": raw.get("doc_type_aliases", fallback["doc_type_aliases"]),
    }


def _session_dir_from_docs(docs: list[dict[str, Any]]) -> str:
    for doc in docs:
        if doc.get("session_dir"):
            return _to_text(doc.get("session_dir"))
        saved_path = _to_text(doc.get("saved_path") or doc.get("storage_path"))
        if saved_path:
            try:
                path = Path(saved_path)
                if path.parent.name == "original":
                    return str(path.parent.parent)
                return str(path.parent)
            except Exception:
                continue
    return ""


def _public_file_records(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for doc in docs:
        public.append(
            {
                "upload_id": doc.get("upload_id") or doc.get("doc_id"),
                "file_name": doc.get("original_filename") or doc.get("doc_name") or doc.get("name"),
                "file_size": doc.get("file_size") or doc.get("size_bytes"),
                "mime_type": doc.get("mime_type", ""),
                "processing_status": doc.get("processing_status", "saved"),
                "doc_type_guess": doc.get("doc_type_guess") or doc.get("doc_type"),
            }
        )
    return public


def _build_uploaded_document_analysis(
    *,
    docs: list[dict[str, Any]],
    customer: dict[str, Any],
    product_name: str,
    question: str,
    rule_db: dict[str, Any],
    llm: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    empty = {
        "files": [],
        "extraction_results": [],
        "comparison_result": {},
        "missing_key_fields": [],
        "mismatches": [],
    }
    if not docs:
        return empty, None, ""

    session_dir = _session_dir_from_docs(docs)
    required_rule = get_required_rule(product_name, question, rule_db)
    extraction_results: list[dict[str, Any]] = []
    if session_dir:
        extraction_results = extract_documents_for_uploaded_files(docs, customer, question, session_dir, llm=llm)
    else:
        logger.warning("Upload session directory is missing; using filename-based checklist fallback.")

    if not extraction_results:
        fallback_checklist = build_claim_checklist(product_name, question, docs, rule_db)
        uploaded_documents = {
            **empty,
            "files": _public_file_records(docs),
            "comparison_result": {
                "scenario_label": _to_text(required_rule.get("label")) or "일반 청구 서류",
                "readiness_percent": fallback_checklist.get("readiness_percent", 0),
                "readiness_label": fallback_checklist.get("readiness_label", "청구 서류 준비 전"),
                "needs_review_docs": [],
            },
        }
        return uploaded_documents, fallback_checklist, "문서 내용을 자동 분석하지 못해 파일명 기준으로 1차 점검했습니다."

    comparison = compare_extracted_docs_with_required(extraction_results, required_rule)
    missing_key_fields = check_missing_key_fields(extraction_results, required_rule.get("key_fields", []))
    mismatches = detect_customer_document_mismatches(customer, extraction_results)
    checklist = build_claim_checklist_from_comparison(comparison)
    uploaded_documents = {
        "files": _public_file_records(docs),
        "extraction_results": extraction_results,
        "comparison_result": comparison,
        "missing_key_fields": missing_key_fields,
        "mismatches": mismatches,
    }
    extracted_count = len([item for item in extraction_results if item.get("processing_status") == "extracted"])
    missing_count = len(comparison.get("missing_groups") or [])
    review_count = len(comparison.get("needs_review_docs") or []) + len(
        [item for item in missing_key_fields if item.get("status") == "missing"]
    )
    summary = (
        f"업로드 서류 {len(docs)}건 중 {extracted_count}건을 자동 분석했고, "
        f"추가 필요 서류 {missing_count}개와 확인 필요 항목 {review_count}개를 점검했습니다. "
        "[출처: CLAIM_RULESET|문서분석]"
    )
    return uploaded_documents, checklist, summary


def _append_document_analysis_summary(content: str, summary: str) -> str:
    if not summary:
        return content
    return f"{content}\n\n업로드 서류 분석 요약: {summary}"


def _normalize_doc_type(doc_type: str, aliases: dict[str, str]) -> str:
    key = _to_text(doc_type).strip()
    if not key:
        return ""
    return _to_text(aliases.get(key, aliases.get(key.lower(), key.lower())))


def _doc_type_label(doc_type: str) -> str:
    labels = {
        "receipt": "진료비 영수증",
        "medical_statement": "진료확인서 또는 진단서",
        "treatment_detail": "진료비 세부내역서",
        "diagnosis_certificate": "진단서",
        "pathology_report": "병리보고서",
        "dental_treatment_record": "치과 진료기록",
        "xray_image": "엑스레이 자료",
        "repair_estimate": "수리 견적서",
        "accident_report": "사고사실확인서",
        "vehicle_registration": "차량등록증",
        "estimate": "수리 견적서",
        "pdf": "PDF 서류",
        "misc": "기타 서류",
    }
    normalized = _to_text(doc_type).strip()
    return labels.get(normalized, normalized or "서류")


def _doc_type_labels(doc_types: list[str] | set[str]) -> list[str]:
    return [_doc_type_label(doc_type) for doc_type in sorted([d for d in doc_types if d])]


def _required_docs_by_product(product_name: str, rule_db: dict[str, Any]) -> set[str]:
    rules = rule_db.get("rules", [])
    for rule in rules:
        keyword = _to_text(rule.get("product_keyword")).strip()
        if keyword and keyword in product_name:
            return set(_to_text(v) for v in rule.get("required_docs", []))
    return set(_to_text(v) for v in rule_db.get("default", []))


def _precedent_score(query: str, case: dict[str, Any]) -> int:
    text = f"{case.get('issue','')} {case.get('summary','')} {case.get('tags','')}"
    words = [w for w in re.split(r"\s+", query) if len(w) >= 2]
    return sum(1 for w in words if w in text)


def _run_precedent_dispute_worker(state: dict[str, Any], *, llm: Any) -> dict[str, Any]:
    validate_node_entry("PRECEDENT_DISPUTE_WORKER", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()
    query = _to_text(updated.get("user_query"))
    customer = updated.get("customer_db_info") or {}
    product_name = _to_text(customer.get("product_name"))

    cases = _load_precedent_cases()
    ranked = sorted(cases, key=lambda c: _precedent_score(query, c), reverse=True)
    top_cases = ranked[:3]

    if top_cases:
        context = "\n\n".join(
            [
                f"[CASE{i}] 사건번호:{c.get('case_id')} / 쟁점:{c.get('issue')} / 요약:{c.get('summary')} / 판단:{c.get('decision')}"
                for i, c in enumerate(top_cases, start=1)
            ]
        )
        citations = [
            {
                "source_id": f"CASE{i}",
                "case_id": c.get("case_id"),
                "title": c.get("title"),
            }
            for i, c in enumerate(top_cases, start=1)
        ]
    else:
        context = "[CASE0] 로컬 분쟁조정례 DB에 일치 사례 없음"
        citations = [{"source_id": "CASE0", "case_id": "N/A", "title": "No Match"}]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """당신은 보험 분쟁 사례를 고객 눈높이에 맞춰 설명하는 안내 어시스턴트입니다.
다음 사례 컨텍스트를 바탕으로 고객이 이해하기 쉽게 3단락으로 안내하세요.
법률/심사 용어는 필요한 만큼만 쓰고, 어려운 말은 쉬운 말로 풀어 쓰세요.
확정적으로 단정하지 말고 "비슷하게 볼 여지가 있습니다", "다르게 판단될 수 있습니다"처럼 조건부로 안내하세요.

단락 구성:
1) 비슷하게 볼 수 있는 점
2) 다르게 확인될 수 있는 점
3) 고객님이 유의하실 점

각 단락 끝에 [출처: CASE번호|사건번호]를 붙이세요.
<context>
{context}
</context>
""",
            ),
            ("user", "고객질문: {query}"),
        ]
    )
    answer = llm.invoke(prompt.format_messages(context=context, query=query)).content
    answer = _guardrail_content(_to_text(answer), citations)
    rule_db = _load_product_doc_rules()
    claim_checklist = build_claim_checklist(product_name, query, updated.get("user_docs") or [], rule_db)
    uploaded_documents, vision_checklist, doc_analysis_summary = _build_uploaded_document_analysis(
        docs=updated.get("user_docs") or [],
        customer=customer,
        product_name=product_name,
        question=query,
        rule_db=rule_db,
        llm=llm,
    )
    if vision_checklist:
        claim_checklist = vision_checklist
    answer = _append_document_analysis_summary(answer, doc_analysis_summary)
    diagnosis_result = build_diagnosis_result(
        customer_info=customer,
        customer_id=_to_text(updated.get("user_id")),
        question=query,
        route="precedent_dispute",
        evidence_cards=build_case_evidence_cards(top_cases, query, product_name),
        claim_checklist=claim_checklist,
        uploaded_documents=uploaded_documents,
    )

    draft = {
        "worker_type": "precedent_dispute",
        "content": answer,
        "citations": citations,
        "diagnosis_result": diagnosis_result,
        "created_at": updated["updated_at"],
    }
    patch = {
        "draft_response": draft,
        "citations": citations,
        "status": "WORKER_DRAFTED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("PRECEDENT_DISPUTE_WORKER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(
            node="PRECEDENT_DISPUTE_WORKER",
            action="DRAFT_CREATED",
            note=f"cases={len(top_cases)}",
        )
    )
    return updated


def _run_document_claim_worker(
    state: dict[str, Any], *, vectorstore: Chroma | None = None, llm: Any
) -> dict[str, Any]:
    validate_node_entry("DOCUMENT_CLAIM_WORKER", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()

    customer = updated.get("customer_db_info") or {}
    product_name = _to_text(customer.get("product_name"))
    docs = updated.get("user_docs") or []
    query = _to_text(updated.get("user_query"))
    rule_db = _load_product_doc_rules()
    uploaded_documents, vision_checklist, doc_analysis_summary = _build_uploaded_document_analysis(
        docs=docs,
        customer=customer,
        product_name=product_name,
        question=query,
        rule_db=rule_db,
        llm=llm,
    )
    aliases = rule_db.get("doc_type_aliases", {})
    doc_types = {_normalize_doc_type(_to_text(d.get("doc_type")), aliases) for d in docs}
    doc_types = {d for d in doc_types if d}
    required = _required_docs_by_product(product_name, rule_db)
    missing = sorted(required - doc_types)
    amount = _extract_claim_amount(query)
    evidence_docs: list[Any] = []
    if vectorstore is not None:
        try:
            evidence_docs = _dedupe_docs(
                [
                    *vectorstore.similarity_search(query, k=6),
                    *vectorstore.similarity_search(_expanded_policy_query(query, product_name), k=6),
                ]
            )
            evidence_docs = rerank_docs_by_customer_product(evidence_docs, product_name, query)[:5]
        except Exception:
            logger.exception("Document claim evidence search failed")

    claim_checklist = vision_checklist or build_claim_checklist(product_name, query, docs, rule_db)
    evidence_cards = build_evidence_cards(evidence_docs, query, product_name)
    diagnosis_result = build_diagnosis_result(
        customer_info=customer,
        customer_id=_to_text(updated.get("user_id")),
        question=query,
        route="document_claim",
        evidence_cards=evidence_cards,
        claim_checklist=claim_checklist,
        uploaded_documents=uploaded_documents,
    )

    checklist_missing = claim_checklist.get("missing_docs") or _doc_type_labels(missing)
    if checklist_missing:
        status_text = "추가 서류 확인 필요"
        body = (
            "올려주신 서류를 먼저 확인해보니, 접수를 진행하려면 아래 서류를 더 준비해주시면 좋겠습니다.\n\n"
            f"필요한 서류: {', '.join(checklist_missing)} [출처: CLAIM_RULESET|필수서류규칙]"
        )
    else:
        status_text = "기본 서류 확인됨"
        body = (
            "올려주신 서류 기준으로는 기본 서류가 갖춰진 것으로 확인됩니다. "
            "이제 담당자가 세부 내용을 확인하는 단계로 이어질 수 있습니다. [출처: CLAIM_RULESET|서류정합성규칙]"
        )

    payload = {
        "status": status_text,
        "ticket_id": f"CLM-{uuid.uuid4().hex[:10].upper()}",
        "extracted_data": {
            "claimed_amount": amount,
            "doc_count": len(docs),
            "doc_types": sorted([t for t in doc_types if t]),
            "required_docs": sorted([r for r in required if r]),
            "product_name": product_name,
            "vision_extractions": uploaded_documents.get("extraction_results", []),
        },
    }
    detected_docs = _doc_type_labels(doc_types)
    required_docs = _doc_type_labels(required)
    summary_lines = [
        body,
        "",
        f"접수 상태: {status_text}",
        f"접수 번호: `{payload['ticket_id']}`",
        f"확인된 서류: {', '.join(detected_docs) if detected_docs else '업로드된 파일명만으로는 서류 종류를 확정하기 어렵습니다.'}",
        f"상품 기준 필요 서류: {', '.join(required_docs) if required_docs else '별도 필수 서류 규칙이 확인되지 않았습니다.'}",
    ]
    if amount is not None:
        summary_lines.append(f"확인된 청구 금액: {amount:,}원")
    summary_lines.append("정확한 지급 여부와 금액은 담당자 확인 과정에서 최종 안내됩니다.")

    draft = {
        "worker_type": "document_claim",
        "content": _append_document_analysis_summary("\n".join(summary_lines), doc_analysis_summary),
        "citations": [{"source_id": "CLAIM_RULESET", "rule": "DOC_VALIDATION_V2_INTERNAL_DB"}],
        "payload": payload,
        "diagnosis_result": diagnosis_result,
        "debug": {
            "evidence_doc_count": len(evidence_docs),
            "vision_used": bool(uploaded_documents.get("extraction_results")),
        },
        "created_at": updated["updated_at"],
    }
    patch = {
        "draft_response": draft,
        "citations": draft["citations"],
        "status": "WORKER_DRAFTED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("DOCUMENT_CLAIM_WORKER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(
            node="DOCUMENT_CLAIM_WORKER",
            action="DRAFT_CREATED",
            note=f"product={product_name or 'N/A'}, docs={len(docs)}, missing={len(missing)}",
        )
    )
    return updated


def _run_cs_complaint_worker(state: dict[str, Any]) -> dict[str, Any]:
    validate_node_entry("CS_COMPLAINT_WORKER", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()
    customer = updated.get("customer_db_info") or {}
    product_name = _to_text(customer.get("product_name"))
    rule_db = _load_product_doc_rules()
    query = _to_text(updated.get("user_query"))
    uploaded_documents, vision_checklist, doc_analysis_summary = _build_uploaded_document_analysis(
        docs=updated.get("user_docs") or [],
        customer=customer,
        product_name=product_name,
        question=query,
        rule_db=rule_db,
        llm=None,
    )

    queue_ticket_id = f"CSQ-{uuid.uuid4().hex[:10].upper()}"
    content = (
        "불편을 겪으신 점 먼저 죄송합니다. 말씀해주신 내용은 상담원이 이어서 확인할 수 있도록 접수해두었습니다. "
        f"상담원 연결 접수 번호는 `{queue_ticket_id}`입니다. "
        "연결 전까지 확인된 내용과 준비하시면 좋은 서류를 함께 정리해드리겠습니다. "
        "[출처: CS_PLAYBOOK|민원응대기준]"
    )
    content = _append_document_analysis_summary(content, doc_analysis_summary)
    draft = {
        "worker_type": "cs_complaint",
        "content": content,
        "citations": [{"source_id": "CS_PLAYBOOK", "section": "민원응대기준"}],
        "diagnosis_result": build_diagnosis_result(
            customer_info=customer,
            customer_id=_to_text(updated.get("user_id")),
            question=query,
            route="cs_complaint",
            evidence_cards=[],
            claim_checklist=vision_checklist
            or build_claim_checklist(product_name, query, updated.get("user_docs") or [], rule_db),
            uploaded_documents=uploaded_documents,
        ),
        "created_at": updated["updated_at"],
    }
    patch = {
        "draft_response": draft,
        "citations": draft["citations"],
        "status": "WORKER_DRAFTED",
        "updated_at": updated["updated_at"],
        "error": None,
    }
    validate_node_update("CS_COMPLAINT_WORKER", state, patch)
    updated.update(patch)
    updated["audit_log"].append(
        build_audit_event(
            node="CS_COMPLAINT_WORKER",
            action="DRAFT_CREATED",
            note=f"queue_ticket_id={queue_ticket_id}",
        )
    )
    return updated


def run_worker_by_route(
    state: dict[str, Any], *, vectorstore: Chroma | None, llm: Any
) -> dict[str, Any]:
    route = _to_text(state.get("next_route"))
    worker = ROUTE_TO_WORKER.get(route)
    if not worker:
        raise ValueError(f"Unknown route: {route}")

    if worker == "POLICY_DIAGNOSIS_WORKER":
        return _run_policy_diagnosis_worker(state, vectorstore=vectorstore, llm=llm)
    if worker == "PRECEDENT_DISPUTE_WORKER":
        return _run_precedent_dispute_worker(state, llm=llm)
    if worker == "DOCUMENT_CLAIM_WORKER":
        return _run_document_claim_worker(state, vectorstore=vectorstore, llm=llm)
    return _run_cs_complaint_worker(state)
