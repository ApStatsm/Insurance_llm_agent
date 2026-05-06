from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable

from langchain_chroma import Chroma

from app.pipeline.step0 import create_initial_state
from app.pipeline.step1 import run_db_lookup
from app.pipeline.step2 import run_router
from app.pipeline.step3 import run_worker_by_route
from app.pipeline.step4 import manager_review

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _classify_runtime_error(exc: Exception, state: dict[str, Any]) -> tuple[str, str]:
    message = str(exc)
    lowered = message.lower()
    exc_name = exc.__class__.__name__.lower()
    if "openai" in exc_name or "api" in lowered or "rate limit" in lowered or "timeout" in lowered:
        return "E_OPENAI_API_FAILED", state.get("next_route") or "LLM"
    if "chroma" in exc_name or "vector" in lowered or "embedding" in lowered:
        return "E_VECTORSTORE_LOAD_FAILED", "VECTORSTORE"
    if "json" in exc_name or "precedent_cases" in lowered or "product_required_docs" in lowered:
        return "E_KNOWLEDGE_DB_LOAD_FAILED", state.get("next_route") or "KNOWLEDGE_DB"
    return "E_PIPELINE_RUNTIME", "PIPELINE"


def run_multi_agent_pipeline(
    *,
    user_id: str,
    user_query: str,
    user_docs: list[dict[str, Any]],
    vectorstore: Chroma | None = None,
    vectorstore_factory: Callable[[], Chroma] | None = None,
    llm: Any,
    customer_csv_path: str | None = None,
    max_manager_loops: int = 2,
) -> dict[str, Any]:
    state = create_initial_state(user_id=user_id, user_query=user_query, user_docs=user_docs)
    try:
        state = run_db_lookup(state, csv_path=customer_csv_path)
        if state["status"] == "ERROR":
            return state

        state = run_router(state)
        if state["status"] == "ERROR":
            return state

        loops = 0
        while loops <= max_manager_loops:
            route = state.get("next_route")
            if route == "policy_diagnosis" and vectorstore is None:
                if vectorstore_factory is None:
                    raise RuntimeError("Policy diagnosis requires a vectorstore.")
                try:
                    vectorstore = vectorstore_factory()
                except Exception as exc:
                    logger.exception("Vectorstore loading failed")
                    state["status"] = "ERROR"
                    state["updated_at"] = _utc_now_iso()
                    state["error"] = {
                        "error_code": "E_VECTORSTORE_LOAD_FAILED",
                        "error_message": str(exc),
                        "failed_node": "VECTORSTORE",
                        "timestamp": state["updated_at"],
                    }
                    return state
            elif route == "document_claim" and vectorstore is None and vectorstore_factory is not None:
                try:
                    vectorstore = vectorstore_factory()
                except Exception:
                    logger.exception("Optional document-claim evidence search vectorstore loading failed")
            state = run_worker_by_route(state, vectorstore=vectorstore, llm=llm)
            state = manager_review(state)
            if state["status"] == "FINALIZED":
                return state
            loops += 1

        # Manager loop exhausted
        state["status"] = "ERROR"
        state["updated_at"] = _utc_now_iso()
        state["error"] = {
            "error_code": "E_MANAGER_LOOP_EXHAUSTED",
            "error_message": "Manager review loop exceeded max retries.",
            "failed_node": "MANAGER",
            "timestamp": state["updated_at"],
        }
        return state
    except Exception as exc:  # defensive guardrail for UI runtime
        logger.exception("Pipeline runtime failed")
        error_code, failed_node = _classify_runtime_error(exc, state)
        state["status"] = "ERROR"
        state["updated_at"] = _utc_now_iso()
        state["error"] = {
            "error_code": error_code,
            "error_message": str(exc),
            "failed_node": failed_node,
            "timestamp": state["updated_at"],
        }
        return state
