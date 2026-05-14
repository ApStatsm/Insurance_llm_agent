from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from app.services.upload_service import update_upload_manifest
from app.services.vision_utils import is_supported_vision_file, prepare_file_for_vision


logger = logging.getLogger(__name__)

DOCUMENT_TYPES = [
    "진료비 영수증",
    "진료비 세부내역서",
    "진단서",
    "진료확인서",
    "병리보고서",
    "수리견적서",
    "사고사실확인서",
    "차량등록증",
    "침수 사진",
    "기타/판별불가",
]

DEFAULT_EXTRACTION = {
    "doc_type": "기타/판별불가",
    "confidence": 0.0,
    "document_title": "",
    "issuer": "",
    "issue_date": "",
    "person_name": "",
    "date_of_service": "",
    "amount": None,
    "raw_text_summary": "",
    "extracted_fields": {
        "patient_name": None,
        "hospital_name": None,
        "department": None,
        "diagnosis_name": None,
        "diagnosis_date": None,
        "treatment_date": None,
        "treatment_type": None,
        "total_amount": None,
        "covered_amount": None,
        "non_covered_amount": None,
        "pathology_result": None,
        "vehicle_number": None,
        "owner_name": None,
        "repair_shop": None,
        "repair_amount": None,
        "accident_date": None,
        "damage_type": None,
    },
    "missing_fields": [],
    "warnings": [],
    "needs_review": False,
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def infer_uploaded_doc_type(filename: str) -> str:
    text = _to_text(filename).lower()
    if any(token in text for token in ("receipt", "영수증", "진료비")):
        return "진료비 영수증"
    if any(token in text for token in ("diagnosis", "진단서")):
        return "진단서"
    if any(token in text for token in ("confirm", "확인서", "진료확인")):
        return "진료확인서"
    if any(token in text for token in ("detail", "세부내역", "세부산정")):
        return "진료비 세부내역서"
    if any(token in text for token in ("estimate", "견적", "수리견적")):
        return "수리견적서"
    if any(token in text for token in ("accident", "사고사실", "사고확인")):
        return "사고사실확인서"
    if any(token in text for token in ("registration", "차량등록", "등록증")):
        return "차량등록증"
    if any(token in text for token in ("pathology", "병리", "조직검사")):
        return "병리보고서"
    if any(token in text for token in ("photo", "침수사진", "사진", "flood")):
        return "침수 사진"
    return "기타/판별불가"


def build_vision_extraction_prompt(product_name: str, question: str) -> str:
    doc_types = ", ".join(DOCUMENT_TYPES)
    return f"""
당신은 한국어 보험금 청구 서류를 분석하는 Vision 문서 분류/추출 도우미입니다.
가입상품 {product_name or "확인 필요"}
고객 질문 {question or "확인 필요"}

이미지에 보이는 내용만 추출하세요. 보이지 않는 값은 null로 두세요.
추측이 필요한 내용은 warnings 배열에 넣고 needs_review를 true로 설정하세요.
금액은 가능하면 숫자로 변환하고, 날짜는 가능하면 YYYY-MM-DD 형식으로 변환하세요.
문서가 사고/차량 사진인 경우 침수, 파손, 차량 관련 단서를 damage_type 또는 warnings에 반영하세요.
JSON 외의 설명 문장을 절대 출력하지 마세요.

문서 유형 후보 {doc_types}

다음 JSON 스키마만 출력하세요.
{{
  "doc_type": "",
  "confidence": 0.0,
  "document_title": "",
  "issuer": "",
  "issue_date": "",
  "person_name": "",
  "date_of_service": "",
  "amount": null,
  "raw_text_summary": "",
  "extracted_fields": {{
    "patient_name": null,
    "hospital_name": null,
    "department": null,
    "diagnosis_name": null,
    "diagnosis_date": null,
    "treatment_date": null,
    "treatment_type": null,
    "total_amount": null,
    "covered_amount": null,
    "non_covered_amount": null,
    "pathology_result": null,
    "vehicle_number": null,
    "owner_name": null,
    "repair_shop": null,
    "repair_amount": null,
    "accident_date": null,
    "damage_type": null
  }},
  "missing_fields": [],
  "warnings": [],
  "needs_review": false
}}
""".strip()


def _safe_json_loads(text: str) -> dict[str, Any]:
    cleaned = _to_text(text).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}


def _normalize_extraction_result(raw: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(DEFAULT_EXTRACTION, ensure_ascii=False))
    result.update({k: v for k, v in raw.items() if k != "extracted_fields"})
    fields = dict(DEFAULT_EXTRACTION["extracted_fields"])
    if isinstance(raw.get("extracted_fields"), dict):
        fields.update(raw["extracted_fields"])
    result["extracted_fields"] = fields
    if result.get("doc_type") not in DOCUMENT_TYPES:
        result["warnings"] = [*result.get("warnings", []), "문서 유형 후보에 없는 값이 반환되어 확인이 필요합니다."]
        result["doc_type"] = "기타/판별불가"
        result["needs_review"] = True
    try:
        result["confidence"] = float(result.get("confidence") or 0)
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


