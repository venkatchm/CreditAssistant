from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from main import app


class ChatResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_fact_response_is_humanized_and_excludes_null_fields(self) -> None:
        response = self.client.post(
            "/chat",
            json={"user_id": "user_001", "message": "What is my credit score?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["category"], "PERSONAL_FINANCE_FACT")
        self.assertIn("Your latest credit score is 792", payload["message"])
        self.assertIn("Very Good", payload["message"])
        first_card = payload["cards"][0]
        self.assertEqual(first_card["type"], "credit_score")
        self.assertNotIn("priority", first_card)
        self.assertNotIn("value", first_card)
        self.assertEqual(first_card["description"], "Score band: Very Good")

    def test_explanation_response_dedupes_overlapping_factors(self) -> None:
        response = self.client.post(
            "/chat",
            json={"user_id": "user_003", "message": "Why did my score drop?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["category"], "PERSONAL_FINANCE_EXPLANATION")
        self.assertIn("down 58 points", payload["message"])
        factor_descriptions = [card["description"] for card in payload["cards"] if card["type"] == "factor"]
        self.assertEqual(len(factor_descriptions), len(set(factor_descriptions)))

    def test_recommendation_response_is_grounded_and_humanized(self) -> None:
        response = self.client.post(
            "/chat",
            json={"user_id": "user_005", "message": "How can I improve my score?"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["category"], "RECOMMENDATION")
        self.assertTrue(payload["requires_disclaimer"])
        self.assertIn("latest credit score", payload["message"].lower())
        self.assertGreater(len(payload["cards"]), 0)
        self.assertEqual(payload["cards"][0]["priority"], "Medium")


if __name__ == "__main__":
    unittest.main()
