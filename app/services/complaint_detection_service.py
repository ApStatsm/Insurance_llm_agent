from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate


COMPLAINT_DETECTION_PROMPT = """
당신은 보험 고객센터 대화 분석 AI입니다.
고객의 발화와 직전 AI 응답을 분석하여 불만/민원 가능성을 판단하세요.

[고객 발화]
{query}

[직전 AI 응답]
{response}

아래 JSON 형식으로만 응답하세요. 다른 말은 절대 금지입니다.
{{
  "is_complaint": true 또는 false,
  "sentiment_score": 0~10 사이 숫자,
  "complaint_type": "보장범위불만 / 청구절차불만 / 서비스불만 / 약관이해불만 / 기타" 또는 null,
  "reason": "불만으로 판단한 이유 한 줄 요약" 또는 null
}}

불만 감지 기준:
- 말이 안 된다, 이상하다, 왜 안 되냐, 억울하다, 화난다, 불합리하다
- 보상 거절/감액에 대한 항의
- 청구 절차가 복잡하거나 답변이 불충분하다는 표현
- 상담원/담당자 연결을 강하게 요구하는 표현
"""


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_json_loads(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _keyword_fallback(query: str) -> dict[str, Any]:
    complaint_keywords = (
        "말이 안",
        "이상",
        "왜 안",
        "억울",
        "화나",
        "불합리",
        "불만",
        "항의",
        "민원",
        "컴플레인",
        "상담원",
        "담당자",
        "금감원",
        "소송",
    )
    matched = [keyword for keyword in complaint_keywords if keyword in query]
    if not matched:
        return {"is_complaint": False, "sentiment_score": 7, "complaint_type": None, "reason": None}
    severe = any(keyword in query for keyword in ("금감원", "소송", "민원", "항의", "화나", "억울"))
    return {
        "is_complaint": True,
        "sentiment_score": 2 if severe else 4,
        "complaint_type": "기타",
        "reason": f"불만 표현 감지 - {', '.join(matched[:3])}",
    }


def detect_complaint(*, llm: Any, query: str, response: str) -> dict[str, Any]:
    """
    Detect latent complaints after every assistant response.

    The LLM path mirrors the original insurance_agent feature. A keyword fallback
    keeps the customer handoff flow working if JSON parsing or the model call fails.
    """
    prompt = PromptTemplate.from_template(COMPLAINT_DETECTION_PROMPT)
    chain = prompt | llm | StrOutputParser()
    try:
        parsed = _safe_json_loads(chain.invoke({"query": query, "response": response[:1600]}))
    except Exception:
        parsed = _keyword_fallback(_to_text(query))

    score_text = _to_text(parsed.get("sentiment_score"))
    number = re.search(r"\d+(?:\.\d+)?", score_text)
    score = float(number.group(0)) if number else 0.0
    score = max(0.0, min(score, 10.0))
    raw_is_complaint = parsed.get("is_complaint")
    if isinstance(raw_is_complaint, str):
        is_complaint = raw_is_complaint.strip().lower() in ("true", "1", "yes", "y")
    else:
        is_complaint = bool(raw_is_complaint)
    return {
        "is_complaint": is_complaint,
        "sentiment_score": score,
        "complaint_type": parsed.get("complaint_type") or "기타",
        "reason": parsed.get("reason") or "",
    }


def format_complaint_empathy(ticket_id: str, detection: dict[str, Any]) -> str:
    score = float(detection.get("sentiment_score") or 0)
    if score <= 3:
        return (
            "고객님의 불편함이 충분히 이해됩니다. 해당 내용은 상담원이 우선 확인할 수 있도록 "
            f"민원성 문의로 접수해두었습니다. 접수번호는 {ticket_id}입니다."
        )
    return (
        "불편을 드려 죄송합니다. 말씀해주신 의견은 상담원이 이어서 확인할 수 있도록 "
        f"접수해두었습니다. 접수번호는 {ticket_id}입니다."
    )
