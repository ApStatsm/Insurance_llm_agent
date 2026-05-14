"""
agents/claim_agent.py
보험금 청구 서류 접수 + 이미지 분류 + 체크리스트 검증 + 심사 상태 반환
"""

import json
import base64
from datetime import datetime
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils.llm_setup import llm

# ==========================================
# 도메인별 필수 서류 체크리스트
# ==========================================
BASE_DOCUMENTS = {
    "auto": [
        "사고접수확인서",
        "자동차사고사실확인원",
        "진단서 또는 소견서",
        "수리 견적서 또는 수리 영수증",
        "차량 사고 사진",
    ],
    "cancer": [
        "보험금청구서 (삼성화재 양식)",
        "암 진단확인서",
        "병원 진료기록 사본",
        "입원확인서 (입원 시)",
        "병원 영수증",
    ],
    "teeth": [
        "보험금청구서 (삼성화재 양식)",
        "치과 진단서",
        "치과 진료기록 사본",
        "치과 치료 영수증",
    ],
}

RIDER_DOCUMENTS = {
    "렌터카특약":    ["렌터카 이용 영수증", "렌터카 계약서"],
    "긴급출동특약":  ["긴급출동 서비스 확인서"],
    "자기차량손해":  ["수리 완료 확인서", "자동차등록증 사본"],
    "대물확장특약":  ["상대방 차량 수리 견적서"],
    "재진단암특약":  ["재진단 암 진단확인서"],
    "고액암특약":    ["고액암 진단확인서 (암 종류 명시)"],
    "항암치료특약":  ["항암치료 확인서", "처방전 사본"],
    "임플란트특약":  ["임플란트 시술 확인서", "방사선(X-ray) 사진"],
    "크라운특약":    ["크라운 치료 확인서"],
    "보철치료특약":  ["보철치료 확인서"],
}

# 이미지 확장자 → MIME 타입
MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".pdf":  "application/pdf",
}

# ==========================================
# 이미지 서류 분류 프롬프트
# ==========================================
IMAGE_CLASSIFY_PROMPT = """
당신은 보험금 청구 서류 분류 전문가입니다.
아래 이미지를 보고 어떤 종류의 서류인지 판단하여 JSON으로만 응답하세요.
다른 말은 절대 금지입니다.

{
  "doc_type": "진단서 / 영수증 / 진료기록 / 사고사진 / 차량수리견적서 / 처방전 / 시술확인서 / 기타",
  "confidence": "high / medium / low",
  "detail": "서류에서 확인된 주요 정보 한 줄 요약"
}
"""

# ==========================================
# 서류 검증 프롬프트
# ==========================================
VALIDATION_PROMPT = """
당신은 보험금 청구 서류 심사 담당자입니다.
고객이 제출한 서류 목록과 필요 서류 목록을 비교하여 JSON으로만 응답하세요.

[필요 서류 목록]
{required_docs}

[고객 제출 서류 목록]
{submitted_docs}

아래 JSON 형식으로만 응답하세요. 다른 말은 절대 금지입니다.
{{
  "is_complete": true 또는 false,
  "missing_docs": ["누락된 서류 목록"],
  "valid_docs": ["확인된 서류 목록"],
  "status": "접수완료 또는 서류누락",
  "message": "고객에게 전달할 한 줄 안내 메시지"
}}
"""

# ==========================================
# 내부 헬퍼 함수
# ==========================================
def get_required_docs(domain: str, riders: str) -> list:
    """도메인 + 특약 기반 필요 서류 목록 생성"""
    docs = BASE_DOCUMENTS.get(domain, []).copy()
    rider_list = [r.strip() for r in riders.split(";") if r.strip()]
    for rider in rider_list:
        docs.extend(RIDER_DOCUMENTS.get(rider, []))
    return list(dict.fromkeys(docs))  # 중복 제거


def get_riders(customer_info: dict, domain: str) -> str:
    """고객 정보에서 해당 도메인 특약 추출"""
    product_map = {"auto": "P-C", "cancer": "P-B", "teeth": "P-D"}
    for p in customer_info.get("policies", []):
        if p.get("product_id") == product_map.get(domain):
            return p.get("riders", "")
    return ""


def validate_documents(domain: str, riders: str, submitted_docs: list) -> dict:
    """제출 서류 vs 필요 서류 비교 검증"""
    required_docs = get_required_docs(domain, riders)
    prompt = PromptTemplate.from_template(VALIDATION_PROMPT)
    chain = prompt | llm | StrOutputParser()
    result_str = chain.invoke({
        "required_docs":  "\n".join(f"- {d}" for d in required_docs),
        "submitted_docs": "\n".join(f"- {d}" for d in submitted_docs),
    })
    result_str = result_str.strip().replace("```json", "").replace("```", "")
    return json.loads(result_str)


