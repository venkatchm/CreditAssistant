from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.api.routes.chat import router as chat_router
from app.core.dependencies import get_chat_orchestrator
from app.gateway.model_gateway import LocalModelGateway
from app.repositories.json_credit_repository import JsonCreditRepository
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.credit_service import CreditService
from app.services.evidence_builder import EvidenceBuilder
from app.services.execution_planner import ExecutionPlanner
from app.services.grounded_response_composer import GroundedResponseComposer
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.query_analyzer import QueryAnalyzer
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService
from app.services.tool_registry import ToolRegistry
from main import app


class ChatResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_fact_response_is_humanized_and_excludes_null_fields(self) -> None:
        print("\n[chat] testing SIMPLE_FACT route flow for credit score")
        response = self.client.post(
            "/chat",
            json={"user_id": "user_001", "message": "What is my credit score?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        print(f"[chat] category={payload['category']} message={payload['message']}")
        print(f"[chat] first_card={payload['cards'][0]}")

        self.assertEqual(payload["category"], "SIMPLE_FACT")
        self.assertIn("Your latest credit score is 792", payload["message"])
        self.assertIn("Very Good", payload["message"])
        first_card = payload["cards"][0]
        self.assertEqual(first_card["type"], "credit_score")
        self.assertNotIn("priority", first_card)
        self.assertNotIn("value", first_card)
        self.assertEqual(first_card["description"], "Score band: Very Good")

    def test_explanation_response_dedupes_overlapping_factors(self) -> None:
        print("\n[chat] testing COMPLEX_EXPLANATION route flow for score drop")
        response = self.client.post(
            "/chat",
            json={"user_id": "user_003", "message": "Why did my score drop?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        print(f"[chat] category={payload['category']} message={payload['message']}")
        print(f"[chat] explanation={payload['explanation']}")

        self.assertEqual(payload["category"], "COMPLEX_EXPLANATION")
        self.assertIn("down 58 points", payload["message"])
        self.assertIn("explanation", payload)
        self.assertGreater(len(payload["explanation"]["causes"]), 0)
        factor_descriptions = [card["description"] for card in payload["cards"] if card["type"] == "factor"]
        print(f"[chat] factor_descriptions={factor_descriptions}")
        self.assertEqual(len(factor_descriptions), len(set(factor_descriptions)))

    def test_recommendation_response_is_grounded_and_humanized(self) -> None:
        print("\n[chat] testing SIMPLE_RECOMMENDATION route flow")
        response = self.client.post(
            "/chat",
            json={"user_id": "user_005", "message": "How can I improve my score?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        print(f"[chat] category={payload['category']} message={payload['message']}")
        print(f"[chat] recommendation_cards={payload['cards']}")

        self.assertEqual(payload["category"], "SIMPLE_RECOMMENDATION")
        self.assertTrue(payload["requires_disclaimer"])
        self.assertIn("latest credit score", payload["message"].lower())
        self.assertGreater(len(payload["cards"]), 0)
        self.assertEqual(payload["cards"][0]["priority"], "Medium")

    def test_general_knowledge_response_uses_rag(self) -> None:
        print("\n[chat] testing GENERAL_KNOWLEDGE route flow")
        response = self.client.post(
            "/chat",
            json={"user_id": "user_001", "message": "What is credit utilization?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        print(f"[chat] category={payload['category']} message={payload['message']}")
        print(f"[chat] knowledge_cards={payload['cards']}")

        self.assertEqual(payload["category"], "GENERAL_KNOWLEDGE")
        self.assertIn("available revolving credit", payload["message"].lower())
        self.assertGreater(len(payload["cards"]), 0)

    def test_streaming_chat_response_returns_text_stream(self) -> None:
        print("\n[chat] testing streaming chat flow")
        with self.client.stream(
            "POST",
            "/chat",
            json={"user_id": "user_001", "message": "What is credit utilization?", "stream": True},
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
            body = "".join(chunk for chunk in response.iter_text())
        print(f"[chat] streamed_body={body}")
        self.assertIn("event: start", body)
        self.assertIn("event: classification", body)
        self.assertIn("event: plan", body)
        self.assertIn("event: retrieval_start", body)
        self.assertIn("event: retrieval_result", body)
        self.assertIn("event: compose", body)
        self.assertIn("event: data", body)
        self.assertIn("event: end", body)
        self.assertIn("credit utilization", body.lower())

    def test_general_knowledge_returns_insufficient_evidence_message_when_retrieval_misses(self) -> None:
        print("\n[chat] testing insufficient evidence fallback for knowledge response")
        from fastapi import FastAPI

        repository = JsonCreditRepository()
        override_app = FastAPI()
        override_app.include_router(chat_router)
        override_app.dependency_overrides[get_chat_orchestrator] = lambda: ChatOrchestrator(
            query_analyzer=QueryAnalyzer(),
            agent_orchestrator=AgentOrchestrator(
                planner=ExecutionPlanner(),
                tool_registry=ToolRegistry(
                    credit_service=CreditService(repository),
                    metrics_service=MetricsService(repository),
                    recommendation_service=RecommendationService(repository),
                    inquiry_service=InquiryService(repository),
                    payment_history_service=PaymentHistoryService(repository),
                ),
                rag_service=RagService(min_score=50),
                evidence_builder=EvidenceBuilder(),
                response_composer=GroundedResponseComposer(model_gateway=LocalModelGateway(), evidence_builder=EvidenceBuilder()),
            ),
        )
        client = TestClient(override_app)
        response = client.post(
            "/chat",
            json={"user_id": "user_001", "message": "What is credit utilization?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("grounded educational evidence", payload["message"].lower())


if __name__ == "__main__":
    unittest.main()
