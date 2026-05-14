from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from app.core.formatting import as_list, format_file_size, mask_display_value, to_text


def _clean_text(value: Any) -> str:
    return to_text(value)

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
    values = [_clean_text(item) for item in items if _clean_text(item)]
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
        st.markdown(f"- 상태는 {assessment.get('label', '추가 확인 필요')}입니다.")
        st.markdown(f"- {_clean_text(assessment.get('summary', '현재 정보 기준으로 추가 확인이 필요합니다.'))}")
        if assessment.get("missing_info"):
            st.markdown("- 추가 확인 항목")
            _render_bullets(_as_list(assessment.get("missing_info")), "현재 단계에서 별도 표시된 항목 없음")

    if "customer" in sections:
        st.markdown("**고객 가입 정보**")
        st.markdown(f"- 고객 ID는 `{customer.get('customer_id', '확인 필요')}`입니다.")
        st.markdown(f"- 가입 상품은 {customer.get('product_name', '확인 필요')}입니다.")
        st.markdown(f"- 가입연도는 {customer.get('joined_year', '확인 필요')}입니다.")
        st.markdown(f"- 증권번호는 `{customer.get('policy_number', '확인 필요')}`입니다.")
        st.markdown(f"- 특약은 {', '.join(_as_list(customer.get('riders'))) if customer.get('riders') else '확인 필요'}입니다.")
        st.markdown(f"- 담보한도는 {customer.get('coverage_limit', '확인 필요')}입니다.")

    if "incident" in sections:
        st.markdown("**사고 상황 요약**")
        st.markdown(f"- 사고 유형은 {incident.get('incident_type', '확인 필요')}입니다.")
        st.markdown(f"- 원인은 {incident.get('cause', '확인 필요')}입니다.")
        st.markdown(f"- 대상은 {incident.get('target', '확인 필요')}입니다.")
        st.markdown(f"- 진행 단계는 {incident.get('stage', '확인 필요')}입니다.")

    if "next_actions" in sections:
        st.markdown("**다음 행동 안내**")
        _render_bullets(_as_list(diagnosis_result.get("next_actions")), "상담원 또는 담당자 확인을 요청해 주세요")

    if "evidence" in sections:
        st.markdown("**약관 근거**")
        if evidence_cards:
            for idx, card in enumerate(evidence_cards, start=1):
                with st.expander(f"근거 {idx} - {card.get('article_title') or card.get('article_number') or '약관 원문 기준'}"):
                    st.markdown(f"- 문서는 {card.get('document_name', '확인 필요')}입니다.")
                    st.markdown(f"- 상품은 {card.get('product_name', '확인 필요')}입니다.")
                    st.markdown(f"- 조항은 {card.get('article_number', '확인 필요')}입니다.")
                    st.markdown(f"- 구분은 {card.get('clause_type', '약관 원문 기준')}입니다.")
                    st.markdown("**약관 원문**")
                    st.markdown(_clean_text(card.get("source_text", "확인 필요")))
                    st.markdown("**AI 해석**")
                    st.markdown(_clean_text(card.get("ai_interpretation", "확인 필요")))
                    st.markdown("**고객 상황 적용**")
                    st.markdown(_clean_text(card.get("application_to_customer", "확인 필요")))
        else:
            st.info("현재 표시할 약관 근거가 없습니다. 사고 상황을 더 구체적으로 입력하면 근거를 다시 찾을 수 있습니다.")

    if "checklist" in sections:
        st.markdown("**청구 필요서류 체크리스트**")
        st.markdown("- 제출 완료")
        _render_bullets(_as_list(checklist.get("submitted_docs")), "없음")
        st.markdown("- 추가 필요")
        _render_bullets(_as_list(checklist.get("missing_docs")), "없음")
        st.markdown("- 상품 기준 필요 서류")
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
            st.markdown(f"- {name} - {status} · 추정 유형 {guess}")
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
            st.markdown(f"- {item.get('label', any_of or '확인 필요')} - {item.get('reason', '청구 심사에 필요할 수 있습니다.')}")
    else:
        st.markdown("- 없음")

    if extractions:
        st.markdown("**서류별 추출 정보**")
        for result in extractions:
            title = f"{result.get('file_name', '첨부파일')} · {result.get('doc_type', '기타/판별불가')}"
            with st.expander(title):
                fields = result.get("extracted_fields") or {}
                st.markdown(f"- 신뢰도는 {float(result.get('confidence') or 0):.2f}입니다.")
                st.markdown(f"- 발급기관은 {result.get('issuer') or fields.get('hospital_name') or fields.get('repair_shop') or '확인 필요'}입니다.")
                st.markdown(f"- 일자는 {result.get('issue_date') or result.get('date_of_service') or fields.get('treatment_date') or fields.get('accident_date') or '확인 필요'}입니다.")
                st.markdown(f"- 금액은 {result.get('amount') or fields.get('total_amount') or fields.get('repair_amount') or '확인 필요'}입니다.")
                if fields.get("patient_name"):
                    st.markdown(f"- 환자명은 {_mask_display_value(fields.get('patient_name'), kind='name')}입니다.")
                if fields.get("vehicle_number"):
                    st.markdown(f"- 차량번호는 {_mask_display_value(fields.get('vehicle_number'), kind='vehicle')}입니다.")
                if result.get("raw_text_summary"):
                    st.caption(_clean_text(result.get("raw_text_summary"))[:240])
                for warning in _as_list(result.get("warnings")):
                    st.warning(_clean_text(warning))

    needs_review_docs = _as_list(comparison.get("needs_review_docs"))
    missing_fields = [item for item in missing_key_fields if item.get("status") == "missing"]
    if needs_review_docs or missing_fields:
        st.markdown("**확인 필요 정보**")
        for item in needs_review_docs:
            st.warning(_clean_text(f"{item.get('file_name', '첨부파일')} - {item.get('reason', '확인이 필요합니다.')}"))
        for item in missing_fields:
            st.warning(_clean_text(item.get("message", "핵심 필드 확인이 필요합니다.")))

    if mismatches:
        st.markdown("**고객 정보와 불일치 가능성**")
        for item in mismatches:
            st.warning(_clean_text(item.get("message", "고객 정보와 서류 정보 확인이 필요합니다.")))

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
            st.markdown(f"- 적용 상품은 {policy.get('product_name', '확인 필요')}입니다.")
            st.markdown(f"- 판단은 {assessment.get('label', '추가 확인 필요')}입니다.")
            st.markdown(f"- {_clean_text(assessment.get('summary', '현재 정보 기준으로 추가 확인이 필요합니다.'))}")
            st.markdown("**필요서류**")
            _render_bullets(_as_list(checklist.get("required_docs") or checklist.get("missing_docs")), "확인 필요")
            st.markdown("**청구 서류 준비율**")
            st.progress(readiness / 100)
            st.caption(f"{readiness}% · {checklist.get('readiness_label', '청구 서류 준비 전')}")
            if evidence_cards:
                st.markdown("**약관 근거 카드**")
                for idx, card in enumerate(evidence_cards[:3], start=1):
                    st.markdown(
                        f"- 근거 {idx} - {card.get('document_name', '약관 원문')} / "
                        f"{card.get('article_number') or card.get('article_title') or '조항 확인 필요'}"
                    )
                    st.caption(_clean_text(card.get("source_text"))[:220])
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
    st.markdown(f"**접수 상태** {ticket.get('status_label', 'AI 사전진단 완료')}")
    st.markdown(f"**상담원 확인 필요 여부** {'필요' if ticket.get('human_review_required') else '필요 낮음'}")
    st.markdown(f"**우선도** {ticket.get('priority_label', '보통')}")
    reasons = ticket.get("human_review_reasons") or []
    if reasons:
        st.markdown("**추가 확인이 필요한 항목**")
        _render_bullets(reasons, "현재 표시된 항목 없음")
    st.markdown("**다음 단계** 상담원이 아래 요약 내용을 바탕으로 이어서 확인할 수 있도록 접수 요약이 생성되었습니다.")
    if handoff:
        with st.expander("상담원 전달 요약 보기"):
            _render_agent_handoff(handoff)


