from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.gateway.model_gateway import (
    GeneratedAnswerPayload,
    LocalModelGateway,
    ModelGatewayRequest,
    OpenAIModelGateway,
    OpenAIModelGatewayConfig,
    RemoteModelGateway,
    RemoteModelGatewayConfig,
    fallback_generated_payload,
    normalize_generated_payload,
)
from app.schemas.chat import AgentAction, EvidenceItem, ExecutionPlan


class ModelGatewayTests(unittest.TestCase):
    def test_local_gateway_builds_complex_explanation_from_grounded_payload(self) -> None:
        gateway = LocalModelGateway()
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="COMPLEX_EXPLANATION",
                execution_mode="COMPLEX_EXPLANATION",
                steps=["query_analysis", "compose_response"],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query="Why did my credit score drop?",
                response_strategy="tool_and_retrieval_grounded_explanation",
                max_iterations=2,
            ),
            user_message="Why did my credit score drop?",
            evidence=[
                EvidenceItem(source_kind="tool", source_name="get_payment_history", title="payment", detail="Recent delinquency posted"),
                EvidenceItem(source_kind="retrieval", source_name="doc_payment_history_v1", title="Payment History Impact", detail="Late payments can lower scores.", citation="Internal Credit Education Guide"),
            ],
            tool_context={
                "get_credit_profile": {
                    "credit_report": {
                        "score": 611,
                        "score_band": "fair",
                        "score_change_30d": -58,
                        "summary": "A recent 30-day delinquency materially lowered the score despite moderate utilization and an otherwise manageable file.",
                        "score_factors": [
                            "A recent delinquency is the largest negative factor",
                            "Moderate card balances are adding some pressure",
                        ],
                    }
                },
                "get_credit_metrics": {
                    "score_change_30d": -58,
                    "revolving_utilization": 0.305,
                    "total_hard_inquiries_12m": 0,
                    "months_since_last_delinquency": 2,
                    "key_drivers": [
                        "Limited recent inquiries mean payment recovery can help quickly",
                    ],
                },
                "get_recommendations": [
                    {"title": "Protect the next six months of payments"},
                    {"title": "Monitor credit reports monthly"},
                ],
            },
            retrieval_context=["Late payments can lower scores."],
        )
        result = gateway.generate(payload)
        self.assertIsInstance(result, GeneratedAnswerPayload)
        self.assertIn("611", result.message)
        self.assertGreater(len(result.causes), 0)
        self.assertGreater(len(result.evidence), 0)
        self.assertGreater(len(result.suggested_actions), 0)

    def test_local_gateway_decides_next_action_from_remaining_steps(self) -> None:
        gateway = LocalModelGateway()
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="COMPLEX_EXPLANATION",
                execution_mode="COMPLEX_EXPLANATION",
                steps=[],
                tool_names=["get_credit_profile", "get_credit_metrics"],
                retrieval_needed=True,
                retrieval_query="Why did my credit score drop?",
                response_strategy="tool_and_retrieval_grounded_explanation",
                max_iterations=2,
            ),
            user_message="Why did my credit score drop?",
        )
        action = gateway.decide_action(
            payload=payload,
            available_tools=["get_credit_profile", "get_credit_metrics"],
            completed_tools=["get_credit_profile"],
            retrieval_done=False,
        )
        self.assertIsInstance(action, AgentAction)
        self.assertEqual(action.action, "tool_call")
        self.assertEqual(action.tool_name, "get_credit_metrics")

        retrieval_action = gateway.decide_action(
            payload=payload,
            available_tools=["get_credit_profile", "get_credit_metrics"],
            completed_tools=["get_credit_profile", "get_credit_metrics"],
            retrieval_done=False,
        )
        self.assertEqual(retrieval_action.action, "retrieve")

        answer_action = gateway.decide_action(
            payload=payload,
            available_tools=["get_credit_profile", "get_credit_metrics"],
            completed_tools=["get_credit_profile", "get_credit_metrics"],
            retrieval_done=True,
        )
        self.assertEqual(answer_action.action, "answer")

    @patch("app.gateway.model_gateway.request.urlopen")
    def test_remote_gateway_posts_structured_payload(self, mock_urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {
                "output": {
                    "message": "Grounded answer",
                    "causes": ["Cause A"],
                    "evidence": ["Evidence A"],
                    "suggested_actions": ["Action A"],
                }
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        gateway = RemoteModelGateway(
            RemoteModelGatewayConfig(
                base_url="https://model-gateway.local/generate",
                api_key="secret",
                model_name="test-model",
            )
        )
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="GENERAL_KNOWLEDGE",
                execution_mode="KNOWLEDGE_ONLY",
                steps=["query_analysis", "compose_response"],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query="What is credit utilization?",
                response_strategy="retrieval_only_knowledge_response",
                max_iterations=1,
            ),
            user_message="What is credit utilization?",
            retrieval_context=["Credit utilization is the share of your available revolving credit that you are currently using."],
        )
        result = gateway.generate(payload)
        self.assertEqual(result.message, "Grounded answer")
        self.assertEqual(result.causes, ["Cause A"])
        called_request = mock_urlopen.call_args[0][0]
        self.assertEqual(called_request.full_url, "https://model-gateway.local/generate")
        self.assertEqual(called_request.headers["Authorization"], "Bearer secret")

    @patch("app.gateway.model_gateway.OpenAI")
    def test_openai_gateway_builds_responses_api_request(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = MagicMock(
            output_text=json.dumps(
                {
                    "message": "Grounded answer",
                    "causes": ["Cause A"],
                    "evidence": ["Evidence A"],
                    "suggested_actions": ["Action A"],
                }
            )
        )
        mock_openai_cls.return_value = mock_client

        gateway = OpenAIModelGateway(
            OpenAIModelGatewayConfig(
                api_key="test-key",
                model="gpt-5",
            )
        )
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="GENERAL_KNOWLEDGE",
                execution_mode="KNOWLEDGE_ONLY",
                steps=["query_analysis", "compose_response"],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query="What is credit utilization?",
                response_strategy="retrieval_only_knowledge_response",
                max_iterations=1,
            ),
            user_message="What is credit utilization?",
            retrieval_context=["Credit utilization is the share of your available revolving credit that you are currently using."],
        )
        result = gateway.generate(payload)
        self.assertEqual(result.message, "Grounded answer")
        mock_client.responses.create.assert_called_once()
        kwargs = mock_client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5")

    def test_normalize_generated_payload_prettifies_json_evidence(self) -> None:
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="GENERAL_KNOWLEDGE",
                execution_mode="KNOWLEDGE_ONLY",
                steps=[],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query="What is credit utilization?",
                response_strategy="retrieval_only_knowledge_response",
                max_iterations=1,
            ),
            user_message="What is credit utilization?",
        )
        normalized = normalize_generated_payload(
            {
                "message": "Answer",
                "evidence": [
                    '{"source":"doc_credit_utilization_v1","quote":"Keep utilization below 30%.","citation":"Internal Credit Education Guide"}'
                ],
            },
            payload,
        )
        self.assertIn("Keep utilization below 30%.", normalized["evidence"][0])
        self.assertIn("Internal Credit Education Guide", normalized["evidence"][0])

    def test_fallback_generated_payload_uses_grounded_evidence(self) -> None:
        payload = ModelGatewayRequest(
            plan=ExecutionPlan(
                query_type="COMPLEX_EXPLANATION",
                execution_mode="COMPLEX_EXPLANATION",
                steps=[],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query="Why did my credit score drop?",
                response_strategy="tool_and_retrieval_grounded_explanation",
                max_iterations=2,
            ),
            user_message="Why did my credit score drop?",
            evidence=[
                EvidenceItem(source_kind="tool", source_name="get_credit_metrics", title="metrics", detail="Revolving utilization: 30.5%"),
            ],
            tool_context={
                "get_recommendations": [
                    {"title": "Protect the next six months of payments"},
                ]
            },
        )
        fallback = fallback_generated_payload("partial text", payload)
        self.assertEqual(fallback["message"], "partial text")
        self.assertIn("Revolving utilization: 30.5%", fallback["evidence"])
        self.assertIn("Protect the next six months of payments", fallback["suggested_actions"])


if __name__ == "__main__":
    unittest.main()
