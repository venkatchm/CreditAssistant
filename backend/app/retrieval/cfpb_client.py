"""Client for fetching credit education content from CFPB (Consumer Financial Protection Bureau).

CFPB is a US federal agency — all content is public domain (no copyright restrictions).
Data sources:
  - Ask CFPB JSON search: ~676 structured Q&A articles on credit topics
  - Consumer Tools pages: educational guides on credit reports, scores, debt
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx

from app.retrieval.models import SourceDocument

logger = logging.getLogger(__name__)

# Working CFPB search endpoint — returns JSON with question + full text
ASK_CFPB_SEARCH_URL = "https://www.consumerfinance.gov/ask-cfpb/search/json/"

# Broad queries that collectively cover ~676 unique articles
BROAD_QUERIES = ["the", "a", "i", "how", "what", "credit", "loan", "debt", "pay", "bank"]

# Topic classification based on keywords in the question/text
TOPIC_KEYWORDS = {
    "credit_score": ["credit score", "fico", "vantagescore", "scoring"],
    "credit_report": ["credit report", "credit history", "credit file", "credit bureau", "equifax", "experian", "transunion"],
    "credit_cards": ["credit card", "card issuer", "balance transfer", "apr", "annual fee", "minimum payment"],
    "debt_collection": ["debt collector", "debt collection", "collection agency", "collections"],
    "mortgages": ["mortgage", "home loan", "closing costs", "escrow", "foreclosure", "refinance"],
    "auto_loans": ["auto loan", "car loan", "vehicle loan", "car financing"],
    "student_loans": ["student loan", "federal loan", "loan servicer", "loan forgiveness", "fafsa"],
    "bank_accounts": ["bank account", "checking account", "savings account", "overdraft", "atm"],
    "identity_theft": ["identity theft", "fraud", "stolen identity", "freeze"],
    "payday_loans": ["payday loan", "payday lender", "short-term loan"],
}

# Direct educational page URLs with known high-quality content
EDUCATIONAL_PAGES = [
    {
        "url": "https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/",
        "topic": "credit_reports_overview",
        "title": "Credit Reports and Scores Overview",
    },
    {
        "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
        "topic": "debt_collection_overview",
        "title": "Debt Collection Overview",
    },
    {
        "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
        "topic": "auto_loans_overview",
        "title": "Auto Loans Overview",
    },
    {
        "url": "https://www.consumerfinance.gov/consumer-tools/student-loans/",
        "topic": "student_loans_overview",
        "title": "Student Loans Overview",
    },
    {
        "url": "https://www.consumerfinance.gov/consumer-tools/mortgages/",
        "topic": "mortgages_overview",
        "title": "Mortgages Overview",
    },
]


class CfpbClient:
    """Fetches credit education content from CFPB public APIs and pages."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        rate_limit_delay: float = 0.5,
    ) -> None:
        self.http = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "CreditAssistant-EducationIngestion/1.0"},
        )
        self.cache_dir = cache_dir
        self.rate_limit_delay = rate_limit_delay
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_ask_cfpb_articles(self) -> list[SourceDocument]:
        """Fetch all Q&A articles from Ask CFPB using broad search queries."""
        cache_path = self.cache_dir / "ask_cfpb_all.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            logger.info("Loading cached CFPB articles from %s", cache_path)
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return [SourceDocument(**doc) for doc in cached]

        # Fetch articles using multiple broad queries to get full coverage
        seen_urls: set[str] = set()
        all_results: list[dict] = []

        for query in BROAD_QUERIES:
            try:
                response = self.http.get(
                    ASK_CFPB_SEARCH_URL,
                    params={"q": query},
                )
                if response.status_code != 200:
                    logger.warning("CFPB search returned %d for query '%s'", response.status_code, query)
                    continue

                data = response.json()
                results = data.get("results", [])
                for result in results:
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(result)

                logger.info("Query '%s': %d results (%d new, %d total unique)", query, len(results), len(results) - sum(1 for r in results if r.get("url") in seen_urls - {r.get("url")}), len(all_results))
            except Exception:
                logger.exception("Failed to fetch query '%s'", query)

            time.sleep(self.rate_limit_delay)

        logger.info("Total unique CFPB articles fetched: %d", len(all_results))

        # Convert to SourceDocuments
        documents: list[SourceDocument] = []
        for result in all_results:
            question = result.get("question", "").strip()
            text = result.get("text", "").strip()
            url = result.get("url", "")

            if not text or len(text) < 50:
                continue

            # Extract article ID from URL (e.g., /ask-cfpb/what-is-a-credit-score-en-315/ -> 315)
            id_match = re.search(r"-(\d+)/$", url)
            article_id = id_match.group(1) if id_match else url.replace("/", "_").strip("_")
            doc_id = f"cfpb_{article_id}"

            topic = self._classify_topic(question, text)
            content = f"{question}\n\n{text}" if question else text

            documents.append(
                SourceDocument(
                    doc_id=doc_id,
                    topic=topic,
                    title=question or f"CFPB Article {article_id}",
                    content=content,
                    tags=[topic.replace("_", " "), "cfpb", "ask cfpb"],
                    source="CFPB Ask CFPB",
                    version="1.0",
                )
            )

        # Cache for future runs
        if cache_path:
            cache_path.write_text(
                json.dumps([doc.model_dump() for doc in documents], indent=2),
                encoding="utf-8",
            )
            logger.info("Cached %d articles to %s", len(documents), cache_path)

        return documents

    def fetch_educational_pages(self) -> list[SourceDocument]:
        """Scrape key educational pages from CFPB consumer tools."""
        documents: list[SourceDocument] = []

        for page in EDUCATIONAL_PAGES:
            try:
                content = self._fetch_page_content(page["url"])
                if not content or len(content) < 100:
                    logger.warning("Skipping page with insufficient content: %s", page["url"])
                    continue

                documents.append(
                    SourceDocument(
                        doc_id=f"cfpb_page_{page['topic']}",
                        topic=page["topic"],
                        title=page["title"],
                        content=content,
                        tags=[page["topic"].replace("_", " "), "cfpb", "education"],
                        source="CFPB Consumer Tools",
                        version="1.0",
                    )
                )
                time.sleep(self.rate_limit_delay)
            except Exception:
                logger.exception("Failed to fetch page: %s", page["url"])

        logger.info("Fetched %d educational pages", len(documents))
        return documents

    def fetch_all(self) -> list[SourceDocument]:
        """Fetch all available CFPB content."""
        documents = self.fetch_ask_cfpb_articles()
        documents.extend(self.fetch_educational_pages())
        logger.info("Total documents fetched: %d", len(documents))
        return documents

    def _fetch_page_content(self, url: str) -> str:
        """Fetch and extract main text content from a CFPB page."""
        cache_key = url.replace("https://", "").replace("/", "_").rstrip("_")
        cache_path = self.cache_dir / f"page_{cache_key}.txt" if self.cache_dir else None
        if cache_path and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        response = self.http.get(url)
        if response.status_code != 200:
            logger.warning("Failed to fetch page %s: status %d", url, response.status_code)
            return ""

        text = self._extract_main_content(response.text)

        if cache_path:
            cache_path.write_text(text, encoding="utf-8")

        return text

    @staticmethod
    def _extract_main_content(html: str) -> str:
        """Extract readable text from HTML, stripping tags and navigation."""
        for tag in ("script", "style", "nav", "header", "footer", "aside"):
            html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)

        main_match = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.IGNORECASE)
        if main_match:
            html = main_match.group(1)
        else:
            body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
            if body_match:
                html = body_match.group(1)

        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        for phrase in [
            "An official website of the United States government",
            "Skip to main content",
        ]:
            text = text.replace(phrase, "")

        return text.strip()

    @staticmethod
    def _classify_topic(question: str, text: str) -> str:
        """Classify article into a topic based on keyword matching."""
        combined = f"{question} {text}".lower()
        best_topic = "general_credit"
        best_count = 0
        for topic, keywords in TOPIC_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in combined)
            if count > best_count:
                best_count = count
                best_topic = topic
        return best_topic

    def close(self) -> None:
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
