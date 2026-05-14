from __future__ import annotations

from math import ceil
from pathlib import Path
import re
from typing import Any

from langchain_chroma import Chroma


DOMAIN_DIRS = {
    "auto": "auto_chroma_db",
    "cancer": "cancer_chroma_db",
    "teeth": "teeth_chroma_db",
    "precedent": "precedent_chroma_db",
}

LEGACY_UNIFIED_DIR = "insurance_chroma_db"

DOMAIN_HINTS = {
    "auto": ("자동차", "차량", "차 ", "침수", "태풍", "홍수", "수리", "대물", "대인", "자기차량손해"),
    "cancer": ("암", "암진단", "진단비", "고액암", "병리", "조직검사", "항암"),
    "teeth": ("치아", "치과", "임플란트", "크라운", "브릿지", "틀니", "보철"),
    "precedent": ("판례", "분쟁", "소송", "금감원", "분쟁사례", "유사사례"),
}

PRODUCT_HINTS = {
    "auto": ("자동차", "차량", "운전자"),
    "cancer": ("암", "진단비", "악성신생물"),
    "teeth": ("치아", "치과"),
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _dedupe_docs(docs: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    unique: list[Any] = []
    for doc in docs:
        metadata = getattr(doc, "metadata", None) or {}
        key = (_to_text(getattr(doc, "page_content", ""))[:240], _to_text(metadata.get("source") or metadata.get("대분류")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def _extract_product_name(query: str) -> str:
    match = re.search(r"가입상품\s*:\s*([^\n]+)", query)
    return match.group(1).strip() if match else ""


def _domain_from_product(product_name: str) -> str:
    for domain, hints in PRODUCT_HINTS.items():
        if any(hint in product_name for hint in hints):
            return domain
    return ""


class RoutedVectorStore:
    """
    Domain-split vectorstore facade.

    The pipeline can keep calling `similarity_search()` as if it were a single
    Chroma store. Internally this can route to split stores now, and later switch
    back to one integrated store by changing `mode`.
    """

    def __init__(self, *, stores: dict[str, Chroma], unified_store: Chroma | None = None, mode: str = "split") -> None:
        self.stores = stores
        self.unified_store = unified_store
        self.mode = mode

    def _select_domains(self, query: str) -> list[str]:
        product_domain = _domain_from_product(_extract_product_name(query))
        if product_domain and product_domain in self.stores:
            return [product_domain]

        matched = [
            domain
            for domain, hints in DOMAIN_HINTS.items()
            if domain in self.stores and any(hint in query for hint in hints)
        ]
        if matched:
            return list(dict.fromkeys(matched))

        policy_domains = [domain for domain in ("auto", "cancer", "teeth") if domain in self.stores]
        return policy_domains or list(self.stores.keys())

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Any]:
        if self.mode == "unified" and self.unified_store is not None:
            return self.unified_store.similarity_search(query, k=k, **kwargs)

        domains = self._select_domains(_to_text(query))
        if not domains:
            if self.unified_store is not None:
                return self.unified_store.similarity_search(query, k=k, **kwargs)
            return []

        if len(domains) == 1:
            return self.stores[domains[0]].similarity_search(query, k=k, **kwargs)

        per_domain = max(2, ceil(k / len(domains)))
        docs: list[Any] = []
        for domain in domains:
            docs.extend(self.stores[domain].similarity_search(query, k=per_domain, **kwargs))
        return _dedupe_docs(docs)[:k]

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs: Any) -> list[tuple[Any, float]]:
        domains = self._select_domains(_to_text(query))
        if len(domains) == 1:
            store = self.stores[domains[0]]
            return store.similarity_search_with_score(query, k=k, **kwargs)
        if self.unified_store is not None:
            return self.unified_store.similarity_search_with_score(query, k=k, **kwargs)
        scored: list[tuple[Any, float]] = []
        for domain in domains:
            scored.extend(self.stores[domain].similarity_search_with_score(query, k=max(2, ceil(k / len(domains))), **kwargs))
        return sorted(scored, key=lambda item: item[1])[:k]


def vectorstore_healthcheck(root: Path) -> dict[str, bool]:
    return {
        domain: (root / dirname / "chroma.sqlite3").exists()
        for domain, dirname in DOMAIN_DIRS.items()
    } | {"unified": (root / LEGACY_UNIFIED_DIR / "chroma.sqlite3").exists()}


def build_policy_vectorstore(root: Path, embeddings: Any, *, mode: str = "split") -> RoutedVectorStore:
    stores: dict[str, Chroma] = {}
    for domain, dirname in DOMAIN_DIRS.items():
        path = root / dirname
        if path.exists():
            stores[domain] = Chroma(persist_directory=str(path), embedding_function=embeddings)

    unified_path = root / LEGACY_UNIFIED_DIR
    unified = (
        Chroma(persist_directory=str(unified_path), embedding_function=embeddings)
        if unified_path.exists()
        else None
    )
    return RoutedVectorStore(stores=stores, unified_store=unified, mode=mode)
