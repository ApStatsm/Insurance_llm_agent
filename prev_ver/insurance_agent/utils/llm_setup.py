"""
utils/llm_setup.py
LLM, 임베딩 모델, Vector DB를 한 곳에서 초기화합니다.
모든 에이전트는 여기서 가져다 씁니다.
"""

import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_chroma import Chroma

# ==========================================
# API 키 세팅
# ==========================================
if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = "AIzaSyAW7UhI1KlYVgffdmR0V0FAyR_DoV0Ie8Q"

# ==========================================
# 임베딩 모델 (파싱 노트북과 동일하게 유지)
# ※ normalize_embeddings 옵션 사용 금지 (파싱 시 미사용)
# ==========================================
print("⏳ BGE-m3 임베딩 모델 로드 중...")
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3"
)

# ==========================================
# LLM 세팅
# temperature=0.2: 팩트 정확도 유지 + 자연스러운 답변 표현
# ==========================================
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.2
)

# ==========================================
# Vector DB 로드
# ==========================================
print("⏳ 4개의 전문 DB 로드 중...")

auto_db      = Chroma(persist_directory="./insurance_chroma_db", embedding_function=embeddings)
cancer_db    = Chroma(persist_directory="./cancer_chroma_db",    embedding_function=embeddings)
teeth_db     = Chroma(persist_directory="./teeth_chroma_db",     embedding_function=embeddings)
precedent_db = Chroma(persist_directory="./precedent_chroma_db", embedding_function=embeddings)

# DB 상태 확인
DB_MAP = {
    "자동차보험": auto_db,
    "암보험":     cancer_db,
    "치아보험":   teeth_db,
    "판례":       precedent_db,
}
for name, db in DB_MAP.items():
    count = db._collection.count()
    status = "✅" if count > 0 else "❌ 비어있음 (경로 확인 필요)"
    print(f"  {status} {name}: {count}개 청크")

# ==========================================
# Retriever 세팅
# ==========================================
auto_retriever      = auto_db.as_retriever(search_type="mmr", search_kwargs={"k": 5, "fetch_k": 20})
cancer_retriever    = cancer_db.as_retriever(search_type="mmr", search_kwargs={"k": 5, "fetch_k": 20})
teeth_retriever     = teeth_db.as_retriever(search_type="mmr", search_kwargs={"k": 5, "fetch_k": 20})
precedent_retriever = precedent_db.as_retriever(search_kwargs={"k": 3})

retrievers = {
    "auto":      auto_retriever,
    "cancer":    cancer_retriever,
    "teeth":     teeth_retriever,
    "precedent": precedent_retriever,
}

# 도메인 한글 레이블
DOMAIN_LABELS = {
    "auto":      "자동차보험 약관",
    "cancer":    "암보험 약관",
    "teeth":     "치아보험 약관",
    "precedent": "관련 판례/분쟁사례",
}

# 상품 코드 → 도메인 매핑
PRODUCT_TO_DOMAIN = {
    "P-A": None,       # 실손보험 (현재 DB 없음)
    "P-B": "cancer",
    "P-C": "auto",
    "P-D": "teeth",
}

print("✅ 모든 세팅 완료!\n")
