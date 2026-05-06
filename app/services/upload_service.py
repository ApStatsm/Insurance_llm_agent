from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt"}
VISION_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
MANIFEST_NAME = "manifest.json"


class UploadValidationError(ValueError):
    pass


def infer_uploaded_doc_type(filename: str) -> str:
    text = str(filename or "").lower()
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


def _now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sanitize_filename(filename: str) -> str:
    name = Path(str(filename or "uploaded_file")).name
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", stem).strip("._")
    stem = re.sub(r"_+", "_", stem)
    if not stem:
        stem = "uploaded_file"
    stem = stem[:80]
    return f"{stem}{suffix}" if suffix else stem


def _safe_customer_id(customer_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", str(customer_id or "UNKNOWN")).strip("._")
    return safe or "UNKNOWN"


def create_upload_session_dir(customer_id: str, session_id: str | None = None) -> dict[str, str]:
    safe_customer = _safe_customer_id(customer_id)
    safe_session = sanitize_filename(session_id or f"session_{_now_compact()}").replace(".", "_")
    if not safe_session.startswith("session_"):
        safe_session = f"session_{safe_session}"
    session_dir = UPLOAD_ROOT / safe_customer / safe_session
    original_dir = session_dir / "original"
    extracted_dir = session_dir / "extracted"
    thumbnails_dir = session_dir / "thumbnails"
    for path in (original_dir, extracted_dir, thumbnails_dir):
        path.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / MANIFEST_NAME
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "customer_id": customer_id,
                    "session_id": safe_session,
                    "created_at": _now_iso(),
                    "files": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return {
        "customer_id": customer_id,
        "session_id": safe_session,
        "session_dir": str(session_dir),
        "original_dir": str(original_dir),
        "extracted_dir": str(extracted_dir),
        "thumbnails_dir": str(thumbnails_dir),
        "manifest_path": str(manifest_path),
    }


def _unique_saved_path(original_dir: Path, sanitized_name: str) -> Path:
    candidate = original_dir / sanitized_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for idx in range(1, 1000):
        renamed = original_dir / f"{stem}_{idx:03d}{suffix}"
        if not renamed.exists():
            return renamed
    raise UploadValidationError("같은 이름의 파일이 너무 많습니다. 파일명을 바꿔 다시 업로드해 주세요.")


def load_upload_manifest(session_dir: str) -> dict[str, Any]:
    manifest_path = Path(session_dir) / MANIFEST_NAME
    if not manifest_path.exists():
        return {"files": []}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": []}
    return raw if isinstance(raw, dict) else {"files": []}


def update_upload_manifest(session_dir: str, file_record: dict[str, Any]) -> None:
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    manifest = load_upload_manifest(str(session_path))
    files = manifest.get("files")
    if not isinstance(files, list):
        files = []
    updated = False
    for idx, existing in enumerate(files):
        if existing.get("upload_id") == file_record.get("upload_id"):
            files[idx] = file_record
            updated = True
            break
    if not updated:
        files.append(file_record)
    manifest["files"] = files
    manifest["updated_at"] = _now_iso()
    (session_path / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def save_uploaded_file(uploaded_file: Any, customer_id: str, session_id: str) -> dict[str, Any]:
    session_info = create_upload_session_dir(customer_id, session_id)
    original_dir = Path(session_info["original_dir"])
    original_filename = getattr(uploaded_file, "name", "uploaded_file")
    sanitized_name = sanitize_filename(original_filename)
    file_ext = Path(sanitized_name).suffix.lower().lstrip(".")
    if file_ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("지원하지 않는 파일 형식입니다. PDF, PNG, JPG, JPEG 파일을 업로드해 주세요.")

    content_bytes = uploaded_file.getvalue()
    if len(content_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise UploadValidationError("파일 용량이 10MB를 초과했습니다. 용량을 줄여 다시 업로드해 주세요.")

    saved_path = _unique_saved_path(original_dir, sanitized_name)
    saved_path.write_bytes(content_bytes)
    upload_id = f"UPL-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
    doc_type_guess = infer_uploaded_doc_type(original_filename)
    status = "saved" if file_ext in VISION_EXTENSIONS else "unsupported"
    file_record = {
        "upload_id": upload_id,
        "doc_id": upload_id,
        "customer_id": customer_id,
        "session_id": session_info["session_id"],
        "session_dir": session_info["session_dir"],
        "original_filename": original_filename,
        "saved_filename": saved_path.name,
        "saved_path": str(saved_path),
        "storage_path": str(saved_path),
        "file_ext": file_ext,
        "mime_type": getattr(uploaded_file, "type", "") or "",
        "file_size": len(content_bytes),
        "size_bytes": len(content_bytes),
        "doc_name": original_filename,
        "doc_type": doc_type_guess,
        "doc_type_guess": doc_type_guess,
        "processing_status": status,
        "created_at": _now_iso(),
        "extracted_json_path": None,
        "error_message": None,
    }
    update_upload_manifest(session_info["session_dir"], file_record)
    return file_record
