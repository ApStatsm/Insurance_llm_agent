from __future__ import annotations

from typing import Any

import streamlit as st


def _summary_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, run in enumerate(runs, start=1):
        rows.append(
            {
                "번호": idx,
                "시간": run.get("created_at", ""),
                "상태": run.get("status", ""),
                "route": run.get("route", ""),
                "고객ID": run.get("customer_id", ""),
                "질문": run.get("question", "")[:80],
                "ticket": (run.get("ticket_summary") or {}).get("ticket_id", ""),
            }
        )
    return rows


def render_admin_debug_mode() -> None:
    st.markdown("## 관리자 디버그 모드")
    st.caption("고객 화면에는 노출하지 않는 파이프라인 실행 상태, RAG 디버그, 진단 결과 원본을 확인하는 내부용 화면입니다.")

    runs = list(st.session_state.get("debug_runs") or [])
    if not runs:
        st.info("아직 디버그할 실행 기록이 없습니다. 고객 상담에서 질문을 한 번 처리하면 여기에 기록됩니다.")
        return

    if st.button("디버그 기록 비우기", use_container_width=False):
        st.session_state.debug_runs = []
        st.rerun()

    st.markdown("### 최근 실행 기록")
    st.dataframe(_summary_rows(runs), use_container_width=True, hide_index=True)

    labels = [
        f"{idx}. {run.get('created_at', '')} / {run.get('route', 'route 없음')} / {run.get('question', '')[:32]}"
        for idx, run in enumerate(runs, start=1)
    ]
    selected_label = st.selectbox("상세 확인할 실행 선택", labels, index=len(labels) - 1)
    selected_index = labels.index(selected_label)
    run = runs[selected_index]

    st.markdown("### 실행 요약")
    st.markdown(f"- 고객 ID는 `{run.get('customer_id', '')}`입니다.")
    st.markdown(f"- 질문은 {run.get('question', '')}")
    st.markdown(f"- 처리 상태는 `{run.get('status', '')}`입니다.")
    st.markdown(f"- route는 `{run.get('route', '')}`입니다.")
    st.markdown(f"- retry는 `{run.get('retry_count', 0)}`입니다.")
    if run.get("upload_errors"):
        st.warning("파일 업로드 처리 오류가 있습니다.")
        st.code("\n".join(run.get("upload_errors") or []))
    if run.get("ticket_error"):
        st.warning(run.get("ticket_error"))

    tab_pipeline, tab_diagnosis, tab_ticket, tab_answer, tab_session = st.tabs(
        ["Pipeline State", "Diagnosis", "Ticket/Handoff", "Answer", "Session"]
    )
    with tab_pipeline:
        st.json(run.get("pipeline_state") or {})
    with tab_diagnosis:
        st.json(run.get("diagnosis_result") or {})
    with tab_ticket:
        st.markdown("**Ticket Summary**")
        st.json(run.get("ticket_summary") or {})
        st.markdown("**Agent Handoff**")
        st.json(run.get("agent_handoff_summary") or {})
    with tab_answer:
        st.markdown(run.get("answer") or "표시할 답변이 없습니다.")
    with tab_session:
        st.json(
            {
                "current_chat_id": st.session_state.get("current_chat_id"),
                "active_customer_id": st.session_state.get("active_customer_id"),
                "last_selected_policy": st.session_state.get("last_selected_policy"),
                "chat_session_count": len(st.session_state.get("chat_sessions") or {}),
                "message_count": len(st.session_state.get("messages") or []),
            }
        )
