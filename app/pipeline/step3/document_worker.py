from __future__ import annotations

from typing import Any

from langchain_chroma import Chroma

from app.pipeline.step3.worker_common import _run_document_claim_worker


def run_document_claim_worker(
    state: dict[str, Any], *, vectorstore: Chroma | None, llm: Any
) -> dict[str, Any]:
    return _run_document_claim_worker(state, vectorstore=vectorstore, llm=llm)
