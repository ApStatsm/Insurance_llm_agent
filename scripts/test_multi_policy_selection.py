from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.customer_service import (
    build_customer_context,
    infer_policy_category,
    select_relevant_policies,
)


TEST_CASES = [
    {
        "customer_id": "CUST-0001",
        "question": "교통사고가 나서 차도 망가지고 병원 치료도 받았는데 뭐 청구 가능해?",
        "expected": {"auto", "indemnity"},
    },
    {
        "customer_id": "CUST-0001",
        "question": "태풍 때문에 차가 침수됐는데 보상 가능해?",
        "expected": {"auto"},
    },
    {
        "customer_id": "CUST-0001",
        "question": "도수치료 받았는데 실손 청구 가능해?",
        "expected": {"indemnity"},
    },
    {
        "customer_id": "CUST-0005",
        "question": "암 진단 받고 항암치료비랑 진단비를 청구하고 싶어",
        "expected": {"cancer", "indemnity"},
    },
    {
        "customer_id": "CUST-0020",
        "question": "교통사고로 치아가 깨지고 병원 치료도 받았어",
        "expected": {"auto", "dental", "indemnity"},
    },
]


def main() -> int:
    failures = 0
    for case in TEST_CASES:
        context = build_customer_context(case["customer_id"])
        selected = select_relevant_policies(context, case["question"])
        categories = {infer_policy_category(policy.get("product_name", "")) for policy in selected}
        available = [policy.get("product_name") for policy in context.get("policies", [])]
        selected_names = [policy.get("product_name") for policy in selected]
        ok = categories == case["expected"]
        status = "PASS" if ok else "FAIL"
        print(status)
        print(f"  question: {case['question']}")
        print(f"  available: {available}")
        print(f"  selected: {selected_names}")
        print(f"  categories: {sorted(categories)} expected={sorted(case['expected'])}")
        if not ok:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
