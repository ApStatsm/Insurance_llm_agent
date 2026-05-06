from __future__ import annotations

from typing import Any

DOC_TYPE_TO_CATEGORY = {
    "진료비 영수증": "medical",
    "진료비 세부내역서": "medical",
    "진단서": "medical",
    "진료확인서": "medical",
    "진료확인서 또는 진단서": "medical",
    "병리보고서": "medical",
    "치과 진료기록": "medical",
    "엑스레이": "medical",
    "엑스레이 자료": "medical",
    "수리견적서": "auto",
    "수리 견적서": "auto",
    "사고사실확인서": "auto",
    "차량등록증": "auto",
    "침수 사진": "auto",
}

FIELD_LABELS = {
    "patient_name": "환자명",
    "hospital_name": "병원명",
    "treatment_date": "진료일",
    "diagnosis_name": "진단명",
    "diagnosis_date": "진단일",
    "pathology_result": "병리/조직검사 결과",
    "vehicle_number": "차량번호",
    "owner_name": "차량 소유자명",
    "repair_shop": "수리업체명",
    "repair_amount": "수리금액",
    "accident_date": "사고일",
    "damage_type": "손상 유형",
    "total_amount": "총 금액",
    "treatment_type": "치료 유형",
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys([item for item in items if item]))


def _readiness_label(percent: int) -> str:
    if percent <= 0:
        return "청구 서류 준비 전"
    if percent < 50:
        return "서류 준비 필요"
    if percent < 80:
        return "일부 준비 완료"
    if percent < 100:
        return "거의 준비 완료"
    return "기본 서류 준비 완료"


def infer_product_category(product_name: str, question: str = "") -> str:
    text = f"{_to_text(product_name)} {_to_text(question)}"
    hints = {
        "auto": ("자동차", "차량", "운전자", "침수", "수리", "대물", "대인"),
        "cancer": ("암", "암진단", "진단비", "고액암", "병리", "악성신생물"),
        "indemnity": ("실손", "의료비", "도수치료", "비급여", "진료비", "입원", "통원"),
        "dental": ("치아", "치과", "보철", "임플란트", "크라운", "브릿지"),
    }
    for category, tokens in hints.items():
        if any(token in text for token in tokens):
            return category
    return "unknown"


def infer_claim_scenario(product_name: str, question: str) -> tuple[str, str]:
    text = f"{_to_text(product_name)} {_to_text(question)}"
    if any(token in text for token in ("자동차", "차량", "침수", "태풍", "홍수")):
        return "auto", "flood"
    if any(token in text for token in ("암", "진단비", "고액암", "병리")):
        return "cancer", "diagnosis_benefit"
    if any(token in text for token in ("실손", "도수치료", "비급여", "진료비", "통원")):
        return "indemnity", "manual_therapy"
    if any(token in text for token in ("치아", "임플란트", "크라운", "보철")):
        return "dental", "prosthetic"
    return "unknown", "general"


def _legacy_required_docs_to_groups(required_docs: list[str]) -> list[dict[str, Any]]:
    return [{"label": _to_text(doc), "any_of": [_to_text(doc)]} for doc in required_docs if _to_text(doc)]


def _doc_code_to_label(doc_code: str) -> str:
    mapping = {
        "receipt": "진료비 영수증",
        "medical_statement": "진료확인서",
        "treatment_detail": "진료비 세부내역서",
        "diagnosis_certificate": "진단서",
        "pathology_report": "병리보고서",
        "dental_treatment_record": "진료확인서",
        "xray_image": "엑스레이",
        "repair_estimate": "수리견적서",
        "accident_report": "사고사실확인서",
        "vehicle_registration": "차량등록증",
        "flood_photo": "침수 사진",
    }
    return mapping.get(_to_text(doc_code), _to_text(doc_code))


