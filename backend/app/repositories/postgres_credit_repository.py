from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import List, Optional

from app.repositories.base import CreditRepository
from synthetic.models import (
    CreditAccount,
    CreditMetrics,
    CreditReport,
    Inquiry,
    LoanAccount,
    MetricTrend,
    PaymentHistoryEntry,
    Recommendation,
    User,
)

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None
    ConnectionPool = None


class _UserCache:
    """Per-user data cache — prefetches all tables in one connection."""

    def __init__(self) -> None:
        self.user: Optional[User] = None
        self.credit_report: Optional[CreditReport] = None
        self.credit_accounts: List[CreditAccount] = []
        self.loan_accounts: List[LoanAccount] = []
        self.inquiries: List[Inquiry] = []
        self.payment_history: List[PaymentHistoryEntry] = []
        self.metrics: Optional[CreditMetrics] = None
        self.recommendations: List[Recommendation] = []


class PostgresCreditRepository(CreditRepository):
    """Credit data repository backed by Supabase Postgres with per-user prefetch cache."""

    def __init__(self, dsn: str, migration_sql: str | None = None) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for the postgres credit repository.")
        self.dsn = dsn
        self._pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._cache: dict[str, _UserCache] = {}
        self._cache_lock = threading.Lock()
        if migration_sql:
            self._apply_migration(migration_sql)

    @contextmanager
    def _connect(self):
        with self._pool.connection() as connection:
            yield connection

    def _prefetch(self, user_id: str) -> _UserCache:
        """Fetch all data for a user using 8 parallel queries."""
        with self._cache_lock:
            if user_id in self._cache:
                return self._cache[user_id]

        cache = _UserCache()

        def _query(sql: str) -> list[dict]:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {"uid": user_id})
                    return cur.fetchall()

        futures = {
            "users": self._executor.submit(_query, "SELECT * FROM users WHERE user_id = %(uid)s"),
            "credit_reports": self._executor.submit(_query, "SELECT * FROM credit_reports WHERE user_id = %(uid)s ORDER BY generated_at DESC LIMIT 1"),
            "credit_accounts": self._executor.submit(_query, "SELECT * FROM credit_accounts WHERE user_id = %(uid)s ORDER BY opened_date"),
            "loan_accounts": self._executor.submit(_query, "SELECT * FROM loan_accounts WHERE user_id = %(uid)s ORDER BY opened_date"),
            "inquiries": self._executor.submit(_query, "SELECT * FROM inquiries WHERE user_id = %(uid)s ORDER BY inquiry_date DESC"),
            "payment_history": self._executor.submit(_query, "SELECT * FROM payment_history WHERE user_id = %(uid)s ORDER BY month DESC"),
            "credit_metrics": self._executor.submit(_query, "SELECT * FROM credit_metrics WHERE user_id = %(uid)s"),
            "recommendations": self._executor.submit(_query, "SELECT * FROM recommendations WHERE user_id = %(uid)s ORDER BY priority"),
        }

        # All 8 queries run in parallel — collect results
        rows = futures["users"].result()
        cache.user = User(**rows[0]) if rows else None

        rows = futures["credit_reports"].result()
        if rows:
            rows[0]["score_factors"] = _parse_jsonb(rows[0].get("score_factors", []))
            cache.credit_report = CreditReport(**rows[0])

        cache.credit_accounts = [CreditAccount(**r) for r in futures["credit_accounts"].result()]
        cache.loan_accounts = [LoanAccount(**r) for r in futures["loan_accounts"].result()]
        cache.inquiries = [Inquiry(**r) for r in futures["inquiries"].result()]
        cache.payment_history = [PaymentHistoryEntry(**r) for r in futures["payment_history"].result()]

        rows = futures["credit_metrics"].result()
        if rows:
            rows[0]["trends"] = [MetricTrend(**t) for t in _parse_jsonb(rows[0].get("trends", []))]
            rows[0]["key_drivers"] = _parse_jsonb(rows[0].get("key_drivers", []))
            cache.metrics = CreditMetrics(**rows[0])

        cache.recommendations = [Recommendation(**r) for r in futures["recommendations"].result()]

        with self._cache_lock:
            self._cache[user_id] = cache
        return cache

    def clear_cache(self, user_id: str | None = None) -> None:
        """Clear cached data. Call this if data changes."""
        with self._cache_lock:
            if user_id:
                self._cache.pop(user_id, None)
            else:
                self._cache.clear()

    def list_users(self) -> List[User]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users ORDER BY user_id")
                return [User(**row) for row in cur.fetchall()]

    def get_user(self, user_id: str) -> Optional[User]:
        return self._prefetch(user_id).user

    def get_credit_report(self, user_id: str) -> Optional[CreditReport]:
        return self._prefetch(user_id).credit_report

    def list_credit_accounts(self, user_id: str) -> List[CreditAccount]:
        return list(self._prefetch(user_id).credit_accounts)

    def list_loan_accounts(self, user_id: str) -> List[LoanAccount]:
        return list(self._prefetch(user_id).loan_accounts)

    def list_inquiries(self, user_id: str) -> List[Inquiry]:
        return list(self._prefetch(user_id).inquiries)

    def list_payment_history(self, user_id: str) -> List[PaymentHistoryEntry]:
        return list(self._prefetch(user_id).payment_history)

    def get_metrics(self, user_id: str) -> Optional[CreditMetrics]:
        return self._prefetch(user_id).metrics

    def list_recommendations(self, user_id: str) -> List[Recommendation]:
        return list(self._prefetch(user_id).recommendations)

    def _apply_migration(self, migration_sql: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)


def _parse_jsonb(value) -> list:
    """Parse JSONB field — psycopg may return it as a string or already parsed."""
    if isinstance(value, str):
        return json.loads(value)
    return value if value else []
