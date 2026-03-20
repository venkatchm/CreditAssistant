from __future__ import annotations

from app.schemas.chat import ClassificationResult


class ClassifierService:
    def classify(self, message: str) -> ClassificationResult:
        normalized = " ".join(message.lower().strip().split())

        if any(token in normalized for token in ["improve", "improving", "recommend", "should i do", "how can i improve"]):
            category = "RECOMMENDATION"
        elif any(token in normalized for token in ["why did", "why has", "why is", "score change", "score drop", "score dropped"]):
            category = "PERSONAL_FINANCE_EXPLANATION"
        elif any(token in normalized for token in ["my credit score", "my score", "recent inquiries", "payment history", "show my payments", "show my inquiry", "my utilization"]):
            category = "PERSONAL_FINANCE_FACT"
        elif any(token in normalized for token in ["what is credit utilization", "what is utilization", "what is apr", "what is a hard inquiry"]):
            category = "GENERAL_FINANCE_KNOWLEDGE"
        else:
            category = "UNSUPPORTED"

        return ClassificationResult(category=category, normalized_message=normalized)
