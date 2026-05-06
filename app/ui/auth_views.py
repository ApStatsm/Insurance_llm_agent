from __future__ import annotations

import logging
from typing import Any, Callable

import streamlit as st

from app.core.formatting import as_list as _as_list
from app.services.customer_service import (
    authenticate_customer,
    build_customer_context,
    find_demo_accounts,
    load_customers,
)

logger = logging.getLogger(__name__)

def _policy_label(policy: dict[str, Any]) -> str:
    riders = ", ".join(_as_list(policy.get("riders") or policy.get("special_clauses")))
    base = f"{policy.get('product_name', '상품 확인 필요')} / {policy.get('joined_year') or policy.get('join_year') or '연도 확인 필요'}"
    return f"{base} / 특약: {riders}" if riders else base


def _clear_auth_session(default_messages_factory: Callable[[], list[dict[str, str]]]) -> None:
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
    st.session_state.messages = default_messages_factory()
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


def render_logged_in_sidebar(default_messages_factory: Callable[[], list[dict[str, str]]]) -> str:
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
        _clear_auth_session(default_messages_factory)
        st.rerun()
    return active_id




render_login_screen = _render_login_screen
clear_auth_session = _clear_auth_session
