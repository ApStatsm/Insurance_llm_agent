from __future__ import annotations

from typing import Any


ERROR_TYPE_LABELS = {
    "E_CUSTOMER_NOT_FOUND": "고객 ID 확인 실패",
    "E_DB_LOOKUP_FAILED": "고객 정보 조회 실패",
    "E_VECTORSTORE_LOAD_FAILED": "약관 DB 로딩 실패",
    "E_POLICY_SEARCH_EMPTY": "약관 검색 실패",
    "E_OPENAI_API_FAILED": "AI 답변 생성 실패",
    "E_FILE_UPLOAD_FAILED": "파일 처리 실패",
    "E_KNOWLEDGE_DB_LOAD_FAILED": "내부 기준 데이터 로딩 실패",
    "E_PIPELINE_RUNTIME": "처리 중 예외 발생",
    "E_MANAGER_LOOP_EXHAUSTED": "답변 검토 반복 초과",
}


ERROR_GUIDES = {
    "E_CUSTOMER_NOT_FOUND": [
        "입력하신 고객 ID에 해당하는 가입 정보를 찾을 수 없습니다.",
        "고객 ID를 다시 확인해 주세요.",
    ],
    "E_DB_LOOKUP_FAILED": [
        "고객 가입 정보를 확인하는 중 문제가 발생했습니다.",
        "고객 ID를 다시 확인해 주시고, 문제가 반복되면 상담원 연결을 요청해 주세요.",
    ],
    "E_VECTORSTORE_LOAD_FAILED": [
        "내부 약관 DB를 불러오는 중 문제가 발생했습니다.",
        "현재 약관 검색 기능이 제한될 수 있습니다. 잠시 후 다시 시도해 주세요.",
    ],
    "E_POLICY_SEARCH_EMPTY": [
        "관련 약관을 찾지 못했습니다.",
        "사고 원인, 발생 일자, 치료명이나 차량 피해 내용을 조금 더 구체적으로 입력해 주세요.",
    ],
    "E_OPENAI_API_FAILED": [
        "AI 답변 생성 중 일시적인 문제가 발생했습니다.",
        "잠시 후 다시 시도해 주세요.",
    ],
    "E_FILE_UPLOAD_FAILED": [
        "업로드한 파일을 처리하는 중 문제가 발생했습니다.",
        "파일 형식이나 용량을 확인해 주세요.",
    ],
    "E_KNOWLEDGE_DB_LOAD_FAILED": [
        "내부 기준 데이터 로딩 중 문제가 발생했습니다.",
        "현재 일부 기능이 제한될 수 있습니다.",
    ],
    "E_MANAGER_LOOP_EXHAUSTED": [
        "답변 검토가 반복되어 최종 안내를 만들지 못했습니다.",
        "질문을 조금 더 짧고 구체적으로 다시 입력해 주세요.",
    ],
    "E_PIPELINE_RUNTIME": [
        "요청을 처리하는 중 예상하지 못한 문제가 발생했습니다.",
        "문제가 반복되면 상담원 연결을 요청해 주세요.",
    ],
}


def _error_code_from_exception(error: Exception) -> str:
    name = error.__class__.__name__.lower()
    message = str(error).lower()
    if "openai" in name or "api" in message or "rate limit" in message or "timeout" in message:
        return "E_OPENAI_API_FAILED"
    if "chroma" in name or "vector" in message or "embedding" in message:
        return "E_VECTORSTORE_LOAD_FAILED"
    if "json" in name or "precedent_cases" in message or "product_required_docs" in message:
        return "E_KNOWLEDGE_DB_LOAD_FAILED"
    return "E_PIPELINE_RUNTIME"


def to_user_friendly_error(error: Exception | dict[str, Any] | None) -> dict[str, Any]:
    if error is None:
        code = "E_PIPELINE_RUNTIME"
        detail = ""
    elif isinstance(error, dict):
        code = str(error.get("error_code") or "E_PIPELINE_RUNTIME")
        detail = str(error.get("error_message") or "")
        if code == "E_DB_LOOKUP_FAILED" and "not found" in detail.lower():
            code = "E_CUSTOMER_NOT_FOUND"
    else:
        code = _error_code_from_exception(error)
        detail = str(error)

    label = ERROR_TYPE_LABELS.get(code, ERROR_TYPE_LABELS["E_PIPELINE_RUNTIME"])
    guides = ERROR_GUIDES.get(code, ERROR_GUIDES["E_PIPELINE_RUNTIME"])
    content = "\n".join(
        [
            "죄송합니다. 요청을 처리하는 중 문제가 발생했습니다.",
            "",
            "문제 유형:",
            f"- {label}",
            "",
            "안내:",
            *[f"- {guide}" for guide in guides],
        ]
    )
    return {
        "error_code": code,
        "error_type": label,
        "guides": guides,
        "content": content,
        "detail": detail,
    }