def _fallback_rule_from_legacy(
    product_name: str, question: str, required_docs_rules: dict[str, Any]
) -> dict[str, Any]:
    category, scenario = infer_claim_scenario(product_name, question)
    required_codes: list[str] = []
    for rule in required_docs_rules.get("rules", []):
        keyword = _to_text(rule.get("product_keyword"))
        if keyword and keyword in _to_text(product_name):
            required_codes = [_to_text(doc) for doc in rule.get("required_docs", [])]
            break
    if not required_codes:
        required_codes = [_to_text(doc) for doc in required_docs_rules.get("default", [])]
    if category == "auto" and scenario == "flood":
        required_codes.append("flood_photo")
    required_labels = _unique([_doc_code_to_label(code) for code in required_codes])
    return {
        "label": "일반 청구 서류 기준",
        "required_doc_groups": _legacy_required_docs_to_groups(required_labels),
        "key_fields": [],
    }


def get_required_rule(product_name: str, question: str, required_docs_rules: dict[str, Any]) -> dict[str, Any]:
    category, scenario = infer_claim_scenario(product_name, question)
    scenario_rules = required_docs_rules.get("claim_scenarios", {})
    if isinstance(scenario_rules, dict):
        category_rules = scenario_rules.get(category, {})
        if isinstance(category_rules, dict) and isinstance(category_rules.get(scenario), dict):
            return category_rules[scenario]
    return _fallback_rule_from_legacy(product_name, question, required_docs_rules)


def compare_extracted_docs_with_required(
    extraction_results: list[dict[str, Any]], required_rule: dict[str, Any]
) -> dict[str, Any]:
    groups = required_rule.get("required_doc_groups") or []
    submitted_docs = _unique([_to_text(item.get("doc_type")) for item in extraction_results])
    satisfied_groups: list[dict[str, Any]] = []
    missing_groups: list[dict[str, Any]] = []
    needs_review_docs: list[dict[str, Any]] = []

    for group in groups:
        any_of = [_to_text(doc) for doc in group.get("any_of", [])]
        matched = None
        for result in extraction_results:
            doc_type = _to_text(result.get("doc_type"))
            if doc_type in any_of:
                matched = result
                break
        if matched:
            satisfied_groups.append(
                {
                    "label": _to_text(group.get("label")),
                    "matched_doc_type": _to_text(matched.get("doc_type")),
                    "file_name": _to_text(matched.get("file_name")),
                }
            )
        else:
            missing_groups.append(
                {
                    "label": _to_text(group.get("label")),
                    "any_of": any_of,
                    "reason": _to_text(group.get("reason")) or "청구 심사에 필요할 수 있는 서류입니다.",
                }
            )

    for result in extraction_results:
        doc_type = _to_text(result.get("doc_type"))
        confidence = float(result.get("confidence") or 0)
        if doc_type in ("기타/판별불가", "기타 서류", "") or confidence < 0.6 or result.get("needs_review"):
            needs_review_docs.append(
                {
                    "file_name": _to_text(result.get("file_name")),
                    "doc_type": doc_type or "기타/판별불가",
                    "reason": "문서 유형 또는 핵심 정보 확인이 필요합니다.",
                }
            )

    readiness_percent = int(len(satisfied_groups) / len(groups) * 100) if groups else 0
    return {
        "scenario_label": _to_text(required_rule.get("label")) or "일반 청구 서류",
        "required_doc_groups": groups,
        "submitted_docs": submitted_docs,
        "satisfied_groups": satisfied_groups,
        "missing_groups": missing_groups,
        "needs_review_docs": needs_review_docs,
        "readiness_percent": readiness_percent,
        "readiness_label": _readiness_label(readiness_percent),
    }


def check_missing_key_fields(extraction_results: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, str]]:
    combined: dict[str, Any] = {}
    for result in extraction_results:
        fields = result.get("extracted_fields") or {}
        if isinstance(fields, dict):
            for key, value in fields.items():
                if value not in (None, "", []):
                    combined[key] = value
        for key in ("person_name", "date_of_service", "amount"):
            value = result.get(key)
            if value not in (None, "", []):
                combined[key] = value

    aliases = {
        "patient_name": ["patient_name", "person_name"],
        "treatment_date": ["treatment_date", "date_of_service"],
        "total_amount": ["total_amount", "amount"],
    }
    checks: list[dict[str, str]] = []
    for field in key_fields:
        candidate_fields = aliases.get(field, [field])
        found = any(combined.get(candidate) not in (None, "", []) for candidate in candidate_fields)
        label = FIELD_LABELS.get(field, field)
        checks.append(
            {
                "field": field,
                "label": label,
                "status": "found" if found else "missing",
                "message": f"{label}이 확인되었습니다." if found else f"제출된 서류에서 {label}이 명확히 확인되지 않습니다.",
            }
        )
    return checks


