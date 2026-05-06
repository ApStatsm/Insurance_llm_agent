from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _doc_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or value.get("doc") or " 또는 ".join(_to_list(value.get("any_of"))) or "")
    return str(value or "")


def compute_top_missing_docs(tickets: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for ticket in tickets:
        for item in _to_list(ticket.get("missing_docs")):
            label = _doc_label(item).strip()
            if label:
                counter[label] += 1
    return [{"doc": doc, "count": count} for doc, count in counter.most_common(top_n)]


def compute_dashboard_metrics(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now().date().isoformat()
    total = len(tickets)
    today_count = 0
    readiness_values: list[int] = []
    route_counter: Counter[str] = Counter()
    product_counter: Counter[str] = Counter()
    priority_counter: Counter[str] = Counter()
    human_review_count = 0
    ready_count = 0
    complaint_count = 0
    ai_reviewed_count = 0

    for ticket in tickets:
        created = str(ticket.get("created_at") or "")
        if created[:10] == today:
            today_count += 1
        status = str(ticket.get("status") or "")
        if status in ("ai_reviewed", "waiting_for_documents", "needs_human_review", "ready_for_submission", "transferred_to_agent"):
            ai_reviewed_count += 1
        if ticket.get("human_review_required") or status == "needs_human_review":
            human_review_count += 1
        readiness = int(ticket.get("readiness_percent") or 0)
        readiness_values.append(readiness)
        if readiness >= 80:
            ready_count += 1
        route = str(ticket.get("route_label") or ticket.get("route") or "기타")
        products = _to_list(ticket.get("involved_products")) or [ticket.get("product_name") or "확인 필요"]
        priority = str(ticket.get("priority_label") or ticket.get("priority") or "보통")
        route_counter[route] += 1
        for product in products:
            product_counter[str(product or "확인 필요")] += 1
        priority_counter[priority] += 1
        if ticket.get("route") == "cs_complaint" or ticket.get("priority") == "urgent":
            complaint_count += 1

    return {
        "total_tickets": total,
        "today_tickets": today_count,
        "ai_reviewed_count": ai_reviewed_count,
        "human_review_count": human_review_count,
        "avg_readiness_percent": int(sum(readiness_values) / len(readiness_values)) if readiness_values else 0,
        "ready_count": ready_count,
        "complaint_count": complaint_count,
        "route_distribution": dict(route_counter),
        "product_distribution": dict(product_counter),
        "priority_distribution": dict(priority_counter),
        "top_missing_docs": compute_top_missing_docs(tickets),
    }


def human_review_queue(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = [
        ticket
        for ticket in tickets
        if ticket.get("human_review_required")
        or ticket.get("status") == "needs_human_review"
        or ticket.get("priority") in ("high", "urgent")
    ]
    return sorted(queue, key=lambda item: str(item.get("created_at") or ""), reverse=True)
