from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


VISION_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def is_supported_vision_file(file_path: str) -> bool:
    return Path(str(file_path)).suffix.lower() in VISION_EXTENSIONS


def image_file_to_base64(file_path: str) -> str:
    return base64.b64encode(Path(file_path).read_bytes()).decode("ascii")


def pdf_to_page_images(file_path: str, output_dir: str, max_pages: int = 2) -> list[str]:
    import fitz

    source = Path(file_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[str] = []
    doc = fitz.open(str(source))
    try:
        for page_index in range(min(max_pages, doc.page_count)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            out_path = target_dir / f"{source.stem}_page_{page_index + 1}.png"
            pix.save(str(out_path))
            image_paths.append(str(out_path))
    finally:
        doc.close()
    return image_paths


def prepare_file_for_vision(file_path: str, thumbnails_dir: str) -> list[dict[str, Any]]:
    source = Path(str(file_path))
    suffix = source.suffix.lower()
    if suffix not in VISION_EXTENSIONS:
        return []

    prepared_paths: list[tuple[str, str]] = []
    if suffix == ".pdf":
        try:
            prepared_paths = [(path, "image/png") for path in pdf_to_page_images(str(source), thumbnails_dir)]
        except Exception as exc:
            raise RuntimeError("PDF 미리보기 변환에 실패했습니다. 파일명 기준 점검을 진행합니다.") from exc
    else:
        prepared_paths = [(str(source), IMAGE_MIME_TYPES.get(suffix, "image/png"))]

    return [
        {
            "kind": "image",
            "path": path,
            "mime_type": mime_type,
            "base64": image_file_to_base64(path),
        }
        for path, mime_type in prepared_paths
    ]
