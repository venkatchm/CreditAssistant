from __future__ import annotations

from app.schemas.chat import ClassificationResult


class QueryAnalyzer:
    def analyze(self, message: str) -> ClassificationResult:
        normalized = " ".join(message.lower().strip().split())

        if any(token in normalized for token in ["what is credit utilization", "what is utilization", "what is a hard inquiry", "what is payment history"]):
            category = "GENERAL_KNOWLEDGE"
        elif any(token in normalized for token in ["why did", "why has", "why is", "score drop", "score dropped", "score change"]):
            category = "COMPLEX_EXPLANATION"
        elif any(token in normalized for token in ["how can i improve", "recommend", "what should i do", "improve my score"]):
            category = "SIMPLE_RECOMMENDATION"
        elif any(token in normalized for token in ["credit score", "show my inquiries", "show my payment history", "my utilization", "my inquiries", "my payments"]):
            category = "SIMPLE_FACT"
        else:
            category = "UNSUPPORTED"

        return ClassificationResult(category=category, normalized_message=normalized)
