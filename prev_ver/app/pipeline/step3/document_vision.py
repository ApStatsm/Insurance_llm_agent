from __future__ import annotations

import base64
import json
from typing import Any

from langchain_core.messages import HumanMessage


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _image_data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _pdf_page_data_urls(data: bytes, *, max_pages: int = 2, zoom: float = 2.0) -> list[str]:
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise RuntimeError("PDF Vision 추출에는 PyMuPDF 설치가 필요합니다. `pip install PyMuPDF`를 실행하세요.") from exc

    urls: list[str] = []
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for page_index in range(min(max_pages, doc.page_count)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            urls.append(_image_data_url(pix.tobytes("png"), "image/png"))
    finally:
        doc.close()
    return urls


def _uploaded_doc_to_image_urls(doc: dict[str, Any]) -> list[str]:
    name = _to_text(doc.get("doc_name")).lower()
    raw = doc.get("content_bytes")
    if not isinstance(raw, bytes) or not raw:
        return []

    if name.endswith(".pdf"):
        return _pdf_page_data_urls(raw)
    if name.endswith(".png"):
        return [_image_data_url(raw, "image/png")]
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return [_image_data_url(raw, "image/jpeg")]
    return []


def _safe_json_loads(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def extract_document_fields_with_vision(
    *,
    docs: list[dict[str, Any]],
    llm: Any,
    max_docs: int = 4,
) -> list[dict[str, Any]]:
    """
    Extract claim-relevant fields from uploaded image/PDF documents.

    The returned values are candidates for first-pass validation, not final claim facts.
    """
    results: list[dict[str, Any]] = []
    for doc in docs[:max_docs]:
        image_urls = _uploaded_doc_to_image_urls(doc)
        if not image_urls:
            results.append(
                {
                    "doc_id": doc.get("doc_id"),
                    "doc_name": doc.get("doc_name"),
                    "status": "skipped",
                    "reason": "vision_unsupported_or_empty",
                }
            )
            continue

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "다음 보험 청구 서류 이미지/PDF 페이지에서 필요한 정보를 추출하세요. "
                    "반드시 JSON 객체만 출력하세요. 확실하지 않은 값은 null로 두세요. "
                    "doc_type은 receipt, medical_statement, treatment_detail, diagnosis_certificate, "
                    "pathology_report, repair_estimate, accident_report, vehicle_registration, misc 중 하나로 고르세요. "
                    "필드는 doc_type, issuer_name, patient_name, treatment_date, issue_date, total_amount, "
                    "vehicle_number, diagnosis_name, confidence, warnings."
                ),
            }
        ]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})

        try:
            response = llm.invoke([HumanMessage(content=content)])
            parsed = _safe_json_loads(_to_text(response.content))
            parsed["doc_id"] = doc.get("doc_id")
            parsed["doc_name"] = doc.get("doc_name")
            parsed["status"] = "extracted"
            results.append(parsed)
        except Exception as exc:
            results.append(
                {
                    "doc_id": doc.get("doc_id"),
                    "doc_name": doc.get("doc_name"),
                    "status": "failed",
                    "reason": f"{exc.__class__.__name__}: {exc}",
                }
            )
    return results