def fallback_extraction_result(file_record: dict[str, Any], reason: str) -> dict[str, Any]:
    guessed = _to_text(file_record.get("doc_type_guess")) or infer_uploaded_doc_type(_to_text(file_record.get("original_filename")))
    if guessed in ("기타 서류", "PDF 서류"):
        guessed = "기타/판별불가"
    result = _normalize_extraction_result(
        {
            "doc_type": guessed,
            "confidence": 0.3,
            "raw_text_summary": "Vision 분석 실패로 파일명 기준으로 문서 유형만 추정했습니다.",
            "warnings": [reason or "Vision 분석 실패로 문서 내용 검증은 수행하지 못했습니다."],
            "needs_review": True,
        }
    )
    result["file_name"] = _to_text(file_record.get("original_filename") or file_record.get("saved_filename"))
    result["upload_id"] = file_record.get("upload_id")
    result["processing_status"] = "failed" if file_record.get("file_ext") != "txt" else "unsupported"
    return result


def extract_document_fields_with_vision(
    file_record: dict[str, Any],
    customer_info: dict[str, Any],
    question: str,
    vision_inputs: list[dict[str, Any]],
    llm: Any | None = None,
) -> dict[str, Any]:
    if not vision_inputs:
        return fallback_extraction_result(file_record, "Vision 분석 대상 파일이 아니어서 파일명 기준으로 추정했습니다.")
    if llm is None:
        return fallback_extraction_result(file_record, "Vision LLM을 사용할 수 없어 파일명 기준으로 추정했습니다.")

    product_name = _to_text((customer_info or {}).get("product_name"))
    filename_hint = _to_text(file_record.get("original_filename") or file_record.get("saved_filename"))
    guess_hint = _to_text(file_record.get("doc_type_guess"))
    prompt = (
        f"{build_vision_extraction_prompt(product_name, question)}\n\n"
        f"참고 파일명 {filename_hint}\n"
        f"파일명 기반 1차 추정 {guess_hint or '확인 필요'}"
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for item in vision_inputs:
        data_url = f"data:{item.get('mime_type', 'image/png')};base64,{item.get('base64', '')}"
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    try:
        response = llm.invoke([HumanMessage(content=content)])
        parsed = _safe_json_loads(_to_text(response.content))
        result = _normalize_extraction_result(parsed)
        result["processing_status"] = "extracted"
    except Exception as exc:
        logger.exception("Vision document extraction failed: %s", file_record.get("saved_filename"))
        result = fallback_extraction_result(file_record, f"Vision 분석 실패 - {exc.__class__.__name__}")

    result["file_name"] = _to_text(file_record.get("original_filename") or file_record.get("saved_filename"))
    result["saved_filename"] = file_record.get("saved_filename")
    result["upload_id"] = file_record.get("upload_id")
    return result


def save_extraction_result(file_record: dict[str, Any], extraction_result: dict[str, Any], session_dir: str) -> str:
    extracted_dir = Path(session_dir) / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    target = extracted_dir / f"{Path(_to_text(file_record.get('saved_filename'))).stem}.json"
    target.write_text(json.dumps(extraction_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def extract_documents_for_uploaded_files(
    file_records: list[dict[str, Any]],
    customer_info: dict[str, Any],
    question: str,
    session_dir: str,
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    thumbnails_dir = str(Path(session_dir) / "thumbnails")
    for record in file_records:
        working_record = dict(record)
        try:
            if is_supported_vision_file(_to_text(record.get("saved_path"))):
                working_record["processing_status"] = "extracting"
                update_upload_manifest(session_dir, working_record)
                vision_inputs = prepare_file_for_vision(_to_text(record.get("saved_path")), thumbnails_dir)
                extraction = extract_document_fields_with_vision(record, customer_info, question, vision_inputs, llm=llm)
            else:
                extraction = fallback_extraction_result(record, "지원하지 않는 Vision 형식이라 파일명 기준으로 추정했습니다.")
            json_path = save_extraction_result(record, extraction, session_dir)
            working_record["extracted_json_path"] = json_path
            working_record["processing_status"] = extraction.get("processing_status", "extracted")
            working_record["doc_type"] = extraction.get("doc_type") or working_record.get("doc_type")
            working_record["error_message"] = "; ".join(extraction.get("warnings") or []) or None
            update_upload_manifest(session_dir, working_record)
            results.append(extraction)
        except Exception as exc:
            logger.exception("Uploaded document processing failed: %s", record.get("saved_filename"))
            extraction = fallback_extraction_result(record, f"문서 처리 실패 - {exc.__class__.__name__}")
            try:
                json_path = save_extraction_result(record, extraction, session_dir)
            except Exception:
                json_path = None
            working_record["processing_status"] = "failed"
            working_record["extracted_json_path"] = json_path
            working_record["error_message"] = extraction["warnings"][0] if extraction.get("warnings") else str(exc)
            update_upload_manifest(session_dir, working_record)
            results.append(extraction)
    return results
