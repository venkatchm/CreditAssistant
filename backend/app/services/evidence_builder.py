from __future__ import annotations

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
