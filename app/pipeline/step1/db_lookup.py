from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.pipeline.step0.error_codes import E_MISSING_REQUIRED_FIELD
from app.pipeline.step0.validator import Step0ValidationError, build_audit_event, validate_node_entry, validate_node_update
from app.services.customer_service import build_customer_context, select_relevant_policy


DEFAULT_CUSTOMER_DB_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "customer_db" / "customers.csv"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mask_user_id(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(0, len(value) - 6)}{value[-2:]}"


def _split_items(raw: str) -> list[str]:
    if not raw:
        return []
    for sep in ("|", ";", ","):
        if sep in raw:
            return [item.strip() for item in raw.split(sep) if item.strip()]
    return [raw.strip()] if raw.strip() else []


def _parse_coverage_limits(raw: str) -> list[dict[str, Any]]:
    """
    Supported examples:
    - "입원비:5000000|통원비:300000"
    - "MRI=2000000;도수치료=100000"
    """
    items = _split_items(raw)
    parsed: list[dict[str, Any]] = []
    for item in items:
        if ":" in item:
            name, amount = item.split(":", 1)
        elif "=" in item:
            name, amount = item.split("=", 1)
        else:
            parsed.append({"coverage_name": item, "limit_amount": None, "currency": "KRW"})
            continue
        number_only = "".join(ch for ch in amount if ch.isdigit())
        limit_amount = int(number_only) if number_only else None
        parsed.append(
            {
                "coverage_name": name.strip(),
                "limit_amount": limit_amount,
                "currency": "KRW",
            }
        )
    return parsed


def _pick(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row and row[key]:
            return row[key].strip()
    return ""


def _row_to_customer_info(row: dict[str, str]) -> dict[str, Any]:
    join_year_raw = _pick(row, "join_year", "가입연도")
    join_year = int(join_year_raw) if join_year_raw.isdigit() else None
    return {
        "join_year": join_year,
        "product_name": _pick(row, "product_name", "상품명"),
        "policy_number": _pick(row, "policy_number", "증권번호"),
        "coverage_limits": _parse_coverage_limits(_pick(row, "coverage_limits", "담보한도")),
        "special_clauses": _split_items(_pick(row, "special_clauses", "특약")),
    }


def _load_customer_info(*, user_id: str, csv_path: Path, question: str | None = None) -> dict[str, Any]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Customer DB CSV not found: {csv_path}")

    try:
        customer_context = build_customer_context(user_id, csv_path)
        info = select_relevant_policy(customer_context, question)
        if not info.get("product_name"):
            raise Step0ValidationError(
                E_MISSING_REQUIRED_FIELD, "Matched customer row is missing product_name"
            )
        return info
    except KeyError:
        raise
    except Exception:
        # Fall back to the legacy single-row reader for older demo CSVs.
        pass

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Customer DB CSV has no header")

        for row in reader:
            row_user_id = _pick(row, "user_id", "고객ID")
            if row_user_id == user_id:
                info = _row_to_customer_info(row)
                if not info.get("product_name"):
                    raise Step0ValidationError(
                        E_MISSING_REQUIRED_FIELD, "Matched customer row is missing product_name"
                    )
                return info

    raise KeyError(f"user_id not found in customer DB: {user_id}")


def run_db_lookup(state: dict[str, Any], *, csv_path: str | Path | None = None) -> dict[str, Any]:
    """
    Step 1 node:
    - validates entry gate for DB_LOOKUP
    - enriches customer_db_info from CSV by user_id
    - sets status to DB_ENRICHED or ERROR
    """
    validate_node_entry("DB_LOOKUP", state)
    updated = deepcopy(state)
    updated["updated_at"] = _utc_now_iso()

    path = Path(csv_path) if csv_path else DEFAULT_CUSTOMER_DB_PATH
    user_id = str(updated["user_id"])

    try:
        customer_info = _load_customer_info(user_id=user_id, csv_path=path, question=updated.get("user_query"))
        patch = {
            "customer_db_info": customer_info,
            "status": "DB_ENRICHED",
            "updated_at": updated["updated_at"],
            "error": None,
        }
        validate_node_update("DB_LOOKUP", state, patch)
        updated.update(patch)
        updated["audit_log"].append(
            build_audit_event(
                node="DB_LOOKUP",
                action="CUSTOMER_DB_ENRICHED",
                note=f"user={_mask_user_id(user_id)}, csv={path.name}",
            )
        )
    except Exception as exc:
        patch = {
            "status": "ERROR",
            "updated_at": updated["updated_at"],
            "error": {
                "error_code": "E_DB_LOOKUP_FAILED",
                "error_message": str(exc),
                "failed_node": "DB_LOOKUP",
                "timestamp": updated["updated_at"],
            },
        }
        validate_node_update("DB_LOOKUP", state, patch)
        updated.update(patch)
        updated["audit_log"].append(
            build_audit_event(
                node="DB_LOOKUP",
                action="CUSTOMER_DB_LOOKUP_FAILED",
                note=f"user={_mask_user_id(user_id)}, reason={exc.__class__.__name__}",
            )
        )

    return updated
