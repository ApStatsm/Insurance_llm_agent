"""
agents/rag_agent.py
벡터 DB 검색 + LLM 답변 생성을 담당합니다.
"""

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils.llm_setup import llm, retrievers, precedent_db, DOMAIN_LABELS

# ==========================================
# 판례 유사도 임계값
# BGE-m3 cosine distance 기준: 낮을수록 유사
# 0.45 이하면 관련 판례로 판단
# ==========================================
PRECEDENT_SCORE_THRESHOLD = 0.45

# ==========================================
# 프롬프트 템플릿
# ==========================================
TEMPLATE = """
당신은 삼성화재 최고의 보험 보상 심사역이자 법률 자문 에이전트입니다.
고객의 질문에 대해 아래 검색된 자료를 바탕으로 명확하게 답변해주세요.

{context_block}

고객 질문: {question}

답변 작성 가이드:
1. 위 검색 결과 중 고객 질문과 관련이 없는 보험 내용은 완전히 무시하세요.
2. [고객 가입 정보]가 있다면 해당 고객의 가입 조건(특약, 보장한도, 가입연도)을 반드시 반영하여 개인화된 답변을 작성하세요.
3. 관련된 보험 약관의 기준을 먼저 설명하세요.
4. 아래 두 가지 경우를 반드시 구분하세요:
   - 컨텍스트에 [관련 판례/분쟁사례 검색결과] 섹션이 존재하는 경우에만 → "관련 판례에 따르면~"으로 출처를 명시하며 근거로 제시하세요.
   - 해당 섹션이 없는 경우 → 판례에 대한 언급을 일절 하지 마세요. "관련 판례가 없습니다" 같은 문장도 금지입니다.
5. 검색된 문서에 관련 내용이 없다면 "해당 내용은 약관 데이터에서 확인할 수 없습니다"라고 답하세요.

최종 답변:
"""


def format_docs(docs, domain_label: str) -> str:
    """검색 결과에 도메인 출처 태그를 붙여서 반환"""
    if not docs:
        return ""
    content = "\n\n".join(doc.page_content for doc in docs)
    return f"[{domain_label} 검색결과]\n{content}"


def search_and_answer(
    query: str,
    domains: list,
    customer_context: str = ""
) -> str:
    """
    지정된 도메인 DB를 검색하고 LLM 답변을 생성합니다.

    Args:
        query: 사용자 질문
        domains: 검색할 도메인 리스트 ["auto", "cancer", "teeth"]
        customer_context: 고객 가입 정보 텍스트 (개인화 답변용)
    """
    context_blocks = []

    # 고객 정보 컨텍스트 (있을 때만)
    if customer_context:
        context_blocks.append(f"[고객 가입 정보]\n{customer_context}")

    # 도메인별 약관 검색
    for domain in domains:
        if domain == "precedent":
            continue  # 판례는 아래에서 별도 처리
        if domain not in retrievers:
            continue
        docs = retrievers[domain].invoke(query)
        block = format_docs(docs, DOMAIN_LABELS[domain])
        if block:
            context_blocks.append(block)

    # 판례: 유사도 점수 필터링 후 관련 있을 때만 추가
    precedent_results = precedent_db.similarity_search_with_score(query, k=3)
    relevant_precedents = [
        doc for doc, score in precedent_results
        if score < PRECEDENT_SCORE_THRESHOLD
    ]
    if relevant_precedents:
        print(f"  ⚖️  관련 판례 {len(relevant_precedents)}건 발견")
        block = format_docs(relevant_precedents, DOMAIN_LABELS["precedent"])
        context_blocks.append(block)
    else:
        print(f"  ⚖️  관련 판례 없음 → 판례 컨텍스트 미포함")

    context_block = "\n\n" + ("=" * 40 + "\n\n").join(context_blocks)

    # LLM 답변 생성
    prompt = PromptTemplate.from_template(TEMPLATE)
    chain = prompt | llm | StrOutputParser()

    return chain.invoke({
        "context_block": context_block,
        "question": query
    })
