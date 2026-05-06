from __future__ import annotations

import os
from pathlib import Path
import logging
import re
import uuid
from typing import Any
import sys

# Transformers가 Keras 3/TensorFlow 경로를 타지 않도록 강제 (PyTorch 임베딩 사용)
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
# Streamlit Cloud에서 Chroma/opentelemetry가 오래된 protobuf descriptor를 불러올 때
# C++ protobuf 구현과 충돌하지 않도록 import 전에 pure-python 구현을 사용한다.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import streamlit as st
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

try:
    from app.core.formatting import as_list, format_file_size, mask_customer_id, mask_display_value
    from app.pipeline import run_multi_agent_pipeline
    from app.pipeline.errors import to_user_friendly_error
    from app.services.agent_handoff_service import build_agent_handoff_summary
    from app.services.dashboard_service import compute_dashboard_metrics, human_review_queue
    from app.services.customer_service import (
        authenticate_customer,
        build_customer_context,
        find_demo_accounts,
        load_customers,
        select_relevant_policy,
    )
    from app.services.human_review_service import assess_human_review_need
    from app.services.ticket_service import (
        build_ticket_record,
        create_mock_tickets_if_empty,
        load_ticket_detail,
        load_ticket_index,
        save_ticket,
    )
    from app.services.upload_service import UploadValidationError, create_upload_session_dir, save_uploaded_file
except ModuleNotFoundError:
    # Allow `streamlit run main.py` from inside `app/` directory.
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from app.core.formatting import as_list, format_file_size, mask_customer_id, mask_display_value
    from app.pipeline import run_multi_agent_pipeline
    from app.pipeline.errors import to_user_friendly_error
    from app.services.agent_handoff_service import build_agent_handoff_summary
    from app.services.dashboard_service import compute_dashboard_metrics, human_review_queue
    from app.services.customer_service import (
        authenticate_customer,
        build_customer_context,
        find_demo_accounts,
        load_customers,
        select_relevant_policy,
    )
    from app.services.human_review_service import assess_human_review_need
    from app.services.ticket_service import (
        build_ticket_record,
        create_mock_tickets_if_empty,
        load_ticket_detail,
        load_ticket_index,
        save_ticket,
    )
    from app.services.upload_service import UploadValidationError, create_upload_session_dir, save_uploaded_file

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_DIR = PROJECT_ROOT / "data" / "vectorstore" / "insurance_chroma_db"
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads" / "chat_files"
ASSISTANT_AVATAR = BASE_DIR / "assets" / "samsung_fire_avatar.svg"
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_KEY_FILE = PROJECT_ROOT / "config" / "OpenAI api.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


