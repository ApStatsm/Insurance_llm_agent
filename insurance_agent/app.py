"""
app.py
삼성화재 보험 AI 에이전트 - Streamlit 대시보드
실행: streamlit run app.py
"""

import streamlit as st
import sys, json, os, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(
    page_title="삼성화재 AI 보험 어시스턴트",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# 커스텀 CSS
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

* { font-family: 'Noto Sans KR', sans-serif; }

/* 전체 배경 */
.stApp { background-color: #f4f6f9; }

/* 사이드바 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #003876 0%, #0057b8 100%);
    color: white;
}
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] .stSelectbox label { color: white !important; }

/* 탭 스타일 */
.stTabs [data-baseweb="tab-list"] {
    background-color: white;
    border-radius: 12px;
    padding: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 500;
    color: #666;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background-color: #0057b8 !important;
    color: white !important;
}

/* 채팅 메시지 */
.chat-user {
    background: #0057b8;
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 8px 0;
    margin-left: 20%;
    font-size: 0.95rem;
    line-height: 1.6;
}
.chat-bot {
    background: white;
    color: #1a1a2e;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px;
    margin: 8px 0;
    margin-right: 20%;
    font-size: 0.95rem;
    line-height: 1.6;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-left: 3px solid #0057b8;
}
.chat-label-user {
    text-align: right;
    font-size: 0.75rem;
    color: #999;
    margin-bottom: 2px;
    margin-right: 4px;
}
.chat-label-bot {
    font-size: 0.75rem;
    color: #999;
    margin-bottom: 2px;
    margin-left: 4px;
}

/* 고객 정보 카드 */
.info-card {
    background: white;
    border-radius: 12px;
    padding: 16px;
    margin: 8px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-top: 3px solid #0057b8;
}
.info-card h4 { color: #0057b8; margin: 0 0 8px 0; font-size: 0.9rem; }
.info-card p  { margin: 4px 0; font-size: 0.85rem; color: #444; }

/* 상태 배지 */
.badge-blue   { background:#e8f0fe; color:#0057b8; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-green  { background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-orange { background:#fff3e0; color:#e65100; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-red    { background:#fce4ec; color:#c62828; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }

/* 민원 테이블 */
.complaint-row {
    background: white;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 6px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    font-size: 0.88rem;
}

/* 버튼 */
.stButton button {
    background: #0057b8;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 500;
    padding: 8px 20px;
}
.stButton button:hover { background: #003876; }

/* 입력창 */
.stTextInput input, .stTextArea textarea {
    border-radius: 10px !important;
    border: 1.5px solid #e0e0e0 !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #0057b8 !important;
    box-shadow: 0 0 0 2px rgba(0,87,184,0.1) !important;
}

/* 파일 업로더 */
[data-testid="stFileUploader"] {
    background: #f0f4ff;
    border: 2px dashed #0057b8;
    border-radius: 10px;
    padding: 12px;
}

/* 메트릭 카드 */
[data-testid="stMetric"] {
    background: white;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 세션 상태 초기화
# ==========================================
def init_session():
    defaults = {
        "logged_in":       False,
        "customer_info":   None,
        "chat_history":    [],      # [{"role": "user"/"bot", "content": str, "time": str}]
        "claim_step":      None,    # None / "waiting_docs" / "submitted"
        "claim_domain":    None,
        "agents_loaded":   False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ==========================================
# 에이전트 로드 (최초 1회)
# ==========================================
@st.cache_resource(show_spinner="🔄 AI 엔진 초기화 중...")
def load_agents():
    from utils.llm_setup import llm, PRODUCT_TO_DOMAIN
    from agents.customer_agent import login, format_customer_info
    from agents.rag_agent import search_and_answer
    from agents.claim_agent import handle_claim
    from agents.complaint_agent import check_and_record
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    return {
        "llm": llm,
        "PRODUCT_TO_DOMAIN": PRODUCT_TO_DOMAIN,
        "login": login,
        "format_customer_info": format_customer_info,
        "search_and_answer": search_and_answer,
        "handle_claim": handle_claim,
        "check_and_record": check_and_record,
        "PromptTemplate": PromptTemplate,
        "StrOutputParser": StrOutputParser,
    }

try:
    agents = load_agents()
    st.session_state["agents_loaded"] = True
except Exception as e:
    st.error(f"❌ 에이전트 로드 실패: {e}")
    st.stop()


# ==========================================
# 라우터 함수
# ==========================================
BLOCKED_KEYWORDS = ["씨발", "개새끼", "병신", "존나", "ㅅㅂ", "ㅂㅅ"]

INTENT_ROUTER_PROMPT = """
당신은 삼성화재 보험 고객센터 AI의 질문 분류기입니다.

[로그인 고객 정보]
{customer_info}

[고객 질문]
{query}

아래 JSON 형식으로만 응답하세요. 다른 말은 절대 금지입니다.

{{
  "intent": "보장조회 또는 미가입문의 또는 사고청구 또는 일반문의 또는 out_of_scope",
  "target_domain": ["auto", "cancer", "teeth", "precedent" 중 해당하는 것만],
  "is_subscribed": true 또는 false,
  "needs_document_guide": true 또는 false,
  "sub_queries": ["약관 검색에 쓸 핵심 질문들"]
}}

분류 기준:
- 보장조회: 가입한 보험의 보장 범위, 지급 여부 질문
- 미가입문의: 아직 가입하지 않은 보험에 대한 설명/가입 문의
- 사고청구: 실제 사고 발생 또는 보험금 청구 의사 표현
- 일반문의: 보험과 관련된 일반적인 질문
- out_of_scope: 보험과 전혀 관련 없는 질문 (날씨, 음식, 연예인 등)
- needs_document_guide: 사고청구인 경우 true
"""

OUT_OF_SCOPE_PROMPT = """
고객이 보험과 관련 없는 질문을 했습니다.
친근하고 자연스럽게 짧게 답변한 뒤, 마지막에 보험 관련 질문을 유도하는 멘트로 마무리하세요.
보험 유도 멘트 예시: "혹시 보험 관련해서 궁금하신 점이 있으시면 편하게 말씀해 주세요 😊"

고객 질문: {query}
답변:"""


def router_agent(user_query: str) -> dict:
    a = agents
    customer_info_str = a["format_customer_info"](st.session_state["customer_info"])
    prompt = a["PromptTemplate"].from_template(INTENT_ROUTER_PROMPT)
    chain  = prompt | a["llm"] | a["StrOutputParser"]()
    result = chain.invoke({"customer_info": customer_info_str, "query": user_query})
    result = result.strip().replace("```json", "").replace("```", "")
    return json.loads(result)


def execute(user_query: str, image_paths: list = None) -> str:
    a = agents
    customer_info    = st.session_state["customer_info"]
    customer_context = a["format_customer_info"](customer_info)

    # 욕설 필터
    if any(k in user_query for k in BLOCKED_KEYWORDS):
        return "⚠️ 부적절한 표현이 포함되어 있어 답변드리기 어렵습니다.\n정중한 표현으로 다시 질문해 주시면 성심껏 도와드리겠습니다."

    routing = router_agent(user_query)
    intent  = routing["intent"]
    domains = routing["target_domain"]

    if intent == "out_of_scope":
        prompt = a["PromptTemplate"].from_template(OUT_OF_SCOPE_PROMPT)
        chain  = prompt | a["llm"] | a["StrOutputParser"]()
        answer = chain.invoke({"query": user_query})

    elif intent == "보장조회":
        answer = a["search_and_answer"](user_query, domains, customer_context)

    elif intent == "미가입문의":
        answer = a["search_and_answer"](user_query, domains, "")
        answer += "\n\n📌 가입을 원하시면 삼성화재 홈페이지(www.samsungfire.com)에서 가입하실 수 있습니다."

    elif intent == "사고청구":
        domain = domains[0] if domains else "auto"
        st.session_state["claim_step"]   = "waiting_docs"
        st.session_state["claim_domain"] = domain

        coverage = a["search_and_answer"](user_query, domains, customer_context)
        claim    = a["handle_claim"](customer_info, domain, user_query, image_paths=image_paths)
        answer   = f"{coverage}\n\n{'─'*40}\n\n{claim}"

    else:
        answer = a["search_and_answer"](user_query, domains, "")

    # 불만 감지
    if intent not in ("out_of_scope",):
        complaint_msg = a["check_and_record"](customer_info, user_query, answer)
        if complaint_msg:
            answer += complaint_msg

    return answer


def add_message(role: str, content: str):
    st.session_state["chat_history"].append({
        "role": role,
        "content": content,
        "time": datetime.now().strftime("%H:%M"),
    })


# ==========================================
# 사이드바 — 로그인 & 고객 정보
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ 삼성화재 AI")
    st.markdown("---")

    if not st.session_state["logged_in"]:
        st.markdown("### 로그인")
        cid = st.text_input("고객 ID", placeholder="CUST-0001")
        pwd = st.text_input("비밀번호", type="password", placeholder="****")

        if st.button("로그인", use_container_width=True):
            info = agents["login"](cid, pwd)
            if info:
                st.session_state["logged_in"]     = True
                st.session_state["customer_info"] = info
                add_message("bot", f"안녕하세요, **{info['name']}**님! 😊\n삼성화재 AI 어시스턴트입니다. 보험 관련 궁금한 점을 편하게 물어보세요.")
                st.rerun()
            else:
                st.error("ID 또는 비밀번호를 확인해주세요.")
    else:
        info = st.session_state["customer_info"]
        st.markdown(f"### 👤 {info['name']}님")
        st.markdown("---")
        st.markdown("**가입 보험**")
        for p in info["policies"]:
            years = datetime.now().year - int(p["joined_year"])
            st.markdown(f"""
<div class="info-card">
  <h4>🔵 {p['product_name']}</h4>
  <p>📅 {p['joined_year']}년 가입 ({years}년차)</p>
  <p>💰 한도: {p['coverage_limit']}</p>
  <p>➕ 특약: {p['riders']}</p>
</div>
""", unsafe_allow_html=True)

        st.markdown("---")
        if st.button("로그아웃", use_container_width=True):
            for k in ["logged_in", "customer_info", "chat_history", "claim_step", "claim_domain"]:
                st.session_state[k] = None if k not in ["chat_history"] else []
            st.session_state["logged_in"] = False
            st.rerun()


# ==========================================
# 메인 콘텐츠
# ==========================================
if not st.session_state["logged_in"]:
    # 로그인 전 랜딩
    st.markdown("""
    <div style="text-align:center; padding: 80px 0;">
        <div style="font-size:4rem;">🛡️</div>
        <h1 style="color:#0057b8; font-weight:700; margin:16px 0 8px;">삼성화재 AI 어시스턴트</h1>
        <p style="color:#666; font-size:1.1rem;">보험 약관 조회부터 청구까지, AI가 도와드립니다.</p>
        <br>
        <div style="display:flex; justify-content:center; gap:24px; flex-wrap:wrap;">
            <div style="background:white; border-radius:12px; padding:20px 28px; box-shadow:0 2px 12px rgba(0,0,0,0.08); min-width:160px;">
                <div style="font-size:2rem;">💬</div>
                <p style="color:#333; font-weight:500; margin:8px 0 0;">약관 Q&A</p>
            </div>
            <div style="background:white; border-radius:12px; padding:20px 28px; box-shadow:0 2px 12px rgba(0,0,0,0.08); min-width:160px;">
                <div style="font-size:2rem;">📋</div>
                <p style="color:#333; font-weight:500; margin:8px 0 0;">보험금 청구</p>
            </div>
            <div style="background:white; border-radius:12px; padding:20px 28px; box-shadow:0 2px 12px rgba(0,0,0,0.08); min-width:160px;">
                <div style="font-size:2rem;">⚖️</div>
                <p style="color:#333; font-weight:500; margin:8px 0 0;">판례 검색</p>
            </div>
            <div style="background:white; border-radius:12px; padding:20px 28px; box-shadow:0 2px 12px rgba(0,0,0,0.08); min-width:160px;">
                <div style="font-size:2rem;">🚨</div>
                <p style="color:#333; font-weight:500; margin:8px 0 0;">민원 접수</p>
            </div>
        </div>
        <br><br>
        <p style="color:#999;">← 왼쪽에서 로그인해주세요</p>
    </div>
    """, unsafe_allow_html=True)

else:
    # ── 탭 구성 ──────────────────────────────────
    tab_chat, tab_claim, tab_complaint = st.tabs(["💬 채팅 상담", "📋 보험금 청구", "🚨 민원 현황"])


    # ============================
    # 탭 1: 채팅 상담
    # ============================
    with tab_chat:
        st.markdown("### 💬 AI 보험 상담")

        # 채팅 히스토리 출력
        chat_container = st.container(height=480)
        with chat_container:
            for msg in st.session_state["chat_history"]:
                if msg["role"] == "user":
                    st.markdown(f'<div class="chat-label-user">{msg["time"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="chat-label-bot">🛡️ AI 어시스턴트 · {msg["time"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="chat-bot">{msg["content"]}</div>', unsafe_allow_html=True)

        st.markdown("---")

        # 입력 영역
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            user_input = st.text_input(
                "질문 입력",
                placeholder="보험 관련 질문을 입력하세요...",
                label_visibility="collapsed",
                key="chat_input"
            )
        with col_btn:
            send_btn = st.button("전송", use_container_width=True)

        # 청구 프로세스 진입 시 파일 첨부 영역
        if st.session_state.get("claim_step") == "waiting_docs":
            st.markdown("#### 📎 서류 첨부")
            st.info("청구 서류를 이미지로 첨부해주세요. (JPG, PNG, PDF 지원)")
            uploaded_files = st.file_uploader(
                "서류 이미지 업로드",
                type=["jpg", "jpeg", "png", "pdf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
                key="doc_uploader"
            )

            if uploaded_files:
                # 미리보기
                cols = st.columns(min(len(uploaded_files), 4))
                for i, f in enumerate(uploaded_files):
                    with cols[i % 4]:
                        if f.type.startswith("image"):
                            st.image(f, caption=f.name, use_container_width=True)
                        else:
                            st.markdown(f"📄 {f.name}")

                if st.button("📤 서류 제출 및 검증", use_container_width=True):
                    # 임시 저장
                    tmp_paths = []
                    with tempfile.TemporaryDirectory() as tmpdir:
                        for f in uploaded_files:
                            tmp_path = os.path.join(tmpdir, f.name)
                            with open(tmp_path, "wb") as fp:
                                fp.write(f.read())
                            tmp_paths.append(tmp_path)

                        with st.spinner("🔍 서류 분석 중..."):
                            from agents.claim_agent import handle_claim
                            result = handle_claim(
                                customer_info=st.session_state["customer_info"],
                                domain=st.session_state["claim_domain"],
                                query="서류 제출",
                                image_paths=tmp_paths
                            )

                    add_message("bot", result)
                    st.session_state["claim_step"] = "submitted"
                    st.rerun()

        # 전송 처리
        if (send_btn or user_input) and user_input:
            add_message("user", user_input)
            with st.spinner("🤔 답변 생성 중..."):
                response = execute(user_input)
            add_message("bot", response)
            st.rerun()


    # ============================
    # 탭 2: 보험금 청구
    # ============================
    with tab_claim:
        st.markdown("### 📋 보험금 청구")

        info = st.session_state["customer_info"]

        # 청구 가능 보험 선택
        domain_map = {"P-C": ("자동차보험", "auto"), "P-B": ("암보험", "cancer"), "P-D": ("치아보험", "teeth")}
        options = {}
        for p in info["policies"]:
            if p["product_id"] in domain_map:
                label, domain = domain_map[p["product_id"]]
                options[label] = domain

        if not options:
            st.warning("청구 가능한 보험이 없습니다.")
        else:
            selected_label = st.selectbox("청구할 보험 선택", list(options.keys()))
            selected_domain = options[selected_label]

            st.markdown("---")
            st.markdown("#### 📎 서류 업로드")
            st.info(f"**{selected_label}** 청구에 필요한 서류를 업로드해주세요.")

            uploaded = st.file_uploader(
                "서류 이미지",
                type=["jpg", "jpeg", "png", "pdf"],
                accept_multiple_files=True,
                key="claim_tab_uploader"
            )

            if uploaded:
                # 미리보기
                cols = st.columns(min(len(uploaded), 4))
                for i, f in enumerate(uploaded):
                    with cols[i % 4]:
                        if f.type.startswith("image"):
                            st.image(f, caption=f.name, use_container_width=True)
                        else:
                            st.markdown(f"📄 {f.name}")

            if st.button("📤 청구 접수하기", use_container_width=True, disabled=not uploaded):
                tmp_paths = []
                with tempfile.TemporaryDirectory() as tmpdir:
                    for f in uploaded:
                        tmp_path = os.path.join(tmpdir, f.name)
                        with open(tmp_path, "wb") as fp:
                            fp.write(f.read())
                        tmp_paths.append(tmp_path)

                    with st.spinner("🔍 서류 분석 및 심사 중..."):
                        from agents.claim_agent import handle_claim
                        result = handle_claim(
                            customer_info=info,
                            domain=selected_domain,
                            query="보험금 청구",
                            image_paths=tmp_paths
                        )

                st.markdown("#### 📊 심사 결과")
                if "접수 완료" in result or "✅" in result:
                    st.success(result)
                elif "누락" in result or "⚠️" in result:
                    st.warning(result)
                else:
                    st.info(result)

                # 채팅에도 기록
                add_message("bot", f"[청구 탭] {result}")


    # ============================
    # 탭 3: 민원 현황
    # ============================
    with tab_complaint:
        st.markdown("### 🚨 민원 현황")

        complaint_path = Path(__file__).parent / "complaint_db.csv"

        if not complaint_path.exists():
            st.info("접수된 민원이 없습니다.")
        else:
            import pandas as pd
            df = pd.read_csv(complaint_path, encoding="utf-8-sig")

            # 내 민원만 필터
            my_df = df[df["customer_id"] == st.session_state["customer_info"]["customer_id"]]

            # 전체 요약 메트릭
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("전체 민원", len(my_df))
            with col2:
                pending = len(my_df[my_df["status"] == "접수"])
                st.metric("처리 중", pending)
            with col3:
                avg_score = round(my_df["sentiment_score"].mean(), 1) if len(my_df) > 0 else "-"
                st.metric("평균 감정 점수", f"{avg_score} / 10")

            st.markdown("---")
            st.markdown("#### 📋 민원 목록")

            if len(my_df) == 0:
                st.info("접수된 민원이 없습니다.")
            else:
                for _, row in my_df.iterrows():
                    score = row["sentiment_score"]
                    if score <= 3:
                        badge = '<span class="badge-red">매우불만</span>'
                    elif score <= 5:
                        badge = '<span class="badge-orange">불만</span>'
                    elif score <= 7:
                        badge = '<span class="badge-blue">보통</span>'
                    else:
                        badge = '<span class="badge-green">만족</span>'

                    st.markdown(f"""
<div class="complaint-row">
    <b>{row['complaint_id']}</b> · {row['timestamp']} · {badge}
    <br><span style="color:#666">유형: {row['complaint_type']} | 상태: {row['status']}</span>
    <br><span style="color:#333; margin-top:4px; display:block">"{row['customer_query']}"</span>
</div>
""", unsafe_allow_html=True)
