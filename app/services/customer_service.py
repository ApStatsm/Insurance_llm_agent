from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


CUSTOMER_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "customer_db" / "customers.csv"

PRODUCT_HINTS = {
    "auto": {
        "tokens": ("자동차", "차", "차량", "교통사고", "접촉사고", "침수", "태풍", "홍수", "수리", "견적", "대물", "대인", "자기차량손해", "렌터카", "긴급출동", "사고"),
        "product_tokens": ("자동차", "차량"),
    },
    "cancer": {
        "tokens": ("암", "진단비", "고액암", "병리", "조직검사"),
        "product_tokens": ("암",),
    },
    "indemnity": {
        "tokens": ("실손", "실비", "병원", "치료", "진료비", "치료비", "입원", "통원", "약제비", "도수치료", "비급여", "MRI", "검사", "수술", "상해치료", "의료비"),
        "product_tokens": ("실손", "의료비"),
    },
    "dental": {
        "tokens": ("치아", "치과", "임플란트", "크라운", "브릿지", "틀니", "보철", "충치", "잇몸", "깨지"),
        "product_tokens": ("치아", "치과"),
    },
}


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _split_items(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for sep in (";", "|", ","):
        if sep in text:
            return [item.strip() for item in text.split(sep) if item.strip()]
    return [text]


def _coverage_to_limits(value: Any) -> list[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return []
    if any(mark in text for mark in (":", "=", "|", ";")):
        items = []
        for raw in _split_items(text):
            if ":" in raw:
                name, amount = raw.split(":", 1)
            elif "=" in raw:
                name, amount = raw.split("=", 1)
            else:
                name, amount = "가입금액", raw
            digits = "".join(ch for ch in amount if ch.isdigit())
            items.append(
                {
                    "coverage_name": name.strip() or "가입금액",
                    "limit_amount": int(digits) if digits else None,
                    "display_amount": amount.strip(),
                    "currency": "KRW",
                }
            )
        return items
    return [{"coverage_name": "가입금액", "limit_amount": None, "display_amount": text, "currency": "KRW"}]


def _normalize_customer_id(customer_id: str) -> str:
    return str(customer_id or "").strip().upper()


def _normalize_policy(row: dict[str, Any]) -> dict[str, Any]:
    joined_year = _pick(row, "joined_year", "join_year", "가입연도")
    riders = _split_items(_pick(row, "riders", "special_clauses", "특약"))
    coverage_limit = _pick(row, "coverage_limit", "coverage_limits", "담보한도")
    customer_id = _normalize_customer_id(_pick(row, "customer_id", "user_id", "고객ID"))
    return {
        "customer_id": customer_id,
        "customer_name": _pick(row, "customer_name", "고객명"),
        "phone": _pick(row, "phone", "전화번호"),
        "product_id": _pick(row, "product_id", "상품ID"),
        "product_name": _pick(row, "product_name", "상품명"),
        "joined_year": joined_year,
        "join_year": int(joined_year) if joined_year.isdigit() else joined_year,
        "policy_number": _pick(row, "policy_number", "증권번호"),
        "riders": riders,
        "special_clauses": riders,
        "coverage_limit": coverage_limit,
        "coverage_limits": _coverage_to_limits(coverage_limit),
        "insured_person": _pick(row, "insured_person", "피보험자"),
        "vehicle_number": _pick(row, "vehicle_number", "차량번호"),
    }


def load_customers(csv_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(csv_path) if csv_path else CUSTOMER_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"customers.csv를 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("customers.csv 헤더를 찾을 수 없습니다.")
        rows = [dict(row) for row in reader]

    required = {"customer_id", "user_id", "고객ID"}
    if not any(key in (reader.fieldnames or []) for key in required):
        raise ValueError("customers.csv에 customer_id 또는 user_id 컬럼이 필요합니다.")
    return rows


def get_customer_policies(customer_id: str, csv_path: str | Path | None = None) -> list[dict[str, Any]]:
    normalized_id = _normalize_customer_id(customer_id)
    rows = load_customers(csv_path)
    policies = [
        _normalize_policy(row)
        for row in rows
        if _normalize_customer_id(_pick(row, "customer_id", "user_id", "고객ID")) == normalized_id
    ]
    return [policy for policy in policies if policy.get("product_name")]


def get_customer_profile(customer_id: str, csv_path: str | Path | None = None) -> dict[str, Any] | None:
    policies = get_customer_policies(customer_id, csv_path)
    if not policies:
        return None
    first = policies[0]
    return {
        "customer_id": first.get("customer_id"),
        "customer_name": first.get("customer_name"),
        "phone": first.get("phone"),
        "policies": policies,
    }


def build_customer_context(customer_id: str, csv_path: str | Path | None = None) -> dict[str, Any]:
    profile = get_customer_profile(customer_id, csv_path)
    if not profile:
        raise KeyError(f"가입상품 정보를 찾을 수 없습니다: {customer_id}")
    return profile


def authenticate_customer(customer_id: str, password: str, csv_path: str | Path | None = None) -> dict[str, Any] | None:
    normalized_id = _normalize_customer_id(customer_id)
    rows = load_customers(csv_path)
    matches = [
        row
        for row in rows
        if _normalize_customer_id(_pick(row, "customer_id", "user_id", "고객ID")) == normalized_id
    ]
    if not matches:
        return None

    # Demo-only plain text comparison. A real service must use identity verification,
    # salted password hashing, encryption, rate limiting, and access control.
    if str(_pick(matches[0], "password", "비밀번호")) != str(password or ""):
        return None
    return build_customer_context(normalized_id, csv_path)


def _policy_matches_category(policy: dict[str, Any], category: str) -> bool:
    product_name = str(policy.get("product_name") or "")
    return any(token in product_name for token in PRODUCT_HINTS.get(category, {}).get("product_tokens", ()))


def infer_policy_category(product_name: str) -> str:
    text = str(product_name or "")
    for category in ("auto", "indemnity", "cancer", "dental"):
        if any(token in text for token in PRODUCT_HINTS.get(category, {}).get("product_tokens", ())):
            return category
    return "unknown"


def _question_categories(question: str | None) -> list[str]:
    text = str(question or "")
    categories = []
    for category, rule in PRODUCT_HINTS.items():
        if any(token in text for token in rule["tokens"]):
            categories.append(category)
    return categories


def _policy_question_score(policy: dict[str, Any], question: str | None) -> int:
    product_name = str(policy.get("product_name") or "")
    text = str(question or "")
    score = 0
    for category, rule in PRODUCT_HINTS.items():
        if not _policy_matches_category(policy, category):
            continue
        score += 10
        score += sum(1 for token in rule["tokens"] if token in text)
        score += sum(1 for token in rule["product_tokens"] if token in product_name)
    return score


def select_relevant_policies(customer_context: dict[str, Any], question: str | None = None) -> list[dict[str, Any]]:
    policies = list(customer_context.get("policies") or [])
    if not policies:
        raise KeyError("가입상품 정보를 찾을 수 없습니다.")

    categories = _question_categories(question)
    if not categories:
        return []

    matched = [
        dict(policy)
        for policy in policies
        if any(_policy_matches_category(policy, category) for category in categories)
    ]
    return sorted(matched, key=lambda policy: _policy_question_score(policy, question), reverse=True)


def select_relevant_policy(customer_context: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    policies = list(customer_context.get("policies") or [])
    if not policies:
        raise KeyError("가입상품 정보를 찾을 수 없습니다.")

    relevant_policies = select_relevant_policies(customer_context, question)
    selected = dict(relevant_policies[0] if relevant_policies else policies[0])

    selected.update(
        {
            "customer_id": customer_context.get("customer_id") or selected.get("customer_id"),
            "customer_name": customer_context.get("customer_name") or selected.get("customer_name"),
            "phone": customer_context.get("phone") or selected.get("phone"),
            "policies": policies,
            "relevant_policies": relevant_policies,
            "selected_policy": {
                "product_id": selected.get("product_id"),
                "product_name": selected.get("product_name"),
                "policy_number": selected.get("policy_number"),
            },
        }
    )
    return selected


def find_demo_accounts(customers: list[dict[str, Any]] | None = None) -> dict[str, str]:
    rows = customers if customers is not None else load_customers()
    grouped: dict[str, list[str]] = {}
    products_by_customer: dict[str, set[str]] = {}
    for row in rows:
        cid = _normalize_customer_id(_pick(row, "customer_id", "user_id", "고객ID"))
        product_name = _pick(row, "product_name", "상품명")
        if not cid or not product_name or not cid.startswith("CUST-00"):
            continue
        products_by_customer.setdefault(cid, set()).add(product_name)
        if "자동차" in product_name:
            grouped.setdefault("auto", []).append(cid)
        elif "암" in product_name:
            grouped.setdefault("cancer", []).append(cid)
        elif "실손" in product_name:
            grouped.setdefault("indemnity", []).append(cid)
        elif "치아" in product_name:
            grouped.setdefault("dental", []).append(cid)

    multi = sorted([cid for cid, products in products_by_customer.items() if len(products) >= 3])
    return {
        "auto": sorted(set(grouped.get("auto", [])))[0] if grouped.get("auto") else "",
        "cancer": sorted(set(grouped.get("cancer", [])))[0] if grouped.get("cancer") else "",
        "indemnity": sorted(set(grouped.get("indemnity", [])))[0] if grouped.get("indemnity") else "",
        "dental": sorted(set(grouped.get("dental", [])))[0] if grouped.get("dental") else "",
        "multi_policy": multi[0] if multi else "",
    }
