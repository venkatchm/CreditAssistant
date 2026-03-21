from __future__ import annotations

import unittest

from app.gateway.model_gateway import GeneratedAnswerPayload, LocalModelGateway
from app.repositories.json_credit_repository import JsonCreditRepository
from app.schemas.chat import ClassificationResult, GroundedAnswer, RetrievalDocument, RetrievalResult
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.credit_service import CreditService
from app.services.evidence_builder import EvidenceBuilder
from app.services.execution_planner import ExecutionPlanner
from app.services.grounded_response_composer import GroundedResponseComposer
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService
from app.services.tool_registry import ToolRegistry


class FakeIterativeRagService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_knowledge(self, query: str) -> RetrievalResult:
        self.queries.append(query)
        if len(self.queries) == 1:
            return RetrievalResult(query=query, documents=[], used=False, top_confidence=0.0)
        return RetrievalResult(
            query=query,
            documents=[
                RetrievalDocument(
                    doc_id="doc_credit_utilization_v1",
                    topic="credit_utilization",
                    title="Credit Utilization",
                    snippet="Credit utilization is the share of available revolving credit in use.",
                    source="Internal Credit Education Guide",
                    confidence=0.82,
                )
            ],
            used=True,
            top_confidence=0.82,
        )


class UnsupportedCauseGateway(LocalModelGateway):
    def generate(self, payload):  # type: ignore[override]
        return GeneratedAnswerPayload(
            message="Your score changed because of a hidden unsupported factor.",
            causes=["Hidden unsupported factor from nowhere."],
            evidence=["Completely unrelated unsupported evidence."],
            suggested_actions=["Monitor credit reports monthly"],
        )


class AgentOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repository = JsonCreditRepository()
        cls.agent = AgentOrchestrator(
            planner=ExecutionPlanner(),
            tool_registry=ToolRegistry(
                credit_service=CreditService(repository),
                metrics_service=MetricsService(repository),
                recommendation_service=RecommendationService(repository),
                inquiry_service=InquiryService(repository),
                payment_history_service=PaymentHistoryService(repository),
            ),
            rag_service=RagService(),
            evidence_builder=EvidenceBuilder(),
            response_composer=GroundedResponseComposer(model_gateway=LocalModelGateway()),
        )

    def test_simple_fact_uses_tool_data(self) -> None:
        print("\n[agent] testing SIMPLE_FACT execution path")
        execution = self.agent.execute(
            user_id="user_001",
            message="What is my credit score?",
            analysis=ClassificationResult(category="SIMPLE_FACT", normalized_message="what is my credit score?"),
        )
        response = execution.response
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] cards={response.cards}")
        print(f"[agent] trace={execution.trace}")
        self.assertEqual(response.category, "SIMPLE_FACT")
        self.assertIn("792", response.message)
        self.assertEqual(response.cards[0].type, "credit_score")
        self.assertEqual(execution.plan.execution_mode, "FAST_FACT")
        self.assertIn("get_credit_profile", execution.trace.tool_calls)
        self.assertEqual(execution.trace.tool_calls[0], "get_credit_profile")
        self.assertFalse(execution.trace.retrieval_used)

    def test_general_knowledge_uses_rag(self) -> None:
        print("\n[agent] testing GENERAL_KNOWLEDGE execution path")
        execution = self.agent.execute(
            user_id="user_001",
            message="What is credit utilization?",
            analysis=ClassificationResult(category="GENERAL_KNOWLEDGE", normalized_message="what is credit utilization?"),
        )
        response = execution.response
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] knowledge_cards={response.cards}")
        print(f"[agent] trace={execution.trace}")
        self.assertEqual(response.category, "GENERAL_KNOWLEDGE")
        self.assertGreater(len(response.cards), 0)
        self.assertEqual(response.cards[0].type, "knowledge")
        self.assertIn("revolving credit", response.message.lower())
        self.assertEqual(execution.plan.execution_mode, "KNOWLEDGE_ONLY")
        self.assertTrue(execution.trace.retrieval_used)
        self.assertEqual(execution.trace.tool_calls, [])

    def test_complex_explanation_combines_tools_and_explanation(self) -> None:
        print("\n[agent] testing COMPLEX_EXPLANATION execution path")
        execution = self.agent.execute(
            user_id="user_003",
            message="Why did my score drop?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did my score drop?"),
        )
        response = execution.response
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] explanation={response.explanation}")
        print(f"[agent] cards={response.cards}")
        print(f"[agent] trace={execution.trace}")
        self.assertEqual(response.category, "COMPLEX_EXPLANATION")
        self.assertIsNotNone(response.explanation)
        self.assertGreater(len(response.explanation.causes), 0)
        self.assertGreater(len(response.explanation.evidence), 0)
        self.assertGreater(len(response.explanation.suggested_actions), 0)
        self.assertTrue(any(card.type == "recommendation" for card in response.cards))
        self.assertEqual(execution.plan.execution_mode, "COMPLEX_EXPLANATION")
        self.assertIn("get_credit_profile", execution.trace.tool_calls)
        self.assertIn("get_credit_metrics", execution.trace.tool_calls)
        self.assertIn("get_recommendations", execution.trace.tool_calls)
        self.assertIn("get_payment_history", execution.trace.tool_calls)
        self.assertTrue(execution.trace.retrieval_used)

    def test_simple_recommendation_includes_actions(self) -> None:
        print("\n[agent] testing SIMPLE_RECOMMENDATION execution path")
        execution = self.agent.execute(
            user_id="user_005",
            message="How can I improve my score?",
            analysis=ClassificationResult(category="SIMPLE_RECOMMENDATION", normalized_message="how can i improve my score?"),
        )
        response = execution.response
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] explanation={response.explanation}")
        print(f"[agent] cards={response.cards}")
        print(f"[agent] trace={execution.trace}")
        self.assertEqual(response.category, "SIMPLE_RECOMMENDATION")
        self.assertIsNotNone(response.explanation)
        self.assertGreater(len(response.explanation.suggested_actions), 0)
        self.assertTrue(any(card.type == "recommendation" for card in response.cards))
        self.assertEqual(execution.plan.execution_mode, "FAST_RECOMMENDATION")
        self.assertIn("get_recommendations", execution.trace.tool_calls)
        self.assertIn("get_credit_metrics", execution.trace.tool_calls)

    def test_general_knowledge_fallback_when_retrieval_is_below_threshold(self) -> None:
        print("\n[agent] testing GENERAL_KNOWLEDGE fallback when retrieval misses threshold")
        repository = JsonCreditRepository()
        low_recall_agent = AgentOrchestrator(
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
            response_composer=GroundedResponseComposer(model_gateway=LocalModelGateway()),
        )
        execution = low_recall_agent.execute(
            user_id="user_001",
            message="What is credit utilization?",
            analysis=ClassificationResult(category="GENERAL_KNOWLEDGE", normalized_message="what is credit utilization?"),
        )
        response = execution.response
        print(f"[agent] category={response.category} message={response.message}")
        print(f"[agent] trace={execution.trace}")
        self.assertEqual(response.category, "GENERAL_KNOWLEDGE")
        self.assertEqual(response.cards, [])
        self.assertFalse(execution.trace.retrieval_used)

    def test_complex_explanation_plan_is_bounded_and_grounded(self) -> None:
        print("\n[agent] testing bounded complex explanation planning")
        execution = self.agent.execute(
            user_id="user_003",
            message="Why did my credit score drop?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did my credit score drop?"),
        )
        print(f"[agent] plan={execution.plan}")
        self.assertEqual(execution.plan.max_iterations, 3)
        self.assertIn("get_credit_profile", execution.plan.tool_names)
        self.assertIn("get_payment_history", execution.plan.tool_names)
        self.assertTrue(execution.plan.retrieval_needed)

    def test_complex_explanation_returns_insufficient_evidence_message_without_retrieval(self) -> None:
        print("\n[agent] testing insufficient evidence fallback for complex explanation")
        repository = JsonCreditRepository()
        low_recall_agent = AgentOrchestrator(
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
        )
        execution = low_recall_agent.execute(
            user_id="user_003",
            message="Why did my score drop?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did my score drop?"),
        )
        self.assertIn("enough grounded evidence", execution.response.message.lower())
        self.assertIsNotNone(execution.response.explanation)
        self.assertFalse(execution.trace.retrieval_used)

    def test_trace_records_action_reasoning_steps(self) -> None:
        print("\n[agent] testing action reasoning trace steps")
        execution = self.agent.execute(
            user_id="user_001",
            message="What is credit utilization?",
            analysis=ClassificationResult(category="GENERAL_KNOWLEDGE", normalized_message="what is credit utilization?"),
        )
        decision_steps = [step for step in execution.trace.steps if step.name.startswith("decide_")]
        self.assertGreater(len(decision_steps), 0)
        self.assertTrue(any("Reasoning:" in step.detail for step in decision_steps))
        self.assertTrue(any(step.name == "decide_retrieve" for step in decision_steps))
        self.assertTrue(any(step.name == "decide_answer" for step in decision_steps))

    def test_general_knowledge_can_refine_retrieval_after_initial_miss(self) -> None:
        print("\n[agent] testing iterative retrieval after initial miss")
        repository = JsonCreditRepository()
        rag_service = FakeIterativeRagService()
        iterative_agent = AgentOrchestrator(
            planner=ExecutionPlanner(),
            tool_registry=ToolRegistry(
                credit_service=CreditService(repository),
                metrics_service=MetricsService(repository),
                recommendation_service=RecommendationService(repository),
                inquiry_service=InquiryService(repository),
                payment_history_service=PaymentHistoryService(repository),
            ),
            rag_service=rag_service,  # type: ignore[arg-type]
            evidence_builder=EvidenceBuilder(),
            response_composer=GroundedResponseComposer(model_gateway=LocalModelGateway(), evidence_builder=EvidenceBuilder()),
        )
        execution = iterative_agent.execute(
            user_id="user_001",
            message="What is credit utilization?",
            analysis=ClassificationResult(category="GENERAL_KNOWLEDGE", normalized_message="what is credit utilization?"),
        )
        self.assertEqual(len(rag_service.queries), 2)
        self.assertNotEqual(rag_service.queries[0], rag_service.queries[1])
        self.assertIn("available revolving credit", execution.response.message.lower())
        decision_steps = [step.name for step in execution.trace.steps if step.name.startswith("decide_")]
        self.assertGreaterEqual(decision_steps.count("decide_retrieve"), 2)

    def test_complex_explanation_can_prioritize_inquiries_before_payments(self) -> None:
        print("\n[agent] testing reduced planner control through tool prioritization")
        execution = self.agent.execute(
            user_id="user_003",
            message="Why did hard inquiries affect my score?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did hard inquiries affect my score?"),
        )
        inquiry_index = execution.trace.tool_calls.index("get_inquiries")
        payment_index = execution.trace.tool_calls.index("get_payment_history")
        self.assertLess(inquiry_index, payment_index)

    def test_complex_explanation_filters_unsupported_generated_causes(self) -> None:
        print("\n[agent] testing claim verification for generated causes")
        repository = JsonCreditRepository()
        filtered_agent = AgentOrchestrator(
            planner=ExecutionPlanner(),
            tool_registry=ToolRegistry(
                credit_service=CreditService(repository),
                metrics_service=MetricsService(repository),
                recommendation_service=RecommendationService(repository),
                inquiry_service=InquiryService(repository),
                payment_history_service=PaymentHistoryService(repository),
            ),
            rag_service=RagService(),
            evidence_builder=EvidenceBuilder(),
            response_composer=GroundedResponseComposer(model_gateway=UnsupportedCauseGateway(), evidence_builder=EvidenceBuilder()),
        )
        execution = filtered_agent.execute(
            user_id="user_003",
            message="Why did my score drop?",
            analysis=ClassificationResult(category="COMPLEX_EXPLANATION", normalized_message="why did my score drop?"),
        )
        self.assertTrue(all("unsupported" not in cause.lower() for cause in execution.response.explanation.causes))


if __name__ == "__main__":
    unittest.main()