def format_claim_result(
    validation: dict,
    domain_kr: str,
    customer_info: dict,
    query: str
) -> str:
    """검증 결과를 고객 안내 문자열로 변환"""

    # 상담원 확인 필요 키워드 & 사유
    SPECIALIST_REASON = {
        "음주":     "음주 관련 사고는 면책 조항 검토가 필요합니다.",
        "면책":     "면책 조항 해당 여부 확인이 필요합니다.",
        "고지의무": "고지의무 위반 여부 확인이 필요합니다.",
        "기왕증":   "기왕증 해당 여부 확인이 필요합니다.",
        "분쟁":     "분쟁 관련 건으로 전문 심사가 필요합니다.",
        "소송":     "소송 관련 건으로 전문 심사가 필요합니다.",
        "자살":     "자살 관련 건으로 전문 심사가 필요합니다.",
        "고의":     "고의 사고 여부 확인이 필요합니다.",
        "전쟁":     "전쟁/천재지변 면책 여부 확인이 필요합니다.",
        "천재지변": "전쟁/천재지변 면책 여부 확인이 필요합니다.",
    }

    reason = next(
        (SPECIALIST_REASON[k] for k in SPECIALIST_REASON if k in query),
        None
    )

    # ── 케이스 1: 전문 심사 필요 ────────────────────
    if reason:
        return (
            f"🔍 {domain_kr} 전문 심사 필요\n"
            f"서류는 확인되었으나 아래 사유로 전문 심사가 필요합니다.\n"
            f"⚠️ 사유: {reason}\n\n"
            f"📞 전문 상담: 1588-5114 (삼성화재 고객센터)\n"
            f"⏱️ 처리 기간: 영업일 기준 5~10일"
        )

    # ── 케이스 2: 서류 완비 → 접수 완료 ────────────
    if validation["is_complete"]:
        claim_number = f"CLM-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        timestamp    = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
        return (
            f"✅ {domain_kr} 보험금 청구 접수 완료\n"
            f"청구번호 : {claim_number}\n"
            f"접수일시 : {timestamp}\n"
            f"심사상태 : 🔄 서류 검토 중\n\n"
            f"확인된 서류:\n"
            + "\n".join(f"  ✅ {d}" for d in validation["valid_docs"]) +
            f"\n\n예상 처리 기간: 영업일 기준 3~5일\n"
            f"결과는 등록된 연락처({customer_info.get('phone', '')})로 안내드립니다."
        )

    # ── 케이스 3: 서류 누락 → 재제출 요청 ──────────
    else:
        return (
            f"⚠️  {domain_kr} 서류 누락 안내\n"
            f"확인된 서류:\n"
            + "\n".join(f"  ✅ {d}" for d in validation["valid_docs"]) +
            f"\n\n누락된 서류 (재제출 필요):\n"
            + "\n".join(f"  ❌ {d}" for d in validation["missing_docs"]) +
            f"\n\n누락 서류를 추가 제출해 주시면 심사가 진행됩니다.\n"
            f"📞 문의: 1588-5114 (삼성화재 고객센터)"
        )


# ==========================================
# 이미지 분류
# ==========================================
def classify_document_image(image_path: str) -> dict:
    """
    이미지 파일을 OpenAI Vision(gpt-4o-mini)으로 분석하여 서류 종류 반환
    """
    from langchain_core.messages import HumanMessage

    ext        = Path(image_path).suffix.lower()
    mime_type  = MIME_MAP.get(ext, "image/jpeg")
    image_data = base64.b64encode(Path(image_path).read_bytes()).decode()

    message = HumanMessage(content=[
        {"type": "text", "text": IMAGE_CLASSIFY_PROMPT},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
        },
    ])
    response = llm.invoke([message])

    result_str = response.content.strip().replace("```json", "").replace("```", "")
    return json.loads(result_str)


# ==========================================
# 메인 함수
# ==========================================
def handle_claim(
    customer_info: dict,
    domain: str,
    query: str,
    submitted_docs: list = None,
    image_paths: list = None
) -> str:
    """
    청구 접수 메인 함수

    Args:
        customer_info : 고객 정보 dict
        domain        : "auto" / "cancer" / "teeth"
        query         : 고객 질문 원문
        submitted_docs: 서류명 텍스트 리스트 (직접 입력 시)
        image_paths   : 이미지 파일 경로 리스트 (이미지 제출 시)
    """
    customer_name = customer_info.get("name", "고객")
    domain_kr = {"auto": "자동차보험", "cancer": "암보험", "teeth": "치아보험"}.get(domain, domain)
    riders = get_riders(customer_info, domain)
    required_docs = get_required_docs(domain, riders)

    # ── 이미지 제출 ─────────────────────────────
    if image_paths:
        print(f"  🖼️  이미지 {len(image_paths)}개 분석 중...")
        classified = []
        for path in image_paths:
            result = classify_document_image(path)
            classified.append(result)
            print(f"    - {Path(path).name} → {result['doc_type']} (신뢰도: {result['confidence']})")

        # 신뢰도 low 제외하고 서류명 추출
        submitted_docs = [c["doc_type"] for c in classified if c["confidence"] != "low"]

    # ── 서류 미제출: 필요 서류 안내만 ──────────────
    if not submitted_docs:
        docs_str = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(required_docs))
        return (
            f"📋 {domain_kr} 보험금 청구 안내\n"
            f"{customer_name}님의 가입 특약({riders})을 포함한 필요 서류입니다:\n\n"
            f"{docs_str}\n\n"
            f"📞 서류 제출: 1588-5114 (삼성화재 고객센터)\n"
            f"🌐 온라인 제출: www.samsungfire.com → 보험금 청구"
        )

    # ── 서류 검증 진행 ──────────────────────────
    print(f"  📄 서류 검증 중... ({len(submitted_docs)}건)")
    validation = validate_documents(domain, riders, submitted_docs)

    return format_claim_result(validation, domain_kr, customer_info, query=query)
