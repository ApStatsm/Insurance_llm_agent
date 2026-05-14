"""
agents/complaint_agent.py
고객 불만 감지 + 민원 CSV DB 저장
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils.llm_setup import llm

# 민원 CSV 저장 경로
COMPLAINT_DB_PATH = Path(__file__).parent.parent / "complaint_db.csv"

# CSV 헤더
CSV_HEADERS = [
    "complaint_id",
    "timestamp",
    "customer_id",
    "customer_name",
    "complaint_type",
    "sentiment_score",
    "conversation",
    "customer_query",
    "agent_response",
    "status",
]

# ==========================================
# 불만 감지 프롬프트
# ==========================================
COMPLAINT_DETECTION_PROMPT = """
당신은 보험 고객센터 대화 분석 AI입니다.
고객의 발화를 분석하여 불만 여부를 판단하고 JSON으로만 응답하세요.

[고객 발화]
{query}

[직전 에이전트 응답]
{response}

아래 JSON 형식으로만 응답하세요. 다른 말은 절대 금지입니다.
{{
  "is_complaint": true 또는 false,
  "sentiment_score": 0~10 사이 숫자 (0=매우불만, 10=매우만족),
  "complaint_type": "보장범위불만 / 청구절차불만 / 서비스불만 / 약관이해불만 / 기타" 또는 null,
  "reason": "불만으로 판단한 이유 한 줄 요약" 또는 null
}}

불만 감지 기준:
- "말이 안 되", "이상하다", "왜 안 돼", "억울", "화나", "불합리"
- "그게 말이야", "그럼 뭐가 보장", "도대체", "당연한 거 아냐"
- 보상 거절/감액에 대한 항의
- 절차가 복잡하다는 표현
- 답변이 불충분하다는 표현
"""

def detect_complaint(query: str, response: str) -> dict:
    """고객 발화에서 불만 감지"""
    prompt = PromptTemplate.from_template(COMPLAINT_DETECTION_PROMPT)
    chain = prompt | llm | StrOutputParser()
    result_str = chain.invoke({"query": query, "response": response})
    result_str = result_str.strip().replace("```json", "").replace("```", "")
    return json.loads(result_str)


def save_complaint(
    customer_info: dict,
    query: str,
    response: str,
    detection: dict
) -> str:
    """민원 내용을 CSV에 저장"""

    # CSV 없으면 헤더 포함해서 새로 생성
    file_exists = COMPLAINT_DB_PATH.exists()
    with open(COMPLAINT_DB_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()

        complaint_id = f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        writer.writerow({
            "complaint_id":    complaint_id,
            "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_id":     customer_info.get("customer_id", ""),
            "customer_name":   customer_info.get("name", ""),
            "complaint_type":  detection.get("complaint_type", "기타"),
            "sentiment_score": detection.get("sentiment_score", 0),
            "conversation":    f"Q: {query} / A: {response[:100]}...",
            "customer_query":  query,
            "agent_response":  response[:200],
            "status":          "접수",
        })

    return complaint_id


def check_and_record(
    customer_info: dict,
    query: str,
    response: str
) -> str | None:
    """
    매 응답 후 호출 — 불만 감지 시 민원 저장 후 공감 메시지 반환
    불만 없으면 None 반환
    """
    detection = detect_complaint(query, response)

    if not detection.get("is_complaint"):
        return None

    # 민원 저장
    complaint_id = save_complaint(customer_info, query, response, detection)
    score = detection.get("sentiment_score", 0)

    print(f"  🚨 민원 감지 | 유형: {detection.get('complaint_type')} | 점수: {score}/10 | ID: {complaint_id}")

    # 감정 점수에 따라 공감 메시지 차별화
    if score <= 3:
        empathy = (
            f"고객님의 불편함이 충분히 이해됩니다. "
            f"해당 내용을 담당팀에 전달하여 빠르게 검토하겠습니다. "
            f"민원 접수번호는 {complaint_id}입니다."
        )
    else:
        empathy = (
            f"불편을 드려 죄송합니다. "
            f"고객님의 의견을 소중히 담아 개선에 반영하겠습니다. "
            f"민원 접수번호는 {complaint_id}입니다."
        )

    return f"\n\n💬 {empathy}"
