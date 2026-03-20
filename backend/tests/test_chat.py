from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
