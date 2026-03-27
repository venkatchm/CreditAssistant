from __future__ import annotations

import json
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
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


class PostgresCreditRepository(CreditRepository):
    """Credit data repository backed by Supabase Postgres."""

    def __init__(self, dsn: str, migration_sql: str | None = None) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for the postgres credit repository.")
        self.dsn = dsn
        if migration_sql:
            self._apply_migration(migration_sql)

    @contextmanager
    def _connect(self):
        connection = psycopg.connect(self.dsn, row_factory=dict_row)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def list_users(self) -> List[User]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users ORDER BY user_id")
                return [User(**row) for row in cur.fetchall()]

    def get_user(self, user_id: str) -> Optional[User]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE user_id = %(user_id)s", {"user_id": user_id})
                row = cur.fetchone()
                return User(**row) if row else None

    def get_credit_report(self, user_id: str) -> Optional[CreditReport]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM credit_reports WHERE user_id = %(user_id)s ORDER BY generated_at DESC LIMIT 1",
                    {"user_id": user_id},
                )
                row = cur.fetchone()
                if not row:
                    return None
                row["score_factors"] = _parse_jsonb(row.get("score_factors", []))
                return CreditReport(**row)

    def list_credit_accounts(self, user_id: str) -> List[CreditAccount]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM credit_accounts WHERE user_id = %(user_id)s ORDER BY opened_date",
                    {"user_id": user_id},
                )
                return [CreditAccount(**row) for row in cur.fetchall()]

    def list_loan_accounts(self, user_id: str) -> List[LoanAccount]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM loan_accounts WHERE user_id = %(user_id)s ORDER BY opened_date",
                    {"user_id": user_id},
                )
                return [LoanAccount(**row) for row in cur.fetchall()]

    def list_inquiries(self, user_id: str) -> List[Inquiry]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM inquiries WHERE user_id = %(user_id)s ORDER BY inquiry_date DESC",
                    {"user_id": user_id},
                )
                return [Inquiry(**row) for row in cur.fetchall()]

    def list_payment_history(self, user_id: str) -> List[PaymentHistoryEntry]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM payment_history WHERE user_id = %(user_id)s ORDER BY month DESC",
                    {"user_id": user_id},
                )
                return [PaymentHistoryEntry(**row) for row in cur.fetchall()]

    def get_metrics(self, user_id: str) -> Optional[CreditMetrics]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM credit_metrics WHERE user_id = %(user_id)s",
                    {"user_id": user_id},
                )
                row = cur.fetchone()
                if not row:
                    return None
                row["trends"] = [MetricTrend(**t) for t in _parse_jsonb(row.get("trends", []))]
                row["key_drivers"] = _parse_jsonb(row.get("key_drivers", []))
                return CreditMetrics(**row)

    def list_recommendations(self, user_id: str) -> List[Recommendation]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM recommendations WHERE user_id = %(user_id)s ORDER BY priority",
                    {"user_id": user_id},
                )
                return [Recommendation(**row) for row in cur.fetchall()]

    def _apply_migration(self, migration_sql: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)


def _parse_jsonb(value) -> list:
    """Parse JSONB field — psycopg may return it as a string or already parsed."""
    if isinstance(value, str):
        return json.loads(value)
    return value if value else []
