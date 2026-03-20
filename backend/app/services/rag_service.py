from __future__ import annotations

import json
from pathlib import Path


class RagService:
    def __init__(self, knowledge_path: Path | None = None) -> None:
        self.knowledge_path = knowledge_path or Path(__file__).resolve().parents[2] / "data" / "knowledge.json"
        self._knowledge = self._load_knowledge()

    def _load_knowledge(self) -> list[dict[str, object]]:
        with self.knowledge_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def search_knowledge(self, query: str) -> list[dict[str, str]]:
        normalized_query = " ".join(query.lower().split())
        ranked: list[tuple[int, dict[str, object]]] = []
        query_terms = set(normalized_query.replace("?", "").split())
        for entry in self._knowledge:
            searchable = " ".join(
                [
                    str(entry.get("topic", "")).lower(),
                    str(entry.get("title", "")).lower(),
                    str(entry.get("content", "")).lower(),
                    " ".join(str(tag).lower() for tag in entry.get("tags", [])),
                ]
            )
            score = sum(1 for term in query_terms if term in searchable)
            if score:
                ranked.append((score, entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "topic": str(entry.get("topic", "")),
                "title": str(entry.get("title", "")),
                "content": str(entry.get("content", "")),
            }
            for _, entry in ranked[:3]
        ]
