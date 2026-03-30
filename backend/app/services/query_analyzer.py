from __future__ import annotations

from app.schemas.chat import ClassificationResult


# Purely personal data queries — user is asking to SEE their specific data
_PERSONAL_FACT_PATTERNS = [
    "show my", "list my", "display my", "what is my credit score",
    "what is my score", "what is my utilization",
]

# User wants personalized advice
_RECOMMENDATION_PATTERNS = [
    "how can i improve", "how do i improve", "how to improve", "improve my score",
    "recommend", "what should i do", "what can i do", "tips for", "ways to improve",
    "help me", "advice", "suggestion",
]

# User wants to understand WHY something happened to their credit
_COMPLEX_EXPLANATION_PATTERNS = [
    "why did", "why has", "why is", "score drop", "score dropped", "score change",
    "score went down", "score decreased", "explain my", "analyze my", "what happened to",
    "what caused", "reason for",
]

# Educational / general knowledge — "what is X", "how does X work", etc.
_KNOWLEDGE_STARTERS = [
    "what is", "what are", "what does", "what do",
    "how does", "how do", "how long", "how often", "how much",
    "define", "explain", "meaning of", "difference between",
    "tell me about", "learn about",
    "can closing", "can opening", "does", "do ",
    "when should", "when can", "when do",
    "where can", "where do",
]

# Credit-related topics that confirm a question is about credit/finance
_CREDIT_TOPICS = [
    "credit", "score", "inquiry", "inquiries", "fico", "vantagescore",
    "utilization", "payment", "debt", "loan", "mortgage", "interest",
    "apr", "balance", "limit", "report", "bureau", "equifax", "experian",
    "transunion", "fcra", "tila", "cfpb", "freeze", "dispute",
    "collections", "bankruptcy", "delinquency", "charge-off", "charge off",
    "authorized user", "secured card", "credit card", "hard pull",
    "soft pull", "annual fee", "credit history", "credit mix",
    "debt-to-income", "dti", "refinance", "consolidation",
    "identity theft", "fraud", "cosigner", "preapproval", "pre-approval",
    "negative item", "late payment", "on time", "good score",
]


class QueryAnalyzer:
    def analyze(self, message: str) -> ClassificationResult:
        normalized = " ".join(message.lower().strip().split())
        is_credit_related = any(t in normalized for t in _CREDIT_TOPICS)
        is_educational = any(p in normalized for p in _KNOWLEDGE_STARTERS)

        # 1. Educational question about credit — always use RAG
        #    "What is FCRA?", "How long do inquiries stay?", "Can closing a card hurt?"
        if is_educational and is_credit_related:
            category = "GENERAL_KNOWLEDGE"

        # 2. Complex explanation — user wants to understand changes to THEIR credit
        #    "Why did my score drop?", "What caused my score change?"
        elif any(p in normalized for p in _COMPLEX_EXPLANATION_PATTERNS):
            category = "COMPLEX_EXPLANATION"

        # 3. Recommendation — user wants personalized advice + educational context
        #    "How can I improve my credit score?", "Tips for raising my score"
        elif any(p in normalized for p in _RECOMMENDATION_PATTERNS) and is_credit_related:
            category = "COMPLEX_EXPLANATION"

        # 4. Personal fact — user asking to see their own data
        #    "Show my inquiries", "What is my credit score?"
        elif any(p in normalized for p in _PERSONAL_FACT_PATTERNS):
            category = "SIMPLE_FACT"

        # 5. Mentions credit topics but not clearly educational — try knowledge
        #    "credit freeze", "secured card"
        elif is_credit_related:
            category = "GENERAL_KNOWLEDGE"

        # 6. Fallback
        else:
            category = "UNSUPPORTED"

        return ClassificationResult(category=category, normalized_message=normalized)
