from __future__ import annotations

from typing import Any

from app.pipeline.step3.worker_common import _run_precedent_dispute_worker


def run_precedent_dispute_worker(state: dict[str, Any], *, llm: Any) -> dict[str, Any]:
    return _run_precedent_dispute_worker(state, llm=llm)
