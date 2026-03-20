from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.core.settings import get_settings
from app.services.rag_service import RagService


def main() -> None:
    settings = get_settings()
    if settings.retrieval_backend != "postgres":
        raise SystemExit("Set RETRIEVAL_BACKEND=postgres before bootstrapping the postgres retrieval index.")
    if not settings.retrieval_postgres_dsn:
        raise SystemExit("Set RETRIEVAL_POSTGRES_DSN before bootstrapping the postgres retrieval index.")

    rag = RagService()
    rag.rebuild_index()
    print("Bootstrapped retrieval data into the postgres backend.")


if __name__ == "__main__":
    main()
