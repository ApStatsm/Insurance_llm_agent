from __future__ import annotations

import os
from pathlib import Path
import logging
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
    from app.pipeline import run_multi_agent_pipeline
    from app.pipeline.errors import to_user_friendly_error
    from app.services.agent_handoff_service import build_agent_handoff_summary
    from app.services.human_review_service import assess_human_review_need
    from app.services.ticket_service import (
        build_ticket_record,
        load_ticket_detail,
        save_ticket,
    )
    from app.services.upload_service import UploadValidationError, create_upload_session_dir, save_uploaded_file
except ModuleNotFoundError:
    # Allow `streamlit run main.py` from inside `app/` directory.
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from app.pipeline import run_multi_agent_pipeline
    from app.pipeline.errors import to_user_friendly_error
    from app.services.agent_handoff_service import build_agent_handoff_summary
    from app.services.human_review_service import assess_human_review_need
    from app.services.ticket_service import (
        build_ticket_record,
        load_ticket_detail,
        save_ticket,
    )
    from app.services.upload_service import UploadValidationError, create_upload_session_dir, save_uploaded_file

from app.ui.auth_views import clear_auth_session, render_logged_in_sidebar, render_login_screen
from app.ui.chat_views import (
    render_multi_policy_analysis,
    render_requested_report_parts,
    render_ticket_summary,
    render_uploaded_document_analysis,
    render_chat_message,
    requested_report_sections,
)
from app.ui.dashboard_view import render_admin_dashboard
from app.ui.styles import render_app_shell

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_DIR = PROJECT_ROOT / "data" / "vectorstore" / "insurance_chroma_db"
ASSISTANT_AVATAR = BASE_DIR / "assets" / "samsung_fire_avatar.svg"
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_KEY_FILE = PROJECT_ROOT / "config" / "OpenAI api.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


render_app_shell()

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


def _should_show_ticket_summary(
    *,
    question: str,
    route: str | None,
    diagnosis_result: dict[str, Any] | None,
    ticket_summary: dict[str, Any] | None,
) -> bool:
    if not ticket_summary:
        return False
    text = str(question or "")
    handoff_keywords = (
        "상담원",
        "사람 연결",
        "담당자",
        "연결해줘",
        "민원",
        "불만",
        "항의",
        "컴플레인",
        "소송",
        "금감원",
    )
    if route == "cs_complaint" or any(keyword in text for keyword in handoff_keywords):
        return True

    uploaded = (diagnosis_result or {}).get("uploaded_documents") or {}
    comparison = uploaded.get("comparison_result") or {}
    missing_fields = [
        item for item in uploaded.get("missing_key_fields") or [] if item.get("status") == "missing"
    ]
    return bool(
        uploaded.get("mismatches")
        or comparison.get("needs_review_docs")
        or missing_fields
    )


if not st.session_state.get("authenticated"):
    render_login_screen()
    st.stop()


with st.sidebar:
    mode = st.radio("화면 모드", ["고객 상담", "관리자 대시보드"], index=0)
    st.markdown("---")
    active_customer_id = render_logged_in_sidebar(_default_messages)
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
    render_admin_dashboard()
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
    render_chat_message(msg, assistant_avatar=ASSISTANT_AVATAR)

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
        clear_auth_session(_default_messages)
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
    render_chat_message({"role": "user", "content": question, "attachments": attachments}, assistant_avatar=ASSISTANT_AVATAR)

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
                show_ticket_summary = False
                requested_sections = requested_report_sections(question)
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
                    render_multi_policy_analysis(diagnosis_result)
                    render_uploaded_document_analysis(diagnosis_result)
                    render_requested_report_parts(diagnosis_result, requested_sections)
                    show_ticket_summary = _should_show_ticket_summary(
                        question=question,
                        route=pipeline_state.get("next_route"),
                        diagnosis_result=diagnosis_result,
                        ticket_summary=ticket_summary,
                    )
                    if show_ticket_summary:
                        render_ticket_summary(ticket_summary, agent_handoff_summary)
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
        assistant_message["requested_report_sections"] = requested_sections
    if ticket_summary:
        assistant_message["ticket_summary"] = ticket_summary
        assistant_message["show_ticket_summary"] = show_ticket_summary
    if agent_handoff_summary:
        assistant_message["agent_handoff_summary"] = agent_handoff_summary
    st.session_state.messages.append(assistant_message)
    _sync_current_session_messages()
