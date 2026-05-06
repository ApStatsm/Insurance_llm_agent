from __future__ import annotations

from typing import Any

from langchain_chroma import Chroma

from app.pipeline.step3.cs_worker import run_cs_complaint_worker
from app.pipeline.step3.document_worker import run_document_claim_worker
from app.pipeline.step3.policy_worker import run_policy_diagnosis_worker
from app.pipeline.step3.precedent_worker import run_precedent_dispute_worker


ROUTE_TO_WORKER = {
    "policy_diagnosis": "POLICY_DIAGNOSIS_WORKER",
    "precedent_dispute": "PRECEDENT_DISPUTE_WORKER",
    "document_claim": "DOCUMENT_CLAIM_WORKER",
    "cs_complaint": "CS_COMPLAINT_WORKER",
}


def run_worker_by_route(
    state: dict[str, Any], *, vectorstore: Chroma | None, llm: Any
) -> dict[str, Any]:
    route = str(state.get("next_route") or "")
    worker = ROUTE_TO_WORKER.get(route)
    if not worker:
        raise ValueError(f"Unknown route: {route}")

    if worker == "POLICY_DIAGNOSIS_WORKER":
        return run_policy_diagnosis_worker(state, vectorstore=vectorstore, llm=llm)
    if worker == "PRECEDENT_DISPUTE_WORKER":
        return run_precedent_dispute_worker(state, llm=llm)
    if worker == "DOCUMENT_CLAIM_WORKER":
        return run_document_claim_worker(state, vectorstore=vectorstore, llm=llm)
    return run_cs_complaint_worker(state)
