from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.rag_service import RagService


class RagPipelineTests(unittest.TestCase):
    def test_hybrid_retrieval_returns_grounded_documents(self) -> None:
        print("\n[rag] testing hybrid retrieval for score drop explanation")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "retrieval.sqlite3"
            rag = RagService(db_path=db_path)
            result = rag.search_knowledge("Why did my credit score drop because of late payment?")
        print(f"[rag] documents={result.documents}")
        self.assertTrue(result.used)
        self.assertGreater(len(result.documents), 0)
        self.assertTrue(any(document.source == "Internal Credit Education Guide" for document in result.documents))
        self.assertTrue(any(document.confidence >= 0.2 for document in result.documents))

    def test_rag_service_persists_chunks_to_database(self) -> None:
        print("\n[rag] testing retrieval persistence bootstrap")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "retrieval.sqlite3"
            rag = RagService(db_path=db_path)
            self.assertTrue(db_path.exists())
            result = rag.search_knowledge("What is credit utilization?")
            self.assertTrue(result.used)


if __name__ == "__main__":
    unittest.main()
