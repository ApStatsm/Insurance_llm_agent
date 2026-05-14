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

불만 감지 기준 (아래 조건을 명확히 충족할 때만 true로 판단):
- "억울하다", "화난다", "말이 안 된다" 등 명확한 감정적 불만 표현
- 보상/지급 거절에 대한 직접적인 항의
- 절차가 너무 복잡하다는 구체적 불평
- 답변이 틀렸거나 불충분하다는 직접적 표현

반드시 false로 판단해야 하는 경우:
- "내가 ~했는데" 단순 상황 설명
- "~가입했는데" 가입 사실 언급
- "~사고났는데" 사실 전달
- 질문 형태의 문장
- 보험 정보를 요청하는 문장
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

# ==========================================
# Human Handoff 트리거 조건
# ==========================================
HANDOFF_KEYWORDS = [
    "금감원", "금융감독원", "민원", "소송", "법적조치",
    "변호사", "신고", "언론", "뉴스", "억울"
]

def check_handoff(
    customer_info: dict,
    query: str,
    answer: str,
    sentiment_score: int = None
) -> str | None:
    """
    Human Handoff 필요 여부 판단
    이관 필요하면 안내 메시지 반환, 불필요하면 None 반환

    트리거 조건:
    1. 감정 점수 3 이하 (강한 불만)
    2. 이관 키워드 포함 ("금감원", "소송" 등)
    3. 답변에 "확인 필요", "애매" 등 불확실 표현 포함
    """
    customer_name = customer_info.get("name", "고객")
    reason = None

    UNCERTAIN_EXPRESSIONS = ["약관 해석이 애매", "판단하기 어렵습니다", "검토가 필요합니다", "불분명합니다"]

    # 조건 1: 강한 불만 (감정 점수 3 이하)
    if sentiment_score is not None and sentiment_score <= 3:
        reason = "강한 불만이 감지되어 전문 상담원 연결이 필요합니다."

    # 조건 2: 이관 키워드
    elif any(k in query for k in HANDOFF_KEYWORDS):
        reason = "법적 조치 또는 민원 관련 발언이 감지되었습니다."

    # 조건 3: 답변 불확실 표현
    elif any(e in answer for e in UNCERTAIN_EXPRESSIONS):
        reason = "약관 해석이 복잡하여 전문 심사 담당자 확인이 필요합니다."

    if not reason:
        return None

    # 이관 CSV 기록
    _save_handoff(customer_info, query, reason)

    print(f"  🚨 Human Handoff 트리거 | 사유: {reason}")

    return (
        f"👤 전문 상담원 연결 안내\n"
        f"{customer_name}님의 문의는 AI 처리 범위를 초과하여\n"
        f"전문 상담원에게 연결해 드립니다.\n\n"
        f"📞 전문 상담원 연결: 1588-5114\n"
        f"🕐 운영시간: 평일 09:00 ~ 18:00\n"
        f"🌐 온라인 문의: www.samsungfire.com"
    )


def _save_handoff(customer_info: dict, query: str, reason: str):
    """이관 내역 CSV 저장"""

    HANDOFF_DB_PATH = Path(__file__).parent.parent / "handoff_db.csv"
    HEADERS = ["handoff_id", "timestamp", "customer_id", "customer_name", "reason", "query", "status"]

    file_exists = HANDOFF_DB_PATH.exists()
    with open(HANDOFF_DB_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "handoff_id":    f"HND-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_id":   customer_info.get("customer_id", ""),
            "customer_name": customer_info.get("name", ""),
            "reason":        reason,
            "query":         query,
            "status":        "이관대기",
        })

def check_and_record(
    customer_info: dict,
    query: str,
    response: str
) -> str | None:
    detection = detect_complaint(query, response)

    if not detection.get("is_complaint"):
        # 불만 아니어도 이관 키워드/불확실 표현 체크
        handoff_msg = check_handoff(customer_info, query, response)
        return handoff_msg

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

    empathy_msg = f"\n\n💬 {empathy}"

    # 강한 불만이면 이관도 트리거
    handoff_msg = check_handoff(customer_info, query, response, sentiment_score=score)

    return empathy_msg + (handoff_msg if handoff_msg else "")