st.set_page_config(page_title="보험 약관 AI 챗봇", layout="wide")
st.markdown(
    """
<style>
:root {
  --sf-blue: #0057b8;
  --sf-navy: #0a2d5e;
  --sf-light: #f3f7fc;
  --sf-border: #d8e3f2;
  --sf-user: #dcecff;
  --sf-assistant: #ffffff;
  --sf-accent: #e53935;
}

.stApp {
  background: linear-gradient(180deg, #f7fbff 0%, #eef4fb 100%);
  color: #111111;
}

.main .block-container {
  max-width: 980px;
  padding-top: 1.2rem;
  padding-bottom: 2.4rem;
}

.sf-hero {
  background: linear-gradient(135deg, var(--sf-navy), var(--sf-blue));
  color: #fff;
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 14px;
  box-shadow: 0 10px 24px rgba(0, 48, 110, 0.16);
}

.sf-hero h1 {
  margin: 0;
  font-size: 1.7rem;
  letter-spacing: -0.2px;
}

.sf-hero p {
  margin: 8px 0 0;
  opacity: 0.95;
}

.sf-note {
  color: #4f6178;
  font-size: 0.92rem;
  margin-bottom: 10px;
}

[data-testid="stChatMessage"] {
  border: 1px solid var(--sf-border);
  border-radius: 14px;
  padding: 8px 10px;
  margin-bottom: 8px;
  color: #111111;
  width: auto;
  max-width: 100%;
  min-width: 160px;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: var(--sf-user);
  margin-left: auto;
  margin-right: 0;
  flex-direction: row-reverse;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
  background: var(--sf-assistant);
  margin-left: 0;
  margin-right: auto;
}

[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] div {
  color: #111111 !important;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
  text-align: left;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stImage"] {
  margin-left: auto;
}

[data-testid="chatAvatarIcon-user"] {
  display: none;
}

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageAvatar"] {
  display: none;
}

@media (max-width: 720px) {
  [data-testid="stChatMessage"] {
    min-width: 0;
  }
}

[data-testid="stChatInput"] {
  background: #fff;
  border: 1px solid var(--sf-border);
  border-radius: 14px;
  box-shadow: 0 6px 18px rgba(0, 40, 90, 0.06);
}

.stButton button {
  background: var(--sf-blue);
  color: #fff;
  border: 0;
}

.stButton button:hover {
  background: #00499b;
  color: #fff;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="sf-hero">
  <h1>삼성화재 보험 약관 AI 챗봇</h1>
  <p>사고 상황과 청구 서류를 함께 확인해드리는 AI 안내 도우미</p>
</div>
""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sf-note">사고 상황을 편하게 적어주시면 관련 약관, 사례, 필요 서류를 차근차근 확인해드립니다.</div>',
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def load_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    return Chroma(
        persist_directory=str(DB_DIR),
        embedding_function=embeddings,
    )


def _read_openai_api_key() -> str:
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
        if secret_key:
            return secret_key
    except Exception:
        pass
    if os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_API_KEY", "")
    if OPENAI_KEY_FILE.exists():
        return OPENAI_KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


@st.cache_resource(show_spinner=False)
def build_llm(*, api_key: str):
    if not api_key:
        raise RuntimeError(
            "OpenAI API 키를 찾을 수 없습니다. `OPENAI_API_KEY` 환경변수 또는 Streamlit secrets에 설정하세요."
        )
    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=api_key,
        temperature=0.1,
    )


if not DB_DIR.exists():
    st.error("내부 약관 DB를 찾을 수 없습니다. 현재 약관 검색 기능을 사용할 수 없습니다.")
    with st.expander("개발자 확인용 상세 오류"):
        st.code(f"Vector DB folder not found: {DB_DIR}")
    st.stop()

api_key = _read_openai_api_key()
llm = None

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "안녕하세요. 사고 상황이나 청구하실 내용을 편하게 적어주세요. 필요한 약관과 서류 기준을 함께 확인해드릴게요.",
        }
    ]

if "chat_sessions" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chat_sessions = {
        first_id: {
            "title": "새 대화 1",
            "messages": st.session_state.messages.copy(),
        }
    }
    st.session_state.current_chat_id = first_id

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = next(iter(st.session_state.chat_sessions.keys()))

if "upload_session_ids" not in st.session_state:
    st.session_state.upload_session_ids = {}

if "ticket_keys" not in st.session_state:
    st.session_state.ticket_keys = {}

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def _default_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "assistant",
            "content": "안녕하세요. 사고 상황이나 청구하실 내용을 편하게 적어주세요. 필요한 약관과 서류 기준을 함께 확인해드릴게요.",
        }
    ]


def _sync_current_session_messages() -> None:
    current_id = st.session_state.current_chat_id
    st.session_state.chat_sessions[current_id]["messages"] = st.session_state.messages.copy()


def infer_doc_type(name: str) -> str:
    lowered = name.lower()
    if "영수증" in name or "receipt" in lowered:
        return "receipt"
    if "진단서" in name or "medical" in lowered:
        return "medical_statement"
    if "세부내역" in name or "detail" in lowered:
        return "treatment_detail"
    if "병리" in name or "pathology" in lowered:
        return "pathology_report"
    if "사고사실" in name or "accident" in lowered:
        return "accident_report"
    if "차량등록" in name or "registration" in lowered:
        return "vehicle_registration"
    if "견적" in name or "estimate" in lowered:
        return "estimate"
    if lowered.endswith(".pdf"):
        return "pdf"
    return "misc"


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name).strip("._")
    return safe or "uploaded_file"


def _save_chat_file(uploaded_file: Any, *, chat_id: str) -> dict[str, Any]:
    content_bytes = uploaded_file.getvalue()
    file_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
    session_dir = UPLOAD_DIR / chat_id
    session_dir.mkdir(parents=True, exist_ok=True)
    saved_path = session_dir / f"{file_id}_{_safe_filename(uploaded_file.name)}"
    saved_path.write_bytes(content_bytes)
    return {
        "doc_id": file_id,
        "doc_name": uploaded_file.name,
        "doc_type": infer_doc_type(uploaded_file.name),
        "size_bytes": len(content_bytes),
        "mime_type": getattr(uploaded_file, "type", "") or "",
        "storage_path": str(saved_path),
        "content_bytes": content_bytes,
    }


def _get_upload_session_id(*, customer_id: str, chat_id: str) -> str:
    key = f"{customer_id}:{chat_id}"
    if key not in st.session_state.upload_session_ids:
        session_info = create_upload_session_dir(customer_id)
        st.session_state.upload_session_ids[key] = session_info["session_id"]
    return st.session_state.upload_session_ids[key]


def _message_attachment(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": doc.get("doc_id"),
        "name": doc.get("doc_name"),
        "doc_type": doc.get("doc_type"),
        "size_bytes": doc.get("size_bytes"),
        "mime_type": doc.get("mime_type", ""),
        "path": doc.get("storage_path"),
    }


def _format_file_size(size_bytes: int | None) -> str:
    return format_file_size(size_bytes)


def _is_image_attachment(attachment: dict[str, Any]) -> bool:
    mime_type = str(attachment.get("mime_type", ""))
    name = str(attachment.get("name", "")).lower()
    return mime_type.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp"))


def _render_attachments(attachments: list[dict[str, Any]] | None) -> None:
    for attachment in attachments or []:
        path = Path(str(attachment.get("path", "")))
        name = str(attachment.get("name") or "첨부파일")
        size = _format_file_size(attachment.get("size_bytes"))
        if _is_image_attachment(attachment) and path.exists():
            st.image(str(path), caption=f"{name} ({size})", width=260)
        else:
            st.markdown(f"📎 **{name}** · {size}")


def _as_list(value: Any) -> list[Any]:
    return as_list(value)


def _render_bullets(items: list[Any], empty_text: str = "없음") -> None:
    values = [str(item) for item in items if str(item)]
    if not values:
        st.markdown(f"- {empty_text}")
        return
    for item in values:
        st.markdown(f"- {item}")


def _requested_report_sections(question: str) -> list[str]:
    text = str(question or "")
    sections: list[str] = []
    if any(token in text for token in ("전체 리포트", "상세 리포트", "진단 리포트 전체")):
        return ["assessment", "customer", "incident", "next_actions", "evidence", "checklist", "readiness"]
    if any(token in text for token in ("가입 정보", "가입정보", "내 보험", "가입상품", "증권번호", "특약", "담보한도")):
        sections.append("customer")
    if any(token in text for token in ("사고 요약", "상황 요약", "사고유형", "사고 유형")):
        sections.append("incident")
    if any(token in text for token in ("가능성 진단", "보상 가능성 진단", "1차 판단", "판단만")):
        sections.append("assessment")
    if any(token in text for token in ("약관 근거", "근거 카드", "근거 보여", "조항", "약관 원문", "출처", "판례", "분쟁 사례")):
        sections.append("evidence")
    if any(token in text for token in ("필요서류", "필요 서류", "청구서류", "청구 서류", "서류 체크", "체크리스트", "뭐가 필요", "무슨 서류")):
        sections.append("checklist")
    if any(token in text for token in ("준비율", "준비도", "몇 퍼센트", "몇프로", "몇 프로")):
        sections.append("readiness")
    if any(token in text for token in ("다음 행동", "다음 단계", "뭘 하면", "어떻게 하면", "절차")):
        sections.append("next_actions")
    return list(dict.fromkeys(sections))


def _render_requested_report_parts(
    diagnosis_result: dict[str, Any], requested_sections: list[str] | None = None
) -> None:
    sections = requested_sections or []
    if not sections:
        return

    customer = diagnosis_result.get("customer_summary") or {}
    incident = diagnosis_result.get("incident_summary") or {}
    assessment = diagnosis_result.get("coverage_assessment") or {}
    checklist = diagnosis_result.get("claim_checklist") or {}
    evidence_cards = _as_list(diagnosis_result.get("evidence_cards"))
    readiness = int(checklist.get("readiness_percent") or 0)
    readiness = max(0, min(readiness, 100))

    st.markdown("---")
    st.markdown("#### 요청하신 추가 정보")

    if "assessment" in sections:
        st.markdown("**보상 가능성 진단**")
        st.markdown(f"- 상태: {assessment.get('label', '추가 확인 필요')}")
        st.markdown(f"- 요약: {assessment.get('summary', '현재 정보 기준으로 추가 확인이 필요합니다.')}")
        if assessment.get("missing_info"):
            st.markdown("- 추가 확인:")
            _render_bullets(_as_list(assessment.get("missing_info")), "현재 단계에서 별도 표시된 항목 없음")

    if "customer" in sections:
        st.markdown("**고객 가입 정보**")
        st.markdown(f"- 고객 ID: `{customer.get('customer_id', '확인 필요')}`")
        st.markdown(f"- 가입 상품: {customer.get('product_name', '확인 필요')}")
        st.markdown(f"- 가입연도: {customer.get('joined_year', '확인 필요')}")
        st.markdown(f"- 증권번호: `{customer.get('policy_number', '확인 필요')}`")
        st.markdown(f"- 특약: {', '.join(_as_list(customer.get('riders'))) if customer.get('riders') else '확인 필요'}")
        st.markdown(f"- 담보한도: {customer.get('coverage_limit', '확인 필요')}")

    if "incident" in sections:
        st.markdown("**사고 상황 요약**")
        st.markdown(f"- 사고 유형: {incident.get('incident_type', '확인 필요')}")
        st.markdown(f"- 원인: {incident.get('cause', '확인 필요')}")
        st.markdown(f"- 대상: {incident.get('target', '확인 필요')}")
        st.markdown(f"- 진행 단계: {incident.get('stage', '확인 필요')}")

    if "next_actions" in sections:
        st.markdown("**다음 행동 안내**")
        _render_bullets(_as_list(diagnosis_result.get("next_actions")), "상담원 또는 담당자 확인을 요청해 주세요")

    if "evidence" in sections:
        st.markdown("**약관 근거**")
        if evidence_cards:
            for idx, card in enumerate(evidence_cards, start=1):
                with st.expander(f"근거 {idx}: {card.get('article_title') or card.get('article_number') or '약관 원문 기준'}"):
                    st.markdown(f"- 문서: {card.get('document_name', '확인 필요')}")
                    st.markdown(f"- 상품: {card.get('product_name', '확인 필요')}")
                    st.markdown(f"- 조항: {card.get('article_number', '확인 필요')}")
                    st.markdown(f"- 구분: {card.get('clause_type', '약관 원문 기준')}")
                    st.markdown("**약관 원문**")
                    st.markdown(card.get("source_text", "확인 필요"))
                    st.markdown("**AI 해석**")
                    st.markdown(card.get("ai_interpretation", "확인 필요"))
                    st.markdown("**고객 상황 적용**")
                    st.markdown(card.get("application_to_customer", "확인 필요"))
        else:
            st.info("현재 표시할 약관 근거가 없습니다. 사고 상황을 더 구체적으로 입력하면 근거를 다시 찾을 수 있습니다.")

    if "checklist" in sections:
        st.markdown("**청구 필요서류 체크리스트**")
        st.markdown("- 제출 완료:")
        _render_bullets(_as_list(checklist.get("submitted_docs")), "없음")
        st.markdown("- 추가 필요:")
        _render_bullets(_as_list(checklist.get("missing_docs")), "없음")
        st.markdown("- 상품 기준 필요 서류:")
        _render_bullets(_as_list(checklist.get("required_docs")), "확인 필요")

    if "readiness" in sections:
        st.markdown("**청구 서류 준비율**")
        st.progress(readiness / 100)
        st.caption(f"{readiness}% · {checklist.get('readiness_label', '청구 서류 준비 전')}")

    disclaimer = diagnosis_result.get("disclaimer")
    if disclaimer:
        st.caption(disclaimer)


def _mask_display_value(value: Any, *, kind: str = "") -> str:
    return mask_display_value(value, kind=kind)


def _render_uploaded_document_analysis(diagnosis_result: dict[str, Any]) -> None:
    uploaded = diagnosis_result.get("uploaded_documents") or {}
    files = _as_list(uploaded.get("files"))
    extractions = _as_list(uploaded.get("extraction_results"))
    comparison = uploaded.get("comparison_result") or {}
    missing_key_fields = _as_list(uploaded.get("missing_key_fields"))
    mismatches = _as_list(uploaded.get("mismatches"))
    if not files and not extractions:
        return

    st.markdown("---")
    st.markdown("#### 업로드 서류 분석 결과")

    st.markdown("**처리 상태**")
    if files:
        for file_info in files:
            name = file_info.get("file_name") or "첨부파일"
            status = file_info.get("processing_status") or "saved"
            guess = file_info.get("doc_type_guess") or "확인 필요"
            st.markdown(f"- {name}: {status} · 추정 유형: {guess}")
    else:
        st.markdown("- 업로드 파일 없음")

    satisfied = _as_list(comparison.get("satisfied_groups"))
    missing_groups = _as_list(comparison.get("missing_groups"))
    st.markdown("**제출 완료 서류**")
    if satisfied:
        for item in satisfied:
            st.markdown(f"- {item.get('matched_doc_type', '확인 필요')} ({item.get('file_name', '파일명 확인 필요')})")
    else:
        _render_bullets(_as_list(comparison.get("submitted_docs")), "없음")

    st.markdown("**추가 필요 서류**")
    if missing_groups:
        for item in missing_groups:
            any_of = ", ".join(_as_list(item.get("any_of")))
            st.markdown(f"- {item.get('label', any_of or '확인 필요')}: {item.get('reason', '청구 심사에 필요할 수 있습니다.')}")
    else:
        st.markdown("- 없음")

    if extractions:
        st.markdown("**서류별 추출 정보**")
        for result in extractions:
            title = f"{result.get('file_name', '첨부파일')} · {result.get('doc_type', '기타/판별불가')}"
            with st.expander(title):
                fields = result.get("extracted_fields") or {}
                st.markdown(f"- 신뢰도: {float(result.get('confidence') or 0):.2f}")
                st.markdown(f"- 발급기관: {result.get('issuer') or fields.get('hospital_name') or fields.get('repair_shop') or '확인 필요'}")
                st.markdown(f"- 일자: {result.get('issue_date') or result.get('date_of_service') or fields.get('treatment_date') or fields.get('accident_date') or '확인 필요'}")
                st.markdown(f"- 금액: {result.get('amount') or fields.get('total_amount') or fields.get('repair_amount') or '확인 필요'}")
                if fields.get("patient_name"):
                    st.markdown(f"- 환자명: {_mask_display_value(fields.get('patient_name'), kind='name')}")
                if fields.get("vehicle_number"):
                    st.markdown(f"- 차량번호: {_mask_display_value(fields.get('vehicle_number'), kind='vehicle')}")
                if result.get("raw_text_summary"):
                    st.caption(str(result.get("raw_text_summary"))[:240])
                for warning in _as_list(result.get("warnings")):
                    st.warning(str(warning))

    needs_review_docs = _as_list(comparison.get("needs_review_docs"))
    missing_fields = [item for item in missing_key_fields if item.get("status") == "missing"]
    if needs_review_docs or missing_fields:
        st.markdown("**확인 필요 정보**")
        for item in needs_review_docs:
            st.warning(f"{item.get('file_name', '첨부파일')}: {item.get('reason', '확인이 필요합니다.')}")
        for item in missing_fields:
            st.warning(item.get("message", "핵심 필드 확인이 필요합니다."))

    if mismatches:
        st.markdown("**고객 정보와 불일치 가능성**")
        for item in mismatches:
            st.warning(item.get("message", "고객 정보와 서류 정보 확인이 필요합니다."))

    readiness = int(comparison.get("readiness_percent") or diagnosis_result.get("claim_checklist", {}).get("readiness_percent") or 0)
    readiness = max(0, min(readiness, 100))
    st.markdown("**청구 서류 준비율**")
    st.progress(readiness / 100)
    st.caption(f"{readiness}% · {comparison.get('readiness_label') or diagnosis_result.get('claim_checklist', {}).get('readiness_label', '청구 서류 준비 전')}")


def _render_multi_policy_analysis(diagnosis_result: dict[str, Any]) -> None:
    analysis = diagnosis_result.get("multi_policy_analysis") or {}
    if not analysis.get("enabled"):
        return
    policy_results = _as_list(analysis.get("policy_results"))
    if not policy_results:
        return

    st.markdown("---")
    st.markdown("#### 복수 보험상품 검토 결과")
    st.caption(analysis.get("reason", "여러 가입상품을 함께 검토했습니다."))

    names = [str((item.get("policy") or {}).get("product_name") or "") for item in policy_results]
    if names:
        st.markdown("**검토 대상 상품**")
        _render_bullets([name for name in names if name], "확인 필요")

    for result in policy_results:
        policy = result.get("policy") or {}
        assessment = result.get("coverage_assessment") or {}
        checklist = result.get("claim_checklist") or {}
        evidence_cards = _as_list(result.get("evidence_cards"))
        readiness = int(checklist.get("readiness_percent") or 0)
        readiness = max(0, min(readiness, 100))
        title = result.get("section_title") or policy.get("product_name") or "가입상품 기준 검토"
        with st.expander(title):
            st.markdown(f"- 적용 상품: {policy.get('product_name', '확인 필요')}")
            st.markdown(f"- 판단: {assessment.get('label', '추가 확인 필요')}")
            st.markdown(f"- 요약: {assessment.get('summary', '현재 정보 기준으로 추가 확인이 필요합니다.')}")
            st.markdown("**필요서류**")
            _render_bullets(_as_list(checklist.get("required_docs") or checklist.get("missing_docs")), "확인 필요")
            st.markdown("**청구 서류 준비율**")
            st.progress(readiness / 100)
            st.caption(f"{readiness}% · {checklist.get('readiness_label', '청구 서류 준비 전')}")
            if evidence_cards:
                st.markdown("**약관 근거 카드**")
                for idx, card in enumerate(evidence_cards[:3], start=1):
                    st.markdown(
                        f"- 근거 {idx}: {card.get('document_name', '약관 원문')} / "
                        f"{card.get('article_number') or card.get('article_title') or '조항 확인 필요'}"
                    )
                    st.caption(str(card.get("source_text") or "")[:220])
            else:
                st.info("해당 상품 기준 근거를 충분히 찾지 못했습니다.")
            if result.get("cautions"):
                st.markdown("**주의사항**")
                _render_bullets(_as_list(result.get("cautions")), "없음")
            if result.get("next_actions"):
                st.markdown("**다음 행동**")
                _render_bullets(_as_list(result.get("next_actions")), "상담원 확인 요청")

    cautions = (analysis.get("combined_summary") or {}).get("cross_policy_cautions") or []
    if cautions:
        st.markdown("**함께 확인할 점**")
        _render_bullets(_as_list(cautions), "없음")


def _render_ticket_summary(ticket: dict[str, Any] | None, handoff: dict[str, Any] | None = None) -> None:
    if not ticket:
        return
    st.markdown("---")
    st.markdown("#### 상담원 전달 준비")
    st.markdown(f"**가상 접수번호:** `{ticket.get('ticket_id', '생성 실패')}`")
    st.markdown(f"**접수 상태:** {ticket.get('status_label', 'AI 사전진단 완료')}")
    st.markdown(f"**상담원 확인 필요 여부:** {'필요' if ticket.get('human_review_required') else '필요 낮음'}")
    st.markdown(f"**우선도:** {ticket.get('priority_label', '보통')}")
    reasons = ticket.get("human_review_reasons") or []
    if reasons:
        st.markdown("**추가 확인이 필요한 항목**")
        _render_bullets(reasons, "현재 표시된 항목 없음")
    st.markdown("**다음 단계:** 상담원이 아래 요약 내용을 바탕으로 이어서 확인할 수 있도록 접수 요약이 생성되었습니다.")
    st.caption("이 접수번호는 데모용 가상 접수번호이며 실제 보험사 접수번호가 아닙니다.")
    if handoff:
        with st.expander("상담원 전달 요약 보기"):
            _render_agent_handoff(handoff)


def _render_agent_handoff(handoff: dict[str, Any]) -> None:
    if not handoff:
        st.info("상담원 전달 요약이 아직 생성되지 않았습니다.")
        return
    st.caption(handoff.get("notice", "본 요약은 AI 사전진단 결과를 상담원이 이어서 확인할 수 있도록 정리한 참고 자료입니다."))
    info = handoff.get("ticket_info") or {}
    customer = handoff.get("customer_summary") or {}
    inquiry = handoff.get("inquiry_summary") or {}
    ai = handoff.get("ai_assessment") or {}
    docs = handoff.get("document_status") or {}
    review = handoff.get("human_review") or {}
    st.markdown(f"- 접수번호: `{info.get('ticket_id', '')}`")
    st.markdown(f"- 경로/상태/우선도: {info.get('route_label', '')} · {info.get('status_label', '')} · {info.get('priority_label', '')}")
    st.markdown(f"- 고객/상품: `{customer.get('customer_id', '')}` · {customer.get('product_name', '확인 필요')}")
    st.markdown(f"- 문의: {inquiry.get('original_question', '')}")
    st.markdown(f"- 사고유형/단계: {inquiry.get('incident_type', '')} · {inquiry.get('current_stage', '')}")
    st.markdown(f"- AI 판단: {ai.get('coverage_label', '추가 확인 필요')} · {ai.get('assessment_summary', '')}")
    st.markdown(f"- 제출 서류: {', '.join(docs.get('submitted_docs') or []) or '없음'}")
    st.markdown(f"- 누락 서류: {', '.join(docs.get('missing_docs') or []) or '없음'}")
    st.markdown(f"- 청구 서류 준비율: {docs.get('readiness_percent', 0)}%")
    if review.get("reasons"):
        st.markdown("**상담원 확인 사유**")
        _render_bullets(review.get("reasons"), "없음")
    if review.get("recommended_questions"):
        st.markdown("**고객에게 확인할 질문**")
        _render_bullets(review.get("recommended_questions"), "없음")
    multi = handoff.get("multi_policy_review") or {}
    if multi.get("enabled"):
        st.markdown("**복수 상품 검토 결과**")
        for item in _as_list(multi.get("policy_summaries")):
            st.markdown(
                f"- {item.get('product_name', '확인 필요')}: "
                f"{item.get('section_title', '상품 기준 검토')} / {item.get('coverage_label', '추가 확인 필요')}"
            )
        if multi.get("cross_policy_cautions"):
            st.markdown("**상품 간 확인 필요사항**")
            _render_bullets(_as_list(multi.get("cross_policy_cautions")), "없음")
    if handoff.get("recommended_next_steps"):
        st.markdown("**추천 후속 조치**")
        _render_bullets(handoff.get("recommended_next_steps"), "없음")


def _create_or_get_ticket(
    *,
    pipeline_state: dict[str, Any],
    diagnosis_result: dict[str, Any] | None,
    question: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    if not diagnosis_result:
        return None, None, None
    ticket_key = f"{pipeline_state.get('trace_id')}:{pipeline_state.get('user_id')}:{question}"
    existing_id = st.session_state.ticket_keys.get(ticket_key)
    if existing_id:
        detail = load_ticket_detail(existing_id)
        return detail or {"ticket_id": existing_id}, (detail or {}).get("agent_handoff_summary"), None
    try:
        route = pipeline_state.get("next_route") or "unknown"
        customer_info = pipeline_state.get("customer_db_info") or {}
        human_review = assess_human_review_need(route, diagnosis_result, customer_info)
        draft_state = dict(pipeline_state)
        ticket_preview = build_ticket_record(
            draft_state,
            diagnosis_result,
            customer_info,
            route,
            question,
            human_review,
            {},
        )
        draft_state["ticket_status"] = ticket_preview.get("status")
        handoff = build_agent_handoff_summary(
            ticket_preview["ticket_id"], draft_state, diagnosis_result, customer_info, human_review
        )
        ticket_record = build_ticket_record(
            draft_state,
            diagnosis_result,
            customer_info,
            route,
            question,
            human_review,
            handoff,
        )
        saved = save_ticket(ticket_record)
        st.session_state.ticket_keys[ticket_key] = saved["ticket_id"]
        return ticket_record, handoff, None
    except Exception as exc:
        logger.exception("Ticket creation failed")
        return None, None, f"접수 요약을 저장하는 중 문제가 발생했습니다. AI 진단 결과는 정상적으로 확인할 수 있습니다. ({exc})"


def _mask_customer_id(value: Any) -> str:
    return mask_customer_id(value)


def _render_distribution(title: str, data: dict[str, Any]) -> None:
    st.markdown(f"**{title}**")
    if not data:
        st.caption("표시할 데이터가 없습니다.")
        return
    rows = [{"구분": key, "건수": value} for key, value in data.items()]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_ticket_detail(ticket_id: str, index_fallback: dict[str, Any] | None = None) -> None:
    detail = load_ticket_detail(ticket_id) or index_fallback or {}
    if not detail:
        st.info("접수 상세 정보를 찾지 못했습니다.")
        return
    handoff = detail.get("agent_handoff_summary") or {}
    st.markdown(f"### 접수 상세: `{detail.get('ticket_id', ticket_id)}`")
    st.markdown(f"- 생성일시: {detail.get('created_at', '확인 필요')}")
    st.markdown(f"- 고객 ID: `{_mask_customer_id(detail.get('customer_id'))}`")
    st.markdown(f"- 가입 상품: {detail.get('product_name', '확인 필요')}")
    st.markdown(f"- 문의 유형: {detail.get('incident_type', '확인 필요')}")
    st.markdown(f"- 상태/우선도: {detail.get('status_label', '확인 필요')} · {detail.get('priority_label', '보통')}")
    summary = detail.get("summary") or {}
    if summary.get("question"):
        st.markdown(f"- 고객 질문: {summary.get('question')}")
    if summary.get("assessment_summary"):
        st.markdown(f"- AI 진단 요약: {summary.get('assessment_summary')}")
    st.markdown(f"- 제출 서류: {', '.join(detail.get('submitted_docs') or []) or '없음'}")
    st.markdown(f"- 누락 서류: {', '.join(detail.get('missing_docs') or []) or '없음'}")
    if detail.get("human_review_reasons"):
        st.markdown("**상담원 확인 사유**")
        _render_bullets(detail.get("human_review_reasons"), "없음")
    if handoff:
        _render_agent_handoff(handoff)
    with st.expander("개발자용 raw ticket JSON"):
        st.json(detail)


def _render_admin_dashboard() -> None:
    st.markdown("## 관리자 대시보드")
    st.caption("본 대시보드는 데모용 mock 운영 화면이며 실제 보험사 업무 시스템과 연동되어 있지 않습니다.")
    try:
        tickets = load_ticket_index()
    except Exception as exc:
        logger.exception("Dashboard ticket loading failed")
        st.error("관리자 대시보드 데이터를 불러오지 못했습니다. 접수 데이터 파일을 확인해 주세요.")
        with st.expander("개발자 확인용 상세 오류"):
            st.code(str(exc))
        return

    if not tickets:
        st.info("아직 생성된 접수 데이터가 없습니다.")
        if st.button("데모용 접수 데이터 생성"):
            create_mock_tickets_if_empty()
            st.rerun()
        return

    if st.button("데모용 접수 데이터 생성", help="접수 데이터가 비어 있을 때만 생성됩니다."):
        created = create_mock_tickets_if_empty()
        st.success(f"{len(created)}건 생성됨" if created else "이미 접수 데이터가 있어 새로 생성하지 않았습니다.")
        st.rerun()

    try:
        metrics = compute_dashboard_metrics(tickets)
    except Exception as exc:
        logger.exception("Dashboard metric calculation failed")
        st.error("관리자 대시보드 통계를 계산하지 못했습니다.")
        with st.expander("개발자 확인용 상세 오류"):
            st.code(str(exc))
        return

    cols = st.columns(4)
    cols[0].metric("전체 접수", metrics["total_tickets"])
    cols[1].metric("오늘 접수", metrics["today_tickets"])
    cols[2].metric("상담원 확인 필요", metrics["human_review_count"])
    cols[3].metric("평균 청구 서류 준비율", f"{metrics['avg_readiness_percent']}%")
    cols2 = st.columns(3)
    cols2[0].metric("AI 사전진단 완료", metrics["ai_reviewed_count"])
    cols2[1].metric("준비율 80% 이상", metrics["ready_count"])
    cols2[2].metric("민원성 문의", metrics["complaint_count"])

    d1, d2, d3 = st.columns(3)
    with d1:
        _render_distribution("문의 유형 분포", metrics["route_distribution"])
    with d2:
        _render_distribution("상품별 문의 분포", metrics["product_distribution"])
    with d3:
        _render_distribution("우선도별 상담 건수", metrics["priority_distribution"])

    st.markdown("### 자주 누락되는 서류 TOP 5")
    st.dataframe(metrics["top_missing_docs"], use_container_width=True, hide_index=True)

    st.markdown("### 상담원 확인 필요 큐")
    queue = human_review_queue(tickets)
    queue_rows = [
        {
            "접수번호": item.get("ticket_id"),
            "생성일시": item.get("created_at"),
            "고객ID": _mask_customer_id(item.get("customer_id")),
            "상품": item.get("product_name"),
            "관련상품": ", ".join(_as_list(item.get("involved_products"))) or item.get("product_name"),
            "문의유형": item.get("incident_type"),
            "route": item.get("route"),
            "상태": item.get("status_label"),
            "우선도": item.get("priority_label"),
            "준비율": f"{item.get('readiness_percent', 0)}%",
            "주요 사유": "; ".join((item.get("human_review_reasons") or [])[:2]),
        }
        for item in queue
    ]
    st.dataframe(queue_rows, use_container_width=True, hide_index=True)

    selectable = [item.get("ticket_id") for item in (queue or tickets) if item.get("ticket_id")]
    if selectable:
        selected = st.selectbox("접수 상세 보기", selectable)
        fallback = next((item for item in tickets if item.get("ticket_id") == selected), None)
        _render_ticket_detail(selected, fallback)


def _render_chat_message(message: dict[str, Any]) -> None:
    role = message.get("role", "assistant")
    if role == "user":
        _, message_col = st.columns([1.15, 2.85])
    else:
        message_col, _ = st.columns([2.85, 1.15])
    avatar = None if role == "user" else str(ASSISTANT_AVATAR)

    with message_col:
        with st.chat_message(role, avatar=avatar):
            if message.get("content"):
                st.markdown(message["content"])
            if role == "assistant" and message.get("diagnosis_result"):
                _render_multi_policy_analysis(message["diagnosis_result"])
                _render_uploaded_document_analysis(message["diagnosis_result"])
                _render_requested_report_parts(
                    message["diagnosis_result"],
                    message.get("requested_report_sections") or [],
                )
            if role == "assistant" and message.get("ticket_summary"):
                _render_ticket_summary(message.get("ticket_summary"), message.get("agent_handoff_summary"))
            _render_attachments(message.get("attachments"))


def _policy_label(policy: dict[str, Any]) -> str:
    riders = ", ".join(_as_list(policy.get("riders") or policy.get("special_clauses")))
    base = f"{policy.get('product_name', '상품 확인 필요')} / {policy.get('joined_year') or policy.get('join_year') or '연도 확인 필요'}"
    return f"{base} / 특약: {riders}" if riders else base


def _clear_auth_session() -> None:
    for key in (
        "authenticated",
        "customer_id",
        "customer_context",
        "customer_name",
        "active_customer_id",
        "debug_customer_id_override",
        "last_selected_policy",
    ):
        st.session_state.pop(key, None)
    st.session_state.authenticated = False
    st.session_state.messages = _default_messages()
    if "chat_sessions" in st.session_state and "current_chat_id" in st.session_state:
        st.session_state.chat_sessions[st.session_state.current_chat_id]["messages"] = st.session_state.messages.copy()


def _render_login_screen() -> None:
    st.markdown("## 삼성화재 보험 AI 상담 데모 로그인")
    st.info(
        "본 로그인은 공모전 데모를 위한 간편 인증입니다. 실제 서비스에서는 본인인증, 암호화, 접근권한 관리가 필요합니다."
    )

    demo_accounts: dict[str, str] = {}
    try:
        demo_accounts = find_demo_accounts(load_customers())
    except Exception as exc:
        logger.exception("Demo account loading failed")
        st.warning("고객 정보를 불러오는 중 문제가 발생했습니다. customers.csv 파일을 확인해 주세요.")
        with st.expander("개발자 확인용 상세 오류"):
            st.code(str(exc))

    with st.form("demo_login_form"):
        customer_id = st.text_input("고객 ID", value="CUST-0001").strip().upper()
        password = st.text_input("비밀번호", value="1234", type="password")
        submitted = st.form_submit_button("로그인", use_container_width=True)

    st.caption("데모 계정: CUST-0001 ~ CUST-0050 / 비밀번호: 1234")
    if demo_accounts:
        st.markdown(
            "- 자동차보험 예시: `{auto}` / 1234\n"
            "- 암보험 예시: `{cancer}` / 1234\n"
            "- 실손보험 예시: `{indemnity}` / 1234\n"
            "- 3개 상품 가입 예시: `{multi_policy}` / 1234".format(**demo_accounts)
        )

    if submitted:
        try:
            context = authenticate_customer(customer_id, password)
        except Exception as exc:
            logger.exception("Customer authentication failed")
            st.error("고객 정보를 불러오는 중 문제가 발생했습니다.")
            with st.expander("개발자 확인용 상세 오류"):
                st.code(str(exc))
            return
        if not context:
            st.error("고객 ID 또는 비밀번호가 올바르지 않습니다.")
            return
        if not context.get("policies"):
            st.error("가입상품 정보를 찾을 수 없습니다. 관리자에게 문의해 주세요.")
            return

        st.session_state.authenticated = True
        st.session_state.customer_id = context["customer_id"]
        st.session_state.customer_context = context
        st.session_state.customer_name = context.get("customer_name") or context["customer_id"]
        st.session_state.active_customer_id = context["customer_id"]
        st.session_state.last_selected_policy = None
        st.success("로그인되었습니다.")
        st.rerun()


def _render_logged_in_sidebar() -> str:
    context = st.session_state.get("customer_context") or {}
    customer_id = st.session_state.get("customer_id", "")
    st.markdown("### 로그인 정보")
    st.markdown(f"**{context.get('customer_name') or customer_id} 고객님**")
    st.caption(f"고객 ID: `{customer_id}`")

    policies = _as_list(context.get("policies"))
    st.markdown(f"**가입상품 {len(policies)}개**")
    for idx, policy in enumerate(policies, start=1):
        st.caption(f"{idx}. {_policy_label(policy)}")

    with st.expander("개발자 모드: 고객 ID override"):
        use_override = st.checkbox("로그인 고객 대신 다른 고객 ID 사용", value=False)
        override_id = st.text_input("디버그용 고객 ID", value=customer_id or "CUST-1029").strip().upper()
        st.caption("기존 고객 ID 직접 입력 방식은 개발/디버그용 fallback으로만 유지됩니다.")

    active_id = override_id if use_override and override_id else customer_id
    if use_override and override_id:
        try:
            override_context = build_customer_context(override_id)
            st.session_state.customer_context_override = override_context
            st.warning(f"현재 디버그용 고객 ID `{override_id}` 기준으로 실행됩니다.")
        except Exception as exc:
            logger.warning("Customer override failed: %s", override_id)
            st.session_state.customer_context_override = None
            st.warning("디버그용 고객 정보를 찾지 못했습니다. 로그인 고객 기준으로 실행합니다.")
            with st.expander("디버그 고객 조회 오류"):
                st.code(str(exc))
            active_id = customer_id
    else:
        st.session_state.customer_context_override = None

    st.session_state.active_customer_id = active_id
    selected = st.session_state.get("last_selected_policy")
    st.markdown("**현재 검토 상품**")
    if selected:
        relevant = _as_list(selected.get("relevant_policies"))
        if relevant:
            for idx, policy in enumerate(relevant, start=1):
                prefix = "주 처리" if idx == 1 else "함께 검토"
                st.caption(f"{idx}. {policy.get('product_name', '확인 필요')} · {prefix}")
        else:
            st.caption(f"{selected.get('product_name', '확인 필요')} · 최근 질문 기준 자동 선택")
    else:
        st.caption("가입상품 중 질문 내용에 맞는 상품이 하나 이상 자동 선택됩니다.")
    if st.button("로그아웃", use_container_width=True):
        _clear_auth_session()
        st.rerun()
    return active_id


if not st.session_state.get("authenticated"):
    _render_login_screen()
    st.stop()


with st.sidebar:
    mode = st.radio("화면 모드", ["고객 상담", "관리자 대시보드"], index=0)
    st.markdown("---")
    active_customer_id = _render_logged_in_sidebar()
    st.markdown("---")
    st.markdown("### 대화 목록")

    st.caption("서류는 채팅 입력창의 첨부 버튼으로 함께 보낼 수 있어요.")

    if st.button("새 대화", use_container_width=True):
        _sync_current_session_messages()
        new_id = str(uuid.uuid4())
        next_num = len(st.session_state.chat_sessions) + 1
        st.session_state.chat_sessions[new_id] = {
            "title": f"새 대화 {next_num}",
            "messages": _default_messages(),
        }
        st.session_state.current_chat_id = new_id
        st.session_state.messages = _default_messages()
        st.rerun()

    current_id = st.session_state.current_chat_id
    st.caption(f"현재 대화: {st.session_state.chat_sessions[current_id]['title']}")

    for chat_id, chat in list(st.session_state.chat_sessions.items())[::-1]:
        if chat_id == current_id:
            continue
        if st.button(chat["title"], key=f"chat_{chat_id}", use_container_width=True):
            _sync_current_session_messages()
            st.session_state.current_chat_id = chat_id
            st.session_state.messages = st.session_state.chat_sessions[chat_id]["messages"].copy()
            st.rerun()

    st.markdown("---")
    st.caption("삼성화재 안내 화면")

if mode == "관리자 대시보드":
    _render_admin_dashboard()
    st.stop()

try:
    llm = build_llm(api_key=api_key)
except RuntimeError as exc:
    logger.exception("LLM initialization failed")
    st.error(to_user_friendly_error(exc)["content"])
    st.info(
        "설정 예시:\n"
        "1) OpenAI API 키 발급\n"
        "2) 터미널에서 `export OPENAI_API_KEY=sk-...`\n"
        "3) 다시 `streamlit run app/main.py` 실행"
    )
    st.stop()

for msg in st.session_state.messages:
    _render_chat_message(msg)

chat_value = st.chat_input(
    "예: 태풍으로 차가 침수됐어요. 보상 가능성이 있을까요?",
    accept_file="multiple",
    file_type=["png", "jpg", "jpeg", "pdf", "txt"],
)

if chat_value:
    if isinstance(chat_value, str):
        question = chat_value
        attached_files = []
    else:
        question = (chat_value.text or "").strip()
        attached_files = list(chat_value.files or [])

    if not question and attached_files:
        question = "첨부한 서류를 확인해 주세요."

    current_chat_id = st.session_state.current_chat_id
    active_customer_id = st.session_state.get("active_customer_id") or st.session_state.get("customer_id")
    if not active_customer_id:
        st.warning("로그인 세션이 초기화되었습니다. 다시 로그인해 주세요.")
        _clear_auth_session()
        st.rerun()
    upload_session_id = _get_upload_session_id(customer_id=active_customer_id, chat_id=current_chat_id)
    user_docs = []
    upload_errors: list[str] = []
    for file in attached_files:
        try:
            user_docs.append(save_uploaded_file(file, customer_id=active_customer_id, session_id=upload_session_id))
        except UploadValidationError as exc:
            logger.warning("Upload validation failed: %s", getattr(file, "name", "unknown"))
            upload_errors.append(f"{getattr(file, 'name', 'unknown')}: {exc}")
        except Exception as exc:
            logger.exception("Failed to save uploaded file: %s", getattr(file, "name", "unknown"))
            upload_errors.append(
                f"{getattr(file, 'name', 'unknown')}: 업로드한 파일을 저장하는 중 문제가 발생했습니다. 파일 형식과 용량을 확인해 주세요."
            )
    attachments = [_message_attachment(doc) for doc in user_docs]

    st.session_state.messages.append(
        {"role": "user", "content": question, "attachments": attachments}
    )
    if st.session_state.chat_sessions[st.session_state.current_chat_id]["title"].startswith("새 대화"):
        st.session_state.chat_sessions[st.session_state.current_chat_id]["title"] = question[:20] + ("..." if len(question) > 20 else "")
    _render_chat_message({"role": "user", "content": question, "attachments": attachments})

    assistant_col, _ = st.columns([2.85, 1.15])
    with assistant_col:
        with st.chat_message("assistant", avatar=str(ASSISTANT_AVATAR)):
            with st.spinner("말씀해주신 내용과 서류를 확인하는 중입니다..."):
                upload_warning = ""
                if upload_errors:
                    upload_warning = to_user_friendly_error(
                        {
                            "error_code": "E_FILE_UPLOAD_FAILED",
                            "error_message": "; ".join(upload_errors),
                        }
                    )["content"]

                try:
                    if upload_errors and attached_files and not user_docs:
                        pipeline_state = {
                            "status": "ERROR",
                            "next_route": None,
                            "retry_count": 0,
                            "customer_db_info": None,
                            "draft_response": None,
                            "review_notes": [],
                            "citations": [],
                            "audit_log": [],
                            "error": {
                                "error_code": "E_FILE_UPLOAD_FAILED",
                                "error_message": "; ".join(upload_errors),
                                "failed_node": "FILE_UPLOAD",
                            },
                        }
                    else:
                        pipeline_state = run_multi_agent_pipeline(
                            user_id=active_customer_id,
                            user_query=question,
                            user_docs=user_docs,
                            vectorstore_factory=load_vectorstore,
                            llm=llm,
                        )
                        if pipeline_state.get("customer_db_info"):
                            st.session_state.last_selected_policy = pipeline_state["customer_db_info"]
                except Exception as exc:
                    logger.exception("Unhandled Streamlit pipeline call failed")
                    pipeline_state = {
                        "status": "ERROR",
                        "next_route": None,
                        "retry_count": 0,
                        "customer_db_info": None,
                        "draft_response": None,
                        "review_notes": [],
                        "citations": [],
                        "audit_log": [],
                        "error": {
                            "error_code": "E_PIPELINE_RUNTIME",
                            "error_message": str(exc),
                            "failed_node": "STREAMLIT_UI",
                        },
                    }

                diagnosis_result = None
                ticket_summary = None
                agent_handoff_summary = None
                ticket_error = None
                requested_report_sections = _requested_report_sections(question)
                if pipeline_state["status"] == "FINALIZED" and pipeline_state.get("final_response"):
                    answer = pipeline_state["final_response"]["content"]
                    diagnosis_result = pipeline_state["final_response"].get("diagnosis_result")
                    if upload_warning:
                        answer = f"{upload_warning}\n\n---\n\n{answer}"
                else:
                    answer = to_user_friendly_error(pipeline_state.get("error"))["content"]

                st.markdown(answer)
                if diagnosis_result:
                    ticket_summary, agent_handoff_summary, ticket_error = _create_or_get_ticket(
                        pipeline_state=pipeline_state,
                        diagnosis_result=diagnosis_result,
                        question=question,
                    )
                    _render_multi_policy_analysis(diagnosis_result)
                    _render_uploaded_document_analysis(diagnosis_result)
                    _render_requested_report_parts(diagnosis_result, requested_report_sections)
                    _render_ticket_summary(ticket_summary, agent_handoff_summary)
                    if ticket_error:
                        st.info("접수 요약을 저장하는 중 문제가 발생했습니다. AI 진단 결과는 정상적으로 확인할 수 있습니다.")

                with st.expander("확인 과정 보기"):
                    st.markdown(f"- 처리 상태: `{pipeline_state.get('status')}`")
                    st.markdown(f"- 확인한 업무 구분: `{pipeline_state.get('next_route')}`")
                    st.markdown(f"- 다시 확인한 횟수: `{pipeline_state.get('retry_count')}`")
                    st.markdown(f"- 가입 정보: `{pipeline_state.get('customer_db_info')}`")
                    if upload_errors:
                        st.markdown("**파일 처리 오류**")
                        st.code("\n".join(upload_errors))
                    if pipeline_state.get("error"):
                        friendly = to_user_friendly_error(pipeline_state.get("error"))
                        st.markdown(f"**오류 유형**: `{friendly['error_type']}`")
                        st.markdown(f"**오류 코드**: `{friendly['error_code']}`")
                        st.code(friendly.get("detail", "") or str(pipeline_state.get("error")))
                    if pipeline_state.get("draft_response"):
                        st.markdown("**답변 작성 내용**")
                        st.markdown(pipeline_state["draft_response"].get("content", ""))
                        if pipeline_state["draft_response"].get("diagnosis_result"):
                            st.markdown("**진단 리포트 원본**")
                            st.json(pipeline_state["draft_response"].get("diagnosis_result"))
                        if pipeline_state["draft_response"].get("debug"):
                            st.markdown("**RAG 디버그 정보**")
                            st.json(pipeline_state["draft_response"].get("debug"))
                    if pipeline_state.get("final_response", {}).get("diagnosis_result"):
                        st.markdown("**최종 진단 리포트 원본**")
                        st.json(pipeline_state["final_response"].get("diagnosis_result"))
                    if pipeline_state.get("review_notes"):
                        st.markdown(f"**추가 확인 메모**: `{pipeline_state['review_notes']}`")
                    if pipeline_state.get("citations"):
                        st.markdown(f"**확인한 근거**: `{pipeline_state['citations']}`")
                    if pipeline_state.get("audit_log"):
                        st.markdown("**처리 로그**")
                        st.json(pipeline_state.get("audit_log"))
                    if ticket_summary:
                        st.markdown("**가상 접수 요약**")
                        st.json(ticket_summary)
                    if agent_handoff_summary:
                        st.markdown("**상담원 전달 요약 원본**")
                        st.json(agent_handoff_summary)
                    if ticket_error:
                        st.markdown("**접수 저장 오류**")
                        st.code(ticket_error)

    assistant_message = {"role": "assistant", "content": answer}
    if diagnosis_result:
        assistant_message["diagnosis_result"] = diagnosis_result
        assistant_message["requested_report_sections"] = requested_report_sections
    if ticket_summary:
        assistant_message["ticket_summary"] = ticket_summary
    if agent_handoff_summary:
        assistant_message["agent_handoff_summary"] = agent_handoff_summary
    st.session_state.messages.append(assistant_message)
    _sync_current_session_messages()
