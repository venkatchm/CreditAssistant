from __future__ import annotations

import unittest

from app.services.query_analyzer import QueryAnalyzer


class QueryAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = QueryAnalyzer()

    def test_simple_fact_query(self) -> None:
        print("\n[query_analyzer] testing SIMPLE_FACT classification")
        result = self.analyzer.analyze("What is my credit score?")
        print(f"[query_analyzer] normalized={result.normalized_message} category={result.category}")
        self.assertEqual(result.category, "SIMPLE_FACT")
        self.assertEqual(result.normalized_message, "what is my credit score?")

    def test_simple_recommendation_query(self) -> None:
        print("\n[query_analyzer] testing SIMPLE_RECOMMENDATION classification")
        result = self.analyzer.analyze("How can I improve my score?")
        print(f"[query_analyzer] normalized={result.normalized_message} category={result.category}")
        self.assertEqual(result.category, "SIMPLE_RECOMMENDATION")

    def test_complex_explanation_query(self) -> None:
        print("\n[query_analyzer] testing COMPLEX_EXPLANATION classification")
        result = self.analyzer.analyze("Why did my score drop?")
        print(f"[query_analyzer] normalized={result.normalized_message} category={result.category}")
        self.assertEqual(result.category, "COMPLEX_EXPLANATION")

    def test_general_knowledge_query(self) -> None:
        print("\n[query_analyzer] testing GENERAL_KNOWLEDGE classification")
        result = self.analyzer.analyze("What is credit utilization?")
        print(f"[query_analyzer] normalized={result.normalized_message} category={result.category}")
        self.assertEqual(result.category, "GENERAL_KNOWLEDGE")

    def test_unsupported_query(self) -> None:
        print("\n[query_analyzer] testing UNSUPPORTED classification")
        result = self.analyzer.analyze("Tell me a joke")
        print(f"[query_analyzer] normalized={result.normalized_message} category={result.category}")
        self.assertEqual(result.category, "UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