def _mask_name(value: str) -> str:
    text = _to_text(value)
    if len(text) <= 1:
        return text
    if len(text) == 2:
        return f"{text[0]}*"
    return f"{text[0]}*{text[-1]}"


def _mask_vehicle(value: str) -> str:
    text = _to_text(value)
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:3]}****"


def detect_customer_document_mismatches(
    customer_info: dict[str, Any], extraction_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    product_name = _to_text(customer_info.get("product_name"))
    product_category = infer_product_category(product_name)
    doc_categories = {DOC_TYPE_TO_CATEGORY.get(_to_text(item.get("doc_type"))) for item in extraction_results}
    doc_categories.discard(None)
    if product_category == "auto" and doc_categories and doc_categories == {"medical"}:
        warnings.append(
            {
                "type": "product_doc_mismatch",
                "severity": "warning",
                "message": "자동차보험 청구로 보이나 의료비 서류만 제출되어 상품과 서류 유형 확인이 필요합니다.",
                "expected": "자동차 사고 관련 서류",
                "found": "의료비 관련 서류",
                "file_name": "",
            }
        )
    if product_category in ("indemnity", "cancer", "dental") and doc_categories and doc_categories == {"auto"}:
        warnings.append(
            {
                "type": "product_doc_mismatch",
                "severity": "warning",
                "message": "의료/질병성 상품 청구로 보이나 차량 관련 서류만 제출되어 확인이 필요합니다.",
                "expected": "의료비 또는 진단 관련 서류",
                "found": "차량 관련 서류",
                "file_name": "",
            }
        )

    expected_name = _to_text(customer_info.get("customer_name") or customer_info.get("insured_name"))
    expected_vehicle = _to_text(customer_info.get("vehicle_number"))
    for result in extraction_results:
        fields = result.get("extracted_fields") or {}
        found_name = _to_text(fields.get("patient_name") or result.get("person_name"))
        if expected_name and found_name and expected_name != found_name:
            warnings.append(
                {
                    "type": "name_mismatch",
                    "severity": "warning",
                    "message": "서류상 환자명이 고객 정보와 일치하는지 확인이 필요합니다.",
                    "expected": _mask_name(expected_name),
                    "found": _mask_name(found_name),
                    "file_name": _to_text(result.get("file_name")),
                }
            )
        found_vehicle = _to_text(fields.get("vehicle_number"))
        if expected_vehicle and found_vehicle and expected_vehicle != found_vehicle:
            warnings.append(
                {
                    "type": "vehicle_number_mismatch",
                    "severity": "warning",
                    "message": "서류상 차량번호가 가입 차량 정보와 일치하는지 확인이 필요합니다.",
                    "expected": _mask_vehicle(expected_vehicle),
                    "found": _mask_vehicle(found_vehicle),
                    "file_name": _to_text(result.get("file_name")),
                }
            )
    return warnings


def build_claim_checklist_from_comparison(comparison_result: dict[str, Any]) -> dict[str, Any]:
    missing_docs = []
    for group in comparison_result.get("missing_groups") or []:
        any_of = group.get("any_of") or []
        missing_docs.append(" 또는 ".join(any_of) if any_of else _to_text(group.get("label")))
    required_docs = []
    for group in comparison_result.get("required_doc_groups") or []:
        any_of = group.get("any_of") or []
        required_docs.append(" 또는 ".join(any_of) if any_of else _to_text(group.get("label")))
    return {
        "required_docs": _unique(required_docs),
        "submitted_docs": comparison_result.get("submitted_docs") or [],
        "missing_docs": _unique(missing_docs),
        "readiness_percent": comparison_result.get("readiness_percent", 0),
        "readiness_label": comparison_result.get("readiness_label", "청구 서류 준비 전"),
        "needs_review_docs": comparison_result.get("needs_review_docs") or [],
    }
