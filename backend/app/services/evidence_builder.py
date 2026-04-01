from __future__ import annotations

import re

from app.schemas.chat import EvidenceItem, RetrievalResult, ToolResult


class EvidenceBuilder:
    def build(self, tool_results: dict[str, ToolResult], retrieval_result: RetrievalResult | None) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for tool_name, result in tool_results.items():
            for detail in result.evidence:
                evidence.append(
                    EvidenceItem(
                        source_kind="tool",
                        source_name=tool_name,
                        title=tool_name,
                        detail=detail,
                        citation=result.source,
                    )
                )
        if retrieval_result:
            for document in retrieval_result.documents:
                evidence.append(
                    EvidenceItem(
                        source_kind="retrieval",
                        source_name=document.doc_id,
                        title=document.title,
                        detail=document.snippet,
                        citation=document.source,
                        confidence=document.confidence,
                    )
                )
        return evidence

    def is_sufficient_for_complex_explanation(self, evidence: list[EvidenceItem]) -> bool:
        has_tool_evidence = any(item.source_kind == "tool" for item in evidence)
        has_retrieval_evidence = any(item.source_kind == "retrieval" for item in evidence)
        return has_tool_evidence and has_retrieval_evidence

    def has_tool_evidence(self, evidence: list[EvidenceItem]) -> bool:
        return any(item.source_kind == "tool" for item in evidence)

    def has_retrieval_evidence(self, evidence: list[EvidenceItem]) -> bool:
        return any(item.source_kind == "retrieval" for item in evidence)

    def filter_supported_texts(self, texts: list[str], evidence: list[EvidenceItem]) -> list[str]:
        return [text for text in texts if self.supports_text(text, evidence)]

    def supports_text(self, text: str, evidence: list[EvidenceItem]) -> bool:
        normalized_text = self._normalize(text)
        if not normalized_text:
            return False
        text_tokens = set(self._tokens(normalized_text))
        if not text_tokens:
            return False
        for item in evidence:
            candidate = self._normalize(f"{item.title} {item.detail} {item.citation or ''}")
            if normalized_text in candidate or candidate in normalized_text:
                return True
            candidate_tokens = set(self._tokens(candidate))
            overlap = text_tokens & candidate_tokens
            if len(overlap) >= min(3, len(text_tokens)):
                return True
        return False

    def _normalize(self, text: str) -> str:
        return " ".join(text.lower().strip().split())

    def _tokens(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 2]
