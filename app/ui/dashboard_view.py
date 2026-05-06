from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from app.core.formatting import as_list as _as_list, mask_customer_id
from app.services.dashboard_service import compute_dashboard_metrics, human_review_queue
from app.services.ticket_service import create_mock_tickets_if_empty, load_ticket_detail, load_ticket_index
from app.ui.chat_views import render_agent_handoff, _render_bullets

logger = logging.getLogger(__name__)

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
        render_agent_handoff(handoff)
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




render_admin_dashboard = _render_admin_dashboard
