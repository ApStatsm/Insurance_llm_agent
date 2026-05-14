"""
app.py
삼성화재 보험 AI 에이전트 - Streamlit 통합 대시보드
실행: streamlit run app.py
"""

import streamlit as st
import sys, json, os, tempfile, csv
import pandas as pd
import plotly.express as px
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="삼성화재 AI 보험 어시스턴트",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
* { font-family: 'Noto Sans KR', sans-serif; }

.stApp { background-color: #f4f6f9; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #003876 0%, #0057b8 100%);
}
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] input { color: #333 !important; }

.stButton > button {
    background-color: white !important;
    color: #0057b8 !important;
    border: 2px solid #0057b8 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    width: 100% !important;
}
.stButton > button:hover {
    background-color: #0057b8 !important;
    color: white !important;
}
[data-testid="stSidebar"] .stButton > button {
    background-color: white !important;
    color: #003876 !important;
    border: 2px solid white !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span,
[data-testid="stSidebar"] .stButton > button div {
    color: #003876 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #003876 !important;
    color: white !important;
    border-color: #003876 !important;
}
[data-testid="stSidebar"] .stButton > button:hover p,
[data-testid="stSidebar"] .stButton > button:hover span,
[data-testid="stSidebar"] .stButton > button:hover div {
    color: white !important;
}

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

/* 채팅 말풍선 */
.chat-user {
    background: #0057b8;
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 8px 0;
    margin-left: 20%;
    font-size: 0.95rem;
    line-height: 1.7;
    word-break: keep-all;
}
.chat-bot {
    background: white;
    color: #1a1a2e;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px;
    margin: 8px 0;
    margin-right: 20%;
    font-size: 0.95rem;
    line-height: 1.7;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-left: 3px solid #0057b8;
    word-break: keep-all;
}
/* 채팅 내 리스트 정렬 */
.chat-bot ul, .chat-bot ol { padding-left: 1.5em; margin: 4px 0; }
.chat-bot li { margin: 2px 0; line-height: 1.7; }

.chat-label-user { text-align:right; font-size:0.75rem; color:#999; margin-bottom:2px; }
.chat-label-bot  { font-size:0.75rem; color:#999; margin-bottom:2px; }

/* 채팅창 고정 높이 + 스크롤 */
[data-testid="stVerticalBlockBorderWrapper"] {
    height: 500px !important;
    overflow-y: auto !important;
}

.policy-card {
    background: rgba(255,255,255,0.15);
    border-radius: 10px;
    padding: 12px;
    margin: 8px 0;
    border: 1px solid rgba(255,255,255,0.3);
}
.policy-card p { margin: 3px 0; font-size: 0.85rem; }

.log-row {
    background: white;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 6px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    font-size: 0.88rem;
    border-left: 4px solid #e0e0e0;
}
.log-row.complaint { border-left-color: #ff9800; }
.log-row.handoff   { border-left-color: #f44336; }
.log-row.claim     { border-left-color: #2196f3; }
.log-row.normal    { border-left-color: #4caf50; }

.badge { border-radius:20px; padding:2px 10px; font-size:0.78rem; font-weight:600; }
.badge-complaint { background:#fff3e0; color:#e65100; }
.badge-handoff   { background:#fce4ec; color:#c62828; }
.badge-claim     { background:#e3f2fd; color:#1565c0; }
.badge-normal    { background:#e8f5e9; color:#2e7d32; }
.badge-intent    { background:#f3e5f5; color:#6a1b9a; }
.badge-blue   { background:#e8f0fe; color:#0057b8; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-green  { background:#e8f5e9; color:#2e7d32; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-orange { background:#fff3e0; color:#e65100; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }
.badge-red    { background:#fce4ec; color:#c62828; border-radius:20px; padding:2px 10px; font-size:0.8rem; font-weight:500; }

.complaint-row {
    background: white;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 6px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    font-size: 0.88rem;
}
[data-testid="stFileUploader"] {
    background: #f0f4ff;
    border: 2px dashed #0057b8;
    border-radius: 10px;
    padding: 12px;
}
</style>
""", unsafe_allow_html=True)


def init_session():
    defaults = {
        "mode":            "user",
        "logged_in":       False,
        "admin_logged_in": False,
        "customer_info":   None,
        "chat_history":    [],
        "claim_step":      None,
        "claim_domain":    None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

BASE_PATH    = Path(__file__).parent
AUDIT_LOG    = BASE_PATH / "audit_log.csv"
COMPLAINT_DB = BASE_PATH / "complaint_db.csv"
HANDOFF_DB   = BASE_PATH / "handoff_db.csv"
CUSTOMER_DB  = BASE_PATH / "customers.csv"

AUDIT_HEADERS = [
    "log_id", "timestamp", "customer_id", "customer_name",
    "query", "intent", "domains", "answer_preview",
    "claim_status", "is_complaint", "is_handoff"
]

ADMIN_ID  = "admin"
ADMIN_PWD = "1234"


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
        "llm":                  llm,
        "PRODUCT_TO_DOMAIN":    PRODUCT_TO_DOMAIN,
        "login":                login,
        "format_customer_info": format_customer_info,
        "search_and_answer":    search_and_answer,
        "handle_claim":         handle_claim,
        "check_and_record":     check_and_record,
        "PromptTemplate":       PromptTemplate,
        "StrOutputParser":      StrOutputParser,
    }

try:
    agents = load_agents()
except Exception as e:
    import traceback
    st.error(f"❌ 에이전트 로드 실패: {e}")
    st.code(traceback.format_exc())
    st.stop()


BLOCKED_KEYWORDS = ["씨발", "개새끼", "병신", "존나", "ㅅㅂ", "ㅂㅅ"]

INTENT_ROUTER_PROMPT = """
당신은 삼성화재 보험 고객센터 AI의 질문 분류기입니다.

[로그인 고객 정보]
{customer_info}

[고객 질문]
{query}

아래 JSON 형식으로만 응답하세요. 다른 말은 절대 금지입니다.

{{
  "intent": "보장조회 또는 가입조회 또는 미가입문의 또는 사고청구 또는 일반문의 또는 out_of_scope",
  "subscribed_domains": ["고객이 실제 가입한 도메인 중 질문과 관련된 것만"],
  "unsubscribed_domains": ["고객이 미가입인데 질문과 관련된 도메인"],
  "needs_document_guide": true 또는 false,
  "sub_queries": ["약관 검색에 쓸 핵심 질문들"]
}}

분류 기준:
- 가입조회: 고객이 자신의 보험 가입 현황을 묻는 질문
- 보장조회: 가입한 보험의 보장 범위, 지급 여부 질문
- 미가입문의: 아직 가입하지 않은 보험에 대한 설명/가입 문의
- 사고청구: 실제 사고 발생 또는 보험금 청구 의사 표현
- 일반문의: 보험과 관련된 일반적인 질문
- out_of_scope: 보험과 전혀 관련 없는 질문

도메인 분류 규칙:
- subscribed_domains: 고객 가입 정보와 질문 내용을 대조하여 실제 가입된 것만
- unsubscribed_domains: 질문과 관련되지만 고객이 미가입인 도메인
- 자동차/차량/사고/운전 → auto
- 암/종양/진단비/항암 → cancer
- 치아/임플란트/스케일링/충치 → teeth
- 판례/판결/법원/분쟁 → precedent
- 복수 상품이 관련되면 모두 포함
"""

OUT_OF_SCOPE_PROMPT = """
고객이 보험과 관련 없는 질문을 했습니다.
친근하고 자연스럽게 짧게 답변한 뒤, 마지막에 보험 관련 질문을 유도하는 멘트로 마무리하세요.
보험 유도 멘트 예시: "혹시 보험 관련해서 궁금하신 점이 있으시면 편하게 말씀해 주세요 😊"

고객 질문: {query}
답변:"""

POLICY_INFO_PROMPT = """
고객의 보험 가입 정보를 아래에서 확인하고, 가입된 보험 목록만 친절하게 안내해주세요.
약관 설명은 절대 하지 마세요. 가입 정보만 전달하고 마지막에 필요한 것이 있는지 물어보세요.

[고객 가입 정보]
{customer_info}

답변:"""


def log_conversation(customer_info, query, intent, domains, answer,
                     claim_status="-", is_complaint=False, is_handoff=False):
    file_exists = AUDIT_LOG.exists()
    with open(AUDIT_LOG, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "log_id":         f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_id":    customer_info.get("customer_id", ""),
            "customer_name":  customer_info.get("name", ""),
            "query":          query,
            "intent":         intent,
            "domains":        ", ".join(domains) if domains else "-",
            "answer_preview": answer[:100],
            "claim_status":   claim_status,
            "is_complaint":   is_complaint,
            "is_handoff":     is_handoff,
        })


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

    history = st.session_state.get("chat_history", [])
    recent  = history[-6:] if len(history) > 6 else history
    conversation_history = "\n".join([
        f"{'고객' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
        for m in recent
    ])

    if any(k in user_query for k in BLOCKED_KEYWORDS):
        return "⚠️ 부적절한 표현이 포함되어 있어 답변드리기 어렵습니다.\n정중한 표현으로 다시 질문해 주시면 성심껏 도와드리겠습니다."

    try:
        routing = router_agent(user_query)
    except Exception as e:
        return f"❌ 라우터 오류: {e}"

    intent               = routing["intent"]
    subscribed_domains   = routing.get("subscribed_domains", [])
    unsubscribed_domains = routing.get("unsubscribed_domains", [])

    domain_to_product = {"auto": "P-C", "cancer": "P-B", "teeth": "P-D"}
    riders_list = []
    for p in customer_info.get("policies", []):
        pid = p.get("product_id", "")
        if any(domain_to_product.get(d) == pid for d in subscribed_domains):
            riders_list.append(p.get("riders", ""))
    riders = ";".join([r for r in riders_list if r])

    if intent == "out_of_scope":
        prompt = a["PromptTemplate"].from_template(OUT_OF_SCOPE_PROMPT)
        chain  = prompt | a["llm"] | a["StrOutputParser"]()
        answer = chain.invoke({"query": user_query})

    elif intent == "가입조회":
        prompt = a["PromptTemplate"].from_template(POLICY_INFO_PROMPT)
        chain  = prompt | a["llm"] | a["StrOutputParser"]()
        answer = chain.invoke({"customer_info": customer_context})

    elif intent == "보장조회":
        answer = a["search_and_answer"](
            user_query, subscribed_domains, customer_context,
            conversation_history=conversation_history, riders=riders
        )
        if unsubscribed_domains:
            domain_kr = {"auto": "자동차보험", "cancer": "암보험", "teeth": "치아보험"}
            names = [domain_kr.get(d, d) for d in unsubscribed_domains]
            answer += f"\n\n💡 {', '.join(names)}은 현재 미가입 상태입니다. 가입을 원하시면 삼성화재 홈페이지(www.samsungfire.com)에서 확인해보세요."

    elif intent == "미가입문의":
        all_domains = subscribed_domains + unsubscribed_domains
        answer = a["search_and_answer"](
            user_query, all_domains, "",
            conversation_history=conversation_history
        )
        answer += "\n\n📌 가입을 원하시면 삼성화재 홈페이지(www.samsungfire.com)에서 가입하실 수 있습니다."

    elif intent == "사고청구":
        domain = subscribed_domains[0] if subscribed_domains else "auto"
        st.session_state["claim_step"]   = "waiting_docs"
        st.session_state["claim_domain"] = domain
        coverage = a["search_and_answer"](
            user_query, subscribed_domains, customer_context,
            conversation_history=conversation_history, riders=riders
        )
        claim  = a["handle_claim"](customer_info, domain, user_query)
        answer = f"{coverage}\n\n{claim}"
        answer += "\n\n※ 최종 지급 여부는 실제 심사 결과에 따라 달라질 수 있습니다."
        if len(subscribed_domains) > 1:
            domain_kr = {"auto": "자동차보험", "cancer": "암보험", "teeth": "치아보험"}
            names = [domain_kr.get(d, d) for d in subscribed_domains]
            answer += f"\n\n💡 {', '.join(names)} 모두 관련될 수 있습니다. 각각 청구 탭에서 개별 접수 가능합니다."

    else:
        answer = a["search_and_answer"](
            user_query, subscribed_domains or unsubscribed_domains, "",
            conversation_history=conversation_history
        )

    is_complaint = False
    is_handoff   = False
    if intent != "out_of_scope":
        try:
            complaint_msg = a["check_and_record"](customer_info, user_query, answer)
            if complaint_msg:
                is_complaint = True
                is_handoff   = "전문 상담원" in complaint_msg
                answer += complaint_msg
        except Exception:
            pass

    log_conversation(
        customer_info=customer_info, query=user_query, intent=intent,
        domains=subscribed_domains + unsubscribed_domains, answer=answer,
        claim_status=st.session_state.get("claim_step") or "-",
        is_complaint=is_complaint, is_handoff=is_handoff,
    )
    return answer


def add_message(role: str, content: str):
    st.session_state["chat_history"].append({
        "role": role, "content": content,
        "time": datetime.now().strftime("%H:%M"),
    })


def render_chat():
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-label-user">{msg["time"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-label-bot">🛡️ AI 어시스턴트 · {msg["time"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="chat-bot">{msg["content"]}</div>', unsafe_allow_html=True)


def load_csv(path):
    if path.exists():
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.DataFrame()


def make_bar_chart(series, title=""):
    """plotly 가로 글씨 바 차트"""
    df = series.reset_index()
    df.columns = ["label", "count"]
    fig = px.bar(df, x="label", y="count", color_discrete_sequence=["#0057b8"])
    fig.update_layout(
        xaxis=dict(tickangle=0),
        xaxis_title="", yaxis_title="건수",
        margin=dict(t=20, b=40), height=300
    )
    return fig


# ==========================================
# 사이드바
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ 삼성화재 AI")
    st.markdown("---")
    mode = st.radio("모드 선택", ["👤 고객 상담", "🔐 관리자"], key="mode_radio", horizontal=True)
    st.session_state["mode"] = "admin" if "관리자" in mode else "user"
    st.markdown("---")

    if st.session_state["mode"] == "user":
        if not st.session_state["logged_in"]:
            st.markdown("### 로그인")
            cid = st.text_input("고객 ID", placeholder="CUST-0001", key="input_cid")
            pwd = st.text_input("비밀번호", type="password", placeholder="****", key="input_pwd")
            if st.button("로그인", key="btn_login"):
                if cid and pwd:
                    info = agents["login"](cid, pwd)
                    if info:
                        st.session_state["logged_in"]     = True
                        st.session_state["customer_info"] = info
                        add_message("bot", f"안녕하세요, {info['name']}님! 😊\n삼성화재 AI 어시스턴트입니다.\n보험 관련 궁금한 점을 편하게 말씀해 주세요.")
                        st.rerun()
                    else:
                        st.error("ID 또는 비밀번호를 확인해주세요.")
                else:
                    st.warning("ID와 비밀번호를 입력해주세요.")
        else:
            info = st.session_state["customer_info"]
            st.markdown(f"### 👤 {info['name']}님")
            st.markdown("---")
            st.markdown("**📋 가입 보험**")
            for p in info["policies"]:
                years = datetime.now().year - int(p["joined_year"])
                st.markdown(f"""
<div class="policy-card">
  <p>🔵 <b>{p['product_name']}</b></p>
  <p>📅 {p['joined_year']}년 가입 ({years}년차)</p>
  <p>💰 한도: {p['coverage_limit']}</p>
  <p>➕ {p['riders']}</p>
</div>
""", unsafe_allow_html=True)
            st.markdown("---")
            if st.button("로그아웃", key="btn_logout"):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
    else:
        if not st.session_state["admin_logged_in"]:
            st.markdown("### 관리자 로그인")
            aid = st.text_input("관리자 ID", key="admin_id")
            apw = st.text_input("비밀번호", type="password", key="admin_pw")
            if st.button("로그인", key="btn_admin_login"):
                if aid == ADMIN_ID and apw == ADMIN_PWD:
                    st.session_state["admin_logged_in"] = True
                    st.rerun()
                else:
                    st.error("ID 또는 비밀번호가 올바르지 않습니다.")
        else:
            st.markdown("### ✅ 관리자 모드")
            st.markdown("---")
            st.markdown("**📁 데이터 상태**")
            st.markdown(f"- audit_log: {'✅' if AUDIT_LOG.exists() else '❌'}")
            st.markdown(f"- complaint_db: {'✅' if COMPLAINT_DB.exists() else '❌'}")
            st.markdown(f"- handoff_db: {'✅' if HANDOFF_DB.exists() else '❌'}")
            st.markdown("---")
            st.markdown("**📅 날짜 필터**")
            date_from = st.date_input("시작일", value=datetime.now().date() - timedelta(days=7))
            date_to   = st.date_input("종료일", value=datetime.now().date())
            st.markdown("---")
            if st.button("로그아웃", key="btn_admin_logout"):
                st.session_state["admin_logged_in"] = False
                st.rerun()


# ==========================================
# 메인 콘텐츠
# ==========================================
if st.session_state["mode"] == "user":
    if not st.session_state["logged_in"]:
        st.markdown("""
        <div style="text-align:center; padding:80px 0;">
            <div style="font-size:4rem;">🛡️</div>
            <h1 style="color:#0057b8; font-weight:700; margin:16px 0 8px;">삼성화재 AI 어시스턴트</h1>
            <p style="color:#666; font-size:1.1rem;">보험 약관 조회부터 청구까지, AI가 도와드립니다.</p>
            <br><br>
            <p style="color:#999;">← 왼쪽에서 로그인해주세요</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        tab_chat, tab_claim = st.tabs(["💬 채팅 상담", "📋 보험금 청구"])

        with tab_chat:
            st.markdown("### 💬 AI 보험 상담")

            # 고정 높이 채팅창
            chat_box = st.container(height=500)
            with chat_box:
                render_chat()

            # 마지막 메시지가 user면 답변 생성
            if (st.session_state["chat_history"] and
                    st.session_state["chat_history"][-1]["role"] == "user"):
                last_query = st.session_state["chat_history"][-1]["content"]
                with st.spinner("🤔 답변 생성 중..."):
                    response = execute(last_query)
                add_message("bot", response)
                st.rerun()

            st.markdown("---")

            with st.form(key="chat_form", clear_on_submit=True):
                col_input, col_btn = st.columns([5, 1])
                with col_input:
                    user_input = st.text_input(
                        "질문 입력",
                        placeholder="보험 관련 질문을 입력하세요...",
                        label_visibility="collapsed",
                    )
                with col_btn:
                    submitted = st.form_submit_button("전송", use_container_width=True)

            if submitted and user_input.strip():
                add_message("user", user_input.strip())
                st.rerun()

            if st.session_state.get("claim_step") == "waiting_docs":
                st.markdown("---")
                st.markdown("#### 📎 서류 첨부")
                st.info("청구 서류를 이미지로 첨부해주세요. (JPG, PNG, PDF)")
                uploaded_files = st.file_uploader(
                    "서류 이미지 업로드",
                    type=["jpg", "jpeg", "png", "pdf"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key="doc_uploader"
                )
                if uploaded_files:
                    cols = st.columns(min(len(uploaded_files), 4))
                    for i, f in enumerate(uploaded_files):
                        with cols[i % 4]:
                            if f.type.startswith("image"):
                                st.image(f, caption=f.name, use_container_width=True)
                            else:
                                st.markdown(f"📄 {f.name}")
                    if st.button("📤 서류 제출 및 검증", key="btn_submit_docs"):
                        with tempfile.TemporaryDirectory() as tmpdir:
                            tmp_paths = []
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

        with tab_claim:
            st.markdown("### 📋 보험금 청구")
            info = st.session_state["customer_info"]
            domain_map = {"P-C": ("자동차보험", "auto"), "P-B": ("암보험", "cancer"), "P-D": ("치아보험", "teeth")}
            options = {}
            for p in info["policies"]:
                if p["product_id"] in domain_map:
                    label, domain = domain_map[p["product_id"]]
                    options[label] = domain
            if not options:
                st.warning("청구 가능한 보험이 없습니다.")
            else:
                selected_label  = st.selectbox("청구할 보험 선택", list(options.keys()), key="claim_select")
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
                    cols = st.columns(min(len(uploaded), 4))
                    for i, f in enumerate(uploaded):
                        with cols[i % 4]:
                            if f.type.startswith("image"):
                                st.image(f, caption=f.name, use_container_width=True)
                            else:
                                st.markdown(f"📄 {f.name}")
                if st.button("📤 청구 접수하기", disabled=not uploaded, key="btn_claim"):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_paths = []
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
                    if "✅" in result:
                        st.success(result)
                    elif "⚠️" in result:
                        st.warning(result)
                    else:
                        st.info(result)
                    add_message("bot", f"[청구 탭] {result}")


else:
    if not st.session_state["admin_logged_in"]:
        st.markdown("""
        <div style="text-align:center; padding:80px 0;">
            <div style="font-size:4rem;">🔐</div>
            <h1 style="color:#1a1a2e; font-weight:700;">관리자 대시보드</h1>
            <p style="color:#666;">← 왼쪽에서 관리자 로그인해주세요</p>
            <p style="color:#999; font-size:0.9rem;">ID: admin / PW: 1234</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        def filter_by_date(df, col="timestamp"):
            if df.empty or col not in df.columns:
                return df
            df[col] = pd.to_datetime(df[col])
            return df[(df[col].dt.date >= date_from) & (df[col].dt.date <= date_to)]

        audit_df     = filter_by_date(load_csv(AUDIT_LOG))
        complaint_df = filter_by_date(load_csv(COMPLAINT_DB))
        handoff_df   = filter_by_date(load_csv(HANDOFF_DB))
        customer_df  = load_csv(CUSTOMER_DB)

        tab_ov, tab_log, tab_comp, tab_hand, tab_cust = st.tabs([
            "📊 전체 현황", "📋 대화 로그", "🚨 민원 관리", "👤 이관 현황", "👥 고객 현황"
        ])

        with tab_ov:
            st.markdown("### 📊 전체 현황")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1: st.metric("전체 상담", f"{len(audit_df)}건")
            with col2: st.metric("민원 접수", f"{len(complaint_df)}건")
            with col3: st.metric("상담원 이관", f"{len(handoff_df)}건")
            with col4:
                claim_count = len(audit_df[audit_df["claim_status"] != "-"]) if not audit_df.empty and "claim_status" in audit_df.columns else 0
                st.metric("청구 접수", f"{claim_count}건")
            with col5:
                rate = round(len(complaint_df) / len(audit_df) * 100, 1) if len(audit_df) > 0 else 0
                st.metric("민원 발생률", f"{rate}%")

            st.markdown("---")
            if not audit_df.empty and "intent" in audit_df.columns:
                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown("#### 📌 Intent 분포")
                    st.plotly_chart(
                        make_bar_chart(audit_df["intent"].value_counts()),
                        use_container_width=True
                    )
                with col_r:
                    st.markdown("#### 📌 도메인 분포")
                    if "domains" in audit_df.columns:
                        domain_counts = {}
                        for d in audit_df["domains"].dropna():
                            for item in str(d).split(","):
                                item = item.strip()
                                if item and item != "-":
                                    domain_counts[item] = domain_counts.get(item, 0) + 1
                        if domain_counts:
                            st.plotly_chart(
                                make_bar_chart(pd.Series(domain_counts)),
                                use_container_width=True
                            )

            st.markdown("---")
            st.markdown("#### 🕐 최근 상담 10건")
            if not audit_df.empty:
                for _, row in audit_df.sort_values("timestamp", ascending=False).head(10).iterrows():
                    is_c = str(row.get("is_complaint","")).lower() == "true"
                    is_h = str(row.get("is_handoff","")).lower() == "true"
                    if is_h:
                        rc, badge = "handoff",   '<span class="badge badge-handoff">이관</span>'
                    elif is_c:
                        rc, badge = "complaint", '<span class="badge badge-complaint">민원</span>'
                    elif str(row.get("claim_status","-")) != "-":
                        rc, badge = "claim",     '<span class="badge badge-claim">청구</span>'
                    else:
                        rc, badge = "normal",    '<span class="badge badge-normal">정상</span>'
                    intent_badge = f'<span class="badge badge-intent">{row.get("intent","-")}</span>'
                    st.markdown(f"""
<div class="log-row {rc}">
    <b>{row.get('customer_name','-')}</b> ({row.get('customer_id','-')}) · {row.get('timestamp','-')} · {badge} · {intent_badge}
    <br><span style="color:#333;">"{row.get('query','-')}"</span>
    <br><span style="color:#999;font-size:0.82rem;">{row.get('answer_preview','-')}</span>
</div>""", unsafe_allow_html=True)
            else:
                st.info("기록된 상담 데이터가 없습니다.")

        with tab_log:
            st.markdown("### 📋 전체 대화 로그")
            if audit_df.empty:
                st.info("기록된 대화 로그가 없습니다.")
            else:
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    intent_filter = st.selectbox("Intent 필터", ["전체"] + list(audit_df["intent"].dropna().unique()))
                with col_f2:
                    complaint_filter = st.selectbox("민원 여부", ["전체", "민원만", "정상만"])
                with col_f3:
                    customer_filter = st.text_input("고객 ID 검색")
                filtered = audit_df.copy()
                if intent_filter != "전체":
                    filtered = filtered[filtered["intent"] == intent_filter]
                if complaint_filter == "민원만":
                    filtered = filtered[filtered["is_complaint"] == True]
                elif complaint_filter == "정상만":
                    filtered = filtered[filtered["is_complaint"] != True]
                if customer_filter:
                    filtered = filtered[filtered["customer_id"].str.contains(customer_filter, na=False)]
                st.markdown(f"**총 {len(filtered)}건**")
                display_cols = [c for c in ["timestamp","customer_name","customer_id","intent","domains","query","answer_preview","is_complaint","is_handoff"] if c in filtered.columns]
                st.dataframe(filtered[display_cols].sort_values("timestamp", ascending=False), use_container_width=True, height=500)
                st.download_button(
                    "📥 CSV 다운로드",
                    data=filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name=f"audit_log_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

        with tab_comp:
            st.markdown("### 🚨 민원 관리")
            if complaint_df.empty:
                st.info("접수된 민원이 없습니다.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("전체 민원", len(complaint_df))
                with col2: st.metric("처리 대기", len(complaint_df[complaint_df["status"]=="접수"]) if "status" in complaint_df.columns else 0)
                with col3:
                    avg = round(complaint_df["sentiment_score"].mean(),1) if "sentiment_score" in complaint_df.columns else "-"
                    st.metric("평균 감정 점수", f"{avg} / 10")
                st.markdown("---")
                for _, row in complaint_df.sort_values("timestamp", ascending=False).iterrows():
                    score = row.get("sentiment_score", 5)
                    badge = (
                        '<span class="badge badge-handoff">매우불만</span>' if score <= 3 else
                        '<span class="badge badge-complaint">불만</span>'   if score <= 5 else
                        '<span class="badge badge-normal">보통</span>'
                    )
                    st.markdown(f"""
<div class="log-row complaint">
    <b>{row.get('complaint_id','-')}</b> · {row.get('timestamp','-')} · {badge}
    <br><b>{row.get('customer_name','-')}</b> ({row.get('customer_id','-')}) | 유형: {row.get('complaint_type','-')} | 상태: {row.get('status','-')}
    <br><span style="color:#333;">"{row.get('customer_query','-')}"</span>
</div>""", unsafe_allow_html=True)

        with tab_hand:
            st.markdown("### 👤 상담원 이관 현황")
            if handoff_df.empty:
                st.info("이관된 케이스가 없습니다.")
            else:
                col1, col2 = st.columns(2)
                with col1: st.metric("전체 이관", len(handoff_df))
                with col2: st.metric("처리 대기", len(handoff_df[handoff_df["status"]=="이관대기"]) if "status" in handoff_df.columns else 0)
                st.markdown("---")
                for _, row in handoff_df.sort_values("timestamp", ascending=False).iterrows():
                    st.markdown(f"""
<div class="log-row handoff">
    <b>{row.get('handoff_id','-')}</b> · {row.get('timestamp','-')}
    <br><b>{row.get('customer_name','-')}</b> ({row.get('customer_id','-')}) | 상태: {row.get('status','-')}
    <br>⚠️ 사유: {row.get('reason','-')}
    <br><span style="color:#333;">"{row.get('query','-')}"</span>
</div>""", unsafe_allow_html=True)

        with tab_cust:
            st.markdown("### 👥 고객 현황")
            if customer_df.empty:
                st.info("고객 데이터가 없습니다.")
            else:
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("전체 고객", customer_df["customer_id"].nunique() if "customer_id" in customer_df.columns else 0)
                with col2: st.metric("전체 계약", len(customer_df))
                with col3:
                    if "product_name" in customer_df.columns:
                        st.metric("최다 가입 상품", customer_df["product_name"].value_counts().index[0])
                st.markdown("---")
                if "product_name" in customer_df.columns:
                    st.markdown("#### 📌 상품별 가입 현황")
                    st.plotly_chart(
                        make_bar_chart(customer_df["product_name"].value_counts()),
                        use_container_width=True
                    )
                st.markdown("---")
                display_df = customer_df.drop(columns=[c for c in ["password"] if c in customer_df.columns])
                st.dataframe(display_df, use_container_width=True, height=400)