from __future__ import annotations

import unittest

from app.repositories.json_credit_repository import JsonCreditRepository
from app.schemas.chat import ClassificationResult
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService


class AgentOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repository = JsonCreditRepository()
        cls.agent = AgentOrchestrator(
            credit_service=CreditService(repository),
            metrics_service=MetricsService(repository),
            recommendation_service=RecommendationService(repository),
            inquiry_service=InquiryService(repository),
            payment_history_service=PaymentHistoryService(repository),
            rag_service=RagService(),
        )

    def test_simple_fact_uses_tool_data(self) -> None:
        print("\n[agent] testing SIMPLE_FACT execution path")
        response = self.agent.execute(
            user_id="user_001",
            message="What is my credit score?",
            analysis=ClassificationResult(category="SIMPLE_FACT", normalized_message="what is my credit score?"),
        )
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] cards={response.cards}")
        self.assertEqual(response.category, "SIMPLE_FACT")
        self.assertIn("792", response.message)
        self.assertEqual(response.cards[0].type, "credit_score")

    def test_general_knowledge_uses_rag(self) -> None:
        print("\n[agent] testing GENERAL_KNOWLEDGE execution path")
        response = self.agent.execute(
            user_id="user_001",
            message="What is credit utilization?",
            analysis=ClassificationResult(category="GENERAL_KNOWLEDGE", normalized_message="what is credit utilization?"),
        )
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] knowledge_cards={response.cards}")
        self.assertEqual(response.category, "GENERAL_KNOWLEDGE")
        self.assertGreater(len(response.cards), 0)
        self.assertEqual(response.cards[0].type, "knowledge")
        self.assertIn("revolving credit", response.message.lower())

    def test_complex_explanation_combines_tools_and_explanation(self) -> None:
        print("\n[agent] testing COMPLEX_EXPLANATION execution path")
        response = self.agent.execute(
            user_id="user_003",
            message="Why did my score drop?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did my score drop?"),
        )
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] explanation={response.explanation}")
        print(f"[agent] cards={response.cards}")
        self.assertEqual(response.category, "COMPLEX_EXPLANATION")
        self.assertIsNotNone(response.explanation)
        self.assertGreater(len(response.explanation.causes), 0)
        self.assertGreater(len(response.explanation.evidence), 0)
        self.assertGreater(len(response.explanation.suggested_actions), 0)
        self.assertTrue(any(card.type == "recommendation" for card in response.cards))

    def test_simple_recommendation_includes_actions(self) -> None:
        print("\n[agent] testing SIMPLE_RECOMMENDATION execution path")
        response = self.agent.execute(
            user_id="user_005",
            message="How can I improve my score?",
            analysis=ClassificationResult(category="SIMPLE_RECOMMENDATION", normalized_message="how can i improve my score?"),
        )
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] explanation={response.explanation}")
        print(f"[agent] cards={response.cards}")
        self.assertEqual(response.category, "SIMPLE_RECOMMENDATION")
        self.assertIsNotNone(response.explanation)
        self.assertGreater(len(response.explanation.suggested_actions), 0)
        self.assertTrue(any(card.type == "recommendation" for card in response.cards))


if __name__ == "__main__":
    unittest.main()
