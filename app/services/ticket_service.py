from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TICKET_DIR = PROJECT_ROOT / "data" / "tickets"
TICKET_INDEX = TICKET_DIR / "tickets.jsonl"

ROUTE_PREFIX = {
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


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def ensure_ticket_dir() -> str:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    if not TICKET_INDEX.exists():
        TICKET_INDEX.write_text("", encoding="utf-8")
    return str(TICKET_DIR)


def load_ticket_index() -> list[dict[str, Any]]:
    ensure_ticket_dir()
    tickets: list[dict[str, Any]] = []
    for line in TICKET_INDEX.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            tickets.append(parsed)
    return tickets


def generate_ticket_id(route: str, created_at: datetime | None = None) -> str:
    ensure_ticket_dir()
    now = created_at or datetime.now()
    prefix = ROUTE_PREFIX.get(route, "GEN")
    date_key = now.strftime("%Y%m%d")
    max_seq = 0
    for ticket in load_ticket_index():
        ticket_id = _to_text(ticket.get("ticket_id"))
        if ticket_id.startswith(f"{prefix}-{date_key}-"):
            try:
                max_seq = max(max_seq, int(ticket_id.rsplit("-", 1)[-1]))
            except ValueError:
                continue
    for path in TICKET_DIR.glob(f"{prefix}-{date_key}-*.json"):
        try:
            max_seq = max(max_seq, int(path.stem.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{prefix}-{date_key}-{max_seq + 1:04d}"


def determine_ticket_status(
    route: str,
    diagnosis_result: dict[str, Any],
    human_review_required: bool,
    readiness_percent: int | None,
) -> str:
    if route == "cs_complaint":
        return "transferred_to_agent" if human_review_required else "ai_reviewed"
    if human_review_required:
        return "needs_human_review"
    if readiness_percent is None:
        return "ai_reviewed"
    if int(readiness_percent) < 80:
        return "waiting_for_documents"
    return "ready_for_submission"


def _index_record(ticket_record: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ticket_id",
        "created_at",
        "customer_id",
        "route",
        "route_label",
        "product_name",
        "incident_type",
        "status",
        "status_label",
        "priority",
        "priority_label",
        "human_review_required",
        "human_review_reasons",
        "readiness_percent",
        "readiness_label",
        "missing_docs",
        "submitted_docs",
        "detail_path",
    ]
    return {key: ticket_record.get(key) for key in keys}


def build_ticket_record(
    state: dict[str, Any],
    diagnosis_result: dict[str, Any],
    customer_info: dict[str, Any],
    route: str,
    question: str,
    human_review: dict[str, Any] | None = None,
    handoff_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_ticket_dir()
    now = datetime.now()
    ticket_id = generate_ticket_id(route, now)
    result = diagnosis_result or {}
    customer_summary = result.get("customer_summary") or {}
    incident = result.get("incident_summary") or {}
    checklist = result.get("claim_checklist") or {}
    review = human_review or {}
    readiness = checklist.get("readiness_percent")
    status = determine_ticket_status(route, result, bool(review.get("human_review_required")), readiness)
    detail_path = TICKET_DIR / f"{ticket_id}.json"
    route_label = {
        "policy_diagnosis": "보상 가능성 문의",
        "document_claim": "청구 서류 점검",
        "precedent_dispute": "분쟁/사례 확인",
        "cs_complaint": "민원/상담 연결",
    }.get(route, "기타")
    ticket_record = {
        "ticket_id": ticket_id,
        "created_at": now.isoformat(timespec="seconds"),
        "customer_id": state.get("user_id") or customer_summary.get("customer_id"),
        "route": route,
        "route_label": route_label,
        "product_name": customer_summary.get("product_name") or customer_info.get("product_name"),
        "incident_type": incident.get("incident_type"),
        "status": status,
        "status_label": STATUS_LABELS.get(status, "AI 사전진단 완료"),
        "priority": review.get("priority", "medium"),
        "priority_label": review.get("priority_label", "보통"),
        "human_review_required": bool(review.get("human_review_required")),
        "human_review_reasons": review.get("reasons") or [],
        "readiness_percent": readiness if readiness is not None else 0,
        "readiness_label": checklist.get("readiness_label", "청구 서류 준비 전"),
        "missing_docs": checklist.get("missing_docs") or [],
        "submitted_docs": checklist.get("submitted_docs") or [],
        "summary": {
            "question": question,
            "coverage_label": (result.get("coverage_assessment") or {}).get("label"),
            "assessment_summary": (result.get("coverage_assessment") or {}).get("summary"),
        },
        "agent_handoff_summary": handoff_summary or {},
        "diagnosis_result": result,
        "detail_path": str(detail_path),
    }
    return ticket_record


def append_ticket_index(ticket_record: dict[str, Any]) -> None:
    ensure_ticket_dir()
    index_record = _index_record(ticket_record)
    existing = load_ticket_index()
    if any(item.get("ticket_id") == index_record.get("ticket_id") for item in existing):
        return
    with TICKET_INDEX.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(index_record, ensure_ascii=False) + "\n")


def save_ticket(ticket_record: dict[str, Any]) -> dict[str, Any]:
    ensure_ticket_dir()
    detail_path = Path(ticket_record.get("detail_path") or TICKET_DIR / f"{ticket_record['ticket_id']}.json")
    ticket_record["detail_path"] = str(detail_path)
    detail_path.write_text(json.dumps(ticket_record, ensure_ascii=False, indent=2), encoding="utf-8")
    append_ticket_index(ticket_record)
    return _index_record(ticket_record)


def load_ticket_detail(ticket_id: str) -> dict[str, Any] | None:
    ensure_ticket_dir()
    safe = Path(_to_text(ticket_id)).name
    path = TICKET_DIR / f"{safe}.json"
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def create_mock_tickets_if_empty() -> list[dict[str, Any]]:
    if load_ticket_index():
        return []
    examples = [
        ("policy_diagnosis", "CUST-3301", "자동차보험 플랜C", "차량 침수", "high", ["사고사실확인서 누락", "자기차량손해 담보 확인 필요"], 50),
        ("document_claim", "CUST-1029", "실손보험 플랜A", "실손 의료비", "medium", ["진료비 세부내역서 누락"], 67),
        ("policy_diagnosis", "CUST-2044", "암보험 플랜B", "암 진단비", "high", ["병리보고서 필요", "진단 확정 요건 확인 필요"], 33),
        ("precedent_dispute", "CUST-2044", "암보험 플랜B", "암 진단비", "high", ["분쟁 사례 확인 요청"], 33),
        ("cs_complaint", "CUST-1029", "실손보험 플랜A", "민원/상담 연결", "urgent", ["민원성 문의 및 상담원 연결 요청"], 0),
    ]
    saved: list[dict[str, Any]] = []
    for route, customer_id, product, incident, priority, reasons, readiness in examples:
        diagnosis_result = {
            "customer_summary": {"customer_id": customer_id, "product_name": product},
            "incident_summary": {"raw_question": incident, "incident_type": incident, "stage": "데모"},
            "coverage_assessment": {"label": "추가 확인 필요", "summary": "데모용 AI 사전진단 요약입니다."},
            "evidence_cards": [],
            "claim_checklist": {
                "submitted_docs": [],
                "missing_docs": reasons[:1],
                "readiness_percent": readiness,
                "readiness_label": "일부 준비 완료" if readiness else "청구 서류 준비 전",
            },
            "uploaded_documents": {},
        }
        human_review = {
            "human_review_required": True,
            "priority": priority,
            "priority_label": {"medium": "보통", "high": "높음", "urgent": "긴급"}.get(priority, "보통"),
            "reasons": reasons,
            "recommended_questions": ["고객에게 추가 확인이 필요한 정보를 확인해 주세요."],
        }
        record = build_ticket_record(
            {"user_id": customer_id, "next_route": route, "user_query": incident},
            diagnosis_result,
            {"product_name": product},
            route,
            incident,
            human_review,
            {"notice": "본 요약은 AI 사전진단 결과를 상담원이 이어서 확인할 수 있도록 정리한 참고 자료입니다."},
        )
        saved.append(save_ticket(record))
    return saved