def _render_agent_handoff(handoff: dict[str, Any]) -> None:
    if not handoff:
        st.info("상담원 전달 요약이 아직 생성되지 않았습니다.")
        return
    st.caption(_clean_text(handoff.get("notice", "본 요약은 AI 사전진단 결과를 상담원이 이어서 확인할 수 있도록 정리한 참고 자료입니다.")))
    info = handoff.get("ticket_info") or {}
    customer = handoff.get("customer_summary") or {}
    inquiry = handoff.get("inquiry_summary") or {}
    ai = handoff.get("ai_assessment") or {}
    docs = handoff.get("document_status") or {}
    review = handoff.get("human_review") or {}
    st.markdown(f"- 경로/상태/우선도는 {info.get('route_label', '')} · {info.get('status_label', '')} · {info.get('priority_label', '')}입니다.")
    st.markdown(f"- 고객/상품은 `{customer.get('customer_id', '')}` · {customer.get('product_name', '확인 필요')}입니다.")
    st.markdown(f"- 문의 내용은 {_clean_text(inquiry.get('original_question', ''))}")
    st.markdown(f"- 사고유형/단계는 {inquiry.get('incident_type', '')} · {inquiry.get('current_stage', '')}입니다.")
    st.markdown(f"- AI 판단은 {ai.get('coverage_label', '추가 확인 필요')} · {_clean_text(ai.get('assessment_summary', ''))}")
    st.markdown(f"- 제출 서류는 {', '.join(docs.get('submitted_docs') or []) or '없음'}입니다.")
    st.markdown(f"- 누락 서류는 {', '.join(docs.get('missing_docs') or []) or '없음'}입니다.")
    st.markdown(f"- 청구 서류 준비율은 {docs.get('readiness_percent', 0)}%입니다.")
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
                f"- {item.get('product_name', '확인 필요')} - "
                f"{item.get('section_title', '상품 기준 검토')} / {item.get('coverage_label', '추가 확인 필요')}"
            )
        if multi.get("cross_policy_cautions"):
            st.markdown("**상품 간 확인 필요사항**")
            _render_bullets(_as_list(multi.get("cross_policy_cautions")), "없음")
    if handoff.get("recommended_next_steps"):
        st.markdown("**추천 후속 조치**")
        _render_bullets(handoff.get("recommended_next_steps"), "없음")


