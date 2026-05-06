from __future__ import annotations

from typing import Any

from langchain_chroma import Chroma

from app.pipeline.step3.worker_common import _run_policy_diagnosis_worker


def run_policy_diagnosis_worker(
    state: dict[str, Any], *, vectorstore: Chroma | None, llm: Any
) -> dict[str, Any]:
    return _run_policy_diagnosis_worker(state, vectorstore=vectorstore, llm=llm)
