"""Seed Supabase Postgres with credit data from local JSON files.

Usage:
    PYTHONPATH=backend python3 backend/scripts/seed_postgres_credit_data.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import psycopg
from psycopg.rows import dict_row

from app.core.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    dsn = settings.retrieval_postgres_dsn
    if not dsn:
        logger.error("RETRIEVAL_POSTGRES_DSN is required. Set it in your environment.")
        sys.exit(1)

    data_dir = backend_dir / "data"
    migrations_dir = backend_dir / "migrations"

    # Apply migration
    migration_sql = (migrations_dir / "0004_credit_data_schema.sql").read_text(encoding="utf-8")
    logger.info("Applying credit data migration...")

    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute(migration_sql)
        conn.commit()
        logger.info("Migration applied successfully")

        # Clear existing data (in reverse FK order)
        with conn.cursor() as cur:
            for table in [
                "recommendations", "credit_metrics", "payment_history",
                "inquiries", "loan_accounts", "credit_accounts",
                "credit_reports", "users",
            ]:
                cur.execute(f"DELETE FROM {table}")
        conn.commit()
        logger.info("Cleared existing credit data")

        # Seed users
        users = _load_json(data_dir / "users.json")
        with conn.cursor() as cur:
            for u in users:
                cur.execute(
                    """INSERT INTO users (user_id, full_name, age, city, state, occupation, annual_income, persona)
                    VALUES (%(user_id)s, %(full_name)s, %(age)s, %(city)s, %(state)s, %(occupation)s, %(annual_income)s, %(persona)s)""",
                    u,
                )
        conn.commit()
        logger.info("Seeded %d users", len(users))

        # Seed credit_reports
        reports = _load_json(data_dir / "credit_reports.json")
        with conn.cursor() as cur:
            for r in reports:
                r["score_factors"] = json.dumps(r.get("score_factors", []))
                cur.execute(
                    """INSERT INTO credit_reports (
                        report_id, user_id, bureau, score, score_band, score_change_30d, generated_at,
                        oldest_account_age_months, average_account_age_months, total_open_accounts,
                        total_accounts, derogatory_marks, bankruptcies, collections, hard_inquiries_12m,
                        revolving_utilization, payment_history_ratio, summary, score_factors
                    ) VALUES (
                        %(report_id)s, %(user_id)s, %(bureau)s, %(score)s, %(score_band)s, %(score_change_30d)s,
                        %(generated_at)s, %(oldest_account_age_months)s, %(average_account_age_months)s,
                        %(total_open_accounts)s, %(total_accounts)s, %(derogatory_marks)s, %(bankruptcies)s,
                        %(collections)s, %(hard_inquiries_12m)s, %(revolving_utilization)s,
                        %(payment_history_ratio)s, %(summary)s, %(score_factors)s
                    )""",
                    r,
                )
        conn.commit()
        logger.info("Seeded %d credit reports", len(reports))

        # Seed credit_accounts
        accounts = _load_json(data_dir / "credit_accounts.json")
        with conn.cursor() as cur:
            for a in accounts:
                cur.execute(
                    """INSERT INTO credit_accounts (
                        account_id, user_id, issuer, product_name, account_type, status, opened_date,
                        closed_date, credit_limit, current_balance, apr, autopay_enabled, utilization, payment_status
                    ) VALUES (
                        %(account_id)s, %(user_id)s, %(issuer)s, %(product_name)s, %(account_type)s, %(status)s,
                        %(opened_date)s, %(closed_date)s, %(credit_limit)s, %(current_balance)s, %(apr)s,
                        %(autopay_enabled)s, %(utilization)s, %(payment_status)s
                    )""",
                    a,
                )
        conn.commit()
        logger.info("Seeded %d credit accounts", len(accounts))

        # Seed loan_accounts
        loans = _load_json(data_dir / "loan_accounts.json")
        with conn.cursor() as cur:
            for l in loans:
                cur.execute(
                    """INSERT INTO loan_accounts (
                        account_id, user_id, lender, product_name, account_type, status, opened_date,
                        original_balance, current_balance, monthly_payment, interest_rate, payment_status
                    ) VALUES (
                        %(account_id)s, %(user_id)s, %(lender)s, %(product_name)s, %(account_type)s, %(status)s,
                        %(opened_date)s, %(original_balance)s, %(current_balance)s, %(monthly_payment)s,
                        %(interest_rate)s, %(payment_status)s
                    )""",
                    l,
                )
        conn.commit()
        logger.info("Seeded %d loan accounts", len(loans))

        # Seed inquiries
        inquiries = _load_json(data_dir / "inquiries.json")
        with conn.cursor() as cur:
            for i in inquiries:
                cur.execute(
                    """INSERT INTO inquiries (
                        inquiry_id, user_id, creditor, inquiry_type, inquiry_date, bureau, is_hard
                    ) VALUES (
                        %(inquiry_id)s, %(user_id)s, %(creditor)s, %(inquiry_type)s, %(inquiry_date)s,
                        %(bureau)s, %(is_hard)s
                    )""",
                    i,
                )
        conn.commit()
        logger.info("Seeded %d inquiries", len(inquiries))

        # Seed payment_history
        payments = _load_json(data_dir / "payment_history.json")
        with conn.cursor() as cur:
            for p in payments:
                cur.execute(
                    """INSERT INTO payment_history (
                        payment_id, user_id, account_id, month, status, amount_due, amount_paid, days_late
                    ) VALUES (
                        %(payment_id)s, %(user_id)s, %(account_id)s, %(month)s, %(status)s,
                        %(amount_due)s, %(amount_paid)s, %(days_late)s
                    )""",
                    p,
                )
        conn.commit()
        logger.info("Seeded %d payment history entries", len(payments))

        # Seed credit_metrics
        metrics = _load_json(data_dir / "credit_metrics.json")
        with conn.cursor() as cur:
            for m in metrics:
                m["trends"] = json.dumps(m.get("trends", []))
                m["key_drivers"] = json.dumps(m.get("key_drivers", []))
                cur.execute(
                    """INSERT INTO credit_metrics (
                        user_id, score, score_band, score_change_30d, revolving_limit_total,
                        revolving_balance_total, revolving_utilization, installment_balance_total,
                        installment_original_total, installment_utilization, open_revolving_accounts,
                        open_installment_accounts, total_hard_inquiries_12m, recent_hard_inquiries_90d,
                        on_time_payment_ratio, delinquent_accounts, months_since_last_delinquency,
                        total_available_credit, trends, key_drivers
                    ) VALUES (
                        %(user_id)s, %(score)s, %(score_band)s, %(score_change_30d)s, %(revolving_limit_total)s,
                        %(revolving_balance_total)s, %(revolving_utilization)s, %(installment_balance_total)s,
                        %(installment_original_total)s, %(installment_utilization)s, %(open_revolving_accounts)s,
                        %(open_installment_accounts)s, %(total_hard_inquiries_12m)s, %(recent_hard_inquiries_90d)s,
                        %(on_time_payment_ratio)s, %(delinquent_accounts)s, %(months_since_last_delinquency)s,
                        %(total_available_credit)s, %(trends)s, %(key_drivers)s
                    )""",
                    m,
                )
        conn.commit()
        logger.info("Seeded %d credit metrics", len(metrics))

        # Seed recommendations
        recs = _load_json(data_dir / "recommendations.json")
        with conn.cursor() as cur:
            for r in recs:
                cur.execute(
                    """INSERT INTO recommendations (
                        recommendation_id, user_id, title, priority, category, rationale, action, expected_impact
                    ) VALUES (
                        %(recommendation_id)s, %(user_id)s, %(title)s, %(priority)s, %(category)s,
                        %(rationale)s, %(action)s, %(expected_impact)s
                    )""",
                    r,
                )
        conn.commit()
        logger.info("Seeded %d recommendations", len(recs))

        logger.info("All credit data seeded successfully!")

    finally:
        conn.close()


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