def render_chat_message(message: dict[str, Any], *, assistant_avatar: str | Path) -> None:
    role = message.get("role", "assistant")
    if role == "user":
        _, message_col = st.columns([1.15, 2.85])
    else:
        message_col, _ = st.columns([2.85, 1.15])
    avatar = None if role == "user" else str(assistant_avatar)

    with message_col:
        with st.chat_message(role, avatar=avatar):
            if message.get("content"):
                st.markdown(_clean_text(message["content"]))
            if role == "assistant" and message.get("diagnosis_result"):
                _render_uploaded_document_analysis(message["diagnosis_result"])
                _render_requested_report_parts(
                    message["diagnosis_result"],
                    message.get("requested_report_sections") or [],
                )
            if role == "assistant" and message.get("ticket_summary") and message.get("show_ticket_summary"):
                _render_ticket_summary(message.get("ticket_summary"), message.get("agent_handoff_summary"))
            _render_attachments(message.get("attachments"))




requested_report_sections = _requested_report_sections
render_requested_report_parts = _render_requested_report_parts
render_uploaded_document_analysis = _render_uploaded_document_analysis
render_multi_policy_analysis = _render_multi_policy_analysis
render_ticket_summary = _render_ticket_summary
render_agent_handoff = _render_agent_handoff
