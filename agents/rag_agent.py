"""
agents/rag_agent.py
벡터 DB 검색 + LLM 답변 생성을 담당합니다.
"""

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from utils.llm_setup import llm, retrievers, precedent_db, DOMAIN_LABELS

PRECEDENT_SCORE_THRESHOLD = 0.45

TEMPLATE = """
당신은 삼성화재 최고의 보험 보상 심사역이자 법률 자문 에이전트입니다.
고객의 질문에 대해 아래 검색된 자료를 바탕으로 명확하게 답변해주세요.

{context_block}

[이전 대화 내용]
{conversation_history}

고객 질문: {question}

답변 작성 가이드:
1. 위 검색 결과 중 고객 질문과 관련이 없는 보험 내용은 완전히 무시하세요.
2. [고객 가입 정보]가 있다면 해당 고객의 가입 조건을 반드시 반영하여 개인화된 답변을 작성하세요.
3. [이전 대화 내용]을 참고하여 맥락이 이어지도록 답변하세요.
   "그러면", "그거", "아까" 같은 지시어가 있으면 이전 대화에서 찾아서 답변하세요.
4. 관련된 보험 약관의 기준을 먼저 설명하세요.
5. 아래 두 가지 경우를 반드시 구분하세요:
   - 컨텍스트에 [관련 판례/분쟁사례 검색결과] 섹션이 존재하는 경우에만 → 판례 언급
   - 해당 섹션이 없는 경우 → 판례 언급 일절 금지
6. 아래 단정 표현은 반드시 완화하세요:
   - "지급됩니다" → "지급될 수 있습니다"
   - "보장됩니다" → "보장될 수 있습니다"
   - "불가능합니다" → "어려울 수 있습니다"
   - "해당됩니다" → "해당될 수 있습니다"
7. 검색된 문서에서 일부 내용을 찾지 못한 경우에도 "약관에 명시되어 있지 않습니다",
   "확인할 수 없습니다" 같은 부정적 표현은 사용하지 마세요.
   대신 찾은 내용을 바탕으로 최대한 안내하고,
   정확한 내용은 고객센터(1588-5114) 확인을 권유하세요.
8. 답변 시 "안녕하세요", "반갑습니다" 등 인사말로 시작하지 마세요.
   고객 이름을 부르며 시작하지 말고 바로 본론으로 답변하세요.

최종 답변:
"""


def format_docs(docs, domain_label: str) -> str:
    if not docs:
        return ""
    content = "\n\n".join(doc.page_content for doc in docs)
    return f"[{domain_label} 검색결과]\n{content}"


def search_and_answer(
    query: str,
    domains: list,
    customer_context: str = "",
    conversation_history: str = "",
    riders: str = ""
) -> str:
    context_blocks = []

    if customer_context:
        context_blocks.append(f"[고객 가입 정보]\n{customer_context}")

    # 특약명 리스트 추출
    rider_list = [r.strip() for r in riders.split(";") if r.strip()] if riders else []

    # 기본 검색 쿼리
    search_query = query
    if riders:
        search_query = f"{query}\n관련 특약: {riders}"

    for domain in domains:
        if domain == "precedent":
            continue
        if domain not in retrievers:
            continue

        # 1. 원본 쿼리로 기본 검색
        docs = retrievers[domain].invoke(search_query)
        seen = set(doc.page_content for doc in docs)

        # 2. 특약명별 개별 검색 (최대 3개) → 중복 제거 후 추가
        for rider in rider_list[:3]:
            rider_docs = retrievers[domain].invoke(rider)
            for doc in rider_docs:
                if doc.page_content not in seen:
                    seen.add(doc.page_content)
                    docs.append(doc)

        print(f"  📄 [{domain}] 총 {len(docs)}개 청크 검색됨 (기본 + 특약별)")

        # 3. 최대 8개로 제한
        block = format_docs(docs[:8], DOMAIN_LABELS[domain])
        if block:
            context_blocks.append(block)

    # 판례 검색
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

    prompt = PromptTemplate.from_template(TEMPLATE)
    chain = prompt | llm | StrOutputParser()

    return chain.invoke({
        "context_block":        context_block,
        "question":             query,
        "conversation_history": conversation_history if conversation_history else "없음"
    })