from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline.step2.router import ROUTING_TEST_CASES, select_route


def test_routing_cases() -> None:
    for case in ROUTING_TEST_CASES:
        actual = select_route(case["question"])
        expected = case["expected_route"]
        assert actual == expected, f"{case['question']} -> {actual}, expected {expected}"


def main() -> int:
    failures: list[str] = []
    for case in ROUTING_TEST_CASES:
        actual = select_route(case["question"])
        expected = case["expected_route"]
        status = "PASS" if actual == expected else "FAIL"
        print(f"{status}: {case['question']} -> {actual} (expected: {expected})")
        if actual != expected:
            failures.append(case["question"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
