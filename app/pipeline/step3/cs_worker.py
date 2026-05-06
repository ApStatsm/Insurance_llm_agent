from __future__ import annotations

from typing import Any

from app.pipeline.step3.worker_common import _run_cs_complaint_worker


def run_cs_complaint_worker(state: dict[str, Any]) -> dict[str, Any]:
    return _run_cs_complaint_worker(state)
